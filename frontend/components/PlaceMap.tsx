"use client";

import dynamic from "next/dynamic";
import type { MapPoint } from "./MapView";

// Leaflet은 window 가 필요해서 서버 렌더링에서 제외한다.
const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="map-box map-loading">지도를 불러오는 중…</div>,
});

export type { MapPoint };

export default function PlaceMap({ points }: { points: MapPoint[] }) {
  const valid = points.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon));
  if (!valid.length) return null;
  return <MapView points={valid} />;
}
