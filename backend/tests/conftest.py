import os
import sys
import tempfile
from pathlib import Path

# api 모듈을 불러오기 전에 테스트용 설정을 정한다(실제 키·DB·트레이싱을 쓰지 않는다).
_TMP = tempfile.mkdtemp(prefix="travel_api_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ.pop("LANGSMITH_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.main as main  # noqa: E402
from api.db import Base, engine  # noqa: E402
from chatbot import ChatbotError  # noqa: E402

CLIENT_A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
CLIENT_B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"


def headers(client_id: str = CLIENT_A) -> dict:
    return {"X-Client-Id": client_id}


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """SSE 본문을 (이벤트 이름, data) 목록으로."""
    events = []
    for block in text.strip().split("\n\n"):
        name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name:
            events.append((name, data))
    return events


class FakeAsk:
    """chatbot.ask_events 대역. 받은 인자를 기록하고, 시나리오에 따라 이벤트를 내보내거나 오류를 낸다."""

    def __init__(self):
        self.calls: list[dict] = []
        self.mode = "ok"  # ok | error | draft_offer | food_offer | crash

    def __call__(self, question, history=None, facts=None, offer_pending=False, food_request=None, **kwargs):
        self.calls.append({"question": question, "history": history, "facts": facts, "offer_pending": offer_pending, "food_request": food_request})
        if self.mode == "error":
            raise ChatbotError("OpenAI 서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.")
        if self.mode == "crash":
            raise RuntimeError("secret-internal-detail")
        yield {"type": "status", "label": "🔎 검색 중", "line": "detail"}
        yield {"type": "token", "text": "안녕"}
        yield {"type": "token", "text": "하세요"}
        trace = {"steps": [], "tool_calls": 0, "tool_limit": 4, "model_calls": 1, "model_limit": 6, "end": "도구 불필요", "grounded": True}
        final = {"type": "final", "answer": "안녕하세요", "trace": trace, "facts": {"places": {"region": "경주"}}, "offer": False}
        if self.mode == "draft_offer":
            final["offer"] = "draft"
        if self.mode == "food_offer":
            final["offer"] = "food"
            final["facts"] = {"weather": {"date": "2026-10-24"}, "draft_places": [{"name": "a", "lat": 1.0, "lon": 2.0}]}
            final["draft"] = {"cond": {"region": "경주", "date": "2026-10-24", "preference": "x"}, "warnings": [], "places": [],
                              "weather_source": "Open-Meteo", "weather_state": "ok", "packing": [], "time_slots": []}
        if food_request:
            final["food"] = {"request": food_request, "days": [], "total_meals": 0, "picked": [], "failed": False, "notes": []}
        yield final


@pytest.fixture(autouse=True)
def frozen_rate_window(monkeypatch):
    """요청 제한은 고정 시간 창(분·일)으로 센다. 테스트 도중 분 경계를 넘으면 카운터가 갈라져 결과가 흔들리므로 창의 한가운데로 시간을 고정한다."""
    from types import SimpleNamespace

    from api import ratelimit

    monkeypatch.setattr(ratelimit, "time", SimpleNamespace(time=lambda: 1_800_000_030.0))  # 60초·86400초 창 모두의 안쪽
    yield


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def fake_ask(monkeypatch):
    fake = FakeAsk()
    monkeypatch.setattr(main, "ask_events", fake)
    return fake


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c
