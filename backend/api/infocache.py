"""장소 정보(웹검색) 캐시. 검색은 장소마다 비용이 들어서 DB에 두고 인스턴스끼리 함께 쓴다. place_info.set_cache로 연결한다."""
from datetime import timedelta

from api.db import PlaceInfoCache, SessionLocal, utcnow


def get(key: str) -> dict | None:
    with SessionLocal() as db:
        row = db.get(PlaceInfoCache, key)
        return dict(row.payload) if row and row.expires_at > utcnow() else None


def put(key: str, payload: dict, days: int) -> None:
    with SessionLocal() as db:
        db.merge(PlaceInfoCache(key=key, payload=payload, expires_at=utcnow() + timedelta(days=days)))
        db.commit()
