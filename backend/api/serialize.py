"""저장된 메시지를 API 응답 모양으로 바꾼다(docs/API.md의 '메시지'). 내부용 facts는 내보내지 않는다."""


def public_message(m: dict) -> dict:
    out = {k: v for k, v in m.items() if k != "facts"}
    out["error"] = bool(m.get("error"))
    if m.get("role") != "assistant":
        return out
    offer = m.get("offer", False)
    out["offer"] = "draft" if offer is True else (offer or False)  # 옛 형식의 True는 draft
    out.setdefault("draft", None)
    out.setdefault("food", None)
    if out["offer"] == "food":
        start = ((m.get("facts") or {}).get("weather") or {}).get("date")
        out["offer_defaults"] = {"start_date": start} if start else {}
    return out
