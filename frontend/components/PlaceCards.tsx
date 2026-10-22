import type { CardPlace } from "@/lib/places";
import type { PlaceInfo } from "@/lib/types";

const DAYS: [string, string][] = [
  ["mon", "월"], ["tue", "화"], ["wed", "수"], ["thu", "목"], ["fri", "금"], ["sat", "토"], ["sun", "일"],
];

function hoursText(v: string | null | undefined): string {
  return v === "closed" ? "휴무" : v === "24h" ? "24시간" : v || "확인 필요";
}

// 웹 검색으로 확인한 운영시간·메뉴. 값이 없으면 "확인 필요"로 두고 만들어 내지 않는다.
function InfoBlock({ info }: { info: PlaceInfo }) {
  if (info.status !== "found") {
    return <div className="small muted pinfo">운영시간·메뉴는 확인하지 못했어요. 방문 전에 확인해 주세요.</div>;
  }
  const dated = Object.entries(info.by_date ?? {});
  const source = info.sources?.[0];
  return (
    <div className="small pinfo">
      {dated.map(([d, state]) => (
        <div key={d} className={state === "휴무" ? "closed" : undefined}>
          {d} · {state}
        </div>
      ))}
      {info.weekly_hours && (
        <details>
          <summary>요일별 운영시간</summary>
          <ul>
            {DAYS.map(([k, ko]) => (
              <li key={k}>{ko} {hoursText(info.weekly_hours?.[k])}</li>
            ))}
          </ul>
        </details>
      )}
      {info.closed_note && <div className="muted">{info.closed_note}</div>}
      {info.menu && info.menu.length > 0 && (
        <div>메뉴: {info.menu.map((m) => (m.price ? `${m.name} ${m.price}` : m.name)).join(" · ")}</div>
      )}
      <div className="muted">
        웹 검색 기준 · 공휴일·임시 휴업은 방문 전 확인
        {source && (
          <>
            {" · "}
            <a href={source.url} target="_blank" rel="noopener noreferrer">출처</a>
          </>
        )}
      </div>
    </div>
  );
}

export default function PlaceCards({ places, infos }: { places: CardPlace[]; infos?: Record<string, PlaceInfo> }) {
  return (
    <div className="place-cards">
      {places.map((p) => (
        <article key={`${p.no}-${p.name}`} className="place place-card">
          <div className="place-no">{p.no}</div>
          <div className="place-body">
            <strong>{p.name}</strong>
            {p.address && <div className="small muted">{p.address}</div>}
            {infos?.[p.name] && <InfoBlock info={infos[p.name]} />}
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
