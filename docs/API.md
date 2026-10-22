# 여행 챗봇 백엔드 API 계약 (v1)

프론트엔드(Next.js BFF)와 백엔드(FastAPI)가 맞추는 계약입니다. 백엔드 구현이 이 문서와 달라지면 **이 문서를 먼저 고칩니다.**

## 공통

| 항목 | 내용 |
|---|---|
| 기본 주소 | 로컬 `http://localhost:8000`, 운영은 비공개 Cloud Run 주소(웹 서버만 호출) |
| 인코딩 | JSON은 UTF-8 |
| 인증(운영) | `Authorization: Bearer <Google ID 토큰>` — Cloud Run IAM이 검사합니다. 로컬은 필요 없음 |
| 사용자 구분 | **`X-Client-Id`** 필수. 브라우저별 익명 ID(영문·숫자·`-`, 16~64자). 모든 세션·메시지는 이 ID에 속하며, 다른 ID로는 보이지 않습니다. |
| 접속자 IP | `X-Client-Ip`(선택). 웹 서버가 실제 접속자 IP를 전달합니다. 백엔드가 `TRUST_CLIENT_IP_HEADER=true`일 때만 신뢰합니다. |
| 요청 제한 | `POST /api/chat`에만 적용(사용자별 분당·일일, IP별 분당). 초과 시 429 |

### 오류 응답
JSON `{"detail": "사람이 읽는 문구"}` 형식입니다. 키·내부 정보는 포함하지 않습니다.

| 상태 | 의미 |
|---|---|
| 400 | `X-Client-Id`가 없거나 형식이 틀림 |
| 404 | 세션이 없거나 **다른 사용자의 세션** (구분하지 않음) |
| 422 | 요청 본문 검증 실패(메시지 비어 있음·500자 초과, 잘못된 날짜·시간 형식, 일수 범위) |
| 429 | 요청 제한 초과. `Retry-After`(초) 헤더와 `{"detail": "...", "retry_after": 초}` |

## 엔드포인트

### `GET /healthz`
인증·DB 없이 `{"status": "ok"}`. 컨테이너 상태 확인용.

### `GET /readyz`
DB 연결까지 확인. 실패 시 503.

### `GET /api/sessions`
내 세션 목록(최근 수정 순, 최대 50개).
```json
[{"id": "a1b2c3d4e5f6", "title": "경주 실내 관광지 추천해줘", "updated_at": "2026-10-22T05:30:12Z"}]
```

### `GET /api/sessions/{id}`
세션과 전체 메시지(저장된 순서). 메시지 모양은 아래 "메시지" 참고.
```json
{"id": "a1b2c3d4e5f6", "title": "…", "updated_at": "…", "messages": [ /* UserMessage | AssistantMessage */ ]}
```

### `DELETE /api/sessions/{id}`
세션 삭제. `204`.

### `POST /api/sessions/{id}/offer/dismiss`
마지막 어시스턴트 메시지의 제안(`offer`)을 닫음(맛집 폼의 "다음에"). 모델 호출 없음. `204`.

### `POST /api/chat`  → `text/event-stream` (SSE)
요청 본문:
```json
{
  "session_id": null,
  "message": "경주 실내 관광지 추천해줘",
  "food_request": null,
  "retry": false
}
```
| 필드 | 설명 |
|---|---|
| `session_id` | 없으면 새 세션을 만들고 첫 이벤트로 알려줍니다. |
| `message` | 사용자가 보낸 문장(1~500자). 맛집 폼 제출이면 화면에 보일 문장(예: `맛집 추천: 2026-10-24부터 3일 · 출발 10:00 · 귀가 18:00`). |
| `food_request` | 맛집 폼 제출 값. 있으면 모델 없이 끼니를 계산해 맛집을 추천합니다. `{"start_date":"YYYY-MM-DD","days":1~14,"departure":"HH:MM","return_time":"HH:MM"}` |
| `retry` | `true`면 직전에 실패해 저장된 질문·오류 쌍을 지우고 같은 요청을 다시 처리합니다. 이때 `message`에 같은 질문을 보냅니다. |

#### SSE 이벤트
각 이벤트는 `event: <이름>` + `data: <JSON>` 형식이고 빈 줄로 끝납니다. 순서는 `session` → (`status` | `token`)* → `final` 또는 `error` 입니다.

| 이벤트 | data | 설명 |
|---|---|---|
| `session` | `{"id": "…", "title": "…"}` | 항상 첫 이벤트 |
| `status` | `{"label": "🔎 장소 검색 중: 서울 성수동 카페", "line": "…"}` | 진행 상황. `label`은 상태줄에, `line`(비어 있을 수 있음)은 상세 로그에 |
| `token` | `{"text": "서울 "}` | 답변 글자 조각을 이어 붙입니다. 초안·맛집 추천은 토큰 없이 `final`만 옵니다. |
| `final` | `{"message": AssistantMessage}` | 정상 종료. 이 메시지가 저장된 최종본입니다. |
| `error` | `{"message": "…", "retryable": true}` | 실패 종료. 실패한 턴이 저장되어 있고, `retry:true`로 다시 보낼 수 있습니다. |

연결이 중간에 끊기면 그 턴은 저장되지 않습니다.

## 메시지

### UserMessage
```json
{"role": "user", "content": "경주 실내 관광지 추천해줘", "error": false}
```
`error`는 실패한 턴의 질문일 때만 `true`.

### AssistantMessage
```json
{
  "role": "assistant",
  "content": "마크다운 답변 전문",
  "question": "경주 실내 관광지 추천해줘",
  "trace": { "...": "아래 Trace" },
  "offer": false,
  "offer_defaults": { "start_date": "2026-10-24" },
  "draft": null,
  "food": null,
  "error": false
}
```
| 필드 | 설명 |
|---|---|
| `content` | 답변 텍스트(마크다운). `draft`/`food`가 있으면 화면은 이 필드 대신 구조화 데이터로 그립니다. 대화 기억·복사용 |
| `offer` | `false` \| `"draft"`(초안 작성 제안) \| `"food"`(맛집 입력 폼). 마지막 메시지일 때만 의미가 있습니다. |
| `offer_defaults` | `offer == "food"`일 때 폼 기본값. `start_date`(조회한 날씨 날짜) |
| `draft` | 초안(아래 Draft). 없으면 `null` |
| `food` | 일자별 맛집 추천(아래 Food). 없으면 `null` |
| `error` | `true`면 `content`는 오류 문구이고 `trace`가 없습니다. 마지막 메시지일 때 "다시 시도" 버튼을 보여줍니다. |

#### Trace (실행 기록, `error`가 아닐 때만)
```json
{
  "steps": [
    {"step": 1, "tool": "search_places", "args": {"region": "경주", "category": "실내 관광지"},
     "status": "success", "note": "첫 검색", "count": 5,
     "places": [{"name": "…", "address": "…", "map_link": "http://place.map.kakao.com/…"}]},
    {"step": 2, "tool": "get_weather", "args": {"region": "경주", "date": "3일 뒤"}, "status": "ok",
     "note": "날씨 조회", "source": "Open-Meteo (…)", "queried_at": "2026-10-22T14:00:00+09:00",
     "result": {"status": "ok", "date": "2026-10-25", "weekday": "일", "temp_max": 19.4, "temp_min": 16.0, "precip_prob": 92}}
  ],
  "tool_calls": 2, "tool_limit": 4, "model_calls": 3, "model_limit": 6,
  "end": "날씨 조회 후 답했다", "grounded": true
}
```
숙소 조회 단계(`tool: "find_stays"`)는 `args`(`keyword`, `check_in`, `check_out`, `adults`, `children`, `domestic`), `source`, `queried_at`, `count`와 함께 `stays`를 가집니다. `price`·`price_with_tax`는 조회 시점의 안내 문구(예: `"150,000원/박"`)이며 비어 있을 수 있고, `booking_link`는 마이리얼트립 예약 페이지입니다(예약·결제는 하지 않음). `image`는 https 주소이거나 빈 문자열입니다.
```json
{"step": 1, "tool": "find_stays", "args": {"keyword": "제주", "check_in": "2026-11-14", "check_out": "2026-11-16", "adults": 2, "children": 0, "domestic": true},
 "status": "success", "note": "숙소 조회 — …", "count": 2, "source": "마이리얼트립 MCP (searchStays)", "queried_at": "2026-10-22T14:00:00+09:00",
 "stays": [{"gid": 2680814, "name": "…", "description": "4성급 · 리조트 · 평창", "price": "150,000원/박", "price_with_tax": "세금포함 165,000원/박",
            "rating": 4.2, "review_count": "2,775", "tags": ["무료취소"], "image": "https://…", "booking_link": "https://accommodation.myrealtrip.com/union/products/2680814?checkIn=…"}]}
```

`status` 값 예: `success`, `ok`, `error`, `auth_error`, `skipped`, `out_of_range`, `partial`. `grounded: false`면 "답변과 조회 결과가 일치하지 않음" 경고를 보여줍니다. 도구마다 추가 필드(`warnings`, `checks` 등)가 있을 수 있으므로 **모르는 필드는 무시**합니다.

#### Draft (여행 계획 초안)
```json
{
  "cond": {"region": "경주", "date": "2026-10-25", "preference": "실내 관광지"},
  "warnings": [],
  "places": [{"name": "…", "address": "…", "map_link": "…", "lat": 35.85, "lon": 129.27}],
  "weather_source": "Open-Meteo (https://open-meteo.com, CC-BY 4.0)",
  "weather_state": "ok",
  "packing": ["날씨에 따라 우산 · 방수 신발을 준비해주세요! (비 올 가능성이 높아요)"],
  "time_slots": ["오전", "점심 무렵", "오후", "늦은 오후"]
}
```
- 날씨 수치는 **포함하지 않습니다**(준비물 문장에만 반영). `weather_state`가 `ok`가 아니면 `packing`이 비어 있고 "예보 없음/날씨 확인 필요"를 안내합니다.
- `places[i]`의 시간대는 `time_slots[i]`(제안일 뿐 조회한 사실이 아님). `lat`/`lon`은 지도에 표시합니다.
- 출처 표기: `weather_source`(Open-Meteo CC-BY 4.0)를 준비물 근처에 표시해야 합니다.

#### Food (일자별 맛집 추천)
```json
{
  "request": {"start_date": "2026-10-24", "days": 3, "departure": "10:00", "return_time": "19:00"},
  "days": [
    {"day": 1, "date": "2026-10-24", "weekday": "토", "meals": [
      {"meal": "점심", "anchor": "경주황룡사역사문화관 근처",
       "place": {"id": "…", "name": "…", "address": "…", "map_link": "…", "category": "한식", "distance_m": 233, "lat": 35.83, "lon": 129.22}}
    ]}
  ],
  "total_meals": 8, "picked": [ /* place 목록 */ ], "failed": false,
  "notes": ["끼니 기준 시각: …", "숙소와 일자별 방문지는 …", "아침은 영업시간을 알 수 없어 …"]
}
```
- `place`가 `null`이면 "추천할 맛집을 찾지 못했어요".
- `days[].meals`가 비어 있으면 그 날은 먹을 끼니가 없습니다.
- 모든 `notes`를 결과 아래에 표시합니다(가정과 한계 안내).

## 화면이 지켜야 할 규칙
1. `final` 이전의 `token`은 임시 표시이고, `final.message`로 교체합니다.
2. `offer == "food"`인 마지막 메시지 아래에 안내 문구와 폼을 보여주고, 제출하면 `food_request`를 포함해 `POST /api/chat`을 호출합니다. "다음에"는 `offer/dismiss`를 호출합니다.
3. `offer == "draft"`인 마지막 메시지 아래에는 `✅ 초안 작성하기`(= 메시지 `"네, 작성해 주세요"`)와 `다음에`(= `"아니요, 괜찮아요"`) 버튼을 보여줍니다.
4. 지도는 **가장 최근의 초안 / 맛집 추천 메시지에만** 그립니다.
5. 429는 `retry_after`초 뒤 다시 시도하라고 안내합니다.
6. 영업시간·평점·가격은 이 API가 제공하지 않으므로 화면에서 지어내지 않습니다.
