"use client";

import { useState } from "react";
import type { Food } from "@/lib/types";
import PlaceMap, { type MapPoint } from "./PlaceMap";

export default function FoodTabs({ food, showMap }: { food: Food; showMap: boolean }) {
  const [tab, setTab] = useState(0);
  const days = food.days;
  const day = days[Math.min(tab, days.length - 1)];

  if (food.failed || days.length === 0) {
    return (
      <section className="card">
        <h3>일자별 맛집 추천</h3>
        <p className="muted">맛집을 찾지 못했어요. 잠시 후 다시 시도해 주세요.</p>
        <Notes notes={food.notes} />
      </section>
    );
  }

  const points: MapPoint[] = (day?.meals ?? []).flatMap((m, i) =>
    m.place && m.place.lat != null && m.place.lon != null
      ? [{ lat: m.place.lat, lon: m.place.lon, name: `${m.meal} · ${m.place.name}`, label: String(i + 1) }]
      : [],
  );

  return (
    <section className="card">
      <h3>일자별 맛집 추천</h3>
      <div className="tabs" role="tablist">
        {days.map((d, i) => (
          <button
            key={d.day}
            role="tab"
            aria-selected={i === tab}
            className={`tab ${i === tab ? "on" : ""}`}
            onClick={() => setTab(i)}
          >
            {d.day}일차 <span className="muted small">{d.date.slice(5)} ({d.weekday})</span>
          </button>
        ))}
      </div>
      {day && day.meals.length === 0 && <p className="muted">이 날은 먹을 끼니가 없어요.</p>}
      <div className="place-grid">
        {day?.meals.map((m, i) => (
          <article key={`${day.day}-${m.meal}-${i}`} className="place">
            <div className="place-no">{i + 1}</div>
            <div className="place-body">
              <div className="muted small">
                {m.meal}
                {m.anchor ? ` · ${m.anchor}` : ""}
              </div>
              {m.place ? (
                <>
                  <strong>{m.place.name}</strong>
                  <div className="small muted">
                    {[m.place.category, m.place.distance_m != null ? `${m.place.distance_m}m` : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                  {m.place.address && <div className="small muted">{m.place.address}</div>}
                  {m.place.map_link && (
                    <a className="btn btn-pill" href={m.place.map_link} target="_blank" rel="noopener noreferrer">
                      지도에서 보기
                    </a>
                  )}
                </>
              ) : (
                <p className="muted">추천할 맛집을 찾지 못했어요.</p>
              )}
            </div>
          </article>
        ))}
      </div>
      {showMap && <PlaceMap points={points} />}
      <Notes notes={food.notes} />
    </section>
  );
}

function Notes({ notes }: { notes: string[] }) {
  if (!notes?.length) return null;
  return (
    <ul className="notes muted small">
      {notes.map((n, i) => (
        <li key={i}>{n}</li>
      ))}
    </ul>
  );
}
