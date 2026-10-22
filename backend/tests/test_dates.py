from datetime import date

import pytest

import weather

TODAY = date(2026, 10, 22)


@pytest.mark.parametrize("text,expected,fixed", [
    ("2023-10-24", date(2026, 10, 24), True),     # 이번 버그: 모델이 지난 해(2023)를 넣음
    ("2023-10-20", date(2027, 10, 20), True),     # 올해 안에서는 이미 지난 날이라 가장 가까운 내년 날짜
    ("2026-10-24", date(2026, 10, 24), False),
    ("2026-10-20", date(2026, 10, 20), False),    # 올해 안의 지난 날짜는 그대로 둔다(호출하는 쪽이 거부)
    ("10월 24일", date(2026, 10, 24), False),
    ("10월 20일", date(2027, 10, 20), False),     # 연도 없는 지난 날짜는 resolve_date가 내년으로 본다
    ("내일", date(2026, 10, 23), False),
    ("2024-02-29", date(2027, 2, 28), True),      # 2월 29일이 없는 해
])
def test_resolve_future(text, expected, fixed):
    assert weather.resolve_future(text, today=TODAY) == (expected, fixed)


def test_checkout_floor_uses_the_checkin_year():
    floor = date(2026, 10, 24)
    assert weather.resolve_future("2023-10-26", floor=floor, after=True, today=TODAY) == (date(2026, 10, 26), True)
    assert weather.resolve_future("2023-10-24", floor=floor, after=True, today=TODAY) == (date(2027, 10, 24), True)  # 당일은 지난 것으로 본다


def test_unreadable_text_is_none():
    assert weather.resolve_future("언젠가", today=TODAY) == (None, False)
    assert weather.resolve_future("", today=TODAY) == (None, False)
