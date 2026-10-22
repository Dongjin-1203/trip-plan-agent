from datetime import timedelta

import pytest

import stays
from chatbot import _run_tool
from run_trace import build_trace
from weather import now_kst

RAW = {
    "structuredContent": {"stays": [
        {"gid": 101, "name": "해변 호텔", "description": "4성급 · 호텔 · 제주", "price": "150,000원/박",
         "additionalPrice": "세금포함 165,000원/박", "rating": 4.5, "reviewCount": "(1,234)", "tags": ["무료취소"],
         "thumbnailUrl": "https://img.example/a.jpg"},
        {"gid": "bad", "name": "무시될 항목"},
        {"gid": 102, "name": "산장", "thumbnailUrl": "http://insecure.example/b.jpg"},
    ]},
}


def dates(offset=10, nights=2):
    d = now_kst().date() + timedelta(days=offset)
    return d.isoformat(), (d + timedelta(days=nights)).isoformat()


@pytest.fixture
def rpc(monkeypatch):
    calls = []

    def fake(method, params):
        calls.append((method, params))
        return RAW

    monkeypatch.setattr(stays, "_rpc", fake)
    return calls


def test_search_normalizes_and_builds_booking_link(rpc):
    ci, co = dates()
    out = stays.search_stays("제주", ci, co, adults=2, children=1, domestic=True)
    assert [s["gid"] for s in out["stays"]] == [101, 102]  # gid가 정수가 아닌 항목은 버린다
    first = out["stays"][0]
    assert first["review_count"] == "1,234" and first["image"].startswith("https://")
    assert out["stays"][1]["image"] == ""  # https가 아닌 이미지는 쓰지 않는다
    assert first["booking_link"] == f"https://accommodation.myrealtrip.com/union/products/101?checkIn={ci}&checkOut={co}&adultCount=2&childCount=1"
    args = rpc[0][1]["arguments"]
    assert args["keyword"] == "제주" and args["isDomestic"] is True and args["adultCount"] == 2


@pytest.mark.parametrize("ci,co", [("2020-01-01", "2020-01-03"), ("내일", "모레"), ("", "")])
def test_invalid_or_past_dates_are_rejected_without_calling(rpc, ci, co):
    with pytest.raises(stays.StaySearchError):
        stays.search_stays("제주", ci, co)
    assert rpc == []


def test_checkout_must_follow_checkin_and_stay_is_limited(rpc):
    ci, _ = dates()
    with pytest.raises(stays.StaySearchError):
        stays.search_stays("제주", ci, ci)
    ci, co = dates(nights=stays.MAX_NIGHTS + 1)
    with pytest.raises(stays.StaySearchError):
        stays.search_stays("제주", ci, co)
    with pytest.raises(stays.StaySearchError):
        stays.search_stays("  ", *dates())
    assert rpc == []


def test_server_errors_become_safe_messages(monkeypatch):
    monkeypatch.setattr(stays.requests, "post", lambda *a, **k: (_ for _ in ()).throw(stays.requests.ConnectionError("secret-host")))
    with pytest.raises(stays.StaySearchError) as e:
        stays.search_stays("제주", *dates())
    assert "secret" not in str(e.value)


def test_unreadable_result_is_an_error(monkeypatch):
    monkeypatch.setattr(stays, "_rpc", lambda m, p: {"content": [], "isError": True})
    with pytest.raises(stays.StaySearchError):
        stays.search_stays("제주", *dates())


def test_run_tool_records_stays_for_trace(rpc):
    ci, co = dates()
    call = {"name": "find_stays", "args": {"keyword": "제주", "check_in": ci, "check_out": co}, "id": "t1"}
    msg, log = _run_tool(call, set())
    assert log["status"] == "success" and log["count"] == 2 and log["stays"][0]["name"] == "해변 호텔"
    assert "image" not in msg.content and "booking_link" in msg.content  # 모델에게 이미지 주소는 주지 않는다
    answer = f"[예약]({log['stays'][0]['booking_link']})"
    trace = build_trace([log], 2, answer)
    assert trace["grounded"] is True and trace["steps"][0]["stays"]
    assert build_trace([log], 2, "[예약](https://accommodation.myrealtrip.com/union/products/999?x=1)")["grounded"] is False


def test_run_tool_reports_validation_error_to_model(rpc):
    call = {"name": "find_stays", "args": {"keyword": "제주", "check_in": "2020-01-01", "check_out": "2020-01-02"}, "id": "t2"}
    msg, log = _run_tool(call, set())
    assert log["status"] == "error" and msg.content.startswith("도구 오류")
