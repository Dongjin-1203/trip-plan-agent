"""DB 기반 요청 횟수 제한. 카운터가 DB에 있어서 Cloud Run 인스턴스가 여러 개여도 함께 센다."""
import random
import time
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from api import settings
from api.db import RateCounter, utcnow


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__("rate limited")
        self.retry_after = retry_after


def _hit(db: Session, key: str, window_seconds: int) -> tuple[int, int]:
    """key의 현재 시간 창 카운터를 1 올리고 (현재 횟수, 창이 끝날 때까지 남은 초)를 돌려준다."""
    now = time.time()
    window = int(now // window_seconds)
    retry_after = max(1, int((window + 1) * window_seconds - now))
    insert = postgresql.insert if db.get_bind().dialect.name == "postgresql" else sqlite.insert
    expires = utcnow() + timedelta(seconds=retry_after + 60)
    stmt = (
        insert(RateCounter)
        .values(key=f"{key}:{window}", count=1, expires_at=expires)
        .on_conflict_do_update(index_elements=["key"], set_={"count": RateCounter.__table__.c.count + 1})
        .returning(RateCounter.__table__.c.count)
    )
    count = db.execute(stmt).scalar_one()
    db.commit()
    return count, retry_after


def check(db: Session, client_id: str, ip: str) -> None:
    """요청 한 번을 센다. 한도를 넘으면 RateLimited. 넘은 요청은 이후 단계의 카운터를 올리지 않는다."""
    rules = [
        (f"ip:{ip}:m", 60, settings.IP_RATE_LIMIT_PER_MINUTE),
        (f"c:{client_id}:m", 60, settings.RATE_LIMIT_PER_MINUTE),
        (f"c:{client_id}:d", 86400, settings.RATE_LIMIT_PER_DAY),
    ]
    for key, window_seconds, limit in rules:
        count, retry_after = _hit(db, key, window_seconds)
        if count > limit:
            raise RateLimited(retry_after)
    if random.random() < 0.02:  # 가끔 만료된 카운터를 정리한다
        db.execute(delete(RateCounter).where(RateCounter.expires_at < utcnow()))
        db.commit()
