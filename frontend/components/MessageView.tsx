"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { placesFromMessage } from "@/lib/places";
import type { Message } from "@/lib/types";
import DraftCard from "./DraftCard";
import FoodTabs from "./FoodTabs";
import PlaceCards from "./PlaceCards";
import TracePanel from "./TracePanel";

type Props = { msg: Message; mapDraft: boolean; mapFood: boolean };

// hast 노드의 글자만 모은다(카드로 대체할 목록인지 판별용).
function textOf(node: any): string {
  if (!node) return "";
  if (typeof node.value === "string") return node.value;
  return (node.children ?? []).map(textOf).join("");
}

// 항목마다 카드로 보여 준 장소 이름이 들어 있는 목록이면 숨긴다. 다른 목록(팁 등)은 그대로 둔다.
function coveredByCards(node: any, names: string[]): boolean {
  const items = (node?.children ?? []).filter((c: any) => c.tagName === "li");
  return items.length > 0 && items.every((li: any) => names.some((n) => textOf(li).includes(n)));
}

export function Markdown({ text, hideNames = [] }: { text: string; hideNames?: string[] }) {
  return (
    <div className="md">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          ol: ({ node, children }) => (hideNames.length && coveredByCards(node, hideNames) ? null : <ol>{children}</ol>),
          ul: ({ node, children }) => (hideNames.length && coveredByCards(node, hideNames) ? null : <ul>{children}</ul>),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

// 숨길 목록을 빼고 남은 글이 없으면 빈 말풍선을 보이지 않게 한다.
function BotBubble({ text, hideNames }: { text: string; hideNames: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [empty, setEmpty] = useState(false);
  useEffect(() => {
    setEmpty(!ref.current?.textContent?.trim());
  }, [text, hideNames]);
  return (
    <div ref={ref} className="bubble bot" hidden={empty}>
      <Markdown text={text} hideNames={hideNames} />
    </div>
  );
}

export default function MessageView({ msg, mapDraft, mapFood }: Props) {
  const places = useMemo(() => (msg.role === "assistant" ? placesFromMessage(msg) : []), [msg]);
  const names = useMemo(() => places.map((p) => p.name), [places]);

  if (msg.role === "user") {
    return (
      <div className="row-user">
        <div className={`bubble user ${msg.error ? "failed" : ""}`}>{msg.content}</div>
      </div>
    );
  }
  return (
    <div className="row-bot">
      <div className="bot-col">
        {msg.error ? (
          <div className="bubble bot error-bubble" role="alert">
            <strong>답변을 가져오지 못했어요.</strong>
            <div>{msg.content}</div>
          </div>
        ) : msg.draft ? (
          <DraftCard draft={msg.draft} showMap={mapDraft} />
        ) : msg.food ? (
          <FoodTabs food={msg.food} showMap={mapFood} />
        ) : (
          <>
            <BotBubble text={msg.content} hideNames={names} />
            {places.length > 0 && <PlaceCards places={places} />}
          </>
        )}
        {!msg.error && msg.trace && msg.trace.steps?.length > 0 && <TracePanel trace={msg.trace} />}
      </div>
    </div>
  );
}
