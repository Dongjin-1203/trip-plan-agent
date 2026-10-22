import type { Draft } from "@/lib/types";
import PlaceMap from "./PlaceMap";

export default function DraftCard({ draft, showMap }: { draft: Draft; showMap: boolean }) {
  const { cond } = draft;
  const title = [cond.region, cond.date, cond.preference].filter(Boolean).join(" · ");
  const points = draft.places.flatMap((p, i) =>
    p.lat != null && p.lon != null ? [{ lat: p.lat, lon: p.lon, name: p.name, label: String(i + 1) }] : [],
  );
  return (
    <section className="card">
      <h3>🗺️ 여행 계획 초안{title ? ` — ${title}` : ""}</h3>
      {draft.warnings.map((w, i) => (
        <p key={i} className="warn">⚠️ {w}</p>
      ))}
      <div className="place-grid">
        {draft.places.map((p, i) => (
          <article key={`${p.name}-${i}`} className="place">
            <div className="place-no">{i + 1}</div>
            <div className="place-body">
              <div className="muted small">{draft.time_slots[i] ?? ""}</div>
              <strong>{p.name}</strong>
              {p.address && <div className="small muted">{p.address}</div>}
              {p.map_link && (
                <a className="btn btn-pill" href={p.map_link} target="_blank" rel="noopener noreferrer">
                  지도에서 보기
                </a>
              )}
            </div>
          </article>
        ))}
        {draft.places.length === 0 && <p className="muted">추천할 장소가 없어요.</p>}
      </div>
      <p className="muted small">시간대는 제안일 뿐이며, 영업시간은 방문 전에 직접 확인해 주세요.</p>
      {showMap && <PlaceMap points={points} />}
      <div className="packing">
        <h4>🎒 준비물</h4>
        {draft.packing.length ? (
          <ul>
            {draft.packing.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">날씨 예보를 확인하지 못해 준비물을 제안하지 않았어요. 출발 전에 예보를 확인해 주세요.</p>
        )}
        {draft.weather_source && <p className="muted small">날씨 출처: {draft.weather_source}</p>}
      </div>
    </section>
  );
}
