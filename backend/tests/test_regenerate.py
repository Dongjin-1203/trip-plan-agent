from conftest import CLIENT_A, CLIENT_B, headers, parse_sse
from test_api import chat


def saved(client, sid, client_id=CLIENT_A):
    return client.get(f"/api/sessions/{sid}", headers=headers(client_id)).json()["messages"]


def test_regenerate_replaces_last_turn_with_stored_question(client, fake_ask):
    sid = parse_sse(chat(client, "경주 카페").text)[0][1]["id"]
    chat(client, "두 번째 질문", session_id=sid)
    assert len(saved(client, sid)) == 4

    events = parse_sse(chat(client, "클라이언트가 바꾼 문장", session_id=sid, regenerate=True).text)
    assert events[-1][0] == "final"
    assert len(saved(client, sid)) == 4  # 마지막 쌍이 새 쌍으로 바뀌었다
    call = fake_ask.calls[-1]
    assert call["question"] == "두 번째 질문"  # 저장된 질문으로 다시 처리한다
    assert [m["content"] for m in call["history"]] == ["경주 카페", "안녕하세요"]  # 지운 쌍은 기억에서 빠진다


def test_regenerate_needs_existing_session_and_no_retry(client, fake_ask):
    assert chat(client, "질문", regenerate=True).status_code == 422
    sid = parse_sse(chat(client, "질문").text)[0][1]["id"]
    assert chat(client, "질문", session_id=sid, regenerate=True, retry=True).status_code == 422


def test_regenerate_without_a_good_last_turn_is_409(client, fake_ask):
    fake_ask.mode = "error"
    sid = parse_sse(chat(client, "실패").text)[0][1]["id"]
    res = chat(client, "실패", session_id=sid, regenerate=True)
    assert res.status_code == 409 and len(saved(client, sid)) == 2  # 실패 쌍은 그대로 둔다


def test_cannot_regenerate_someone_elses_session(client, fake_ask):
    sid = parse_sse(chat(client, "질문").text)[0][1]["id"]
    assert chat(client, "질문", client_id=CLIENT_B, session_id=sid, regenerate=True).status_code == 404
    assert len(saved(client, sid)) == 2


def test_regenerate_is_rate_limited_like_chat(client, fake_ask, monkeypatch):
    from api import settings
    sid = parse_sse(chat(client, "질문").text)[0][1]["id"]
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    assert chat(client, "질문", session_id=sid, regenerate=True).status_code == 429
