import { placesFromMessage, regionOf, staysFromMessage } from "@/lib/places";
import type { AssistantMessage } from "@/lib/types";

// 응답에 쓰인 장소·지역으로 후속 질문을 만든다. 보낼 만한 문장이 없으면 빈 배열.
export function suggestionsFor(msg: AssistantMessage): string[] {
  if (msg.error || msg.offer || msg.food) return [];
  const places = placesFromMessage(msg);
  const region = regionOf(msg);
  const tools = new Set((msg.trace?.steps ?? []).map((s) => s.tool));
  const out: string[] = [];
  if (places[0]) out.push(`${places[0].name} 근처 맛집 알려줘`);
  if (places.length > 1) out.push("이 장소들로 1일 일정 짜줘");
  if (region && !tools.has("get_weather")) out.push(`${region} 날씨 알려줘`);
  if (region && !tools.has("search_places")) out.push(`${region} 가볼 만한 곳 추천해줘`);
  if (region && places.length > 0 && !tools.has("find_stays")) out.push(`${region} 숙소도 추천해줘`);
  if (region && staysFromMessage(msg).length > 0 && !tools.has("search_places")) out.push(`${region} 근처 맛집 알려줘`);
  return out.slice(0, 4);
}

type Props = { items: string[]; onPick: (text: string) => void };

export default function Suggestions({ items, onPick }: Props) {
  if (items.length === 0) return null;
  return (
    <div className="suggest" role="group" aria-label="이어서 물어보기">
      {items.map((t) => (
        <button key={t} type="button" className="suggest-chip" onClick={() => onPick(t)}>
          {t}
        </button>
      ))}
    </div>
  );
}
