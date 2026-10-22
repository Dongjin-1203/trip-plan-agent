from api import settings

from conftest import CLIENT_A, CLIENT_B, headers, parse_sse


def chat(client, message="안녕", client_id=CLIENT_A, **body):
    return client.post("/api/chat", json={"message": message, **body}, headers=headers(client_id))


def first_session_id(client, client_id=CLIENT_A):
    return client.get("/api/sessions", headers=headers(client_id)).json()[0]["id"]


# ── 상태·헤더 ──
def test_health_and_ready(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_client_id_required_and_validated(client, fake_ask):
    assert client.get("/api/sessions").status_code == 400
    assert client.get("/api/sessions", headers={"X-Client-Id": "short"}).status_code == 400
    assert client.get("/api/sessions", headers={"X-Client-Id": "x" * 70}).status_code == 400
    assert client.get("/api/sessions", headers={"X-Client-Id": "bad id with spaces!!"}).status_code == 400


# ── 채팅 스트림 ──
def test_chat_stream_order_and_final_message(client, fake_ask):
    res = chat(client, "경주 카페")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    names = [n for n, _ in events]
    assert names == ["session", "status", "token", "token", "final"]
    assert events[0][1]["title"] == "경주 카페" and len(events[0][1]["id"]) == 32
    assert "".join(d["text"] for n, d in events if n == "token") == "안녕하세요"
    message = events[-1][1]["message"]
    assert message["role"] == "assistant" and message["content"] == "안녕하세요" and message["error"] is False
    assert "facts" not in message  # 내부용 facts는 내보내지 않는다


def test_session_saved_and_listed(client, fake_ask):
    chat(client, "첫 질문")
    sessions = client.get("/api/sessions", headers=headers()).json()
    assert len(sessions) == 1 and sessions[0]["title"] == "첫 질문"
    detail = client.get(f"/api/sessions/{sessions[0]['id']}", headers=headers()).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "첫 질문"


def test_conversation_continues_with_history_and_facts(client, fake_ask):
    sid = parse_sse(chat(client, "질문1").text)[0][1]["id"]
    chat(client, "질문2", session_id=sid)
    second = fake_ask.calls[1]
    assert [m["role"] for m in second["history"]] == ["user", "assistant"]
    assert second["facts"] == {"places": {"region": "경주"}}  # 이전 턴의 조회 사실이 이어진다
    assert len(client.get(f"/api/sessions/{sid}", headers=headers()).json()["messages"]) == 4


# ── 사용자 격리(이번 개편의 핵심) ──
def test_other_client_cannot_see_or_touch_session(client, fake_ask):
    chat(client, "내 비밀 대화", client_id=CLIENT_A)
    sid = first_session_id(client, CLIENT_A)
    assert client.get("/api/sessions", headers=headers(CLIENT_B)).json() == []
    assert client.get(f"/api/sessions/{sid}", headers=headers(CLIENT_B)).status_code == 404
    assert client.delete(f"/api/sessions/{sid}", headers=headers(CLIENT_B)).status_code == 404
    assert client.post(f"/api/sessions/{sid}/offer/dismiss", headers=headers(CLIENT_B)).status_code == 404
    assert chat(client, "끼어들기", client_id=CLIENT_B, session_id=sid).status_code == 404
    # A의 대화는 그대로다
    assert len(client.get(f"/api/sessions/{sid}", headers=headers(CLIENT_A)).json()["messages"]) == 2


def test_unknown_or_malformed_session_is_404(client, fake_ask):
    assert client.get("/api/sessions/" + "0" * 32, headers=headers()).status_code == 404
    assert client.get("/api/sessions/not-a-session", headers=headers()).status_code == 404


# ── 실패·재시도 ──
def test_failure_is_saved_and_retry_replaces_it(client, fake_ask):
    fake_ask.mode = "error"
    events = parse_sse(chat(client, "실패할 질문").text)
    assert [n for n, _ in events] == ["session", "error"]
    assert events[-1][1] == {"message": "OpenAI 서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.", "retryable": True}
    sid = events[0][1]["id"]
    saved = client.get(f"/api/sessions/{sid}", headers=headers()).json()["messages"]
    assert [m["error"] for m in saved] == [True, True]

    fake_ask.mode = "ok"
    final = parse_sse(chat(client, "실패할 질문", session_id=sid, retry=True).text)[-1]
    assert final[0] == "final"
    saved = client.get(f"/api/sessions/{sid}", headers=headers()).json()["messages"]
    assert [m["error"] for m in saved] == [False, False] and len(saved) == 2  # 실패 쌍이 지워지고 성공 쌍만 남음
    assert fake_ask.calls[-1]["history"] == []  # 실패한 턴은 모델 기억에 들어가지 않았다


def test_internal_errors_do_not_leak(client, fake_ask):
    fake_ask.mode = "crash"
    res = chat(client, "터질 질문")
    assert "secret-internal-detail" not in res.text
    assert parse_sse(res.text)[-1][1]["retryable"] is True


# ── 제안(offer) ──
def test_offer_state_flows_to_next_turn(client, fake_ask):
    fake_ask.mode = "draft_offer"
    sid = parse_sse(chat(client, "장소와 날씨").text)[0][1]["id"]
    chat(client, "네, 작성해 주세요", session_id=sid)
    assert fake_ask.calls[1]["offer_pending"] == "draft"  # 직전 메시지의 제안이 다음 턴에 전달된다


def test_food_offer_defaults_and_dismiss(client, fake_ask):
    fake_ask.mode = "food_offer"
    events = parse_sse(chat(client, "초안").text)
    sid, message = events[0][1]["id"], events[-1][1]["message"]
    assert message["offer"] == "food" and message["offer_defaults"] == {"start_date": "2026-10-24"}
    assert message["draft"]["cond"]["region"] == "경주"

    assert client.post(f"/api/sessions/{sid}/offer/dismiss", headers=headers()).status_code == 204
    saved = client.get(f"/api/sessions/{sid}", headers=headers()).json()["messages"]
    assert saved[-1]["offer"] is False

    fake_ask.mode = "ok"
    chat(client, "다른 질문", session_id=sid)
    assert fake_ask.calls[-1]["offer_pending"] is False  # 닫은 제안은 더 이어지지 않는다


def test_food_request_is_passed_to_agent(client, fake_ask):
    body = {"start_date": "2026-10-24", "days": 3, "departure": "10:00", "return_time": "19:00"}
    events = parse_sse(chat(client, "맛집 추천: 데모", food_request=body).text)
    assert fake_ask.calls[0]["food_request"] == body
    assert events[-1][1]["message"]["food"]["request"] == body


# ── 삭제 ──
def test_delete_session(client, fake_ask):
    chat(client, "지울 대화")
    sid = first_session_id(client)
    assert client.delete(f"/api/sessions/{sid}", headers=headers()).status_code == 204
    assert client.get(f"/api/sessions/{sid}", headers=headers()).status_code == 404
    assert client.get("/api/sessions", headers=headers()).json() == []


def test_session_cap_removes_oldest(client, fake_ask, monkeypatch):
    monkeypatch.setattr(settings, "MAX_SESSIONS_PER_CLIENT", 2)
    for i in range(3):
        chat(client, f"대화{i}")
    titles = [s["title"] for s in client.get("/api/sessions", headers=headers()).json()]
    assert titles == ["대화2", "대화1"]


# ── 요청 제한 ──
def test_rate_limit_per_client_per_minute(client, fake_ask, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    assert chat(client).status_code == 200
    assert chat(client).status_code == 200
    third = chat(client)
    assert third.status_code == 429
    assert int(third.headers["retry-after"]) >= 1
    body = third.json()
    assert body["retry_after"] == int(third.headers["retry-after"]) and "detail" in body
    assert chat(client, client_id=CLIENT_B).status_code == 200  # 다른 사용자는 영향이 없다
    assert len(fake_ask.calls) == 3  # 제한된 요청은 모델을 부르지 않았다


def test_rate_limit_per_ip(client, fake_ask, monkeypatch):
    monkeypatch.setattr(settings, "IP_RATE_LIMIT_PER_MINUTE", 2)
    ip = {"X-Forwarded-For": "1.1.1.1, 9.9.9.9"}
    ok = [client.post("/api/chat", json={"message": "m"}, headers={**headers(CLIENT_A), **ip}).status_code for _ in range(2)]
    assert ok == [200, 200]
    assert client.post("/api/chat", json={"message": "m"}, headers={**headers(CLIENT_B), **ip}).status_code == 429  # 같은 IP, 다른 사용자도 제한


def test_client_ip_header_trusted_only_when_enabled(client, fake_ask, monkeypatch):
    monkeypatch.setattr(settings, "IP_RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "TRUST_CLIENT_IP_HEADER", True)
    def post(cid, ip):
        return client.post("/api/chat", json={"message": "m"}, headers={**headers(cid), "X-Client-Ip": ip}).status_code
    assert post(CLIENT_A, "10.0.0.1") == 200
    assert post(CLIENT_B, "10.0.0.2") == 200  # 신뢰하면 IP별로 따로 센다
    assert post(CLIENT_A, "10.0.0.1") == 429


# ── 입력 검증 ──
def test_validation_errors(client, fake_ask):
    assert chat(client, "").status_code == 422
    assert chat(client, "   ").status_code == 422
    assert chat(client, "가" * (settings.MAX_MESSAGE_CHARS + 1)).status_code == 422
    assert chat(client, "가" * settings.MAX_MESSAGE_CHARS).status_code == 200
    bad_days = {"start_date": "2026-10-24", "days": 99, "departure": "10:00", "return_time": "18:00"}
    assert chat(client, "맛집", food_request=bad_days).status_code == 422
    bad_time = {"start_date": "2026-10-24", "days": 2, "departure": "25:00", "return_time": "18:00"}
    assert chat(client, "맛집", food_request=bad_time).status_code == 422
    assert chat(client, "x", session_id="not-hex").status_code == 422
    assert len(fake_ask.calls) == 1  # 검증에 실패한 요청은 에이전트까지 가지 않는다
