"use client";

import { useState } from "react";
import type { FoodRequest } from "@/lib/types";

type Props = {
  defaultStart?: string;
  disabled: boolean;
  onSubmit: (req: FoodRequest, message: string) => void;
  onDismiss: () => void;
};

export default function FoodForm({ defaultStart, disabled, onSubmit, onDismiss }: Props) {
  const [start, setStart] = useState(defaultStart ?? "");
  const [days, setDays] = useState(2);
  const [dep, setDep] = useState("10:00");
  const [ret, setRet] = useState("18:00");
  const [err, setErr] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!start) return setErr("시작일을 선택해 주세요.");
    if (!Number.isInteger(days) || days < 1 || days > 14) return setErr("일수는 1~14일 사이로 입력해 주세요.");
    if (!dep || !ret) return setErr("출발·귀가 시각을 입력해 주세요.");
    setErr("");
    onSubmit(
      { start_date: start, days, departure: dep, return_time: ret },
      `맛집 추천: ${start}부터 ${days}일 · 출발 ${dep} · 귀가 ${ret}`,
    );
  }

  return (
    <form className="card offer" onSubmit={submit}>
      <p>
        <strong>일정에 맞춰 일자별 맛집도 추천해 드릴까요?</strong>
        <br />
        <span className="muted small">여행 기간과 출발·귀가 시각을 알려 주세요. 끼니 시각을 계산해 근처 식당을 찾아요.</span>
      </p>
      <div className="form-grid">
        <label>
          시작일
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
        </label>
        <label>
          일수
          <input
            type="number"
            min={1}
            max={14}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            required
          />
        </label>
        <label>
          출발 시각
          <input type="time" value={dep} onChange={(e) => setDep(e.target.value)} required />
        </label>
        <label>
          귀가 시각
          <input type="time" value={ret} onChange={(e) => setRet(e.target.value)} required />
        </label>
      </div>
      {err && <p className="warn small">{err}</p>}
      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={disabled}>
          맛집 추천받기
        </button>
        <button className="btn btn-secondary" type="button" disabled={disabled} onClick={onDismiss}>
          다음에
        </button>
      </div>
    </form>
  );
}
