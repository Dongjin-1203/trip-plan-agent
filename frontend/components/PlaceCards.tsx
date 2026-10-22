import type { CardPlace } from "@/lib/places";

export default function PlaceCards({ places }: { places: CardPlace[] }) {
  return (
    <div className="place-cards">
      {places.map((p) => (
        <article key={`${p.no}-${p.name}`} className="place place-card">
          <div className="place-no">{p.no}</div>
          <div className="place-body">
            <strong>{p.name}</strong>
            {p.address && <div className="small muted">{p.address}</div>}
            {p.map_link && (
              <a
                className="btn btn-pill"
                href={p.map_link}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`지도에서 ${p.name} 열기 (새 탭)`}
              >
                지도 열기 <span aria-hidden>↗</span>
              </a>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
