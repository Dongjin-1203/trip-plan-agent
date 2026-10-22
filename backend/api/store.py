"""대화 저장소. 모든 함수는 client_id로 소유자를 확인한다(다른 사용자의 세션은 없는 것과 같다)."""
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api import settings
from api.db import ChatMessage, ChatSession, utcnow


def new_session_id() -> str:
    return uuid.uuid4().hex


def list_sessions(db: Session, client_id: str, limit: int | None = None) -> list[ChatSession]:
    """메시지가 하나 이상 있는 내 세션을 최근 수정 순으로."""
    has_messages = select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists()
    stmt = (
        select(ChatSession)
        .where(ChatSession.client_id == client_id, has_messages)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit or settings.MAX_SESSIONS_PER_CLIENT)
    )
    return list(db.scalars(stmt))


def get_session(db: Session, client_id: str, session_id: str) -> ChatSession | None:
    return db.scalars(select(ChatSession).where(ChatSession.id == session_id, ChatSession.client_id == client_id)).first()


def create_session(db: Session, client_id: str, title: str) -> ChatSession:
    """새 세션. 한 사용자의 세션이 상한을 넘으면 가장 오래된 것부터 지운다."""
    ids = list(db.scalars(select(ChatSession.id).where(ChatSession.client_id == client_id).order_by(ChatSession.updated_at.desc())))
    for old_id in ids[settings.MAX_SESSIONS_PER_CLIENT - 1:]:
        _delete_rows(db, old_id)
    session = ChatSession(id=new_session_id(), client_id=client_id, title=title.strip().replace("\n", " ")[:30])
    db.add(session)
    db.commit()
    return session


def load_messages(db: Session, session_id: str) -> list[dict]:
    rows = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.idx))
    return [dict(r.payload) for r in rows]


def append_messages(db: Session, session: ChatSession, payloads: list[dict]) -> None:
    last = db.scalar(select(func.max(ChatMessage.idx)).where(ChatMessage.session_id == session.id))
    start = (last if last is not None else -1) + 1
    for offset, payload in enumerate(payloads):
        db.add(ChatMessage(session_id=session.id, idx=start + offset, payload=payload))
    session.updated_at = utcnow()
    db.add(session)
    db.commit()


def _last_rows(db: Session, session_id: str, n: int) -> list[ChatMessage]:
    rows = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.idx.desc()).limit(n))
    return list(rows)[::-1]


def drop_trailing_error(db: Session, session: ChatSession) -> bool:
    """마지막에 실패해 저장된 질문·오류 쌍을 지운다(다시 시도하기 위해). 지웠으면 True."""
    rows = _last_rows(db, session.id, 2)
    if len(rows) == 2 and all(r.payload.get("error") for r in rows):
        for r in rows:
            db.delete(r)
        db.commit()
        return True
    return False


def _last_turn(db: Session, session: ChatSession) -> list[ChatMessage]:
    """마지막으로 정상 저장된 질문·답변 쌍. 없으면 빈 목록."""
    rows = _last_rows(db, session.id, 2)
    ok = (
        len(rows) == 2
        and rows[0].payload.get("role") == "user" and rows[1].payload.get("role") == "assistant"
        and not rows[0].payload.get("error") and not rows[1].payload.get("error")
    )
    return rows if ok else []


def last_turn_question(db: Session, session: ChatSession) -> str | None:
    """다시 생성할 수 있는 마지막 질문(없으면 None)."""
    rows = _last_turn(db, session)
    return rows[0].payload.get("content") if rows else None


def drop_last_turn(db: Session, session: ChatSession) -> bool:
    """마지막 질문·답변 쌍을 지운다(다시 생성하기 위해). 지웠으면 True."""
    rows = _last_turn(db, session)
    for r in rows:
        db.delete(r)
    if rows:
        db.commit()
    return bool(rows)


def dismiss_offer(db: Session, session: ChatSession) -> bool:
    """마지막 어시스턴트 메시지의 제안(offer)을 닫는다. 닫을 것이 있었으면 True."""
    rows = _last_rows(db, session.id, 1)
    if rows and rows[0].payload.get("role") == "assistant" and rows[0].payload.get("offer"):
        rows[0].payload = {**rows[0].payload, "offer": False}  # 새 dict를 넣어야 JSON 변경이 감지된다
        db.commit()
        return True
    return False


def _delete_rows(db: Session, session_id: str) -> None:
    db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    db.commit()


def delete_session(db: Session, client_id: str, session_id: str) -> bool:
    if get_session(db, client_id, session_id) is None:
        return False
    _delete_rows(db, session_id)
    return True
