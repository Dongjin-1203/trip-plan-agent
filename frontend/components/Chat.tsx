"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  deleteSession,
  dismissOffer,
  getSession,
  listSessions,
  streamChat,
} from "@/lib/api";
import type { AssistantMessage, FoodRequest, Message, SessionSummary } from "@/lib/types";
import FoodForm from "./FoodForm";
import MessageView, { Markdown } from "./MessageView";
import Sidebar from "./Sidebar";
import Suggestions, { suggestionsFor } from "./Suggestions";

type Live = { text: string; label: string; lines: string[] };

const LAST_KEY = "travel-chat:last-session";
const STARTERS = [
  { title: "장소 추천", prompt: "경주 실내 관광지 추천해줘" },
  { title: "날씨 확인", prompt: "이번 주 토요일 제주 날씨 알려줘" },
  { title: "여행 일정 초안", prompt: "부산 가볼 만한 곳 추천해줘" },
  { title: "일자별 맛집", prompt: "서울 성수동 맛집 알려줘" },
];
const FOOD_MSG = /^맛집 추천: (\d{4}-\d{2}-\d{2})부터 (\d+)일 · 출발 (\d{2}:\d{2}) · 귀가 (\d{2}:\d{2})$/;

function remember(id: string | null) {
  try {
    if (id) localStorage.setItem(LAST_KEY, id);
    else localStorage.removeItem(LAST_KEY);
  } catch {
    /* 저장소를 못 쓰는 환경 */
  }
}

function recall(): string | null {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}

function foodFromText(text: string): FoodRequest | null {
  const m = FOOD_MSG.exec(text);
  return m ? { start_date: m[1], days: Number(m[2]), departure: m[3], return_time: m[4] } : null;
}

export default function Chat() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [live, setLive] = useState<Live | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [loading, setLoading] = useState(true);
  const bottom = useRef<HTMLDivElement>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions());
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "대화 목록을 불러오지 못했어요.");
    }
  }, []);

  // 첫 로드: 목록 + 마지막으로 보던 대화 복원
  useEffect(() => {
    (async () => {
      try {
        const list = await listSessions();
        setSessions(list);
        const last = recall();
        if (last && list.some((s) => s.id === last)) {
          const d = await getSession(last);
          setActiveId(d.id);
          setMessages(d.messages);
        }
      } catch (e) {
        setNotice(e instanceof ApiError ? e.message : "대화를 불러오지 못했어요.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, live]);

  // 지도는 가장 최근의 초안 / 맛집 추천 메시지에만 그린다.
  const { lastDraft, lastFood } = useMemo(() => {
    let d = -1;
    let f = -1;
    messages.forEach((m, i) => {
      if (m.role !== "assistant") return;
      if (m.draft) d = i;
      if (m.food) f = i;
    });
    return { lastDraft: d, lastFood: f };
  }, [messages]);

  async function send(message: string, opts: { food?: FoodRequest | null; retry?: boolean } = {}) {
    if (busy || !message.trim()) return;
    setNotice(null);
    setBusy(true);
    setDrawer(false);

    const base = opts.retry ? messages.slice(0, -2) : messages;
    setMessages([...base, { role: "user", content: message }]);
    setLive({ text: "", label: "답변을 준비하고 있어요…", lines: [] });

    let sid = activeId;
    let ended: "final" | "error" | null = null;
    try {
      for await (const ev of streamChat({
        session_id: sid,
        message,
        food_request: opts.food ?? null,
        retry: !!opts.retry,
      })) {
        if (ev.type === "session") {
          sid = ev.id;
          setActiveId(ev.id);
          remember(ev.id);
        } else if (ev.type === "status") {
          setLive((l) =>
            l ? { ...l, label: ev.label || l.label, lines: ev.line ? [...l.lines, ev.line] : l.lines } : l,
          );
        } else if (ev.type === "token") {
          setLive((l) => (l ? { ...l, text: l.text + ev.text } : l));
        } else if (ev.type === "final") {
          ended = "final";
          setMessages((m) => [...m, ev.message]); // 임시 토큰 표시를 저장된 최종본으로 교체
        } else if (ev.type === "error") {
          ended = "error";
          let reloaded = false;
          if (sid) {
            try {
              setMessages((await getSession(sid)).messages);
              reloaded = true;
            } catch {
              /* 아래 대체 표시 */
            }
          }
          if (!reloaded) {
            const failed: AssistantMessage = {
              role: "assistant",
              content: ev.message,
              question: message,
              offer: false,
              draft: null,
              food: null,
              error: true,
            };
            setMessages([...base, { role: "user", content: message, error: true }, failed]);
          }
        }
      }
      if (!ended) throw new ApiError(0, "연결이 끊겨 이번 답변이 저장되지 않았어요. 다시 보내 주세요.");
    } catch (e) {
      // 서버에 저장되지 않은 턴은 화면에서도 되돌린다.
      setMessages(base);
      if (!opts.retry && !activeId && sid) {
        setActiveId(null);
        remember(null);
      }
      setNotice(e instanceof ApiError ? e.message : "알 수 없는 오류가 발생했어요.");
      if (e instanceof ApiError && e.status === 404) {
        setActiveId(null);
        remember(null);
        setMessages([]);
      }
    } finally {
      setLive(null);
      setBusy(false);
      refreshSessions();
    }
  }

  function submitInput() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    send(text);
  }

  async function openSession(id: string) {
    if (busy || id === activeId) return setDrawer(false);
    setNotice(null);
    setDrawer(false);
    try {
      const d = await getSession(id);
      setActiveId(d.id);
      setMessages(d.messages);
      remember(d.id);
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "대화를 불러오지 못했어요.");
      refreshSessions();
    }
  }

  function newChat() {
    if (busy) return;
    setActiveId(null);
    setMessages([]);
    setNotice(null);
    setDrawer(false);
    remember(null);
  }

  async function removeSession(id: string) {
    try {
      await deleteSession(id);
      if (id === activeId) newChat();
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "삭제하지 못했어요.");
    }
    refreshSessions();
  }

  async function dismissFood() {
    if (!activeId) return;
    try {
      await dismissOffer(activeId);
      setMessages((ms) =>
        ms.map((m, i) => (i === ms.length - 1 && m.role === "assistant" ? { ...m, offer: false } : m)),
      );
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "처리하지 못했어요.");
    }
  }

  function retryLast() {
    const last = messages[messages.length - 1];
    const prev = messages[messages.length - 2];
    if (last?.role !== "assistant") return;
    const q = last.question || (prev?.role === "user" ? prev.content : "");
    if (q) send(q, { retry: true, food: foodFromText(q) });
  }

  const last = messages[messages.length - 1];
  const lastBot = last?.role === "assistant" ? last : null;
  const idle = !busy && !live;
  const chips = useMemo(() => (lastBot ? suggestionsFor(lastBot) : []), [lastBot]);

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        open={drawer}
        busy={busy}
        onNew={newChat}
        onSelect={openSession}
        onDelete={removeSession}
        onClose={() => setDrawer(false)}
      />
      <main className="main">
        <header className="topbar">
          <button className="icon-btn menu" aria-label="대화 목록 열기" onClick={() => setDrawer(true)}>
            ☰
          </button>
          <span className="topbar-title">{sessions.find((s) => s.id === activeId)?.title || "새 대화"}</span>
        </header>

        <div className="scroll">
          <div className="thread">
            {loading && <p className="muted center">불러오는 중…</p>}
            {!loading && messages.length === 0 && !live && (
              <div className="empty">
                <h1>어디로 떠나볼까요?</h1>
                <p className="muted">장소를 물어보고, 날씨를 확인하고, 여행 초안과 일자별 맛집까지 이어서 받아보세요.</p>
                <div className="starters">
                  {STARTERS.map((s) => (
                    <button key={s.title} className="starter" disabled={busy} onClick={() => send(s.prompt)}>
                      <span className="starter-title">{s.title}</span>
                      <span className="starter-prompt">{s.prompt}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <MessageView key={i} msg={m} mapDraft={i === lastDraft} mapFood={i === lastFood} />
            ))}

            {live && (
              <div className="row-bot">
                <div className="bot-col">
                  <div className="status-line" role="status">
                    <span className="spinner" aria-hidden /> {live.label}
                  </div>
                  <div className="bubble bot live-bubble">
                    {live.text ? (
                      <Markdown text={live.text} />
                    ) : (
                      <span className="typing" aria-hidden>
                        <i /><i /><i />
                      </span>
                    )}
                  </div>
                  {live.lines.length > 0 && (
                    <details className="trace">
                      <summary>실행 기록 (진행 중)</summary>
                      <ul className="small muted">
                        {live.lines.map((l, i) => (
                          <li key={i}>{l}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              </div>
            )}

            {idle && lastBot?.error && (
              <div className="row-bot">
                <button className="btn btn-primary" onClick={retryLast}>
                  다시 시도하기
                </button>
              </div>
            )}

            {idle && lastBot && !lastBot.error && <Suggestions items={chips} onPick={(t) => send(t)} />}

            {idle && lastBot && !lastBot.error && lastBot.offer === "draft" && (
              <div className="row-bot offer-row">
                <button className="btn btn-primary" onClick={() => send("네, 작성해 주세요")}>
                  초안 작성하기
                </button>
                <button className="btn btn-secondary" onClick={() => send("아니요, 괜찮아요")}>
                  다음에
                </button>
              </div>
            )}

            {idle && lastBot && !lastBot.error && lastBot.offer === "food" && (
              <div className="row-bot">
                <div className="bot-col">
                  <FoodForm
                    defaultStart={lastBot.offer_defaults?.start_date}
                    disabled={!idle}
                    onSubmit={(req, text) => send(text, { food: req })}
                    onDismiss={dismissFood}
                  />
                </div>
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        {notice && (
          <div className="notice" role="alert">
            <span>{notice}</span>
            <button className="icon-btn" aria-label="닫기" onClick={() => setNotice(null)}>
              ✕
            </button>
          </div>
        )}

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            submitInput();
          }}
        >
          <textarea
            value={input}
            rows={1}
            maxLength={500}
            aria-label="메시지 입력"
            placeholder="예: 경주 실내 관광지 추천해줘"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submitInput();
              }
            }}
          />
          <button className="btn btn-primary send" type="submit" disabled={busy || !input.trim()} aria-label="보내기">
            ↑
          </button>
        </form>
      </main>
    </div>
  );
}
