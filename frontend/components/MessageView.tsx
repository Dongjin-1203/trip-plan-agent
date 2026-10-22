import ReactMarkdown from "react-markdown";
import type { Message } from "@/lib/types";
import DraftCard from "./DraftCard";
import FoodTabs from "./FoodTabs";
import TracePanel from "./TracePanel";

type Props = { msg: Message; mapDraft: boolean; mapFood: boolean };

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default function MessageView({ msg, mapDraft, mapFood }: Props) {
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
          <div className="bubble bot error-bubble">⚠️ {msg.content}</div>
        ) : msg.draft ? (
          <DraftCard draft={msg.draft} showMap={mapDraft} />
        ) : msg.food ? (
          <FoodTabs food={msg.food} showMap={mapFood} />
        ) : (
          <div className="bubble bot">
            <Markdown text={msg.content} />
          </div>
        )}
        {!msg.error && msg.trace && msg.trace.steps?.length > 0 && <TracePanel trace={msg.trace} />}
      </div>
    </div>
  );
}
