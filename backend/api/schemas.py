"""요청 본문 검증 (docs/API.md의 POST /api/chat)."""
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from api import settings
from meals import MAX_DAYS

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class FoodRequest(BaseModel):
    start_date: date
    days: int = Field(ge=1, le=MAX_DAYS)
    departure: str = Field(pattern=HHMM)
    return_time: str = Field(pattern=HHMM)

    def to_dict(self) -> dict:
        return {
            "start_date": self.start_date.isoformat(), "days": self.days,
            "departure": self.departure, "return_time": self.return_time,
        }


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    message: str = Field(min_length=1, max_length=settings.MAX_MESSAGE_CHARS)
    food_request: FoodRequest | None = None
    retry: bool = False
    regenerate: bool = False

    @model_validator(mode="after")
    def regenerate_rules(self):
        if self.regenerate and (self.retry or not self.session_id):
            raise ValueError("regenerate는 기존 대화에서 retry 없이만 쓸 수 있습니다.")
        return self

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("메시지가 비어 있습니다.")
        return v
