# 여행 챗봇 백엔드

FastAPI로 챗봇 로직을 감싼 API 서버입니다. 대화는 DB(로컬 SQLite, 운영 Cloud SQL PostgreSQL)에 사용자별로 저장됩니다.
API 계약은 [`../docs/API.md`](../docs/API.md)를 따릅니다.

## 구조
```
chatbot.py tools.py weather.py plan.py meals.py run_trace.py config.py   챗봇 도메인 로직 (Streamlit 버전에서 가져옴)
api/        settings.py db.py store.py ratelimit.py schemas.py serialize.py main.py   HTTP API·저장소
tests/      pytest (모델·카카오 호출 없이 동작)
```

## 로컬 실행
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt      # macOS/Linux: .venv/bin/pip
cp .env.example .env                                   # 키를 채운다
.venv/Scripts/uvicorn api.main:app --reload --port 8000
```
- `DATABASE_URL`을 비워 두면 `local.db`(SQLite)를 씁니다.
- 확인: `curl http://localhost:8000/healthz`
- 대화 호출 예(스트리밍): 
  ```bash
  curl -N -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" -H "X-Client-Id: 11111111-2222-3333-4444-555555555555" \
    -d '{"message":"경주 실내 관광지 추천해줘"}'
  ```

## 테스트
```bash
.venv/Scripts/python -m pytest
```
사용자 격리, SSE 순서, 실패·재시도, 제안 닫기, 요청 제한, 입력 검증을 확인합니다.

## 환경변수
| 이름 | 설명 |
|---|---|
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `KAKAO_REST_API_KEY` | 외부 서비스 키 |
| `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | 트레이싱(선택). 키가 있으면 자동으로 켜지고 `LANGSMITH_TRACING=false`로 끔 |
| `DATABASE_URL` | 운영: `postgresql+psycopg://사용자:비밀번호@/DB?host=/cloudsql/프로젝트:리전:인스턴스` |
| `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_DAY`, `IP_RATE_LIMIT_PER_MINUTE` | 요청 제한 |
| `PLACE_INFO_ENABLED`, `WEB_SEARCH_MODEL` | 장소 정보(웹검색) 기능. 기본 켜짐, `false`로 끔. 모델은 기본으로 `OPENAI_MODEL`을 쓰고 웹검색 도구를 지원하는 모델이어야 함 |
| `TRUST_CLIENT_IP_HEADER` | 웹 서버(BFF)가 보낸 `X-Client-Ip`를 믿을지. 백엔드가 비공개일 때만 `true` |

## 참고
- Windows에서 새로 설치한 네이티브 확장(`.pyd`)이 "애플리케이션 제어 정책"에 막히는 환경이 있어, SQLAlchemy는 확장이 선택 사항인 `2.0.x`로 고정했습니다(`requirements.txt`). 컨테이너(Linux)에서는 영향이 없습니다.
- 테이블은 시작할 때 자동 생성됩니다. 스키마를 바꿔야 할 때가 오면 Alembic 마이그레이션을 도입하세요.
