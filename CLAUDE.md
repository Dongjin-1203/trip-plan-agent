# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

한국어로 답한다. 여행 챗봇 v2: FastAPI 백엔드 + Next.js 15 웹, GCP Cloud Run에 배포되어 있다.

## 명령어

환경은 Windows다. bash 스크립트(`infra/*.sh`)는 Git Bash(`C:\Program Files\Git\bin\bash.exe`)로 실행한다. PowerShell의 `bash`는 깨진 WSL로 연결된다.

백엔드 (`backend/`에서):
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
cp .env.example .env                                  # DATABASE_URL을 비우면 local.db(SQLite)
.venv/Scripts/uvicorn api.main:app --reload --port 8000
.venv/Scripts/python -m pytest                        # 전체 (pytest.ini: testpaths=tests, -q)
.venv/Scripts/python -m pytest tests/test_api.py::test_rate_limit_per_ip   # 단일 테스트
```

프론트엔드 (`frontend/`에서, Node 20+):
```bash
cp .env.example .env.local     # BACKEND_URL=http://localhost:8000
npm install
npm run dev                    # http://localhost:3000
npm run mock                   # 백엔드 대신 docs/API.md를 따르는 목 서버 (mock/server.mjs)
npm run build                  # 타입 검사 포함. 별도 lint/test 스크립트는 없다
```
목 서버 키워드: `날씨`(초안 제안), `네, 작성해`(초안), `오류`(실패 → 다시 시도), `429`(요청 제한).

## 아키텍처

요청 흐름: 브라우저 → Next.js `middleware.ts` → BFF `app/api/[...path]/route.ts` → FastAPI(`backend/api/main.py`) → `chatbot.ask_events`.

- **익명 사용자 ID**: `middleware.ts`가 httpOnly 쿠키 `cid`를 발급하고, 요청에 실려 온 `x-client-id`를 항상 쿠키 값으로 덮어쓴다. BFF는 이 값만 `X-Client-Id`로 백엔드에 넘긴다. 백엔드는 모든 세션·메시지를 client id로 격리하고, 남의 세션과 없는 세션을 똑같이 404로 처리한다.
- **BFF**: 허용 경로 정규식(`ALLOWED`)에 맞는 `/api/*`만 프록시한다. 백엔드가 localhost가 아니면 메타데이터 서버에서 ID 토큰을 받아(`lib/idtoken.ts`) `Authorization: Bearer`를 붙인다. SSE 본문은 그대로 스트리밍한다. 새 엔드포인트를 추가하면 `ALLOWED`도 고쳐야 한다.
- **채팅 SSE**: `POST /api/chat`은 이벤트 `session` → `status`/`token`* → `final` 또는 `error` 순으로 보낸다. 성공·실패 모두 DB에 저장하고, 실패한 턴은 `error: true`로 남겨 `retry: true` 요청 때 `store.drop_trailing_error`로 지운 뒤 다시 실행한다. 실패한 턴은 모델 history에서 제외한다.
- **에이전트(`backend/chatbot.py`)**: LangChain `ChatOpenAI` + 도구(`search_places`=카카오 로컬, `get_weather`). 이벤트를 yield하는 제너레이터다. 대화 상태는 마지막 assistant 메시지의 `facts`(조회한 장소·날씨)와 `offer`(`"draft"`/`"food"`/False)로 다음 턴에 이어진다.
  - `offer == "draft"`일 때만 `draft_travel_plan` 도구를 모델에 노출하고, 실제 초안은 코드(`plan.draft_from_facts`)가 만든다.
  - 맛집 추천은 모델 도구가 아니다. 화면 폼의 `food_request`를 받아 `meals.plan_food`가 끼니를 계산하고 반경 검색한다.
  - `run_trace.build_trace`가 화면의 실행 기록(TracePanel)용 trace를 만든다. `ChatbotError` 메시지만 사용자에게 그대로 보이고, 그 외 예외는 고정 문구로 바꾼다.
- **도메인 모듈**(chatbot, tools, weather, plan, meals, run_trace, config)은 Streamlit 버전에서 가져온 것으로, `api/`가 HTTP·DB 계층이다(`db` 모델, `store` CRUD, `ratelimit`은 DB 카운터 기반, `serialize.public_message`가 내부 필드를 걸러 응답을 만든다).
- **테스트**: `tests/conftest.py`가 임시 SQLite와 트레이싱 끄기를 설정하고, `fake_ask` 픽스처가 `main.ask_events`를 `FakeAsk`로 바꾼다. 모델·카카오 호출 없이 API 계층만 검사한다.
- **API 계약**: `docs/API.md`. 계약(엔드포인트, SSE 이벤트, 오류 형식)을 바꾸면 이 문서와 `frontend/mock/server.mjs`, `frontend/lib/types.ts`도 같이 고친다.

## 배포 (GCP)

- 프로젝트 `trip-plan-agent`, 리전 `asia-northeast3`. 이름이 같은 미사용 프로젝트 `trip-plan-agent-512405`와 혼동한 적이 있으니 gcloud 명령에는 항상 `--project trip-plan-agent`를 붙인다.
- main에 push하면 Cloud Build 트리거가 자동 배포한다: `backend/**` → `infra/cloudbuild.backend.yaml`(pytest → 빌드 → `travel-api`), `frontend/**` → `infra/cloudbuild.frontend.yaml`(`travel-web`). 요청 제한·max-instances 값은 yaml의 substitutions에 있다.
- `travel-api`는 비공개(웹 서비스 계정 `travel-web-sa`만 `run.invoker`), `travel-web`은 공개. DB는 Cloud SQL PostgreSQL(`travel-db`), 유닉스 소켓 연결. 시크릿은 Secret Manager에 있으며 값을 채팅이나 파일에 쓰지 않는다.
- 초기 설정은 `infra/setup-gcp.sh`(멱등)와 `infra/setup-gcp.md` 참고.

## 함정

- Cloud Run이 `/healthz`를 가로채 404를 준다. 배포 확인·헬스체크는 `/readyz`(DB 확인 포함)를 쓴다.
- 접속자 IP는 X-Forwarded-For의 **마지막** 항목을 쓴다(앞 항목은 위조 가능). 백엔드는 `TRUST_CLIENT_IP_HEADER=true`일 때만 `X-Client-Ip`를 믿는다.
- SQLAlchemy는 `>=2.0,<2.1`로 고정한다. 2.1의 네이티브 확장이 이 PC의 Windows 앱 제어 정책에 막힌다. 보안 설정은 바꾸지 않는다.
- 테이블은 시작 시 `init_db()`로 자동 생성된다. 마이그레이션 도구가 없으므로 스키마 변경 시 주의한다.
- 모든 파일은 LF(`.gitattributes`로 강제). Git Bash에서 `git show origin/main:path`는 `MSYS_NO_PATHCONV=1`이 필요하고, gcloud 출력 줄 끝의 `\r`은 `tr -d '\r'`로 지운다.
- Cloud SQL은 요청이 없어도 과금된다. push, 리소스 삭제, 결제 관련 작업은 먼저 사용자에게 확인받는다.
