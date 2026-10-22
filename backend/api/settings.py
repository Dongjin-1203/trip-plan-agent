"""API 서버 설정. 모두 환경변수로 바꿀 수 있고, 로컬은 backend/.env, Cloud Run은 환경변수·Secret Manager로 넣는다."""
import os

import config  # noqa: F401  (.env를 먼저 불러온다)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# 운영(Cloud SQL): postgresql+psycopg://사용자:비밀번호@/DB이름?host=/cloudsql/프로젝트:리전:인스턴스
# 로컬 개발·테스트: SQLite 파일
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite:///./local.db"

# 브라우저가 백엔드를 직접 부를 때 허용할 웹 주소(쉼표로 구분). 웹 서버가 대신 호출하면(BFF) 필요 없다.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# 요청 횟수 제한: 사용자(익명 ID)별 분당·일일, 접속 IP별 분당. 내 OpenAI·카카오 키 사용량 폭주를 막는다.
RATE_LIMIT_PER_MINUTE = _int("RATE_LIMIT_PER_MINUTE", 8)
RATE_LIMIT_PER_DAY = _int("RATE_LIMIT_PER_DAY", 150)
IP_RATE_LIMIT_PER_MINUTE = _int("IP_RATE_LIMIT_PER_MINUTE", 30)

# 웹 서버(BFF)가 전달한 실제 접속자 IP 헤더(X-Client-Ip)를 믿을지. 백엔드를 비공개로 잠그고 웹 서버만 호출할 때만 켠다.
TRUST_CLIENT_IP_HEADER = os.getenv("TRUST_CLIENT_IP_HEADER", "").strip().lower() in ("1", "true", "yes")

MAX_MESSAGE_CHARS = _int("MAX_MESSAGE_CHARS", 500)
MAX_SESSIONS_PER_CLIENT = _int("MAX_SESSIONS_PER_CLIENT", 50)
