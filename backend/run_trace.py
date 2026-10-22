import re

from config import MAX_MODEL_CALLS, MAX_TOOL_CALLS
from trip_plan import TRIP_TOOLS

ENOUGH_RESULTS = 3  # 첫 검색 결과가 이 개수 이상이면 충분하다고 본다.

END_LABELS = {
    "no_tool": "도구 불필요: 대화로 답했다",
    "enough": "결과 충분: 추가 검색 없이 끝냈다",
    "retry_done": "재검색 후 답했다",
    "few": "결과가 적거나 없었지만 더 검색하지 않고 끝냈다",
    "auth_error": "인증 오류: 키 설정 확인 안내로 끝냈다",
    "limit": "호출 한도 도달: 한도에서 멈췄다",
    "draft": "사용자 동의 후 여행 계획 초안을 작성했다(검사 통과 결과만 근거)",
    "food": "입력한 기간·출발시간으로 끼니를 계산해 초안 장소 주변 반경 검색으로 맛집을 추천했다(조회 결과만 근거)",
    "weather": "날씨 조회 후 답했다",
    "stays": "숙소 조회 후 답했다(마이리얼트립 조회 결과만 근거)",
    "info": "장소 정보를 웹검색으로 조회해 답했다(출처가 있는 값만 근거)",
    "trip_ask": "여행 조건 수집 중: 빠진 항목을 사용자에게 물었다",
    "trip_confirm": "여행 조건 수집 완료: 요약을 보여 주고 작성 동의를 받는다",
    "plan": "동의 후 장소·날씨·숙소를 조회해 여행 계획을 작성했다(조회 결과만 근거)",
    "weather_none": "날씨 값을 쓸 수 없어 예보 없음·확인 필요로 답했다",
}

_LINK_ID = re.compile(r"place\.map\.kakao\.com/(\d+)")
_STAY_ID = re.compile(r"accommodation\.myrealtrip\.com/union/products/(\d+)")


def _step_note(prev: dict | None, log: dict) -> str:
    """무엇을 / 왜 다시 검색했는지를 기록 값(인자·결과 건수)만으로 설명한다. 모델의 생각은 쓰지 않는다."""
    if log["status"] == "skipped":
        return "같은 인자 반복이라 실행하지 않음"
    if log["tool"] == "save_trip_info":
        return "여행 조건 저장" + (f" — 빠진 항목: {', '.join(log['missing'])}" if log.get("missing") else " — 필수 항목 모두 수집")
    if log["tool"] == "confirm_trip_plan":
        return "사용자 동의 확인 — 이후 조회한 결과만 근거로 계획 작성"
    if log["tool"] == "draft_travel_plan":
        return "사용자 동의 후 초안 작성 — 검사를 통과한 결과만 근거로 사용"
    if log["tool"] == "nearby_restaurants":
        a = log["args"]
        return f"여행 {a.get('days', '?')}일 · 끼니 {a.get('meals', '?')}끼 · 기준 장소별 반경 검색(끼니마다 1곳 추천)"
    if log["tool"] == "get_places_info":
        return "장소 정보 웹검색 — 출처가 있는 값만 사용(공휴일·임시 휴업은 방문 전 확인)"
    if log["tool"] == "find_stays":
        return "숙소 조회 — 마이리얼트립 검색 결과(가격·예약 링크는 변동될 수 있음)" if log["status"] == "success" else f"숙소 조회 결과 {log['status']}"
    if log["tool"] == "get_weather":
        return {"ok": "날씨 조회", "out_of_range": "예보 범위 밖이라 API를 부르지 않음"}.get(log["status"], f"날씨 조회 결과 {log['status']}")
    if prev is None:
        return "첫 검색"
    args, prev_args = log["args"], prev["args"]
    changed = [k for k in args if args[k] != prev_args.get(k)]
    why = "이전 결과 0건" if prev.get("count") == 0 else f"이전 결과 {prev.get('count', '?')}건"
    return f"재검색({why}) · 바뀐 인자: {', '.join(changed) or '없음'}"


def _end_reason(logs: list[dict], limit_hit: bool) -> str:
    if not logs:
        return "no_tool"
    if any(l["tool"] == "confirm_trip_plan" for l in logs):
        return "limit" if limit_hit else "plan"
    if logs[-1]["tool"] == "save_trip_info":
        return "trip_ask" if logs[-1].get("missing") else "trip_confirm"
    if logs[-1]["tool"] == "draft_travel_plan":
        return "draft"
    if logs[-1]["tool"] == "nearby_restaurants" and logs[-1]["status"] != "auth_error":
        return "food"
    if logs[-1]["status"] == "auth_error":
        return "auth_error"
    if limit_hit:
        return "limit"
    if logs[-1]["tool"] == "find_stays" and logs[-1]["status"] == "success" and logs[-1].get("count"):
        return "stays"
    if logs[-1]["tool"] == "get_places_info":
        return "info"
    if logs[-1]["tool"] == "get_weather":
        return "weather" if logs[-1]["status"] == "ok" else "weather_none"
    count = logs[-1].get("count", 0)
    if len(logs) == 1 and count >= ENOUGH_RESULTS:
        return "enough"
    return "retry_done" if len(logs) > 1 else "few"


def _grounded(answer: str, logs: list[dict]) -> bool:
    """답변의 장소 링크가 마지막 도구 결과에 있는 장소인지 확인한다.
    서로 다른 지역을 검색한 실행(일정 등)은 지역별 마지막 결과를 모두 근거로 인정한다."""
    used_stays = set(_STAY_ID.findall(answer))
    if used_stays and not used_stays <= {str(st["gid"]) for l in logs if l["tool"] == "find_stays" for st in l.get("stays", [])}:
        return False
    used = set(_LINK_ID.findall(answer))
    ok = [l for l in logs if (l["status"] == "success" or l["tool"] in ("draft_travel_plan", "nearby_restaurants")) and l["tool"] not in TRIP_TOOLS]
    if not used:
        return True
    if not ok:
        return False
    if all(l["tool"] == "nearby_restaurants" for l in ok):  # 점심·저녁 검색 결과를 모두 근거로 인정한다.
        allowed = {i for l in ok for p in l.get("places", []) for i in _LINK_ID.findall(p["map_link"])}
        return used <= allowed
    regions = {l["args"].get("region") for l in ok}
    last_per_region = {l["args"].get("region"): l for l in ok}
    planned = any(l["tool"] == "confirm_trip_plan" for l in logs)  # 계획 작성은 여러 번 조회한 결과를 모두 쓴다
    basis = ok if planned else [ok[-1]] if len(regions) == 1 else list(last_per_region.values())
    allowed = {i for l in basis for p in l.get("places", []) for i in _LINK_ID.findall(p["map_link"])}
    return used <= allowed


def build_trace(logs: list[dict], model_calls: int, answer: str, limit_hit: bool = False,
                tool_limit: int = MAX_TOOL_CALLS, model_limit: int = MAX_MODEL_CALLS) -> dict:
    """한 번의 에이전트 실행을 '도구 호출 → 반환 → 다음 호출 또는 답변' 순서로 기록한다."""
    steps = []
    prev = None  # 장소 검색 단계끼리만 재검색 여부를 비교한다.
    for i, log in enumerate(logs, 1):
        steps.append({**log, "step": i, "note": _step_note(prev, log)})
        if log["tool"] == "search_places":
            prev = log
    reason = _end_reason(logs, limit_hit)
    return {
        "steps": steps,
        "tool_calls": len(logs),
        "tool_limit": tool_limit,
        "model_calls": model_calls,
        "model_limit": model_limit,
        "end": END_LABELS[reason],
        "grounded": _grounded(answer, logs),
    }


def title(trace: dict) -> str:
    return (
        f"실행 기록 (도구 {trace['tool_calls']}/{trace['tool_limit']}회 · "
        f"모델 {trace['model_calls']}/{trace['model_limit']}회)"
    )
