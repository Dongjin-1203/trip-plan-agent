import type {
  AssistantMessage,
  FoodRequest,
  SessionDetail,
  SessionSummary,
} from "./types";

export class ApiError extends Error {
  status: number;
  retryAfter?: number;
  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function toError(res: Response): Promise<ApiError> {
  let detail = "";
  let retry: number | undefined;
  try {
    const body = await res.json();
    detail = typeof body?.detail === "string" ? body.detail : "";
    if (typeof body?.retry_after === "number") retry = body.retry_after;
  } catch {
    /* 본문이 JSON이 아님 */
  }
  const header = Number(res.headers.get("retry-after"));
  if (retry === undefined && Number.isFinite(header) && header > 0) retry = header;
  if (res.status === 429) {
    const wait = retry ? `${Math.ceil(retry)}초 뒤에` : "잠시 뒤에";
    return new ApiError(429, `요청이 너무 많아요. ${wait} 다시 시도해 주세요.`, retry);
  }
  return new ApiError(res.status, detail || `요청에 실패했어요 (${res.status})`);
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "서버에 연결하지 못했어요. 네트워크를 확인해 주세요.");
  }
  if (!res.ok) throw await toError(res);
  return res;
}

export async function listSessions(): Promise<SessionSummary[]> {
  return (await request("/api/sessions")).json();
}

export async function getSession(id: string): Promise<SessionDetail> {
  return (await request(`/api/sessions/${encodeURIComponent(id)}`)).json();
}

export async function deleteSession(id: string): Promise<void> {
  await request(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function dismissOffer(id: string): Promise<void> {
  await request(`/api/sessions/${encodeURIComponent(id)}/offer/dismiss`, { method: "POST" });
}

export type ChatEvent =
  | { type: "session"; id: string; title: string }
  | { type: "status"; label: string; line: string }
  | { type: "token"; text: string }
  | { type: "final"; message: AssistantMessage }
  | { type: "error"; message: string; retryable: boolean };

export type ChatBody = {
  session_id: string | null;
  message: string;
  food_request?: FoodRequest | null;
  retry?: boolean;
};

function parseBlock(block: string): ChatEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const raw of block.split("\n")) {
    if (raw.startsWith("event:")) name = raw.slice(6).trim();
    else if (raw.startsWith("data:")) data.push(raw.slice(5).replace(/^ /, ""));
  }
  if (!data.length) return null;
  let d: Record<string, unknown>;
  try {
    d = JSON.parse(data.join("\n"));
  } catch {
    return null;
  }
  switch (name) {
    case "session":
      return { type: "session", id: String(d.id), title: String(d.title ?? "") };
    case "status":
      return { type: "status", label: String(d.label ?? ""), line: String(d.line ?? "") };
    case "token":
      return { type: "token", text: String(d.text ?? "") };
    case "final":
      return { type: "final", message: d.message as AssistantMessage };
    case "error":
      return {
        type: "error",
        message: String(d.message ?? "오류가 발생했어요."),
        retryable: d.retryable !== false,
      };
    default:
      return null;
  }
}

/** POST /api/chat 을 열고 SSE 이벤트를 하나씩 내보낸다. HTTP 오류(429 등)는 ApiError 로 던진다. */
export async function* streamChat(body: ChatBody, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const res = await request("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.body) throw new ApiError(0, "응답을 받지 못했어요.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    buf += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const ev = parseBlock(buf.slice(0, idx));
      buf = buf.slice(idx + 2);
      if (ev) yield ev;
    }
    if (done) break;
  }
  if (buf.trim()) {
    const ev = parseBlock(buf);
    if (ev) yield ev;
  }
}
