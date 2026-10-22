"""장소 정보(웹검색) 실호출 점검. OPENAI_API_KEY가 backend/.env에 있어야 한다. 요청 한 번마다 OpenAI 웹검색 비용이 든다.

    cd backend
    .venv/Scripts/python scripts/smoke_place_info.py 국립경주박물관 첨성대
    .venv/Scripts/python scripts/smoke_place_info.py --restaurant "교동쌈밥"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import place_info  # noqa: E402

args = sys.argv[1:]
kind = "restaurant" if "--restaurant" in args else "attraction"
names = [a for a in args if not a.startswith("--")]
if not names:
    sys.exit(__doc__)

out = place_info.lookup_places_info([{"name": n, "address": ""} for n in names], kind, [])
for r in out["results"]:
    print(json.dumps({k: r.get(k) for k in ("name", "status", "weekly_hours", "closed_note", "menu", "notes", "sources")}, ensure_ascii=False, indent=2))
print("조회 시각:", out["queried_at"], "| 모델:", place_info._model())
