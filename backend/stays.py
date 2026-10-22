"""숙소 조회 서브에이전트. 마이리얼트립 MCP 서버(Streamable HTTP, 인증 불필요)의 searchStays를 부르고 결과를 정리한다.
모델 호출 없이 코드로만 처리한다(검증 → 호출 → 정규화). 예약·결제는 하지 않고 예약 링크만 돌려준다."""
import json
from datetime import date
from urllib.parse import urlencode

import requests
from langchain_core.tools import tool
from langsmith import traceable

from weather import now_kst, resolve_future

MCP_URL = "https://mcp-servers.myrealtrip.com/mcp"
SOURCE = "마이리얼트립 MCP (searchStays)"
BOOKING_URL = "https://accommodation.myrealtrip.com/union/products/{gid}"
MAX_STAYS = 5        # 모델과 화면에 넘기는 최대 숙소 수
MAX_NIGHTS = 30
TIMEOUT = (5, 25)    # (연결, 응답) 초


class StaySearchError(Exception):
    """모델에게 그대로 알려도 되는 안전한 문구만 담는다."""


def _rpc(method: str, params: dict) -> dict:
    """JSON-RPC 한 번 호출. 서버가 JSON 또는 SSE(text/event-stream)로 답해도 읽는다."""
    try:
        resp = requests.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={"Accept": "application/json, text/event-stream"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("text/event-stream"):
            data = next((json.loads(l[5:]) for l in resp.text.splitlines() if l.startswith("data:")), None)
        else:
            data = resp.json()
    except (requests.RequestException, ValueError):
        raise StaySearchError("숙소 조회 서비스에 연결하지 못했습니다.") from None
    if not isinstance(data, dict) or "error" in data or "result" not in data:
        raise StaySearchError("숙소 조회 서비스가 요청을 처리하지 못했습니다.")
    return data["result"]


def _validate_dates(check_in: str, check_out: str) -> tuple[str, str, str | None]:
    """날짜를 해석·검증해 (체크인, 체크아웃, 보정 안내)를 돌려준다. 연도가 지난 해로 온 날짜는 올해 기준으로 바로잡는다."""
    d_in, fixed_in = resolve_future(check_in)
    d_out, fixed_out = resolve_future(check_out, floor=d_in, after=True) if d_in else (None, False)
    if d_in is None or d_out is None:
        raise StaySearchError("날짜를 해석할 수 없습니다. YYYY-MM-DD 형식이나 '10월 24일'처럼 알려 달라고 해야 합니다.")
    if d_in < now_kst().date():
        raise StaySearchError("체크인 날짜가 오늘보다 앞섭니다. 날짜를 확인하세요.")
    if d_out <= d_in:
        raise StaySearchError("체크아웃은 체크인보다 뒤여야 합니다.")
    if (d_out - d_in).days > MAX_NIGHTS:
        raise StaySearchError(f"최대 {MAX_NIGHTS}박까지 조회할 수 있습니다.")
    note = (
        f"요청한 날짜의 연도가 지난 해라 {d_in.isoformat()} ~ {d_out.isoformat()}로 해석했다. 사용자에게 이 날짜가 맞는지 알린다."
        if fixed_in or fixed_out else None
    )
    return d_in.isoformat(), d_out.isoformat(), note


def booking_link(gid: int, check_in: str, check_out: str, adults: int, children: int) -> str:
    query = urlencode({"checkIn": check_in, "checkOut": check_out, "adultCount": adults, "childCount": children})
    return f"{BOOKING_URL.format(gid=int(gid))}?{query}"


def _normalize(raw: dict, check_in: str, check_out: str, adults: int, children: int) -> dict | None:
    gid, name = raw.get("gid"), raw.get("name")
    if not isinstance(gid, int) or not name:
        return None
    image = raw.get("thumbnailUrl")
    return {
        "gid": gid,
        "name": name,
        "description": raw.get("description") or "",
        "price": raw.get("price") or "",                    # 예: "150,000원/박"
        "price_with_tax": raw.get("additionalPrice") or "",
        "rating": raw.get("rating"),
        "review_count": str(raw.get("reviewCount") or "").strip("()"),
        "tags": [t for t in raw.get("tags") or [] if isinstance(t, str)],
        "image": image if isinstance(image, str) and image.startswith("https://") else "",
        "booking_link": booking_link(gid, check_in, check_out, adults, children),
    }


@traceable(name="search_stays", run_type="tool")
def search_stays(keyword: str, check_in: str, check_out: str, adults: int = 2, children: int = 0, domestic: bool = True) -> dict:
    """검증 후 searchStays를 호출한다. 반환: {"stays": [...], "source", "queried_at", "params"}"""
    keyword = (keyword or "").strip()
    if not keyword:
        raise StaySearchError("검색할 지역이나 숙소 이름이 필요합니다.")
    check_in, check_out, date_note = _validate_dates(check_in, check_out)
    adults, children = max(1, min(int(adults), 20)), max(0, min(int(children), 20))
    result = _rpc("tools/call", {"name": "searchStays", "arguments": {
        "keyword": keyword, "checkIn": check_in, "checkOut": check_out,
        "adultCount": adults, "childCount": children, "isDomestic": bool(domestic), "size": 10,
    }})
    items = (result.get("structuredContent") or {}).get("stays")
    if result.get("isError") or not isinstance(items, list):
        raise StaySearchError("숙소 조회 결과를 읽지 못했습니다.")
    stays = [s for s in (_normalize(i, check_in, check_out, adults, children) for i in items if isinstance(i, dict)) if s][:MAX_STAYS]
    return {
        "stays": stays, "date_note": date_note, "source": SOURCE, "queried_at": now_kst().isoformat(timespec="seconds"),
        "params": {"keyword": keyword, "check_in": check_in, "check_out": check_out, "adults": adults, "children": children, "domestic": bool(domestic)},
    }


@tool
def find_stays(keyword: str, check_in: str, check_out: str, adults: int = 2, children: int = 0, domestic: bool = True) -> dict:
    """호텔·리조트·펜션 등 숙소를 마이리얼트립에서 조회한다. 반환: 숙소명(name), 설명(description), 1박 가격(price), 평점(rating), 예약 링크(booking_link).
    keyword: 지역 또는 숙소 이름 (예: 제주, 부산 해운대). check_in, check_out: 사용자가 말한 날짜 표현 그대로('10월 24일') 또는 YYYY-MM-DD(연도는 오늘 날짜 기준으로 정하며 짐작하지 않는다). 사용자가 날짜를 말하지 않았으면 호출하지 말고 먼저 물어본다.
    adults: 성인 수(기본 2), children: 아동 수, domestic: 국내면 true, 해외면 false.
    숙소를 묻는 질문에만 호출한다. 예약은 대신하지 않는다."""
    return search_stays(keyword, check_in, check_out, adults, children, domestic)
