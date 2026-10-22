import json
from datetime import date

import pytest

import place_info
from chatbot import _run_tool

SRC = [{"title": "공식 안내", "url": "https://example.com/info?utm_source=x#top"}]
GOOD = {
    "found": True,
    "weekly_hours": {"mon": "closed", "tue": "9:00-18:00", "wed": "09:00~18:00", "thu": "09:00-18:00", "fri": "09:00-18:00", "sat": "09:00-19:00", "sun": "24시간"},
    "closed_note": "매주 월요일 휴무",
    "menu": [{"name": "국밥", "price": "9,000원"}, {"name": "수육", "price": "싸요"}],
    "notes": "공휴일은 정상 운영",
}


def reply(data) -> str:
    return "결과입니다.\n" + json.dumps(data, ensure_ascii=False) + "\n끝"


@pytest.fixture
def web(monkeypatch):
    calls = []

    def fake(name, address, kind):
        calls.append((name, address, kind))
        return reply(GOOD), SRC

    monkeypatch.setattr(place_info, "_web_search", fake)
    monkeypatch.setattr(place_info, "_cache_get", None)
    monkeypatch.setattr(place_info, "_cache_put", None)
    return calls


# ── 검증·정리 ──
def test_parse_keeps_only_validated_fields():
    info = place_info.parse(reply(GOOD), SRC, "restaurant")
    assert info["status"] == "found"
    assert info["weekly_hours"]["tue"] == "09:00-18:00" and info["weekly_hours"]["wed"] == "09:00-18:00"
    assert info["weekly_hours"]["mon"] == "closed" and info["weekly_hours"]["sun"] == "24h"
    assert info["menu"] == [{"name": "국밥", "price": "9,000원"}, {"name": "수육", "price": None}]  # 형식이 틀린 가격은 버린다
    assert info["sources"] == [{"title": "공식 안내", "url": "https://example.com/info"}]  # 추적·조각 제거


def test_attractions_ignore_menu_and_bad_hours_become_unknown():
    data = {**GOOD, "weekly_hours": {"mon": "25:00-26:00", "tue": "아침 일찍", "wed": "10:00-17:00"}}
    info = place_info.parse(reply(data), SRC, "attraction")
    assert info["menu"] == [] and info["weekly_hours"]["mon"] is None and info["weekly_hours"]["tue"] is None
    assert info["weekly_hours"]["wed"] == "10:00-17:00"


@pytest.mark.parametrize("text,sources", [
    (reply(GOOD), []),                                  # 출처가 없으면 버린다
    (reply({**GOOD, "found": False}), SRC),             # 못 찾았다고 함
    ("JSON이 아닌 답변입니다.", SRC),
    ("{깨진 json", SRC),
    (reply({"found": True, "weekly_hours": {"mon": "아무말"}, "menu": []}), SRC),  # 쓸 수 있는 값이 하나도 없음
    (reply(GOOD), [{"title": "x", "url": "http://insecure.example/a"}]),           # https가 아닌 출처만 있음
])
def test_unverifiable_results_are_not_found(text, sources):
    info = place_info.parse(text, sources, "restaurant")
    assert info["status"] == "not_found" and info["weekly_hours"] is None and info["menu"] == [] and info["sources"] == []


def test_free_text_is_truncated():
    info = place_info.parse(reply({**GOOD, "notes": "x" * 500}), SRC, "attraction")
    assert len(info["notes"]) == 120


def test_day_state_by_weekday():
    info = place_info.parse(reply(GOOD), SRC, "attraction")
    assert place_info.day_state(info, date(2026, 11, 16)) == "휴무"          # 월
    assert place_info.day_state(info, date(2026, 11, 17)) == "09:00-18:00"   # 화
    assert place_info.day_state(info, date(2026, 11, 22)) == "24시간"        # 일
    assert place_info.day_state({"weekly_hours": None}, date(2026, 11, 17)) == "확인 필요"


# ── 조회 ──
def test_lookup_computes_state_per_date_and_caps_places(web):
    refs = [{"name": f"장소{i}", "address": "서울"} for i in range(9)]
    out = place_info.lookup_places_info(refs, "attraction", ["2026-11-16", "2026-11-17", "2026-11-16"])
    assert len(out["results"]) == place_info.MAX_PLACES == len(web)
    assert out["results"][0]["by_date"] == {"2026-11-16(월)": "휴무", "2026-11-17(화)": "09:00-18:00"}
    assert out["dates"] == ["2026-11-16", "2026-11-17"] and out["source"] == place_info.SOURCE


def test_lookup_requires_places(web):
    with pytest.raises(ValueError):
        place_info.lookup_places_info([], "attraction")


def test_search_failures_are_reported_without_internal_details(monkeypatch):
    monkeypatch.setattr(place_info, "_cache_get", None)
    monkeypatch.setattr(place_info, "_web_search", lambda *a: (_ for _ in ()).throw(RuntimeError("secret-key-123")))
    out = place_info.lookup_places_info([{"name": "경복궁", "address": "서울"}])
    assert out["results"][0]["status"] == "error" and "secret" not in json.dumps(out, ensure_ascii=False)


def test_cache_avoids_repeat_searches_and_keeps_misses_short(monkeypatch, web):
    store, ttl = {}, {}
    monkeypatch.setattr(place_info, "_cache_get", lambda k: store.get(k))
    monkeypatch.setattr(place_info, "_cache_put", lambda k, v, days: (store.__setitem__(k, v), ttl.__setitem__(k, days)))
    ref = [{"name": "경복궁", "address": "서울 종로구"}]
    first = place_info.lookup_places_info(ref)["results"][0]
    second = place_info.lookup_places_info(ref)["results"][0]
    assert len(web) == 1 and first["cached"] is False and second["cached"] is True and second["weekly_hours"] == first["weekly_hours"]
    assert list(ttl.values()) == [place_info.CACHE_DAYS]
    monkeypatch.setattr(place_info, "_web_search", lambda *a: ("모름", []))
    place_info.lookup_places_info([{"name": "없는곳", "address": ""}])
    assert sorted(ttl.values()) == [1, place_info.CACHE_DAYS]  # 못 찾은 결과는 하루만


def test_model_view_has_no_invented_values(web):
    out = place_info.lookup_places_info([{"name": "국밥집", "address": "부산"}], "restaurant", ["2026-11-16"])
    view = place_info.compact_for_model(out["results"][0])
    assert view["날짜별 운영"] == {"2026-11-16(월)": "휴무"} and view["메뉴"] == ["국밥 9,000원", "수육"]
    assert view["출처"] == ["https://example.com/info"]
    miss = place_info.compact_for_model({"name": "x", "status": "not_found"})
    assert miss == {"장소": "x", "상태": "확인 못 함"}


# ── 에이전트 도구 경로 ──
def test_run_tool_records_infos_for_trace_and_model(web):
    call = {"name": "get_places_info", "args": {"places": [{"name": "경복궁", "address": "서울"}], "kind": "attraction", "dates": ["2026-11-16"]}, "id": "t1"}
    msg, log = _run_tool(call, set())
    assert log["status"] == "success" and log["count"] == 1 and log["infos"][0]["name"] == "경복궁"
    assert "휴무" in msg.content and "웹 검색 기준" in msg.content
    again, log2 = _run_tool(call, {("get_places_info", json.dumps(call["args"], sort_keys=True, ensure_ascii=False))})
    assert log2["status"] == "skipped"  # 같은 인자는 다시 조회하지 않는다(목록 인자도 비교됨)


def test_run_tool_marks_partial_and_no_data(monkeypatch):
    monkeypatch.setattr(place_info, "_cache_get", None)
    answers = {"a": (reply(GOOD), SRC), "b": ("모름", [])}
    monkeypatch.setattr(place_info, "_web_search", lambda name, addr, kind: answers[name])
    base = {"kind": "attraction"}
    _, log = _run_tool({"name": "get_places_info", "args": {**base, "places": [{"name": "a"}, {"name": "b"}]}, "id": "1"}, set())
    assert log["status"] == "partial" and log["count"] == 1
    _, log = _run_tool({"name": "get_places_info", "args": {**base, "places": [{"name": "b"}]}, "id": "2"}, set())
    assert log["status"] == "no_data" and log["count"] == 0
