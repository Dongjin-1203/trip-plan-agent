"use client";

import { useEffect } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

export type MapPoint = { lat: number; lon: number; name: string; label: string };

function pin(label: string) {
  // 기본 마커 이미지는 번들러에서 깨지므로 CSS 아이콘을 쓴다.
  return L.divIcon({
    className: "map-pin-wrap",
    html: `<span class="map-pin">${label}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -14],
  });
}

function Fit({ points }: { points: MapPoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 1) map.setView([points[0].lat, points[0].lon], 15);
    else if (points.length > 1)
      map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lon] as [number, number])), {
        padding: [30, 30],
        maxZoom: 16,
      });
  }, [map, points]);
  return null;
}

export default function MapView({ points }: { points: MapPoint[] }) {
  if (!points.length) return null;
  return (
    <div className="map-box" role="region" aria-label="지도">
      <MapContainer
        center={[points[0].lat, points[0].lon]}
        zoom={14}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        <Fit points={points} />
        {points.map((p, i) => (
          <Marker key={`${p.name}-${i}`} position={[p.lat, p.lon]} icon={pin(p.label)}>
            <Popup>{p.name}</Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
