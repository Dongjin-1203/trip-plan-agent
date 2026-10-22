"""FastAPI 앱. 챗봇 로직(chatbot.ask_events)을 HTTP API로 감싸고, 대화는 DB에 사용자별로 저장한다. 계약: docs/API.md"""
import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import text
from starlette.background import BackgroundTask

import config
from api import ratelimit, settings, store
from api.db import SessionLocal, init_db
from api.schemas import ChatRequest
from api.serialize import public_message
from chatbot import ChatbotError, ask_events

logger = logging.getLogger("travel_api")
logging.basicConfig(level=logging.INFO)

GENERIC_ERROR = "답변을 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")
SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception:  # 인스턴스가 동시에 시작해 테이블 생성이 겹쳐도 서버는 뜨게 한다
        logger.exception("init_db failed")
    yield


app = FastAPI(title="Travel Chatbot API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Client-Id", "X-Client-Ip"],
)


# ── 의존성 ──────────────────────────────────────────────────────────────
def get_client_id(x_client_id: str | None = Header(default=None)) -> str:
    if not x_client_id or not CLIENT_ID_RE.fullmatch(x_client_id):
        raise HTTPException(400, "X-Client-Id 헤더가 필요합니다. (영문·숫자·-, 16~64자)")
    return x_client_id


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    """요청 제한에 쓸 접속자 IP. 웹 서버(BFF)가 보낸 X-Client-Ip는 TRUST_CLIENT_IP_HEADER가 켜졌을 때만 믿는다."""
    if settings.TRUST_CLIENT_IP_HEADER:
        value = request.headers.get("x-client-ip", "").split(",")[0].strip()
        if value:
            return value[:64]
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:  # Cloud Run은 실제 접속자 IP를 목록 맨 끝에 붙인다
        return forwarded.split(",")[-1].strip()[:64]
    return request.client.host if request.client else "unknown"


def _own_session_or_404(db, client_id: str, session_id: str):
    session = store.get_session(db, client_id, session_id) if SESSION_ID_RE.fullmatch(session_id) else None
    if session is None:  # 없는 세션과 남의 세션을 구분하지 않는다
        raise HTTPException(404, "대화를 찾을 수 없습니다.")
    return session


# ── 상태 확인 ───────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "데이터베이스에 연결할 수 없습니다.") from None
    return {"status": "ok"}


# ── 세션 ────────────────────────────────────────────────────────────────
@app.get("/api/sessions")
def list_sessions(client_id: str = Depends(get_client_id), db=Depends(get_db)):
    return [
        {"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat(timespec="seconds") + "Z"}
        for s in store.list_sessions(db, client_id)
    ]


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, client_id: str = Depends(get_client_id), db=Depends(get_db)):
    session = _own_session_or_404(db, client_id, session_id)
    return {
        "id": session.id, "title": session.title,
        "updated_at": session.updated_at.isoformat(timespec="seconds") + "Z",
        "messages": [public_message(m) for m in store.load_messages(db, session.id)],
    }


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, client_id: str = Depends(get_client_id), db=Depends(get_db)):
    _own_session_or_404(db, client_id, session_id)
    store.delete_session(db, client_id, session_id)
    return Response(status_code=204)


@app.post("/api/sessions/{session_id}/offer/dismiss", status_code=204)
def dismiss_offer(session_id: str, client_id: str = Depends(get_client_id), db=Depends(get_db)):
    session = _own_session_or_404(db, client_id, session_id)
    store.dismiss_offer(db, session)
    return Response(status_code=204)


# ── 채팅(SSE) ───────────────────────────────────────────────────────────
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def flush_traces() -> None:
    """LangSmith는 트레이스를 백그라운드로 보낸다. Cloud Run은 응답이 끝나면 CPU를 줄이므로 응답 직후 전송을 마친다."""
    if not config.tracing_on():
        return
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers
        from langsmith.run_trees import get_cached_client

        wait_for_all_tracers()
        get_cached_client().flush()
    except Exception:
        logger.warning("langsmith flush failed")


def _chat_stream(session_id: str, client_id: str, question: str, food_request: dict | None, retry: bool, regenerate: bool = False):
    """한 턴을 처리하며 SSE 이벤트를 내보낸다. 성공·실패 모두 대화를 저장한다(실패하면 '다시 시도'로 이어 간다)."""
    db = SessionLocal()
    try:
        session = store.get_session(db, client_id, session_id)
        yield _sse("session", {"id": session.id, "title": session.title})
        if retry:
            store.drop_trailing_error(db, session)
        elif regenerate:
            store.drop_last_turn(db, session)

        messages = store.load_messages(db, session.id)
        history = [m for m in messages if not m.get("error")]  # 실패한 턴은 모델 기억에 넣지 않는다
        last_ai = next((m for m in reversed(messages) if m["role"] == "assistant" and not m.get("error")), None)
        facts = (last_ai or {}).get("facts", {})
        offer_pending = last_ai.get("offer") if last_ai and messages[-1] is last_ai else False
        extra = {
            "metadata": {"thread_id": session.id, "app": "travel-chatbot"},
            "tags": ["web", "food_form" if food_request else "chat"],
        }

        result: dict = {}
        error = None
        try:
            for ev in ask_events(question, history, facts, offer_pending, food_request, langsmith_extra=extra):
                if ev["type"] == "status":
                    yield _sse("status", {"label": ev["label"], "line": ev["line"]})
                elif ev["type"] == "token":
                    yield _sse("token", {"text": ev["text"]})
                else:
                    result.update(ev)
        except ChatbotError as e:
            error = str(e)
        except Exception:
            logger.exception("chat failed")
            error = GENERIC_ERROR
        if error is None and "answer" not in result:
            error = GENERIC_ERROR

        if error is None:
            assistant = {
                "role": "assistant", "content": result["answer"], "question": question, "trace": result["trace"],
                "facts": result["facts"], "offer": result["offer"], "draft": result.get("draft"), "food": result.get("food"),
            }
            store.append_messages(db, session, [{"role": "user", "content": question}, assistant])
            yield _sse("final", {"message": public_message(assistant)})
        else:
            store.append_messages(db, session, [
                {"role": "user", "content": question, "error": True},
                {"role": "assistant", "content": error, "question": question, "error": True},
            ])
            yield _sse("error", {"message": error, "retryable": True})
    finally:
        db.close()


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request, client_id: str = Depends(get_client_id)):
    with SessionLocal() as db:
        try:
            ratelimit.check(db, client_id, client_ip(request))
        except ratelimit.RateLimited as e:
            return JSONResponse(
                status_code=429,
                content={"detail": "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.", "retry_after": e.retry_after},
                headers={"Retry-After": str(e.retry_after)},
            )
        if req.session_id:
            session = _own_session_or_404(db, client_id, req.session_id)
            if req.regenerate:
                stored = store.last_turn_question(db, session)
                if stored is None:
                    raise HTTPException(409, "다시 생성할 답변이 없어요.")
                req.message = stored  # 저장된 질문으로 다시 처리한다(클라이언트가 보낸 문장은 쓰지 않는다)
        else:
            session = store.create_session(db, client_id, req.message)
        session_id = session.id

    food_request = req.food_request.to_dict() if req.food_request else None
    return StreamingResponse(
        _chat_stream(session_id, client_id, req.message, food_request, req.retry, req.regenerate),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(flush_traces),
    )
