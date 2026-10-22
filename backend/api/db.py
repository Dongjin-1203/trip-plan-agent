"""DB 연결과 테이블. 운영은 Cloud SQL(PostgreSQL), 로컬·테스트는 SQLite를 같은 코드로 쓴다."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from api import settings


def utcnow() -> datetime:
    """시간대 없는 UTC 시각. 모든 시각을 이 형식으로 저장·비교한다(SQLite와 PostgreSQL에서 같게 동작)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    """대화 세션. 모든 조회는 client_id(익명 ID)로 거른다."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ChatMessage(Base):
    """메시지 한 개. payload는 API 계약(docs/API.md)의 메시지에 내부용 facts를 더한 JSON이다."""

    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("session_id", "idx", name="uq_message_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class RateCounter(Base):
    """요청 횟수 카운터. 키에 시간 창이 들어 있어 창이 지나면 새 행이 쓰인다."""

    __tablename__ = "rate_counters"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},  # FastAPI는 요청을 스레드풀에서 처리한다
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    """테이블이 없으면 만든다. (스키마를 바꿀 때가 오면 Alembic 마이그레이션으로 옮긴다.)"""
    Base.metadata.create_all(engine)
