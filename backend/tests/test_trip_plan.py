import json
from datetime import timedelta

import pytest
from langchain_core.messages import AIMessageChunk

import chatbot
import stays
import tools
import trip_plan
import weather
from weather import now_kst

START = (now_kst().date() + timedelta(days=15)).isoformat()
FULL = {"destination": "제주", "start_date": START, "nights": 2, "adults": 2, "need_stay": True}


# ── 조건 저장·검증 (모델 없음) ──
def test_update_merges_and_reports_missing():
    trip, errors, _ = trip_plan.update(None, {"destination": "제주", "adults": 2})
    assert errors == [] and trip["stage"] == "intake"
    assert trip_plan.missing(trip) == ["출발일", "몇 박인지", "숙소 조회가 필요한지"]
    trip, _, _ = trip_plan.update(trip, {"start_date": START, "nights": 2, "need_stay": False})
    assert trip_plan.complete(trip)


def test_invalid_values_are_rejected_not_saved():
    trip, errors, _ = trip_plan.update(None, {"start_date": "13월 45일", "nights": 99, "adults": 0, "need_stay": "yes", "destination": "  "})
    assert len(errors) == 4 and trip == {"stage": "intake"}
    _, errors, _ = trip_plan.update(None, {"start_date": "언젠가"})
    assert errors


def test_stale_year_in_start_date_is_corrected_with_a_note():
    """모델이 '2023-10-24'처럼 지난 해를 넣으면 올해 기준으로 바로잡고, 모델에게 알리며, 요약에서 사용자가 확인한다."""
    stale = str(int(START[:4]) - 3) + START[4:]
    trip, errors, notes = trip_plan.update(None, {"start_date": stale})
    assert errors == [] and trip["start_date"] == START
    assert notes and START in notes[0]
    full, _, _ = trip_plan.update(None, {**FULL, "start_date": stale})
    assert START in trip_plan.summary(full)


def test_month_day_and_relative_start_dates_are_resolved():
    trip, errors, notes = trip_plan.update(None, {"start_date": "다음 주 토요일"})
    assert errors == [] and trip["start_date"] > weather.now_kst().date().isoformat() and notes == []


def test_changing_a_condition_reopens_confirmation():
    trip, _, _ = trip_plan.update(None, FULL)
    trip["stage"] = "done"
    same, _, _ = trip_plan.update(trip, {"destination": "제주"})
    assert same["stage"] == "done"  # 같은 값을 다시 말해도 바뀌지 않는다
    changed, _, _ = trip_plan.update(trip, {"nights": 3})
    assert changed["stage"] == "intake"


def test_summary_has_dates_and_question():
    trip, _, _ = trip_plan.update(None, {**FULL, "children": 1, "budget": "1인 30만원"})
    text = trip_plan.summary(trip)
    assert "2박 3일" in text and "성인 2명, 아동 1명" in text and "1인 30만원" in text and "작성**할까요" in text
    assert trip_plan.check_out(trip) > START


# ── 에이전트 흐름 (모델·외부 호출은 가짜) ──
class ScriptedLLM:
    script: list = []
    bound: list = []

    def __init__(self, *a, **k):
        pass

    def bind_tools(self, tools_):
        ScriptedLLM.bound.append({t.name for t in tools_})
        return self

    def stream(self, messages):
        kind, *rest = ScriptedLLM.script.pop(0)
        if kind == "text":
            yield AIMessageChunk(content=rest[0])
        else:
            name, args = rest
            yield AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": json.dumps(args), "id": f"c{len(ScriptedLLM.script)}", "index": 0}])


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(chatbot, "ChatOpenAI", ScriptedLLM)
    ScriptedLLM.script, ScriptedLLM.bound = [], []
    return ScriptedLLM


def run(question, facts, offer_pending=False):
    events = list(chatbot.ask_events(question, [], facts, offer_pending))
    return events, events[-1]


def test_missing_info_is_asked_not_assumed(llm):
    llm.script = [("tool", "save_trip_info", {"destination": "제주"}), ("text", "출발일, 몇 박, 인원, 숙소 조회 여부를 알려 주세요.")]
    _, final = run("제주 여행 계획 짜줘", {})
    assert final["type"] == "final" and final["offer"] is False
    assert final["facts"]["trip"]["destination"] == "제주" and final["facts"]["trip"]["stage"] == "intake"
    assert "수집 중" in final["trace"]["end"] and final["trace"]["steps"][0]["missing"]
    assert llm.bound[0] >= {"save_trip_info"} and "confirm_trip_plan" not in llm.bound[0]


def test_complete_info_asks_for_consent_without_another_model_call(llm):
    llm.script = [("tool", "save_trip_info", FULL)]  # 두 번째 모델 호출이 있으면 빈 스크립트에서 실패한다
    events, final = run("제주 ... 모두 말함", {})
    assert final["offer"] == "plan" and final["facts"]["trip"]["stage"] == "confirm"
    assert "작성**할까요" in final["answer"] and "숙소 조회: 필요" in final["answer"]
    assert any(e["type"] == "token" for e in events)


def test_consent_composes_plan_with_wider_limits_and_no_draft_card(llm, monkeypatch):
    monkeypatch.setattr(tools, "_search", lambda region, category: [{"name": "협재해수욕장", "address": "제주", "map_link": "http://place.map.kakao.com/1", "x": "126.2", "y": "33.3"}])
    monkeypatch.setattr(weather, "forecast", lambda region, date: {"status": "ok", "source": "t", "queried_at": "q", "region": region, "date": START, "weekday": "토", "temp_max": 18.0, "temp_min": 10.0, "precip_prob": 10, "units": {}})
    monkeypatch.setattr(stays, "search_stays", lambda *a, **k: {"stays": [{"gid": 7, "name": "바다호텔", "booking_link": "https://accommodation.myrealtrip.com/union/products/7?x=1"}], "source": "s", "queried_at": "q", "params": {}})
    trip, _, _ = trip_plan.update(None, FULL)
    trip["stage"] = "confirm"
    llm.script = [
        ("tool", "confirm_trip_plan", {}),
        ("tool", "search_places", {"region": "제주", "category": "관광지"}),
        ("tool", "get_weather", {"region": "제주", "date": START}),
        ("tool", "find_stays", {"keyword": "제주", "check_in": START, "check_out": trip_plan.check_out(trip), "adults": 2}),
        ("text", "## 여행 개요\n[협재해수욕장](http://place.map.kakao.com/1) / [바다호텔](https://accommodation.myrealtrip.com/union/products/7?x=1)"),
    ]
    _, final = run("네, 작성해 주세요", {"trip": trip, "places": None}, offer_pending="plan")
    assert "confirm_trip_plan" in llm.bound[0]
    assert final["offer"] is False  # 장소+날씨가 있어도 초안 카드를 따로 묻지 않는다
    assert final["facts"]["trip"]["stage"] == "done"
    t = final["trace"]
    assert t["tool_limit"] == 7 and t["tool_calls"] == 4 and t["grounded"] is True and "여행 계획을 작성" in t["end"]


def test_plan_with_unlisted_link_is_flagged(llm, monkeypatch):
    monkeypatch.setattr(tools, "_search", lambda region, category: [{"name": "a", "address": "b", "map_link": "http://place.map.kakao.com/1", "x": "1", "y": "2"}])
    trip, _, _ = trip_plan.update(None, FULL)
    trip["stage"] = "confirm"
    llm.script = [("tool", "confirm_trip_plan", {}), ("tool", "search_places", {"region": "제주", "category": "관광지"}), ("text", "http://place.map.kakao.com/999")]
    _, final = run("네", {"trip": trip}, offer_pending="plan")
    assert final["trace"]["grounded"] is False


def test_confirm_before_ready_is_an_error(llm):
    msg, log, facts = chatbot._run_trip_tool({"name": "confirm_trip_plan", "args": {}, "id": "x"}, {"trip": {"stage": "intake"}})
    assert log["status"] == "error" and msg.content.startswith("도구 오류") and facts["trip"]["stage"] == "intake"
