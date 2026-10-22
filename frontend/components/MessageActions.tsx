"use client";

import { useEffect, useRef, useState } from "react";
import { CopyIcon, RefreshIcon } from "./Icons";

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // http 환경이거나 권한이 없을 때의 대체 방법
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;opacity:0;top:0;left:0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

type Props = { text: string; onRegenerate?: () => void };

export default function MessageActions({ text, onRegenerate }: Props) {
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    setState((await copyToClipboard(text)) ? "done" : "fail");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  }

  if (!text) return null;
  return (
    <div className="msg-actions">
      <button type="button" className="act-btn" onClick={copy} aria-label="답변 복사">
        <CopyIcon /> <span role="status">{state === "done" ? "복사됨" : state === "fail" ? "복사 실패" : "복사"}</span>
      </button>
      {onRegenerate && (
        <button type="button" className="act-btn" onClick={onRegenerate} aria-label="답변 다시 생성">
          <RefreshIcon /> 다시 생성
        </button>
      )}
    </div>
  );
}
