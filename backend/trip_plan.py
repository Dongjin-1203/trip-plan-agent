"""여행 계획 수립 흐름. 대화로 모은 조건을 facts["trip"]에 누적하고, 빠진 항목 판단·검증·요약을 코드로 한다(모델 호출 없음).

단계(trip["stage"]): intake(수집 중) → confirm(요약을 보여 주고 동의 대기) → compose(동의함, 조회 후 작성 중) → done(작성함).
조건이 바뀌면 다시 intake로 돌아가 동의를 새로 받는다."""
from datetime import date, timedelta

from langchain_core.tools import tool

from meals import MAX_DAYS
from weather import now_kst, resolve_future

REQUIRED = {  # 필드 → 사용자에게 물을 때 쓰는 이름
    "destination": "목적지",
    "start_date": "출발일",
    "nights": "몇 박인지",
    "adults": "성인 인원",
    "need_stay": "숙소 조회가 필요한지",
}
OPTIONAL = {"children": "아동 인원", "budget": "예산", "style": "여행 취향"}

PLAN_OFFER_TEXT = "이 조건으로 **여행 계획을 작성**할까요? 바꿀 내용이 있으면 말씀해 주세요."


@tool
def save_trip_info(
    destination: str | None = None,
    start_date: str | None = None,
    nights: int | None = None,
    adults: int | None = None,
    children: int | None = None,
    need_stay: bool | None = None,
    budget: str | None = None,
    style: str | None = None,
) -> str:
    """여행 계획·일정을 짜 달라는 요청을 받으면 가장 먼저, 그리고 사용자가 조건을 더 말할 때마다 호출한다.
    사용자가 실제로 말한 항목만 넘기고 말하지 않은 항목은 생략한다(추측해서 채우지 않는다). 아무것도 못 들었어도 처음엔 인자 없이 호출한다.
    destination: 목적지(예: 제주). start_date: 출발일. 사용자가 말한 표현 그대로 넘겨도 된다(예: '10월 24일', '다음 주 토요일'). YYYY-MM-DD로 쓸 때 연도는 오늘 날짜 기준으로 정하며 짐작하지 않는다. nights: 몇 박(1박=1).
    adults/children: 성인/아동 수. need_stay: 숙소 조회가 필요한지. budget: 예산(예: 1인 30만원). style: 취향(예: 조용한 휴식, 맛집 위주)."""
    return ""  # 실제 저장은 ask_events가 대화 상태(facts)에 직접 한다.


@tool
def confirm_trip_plan() -> str:
    """사용자가 '이 조건으로 여행 계획을 작성할까요?'라는 질문에 동의했을 때만 호출한다. 인자는 없다.
    조건을 바꾸자는 말이면 호출하지 말고 save_trip_info로 바뀐 항목만 저장한다."""
    return ""


TRIP_TOOLS = {save_trip_info.name, confirm_trip_plan.name}


def _clean(args: dict) -> tuple[dict, list[str], list[str]]:
    """넘어온 인자 중 유효한 값만 골라 (값, 오류 문구 목록, 보정 안내 목록)으로 돌려준다."""
    out: dict = {}
    errors: list[str] = []
    notes: list[str] = []

    def text(key: str, label: str, limit: int) -> None:
        v = args.get(key)
        if v is None:
            return
        v = str(v).strip()
        if v:
            out[key] = v[:limit]

    def number(key: str, label: str, lo: int, hi: int) -> None:
        v = args.get(key)
        if v is None:
            return
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not lo <= int(v) <= hi:
            errors.append(f"{label}은(는) {lo}~{hi} 사이 정수여야 합니다.")
            return
        out[key] = int(v)

    text("destination", "목적지", 40)
    text("budget", "예산", 60)
    text("style", "취향", 80)
    number("nights", "박수", 1, MAX_DAYS - 1)
    number("adults", "성인 수", 1, 20)
    number("children", "아동 수", 0, 20)
    if args.get("need_stay") is not None:
        if isinstance(args["need_stay"], bool):
            out["need_stay"] = args["need_stay"]
        else:
            errors.append("숙소 필요 여부는 true/false여야 합니다.")
    if args.get("start_date") is not None:
        raw = str(args["start_date"]).strip()
        d, adjusted = resolve_future(raw)
        if d is None:
            errors.append("출발일을 해석할 수 없습니다. 'YYYY-MM-DD'나 '10월 24일'처럼 알려 달라고 해야 합니다.")
        elif d < now_kst().date():
            errors.append("출발일이 오늘보다 앞섭니다. 날짜를 다시 확인해야 합니다.")
        else:
            out["start_date"] = d.isoformat()
            if adjusted:
                notes.append(f"출발일 '{raw}'의 연도가 지난 해라 {d.isoformat()}로 해석했다. 조건 요약에서 사용자가 날짜를 확인한다.")
    return out, errors, notes


def update(trip: dict | None, args: dict) -> tuple[dict, list[str], list[str]]:
    """저장된 조건에 새로 들은 항목을 합친다. 값이 바뀌면 단계를 intake로 되돌려 동의를 다시 받게 한다."""
    trip = dict(trip or {})
    fields, errors, notes = _clean(args)
    changed = any(trip.get(k) != v for k, v in fields.items())
    trip.update(fields)
    if changed or "stage" not in trip:
        trip["stage"] = "intake"
    return trip, errors, notes


def missing(trip: dict | None) -> list[str]:
    trip = trip or {}
    return [label for key, label in REQUIRED.items() if trip.get(key) is None]


def complete(trip: dict | None) -> bool:
    return bool(trip) and not missing(trip)


def check_out(trip: dict) -> str:
    return (date.fromisoformat(trip["start_date"]) + timedelta(days=trip["nights"])).isoformat()


def summary(trip: dict) -> str:
    """동의를 받기 전에 보여 주는 조건 요약."""
    people = f"성인 {trip['adults']}명" + (f", 아동 {trip['children']}명" if trip.get("children") else "")
    lines = [
        "**여행 조건을 정리했어요**",
        f"- 목적지: {trip['destination']}",
        f"- 일정: {trip['start_date']} ~ {check_out(trip)} ({trip['nights']}박 {trip['nights'] + 1}일)",
        f"- 인원: {people}",
        f"- 숙소 조회: {'필요' if trip['need_stay'] else '불필요'}",
    ]
    if trip.get("budget"):
        lines.append(f"- 예산: {trip['budget']}")
    if trip.get("style"):
        lines.append(f"- 취향: {trip['style']}")
    return "\n".join(lines) + "\n\n" + PLAN_OFFER_TEXT


def public(trip: dict) -> dict:
    return {k: v for k, v in trip.items() if k != "stage"}
