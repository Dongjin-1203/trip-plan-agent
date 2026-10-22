import type { AssistantMessage, PlaceInfo, TracePlace, TraceStay } from "./types";

export type CardPlace = TracePlace & { no: number };

// 답변 본문에 이름이 나온 조회 결과만 카드로 만든다(본문 등장 순서). 본문과 맞는 장소가 없으면 빈 배열 → 텍스트 폴백.
export function placesFromMessage(msg: AssistantMessage): CardPlace[] {
  if (msg.error || msg.draft || msg.food) return [];
  const seen = new Set<string>();
  const found: { place: TracePlace; at: number }[] = [];
  for (const step of msg.trace?.steps ?? []) {
    for (const place of step.places ?? []) {
      if (!place.name || seen.has(place.name)) continue;
      const at = msg.content.indexOf(place.name);
      if (at < 0) continue;
      seen.add(place.name);
      found.push({ place, at });
    }
  }
  return found.sort((a, b) => a.at - b.at).map((f, i) => ({ ...f.place, no: i + 1 }));
}

// 웹 검색으로 조회한 장소 정보를 장소 이름으로 찾을 수 있게 모은다.
export function infoByName(msg: AssistantMessage): Record<string, PlaceInfo> {
  const out: Record<string, PlaceInfo> = {};
  for (const step of msg.trace?.steps ?? []) {
    for (const info of step.infos ?? []) out[info.name] = info;
  }
  return out;
}

// 답변 본문에 이름이 나온 숙소만 카드로 만든다(본문 등장 순서).
export function staysFromMessage(msg: AssistantMessage): TraceStay[] {
  if (msg.error || msg.draft || msg.food) return [];
  const seen = new Set<number>();
  const found: { stay: TraceStay; at: number }[] = [];
  for (const step of msg.trace?.steps ?? []) {
    for (const stay of step.stays ?? []) {
      if (seen.has(stay.gid)) continue;
      const at = msg.content.indexOf(stay.name);
      if (at < 0) continue;
      seen.add(stay.gid);
      found.push({ stay, at });
    }
  }
  return found.sort((a, b) => a.at - b.at).map((f) => f.stay);
}

export function regionOf(msg: AssistantMessage): string | null {
  for (const step of msg.trace?.steps ?? []) {
    const region = step.args?.region ?? step.args?.keyword;
    if (typeof region === "string" && region.trim()) return region.trim();
  }
  return msg.draft?.cond.region || null;
}
