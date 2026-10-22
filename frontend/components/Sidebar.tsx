"use client";

import type { SessionSummary } from "@/lib/types";

type Props = {
  sessions: SessionSummary[];
  activeId: string | null;
  open: boolean;
  busy: boolean;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
};

export default function Sidebar({ sessions, activeId, open, busy, onNew, onSelect, onDelete, onClose }: Props) {
  return (
    <>
      <div className={`scrim ${open ? "show" : ""}`} onClick={onClose} />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="logo">✈</span> 여행 챗봇
        </div>
        <button className="btn btn-primary block" onClick={onNew} disabled={busy}>
          ＋ 새 대화
        </button>
        <nav className="session-list" aria-label="대화 목록">
          {sessions.length === 0 && <p className="muted small pad">아직 대화가 없어요.</p>}
          {sessions.map((s) => (
            <div key={s.id} className={`session ${s.id === activeId ? "on" : ""}`}>
              <button className="session-title" onClick={() => onSelect(s.id)} disabled={busy} title={s.title}>
                {s.title || "새 대화"}
              </button>
              <button
                className="icon-btn"
                aria-label={`대화 삭제: ${s.title}`}
                disabled={busy}
                onClick={() => {
                  if (window.confirm("이 대화를 삭제할까요? 되돌릴 수 없어요.")) onDelete(s.id);
                }}
              >
                🗑
              </button>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
