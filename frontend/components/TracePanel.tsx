import type { Trace } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  success: "성공",
  ok: "성공",
  error: "오류",
  auth_error: "인증 오류",
  skipped: "건너뜀",
  out_of_range: "범위 밖",
  partial: "일부 성공",
};

const TOOL_LABEL: Record<string, string> = {
  search_places: "장소 검색",
  get_weather: "날씨 조회",
  draft_travel_plan: "여행 초안 작성",
  nearby_restaurants: "근처 맛집 검색",
  find_stays: "숙소 조회",
};

const ARG_LABEL: Record<string, string> = {
  region: "지역",
  keyword: "지역",
  check_in: "체크인",
  check_out: "체크아웃",
  adults: "성인",
  children: "아동",
  domestic: "국내",
  category: "종류",
  date: "날짜",
  start_date: "시작일",
  days: "일수",
  departure: "출발",
  return_time: "귀가",
};

function argText(args?: Record<string, unknown>) {
  if (!args) return "";
  return Object.entries(args)
    .map(([k, v]) => `${ARG_LABEL[k] ?? k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" · ");
}

export default function TracePanel({ trace }: { trace: Trace }) {
  return (
    <details className="trace">
      <summary>처리 과정 보기</summary>
      {trace.grounded === false && (
        <p className="warn">주의: 답변과 조회 결과가 일치하지 않을 수 있어요. 지도 링크로 직접 확인해 주세요.</p>
      )}
      <ol className="trace-steps">
        {trace.steps.map((s) => (
          <li key={s.step}>
            <div className="trace-head">
              <strong>{TOOL_LABEL[s.tool] ?? s.tool}</strong>
              <span className={`chip chip-${s.status === "error" || s.status === "auth_error" ? "bad" : "ok"}`}>
                {STATUS_LABEL[s.status] ?? s.status}
              </span>
            </div>
            {argText(s.args) && <div className="muted small">{argText(s.args)}</div>}
            {s.note && <div className="small">{s.note}</div>}
            {s.count != null && <div className="small">결과 {s.count}건</div>}
            {s.places && s.places.length > 0 && (
              <ul className="small trace-places">
                {s.places.map((p, i) => (
                  <li key={i}>
                    {p.map_link ? (
                      <a href={p.map_link} target="_blank" rel="noopener noreferrer">{p.name}</a>
                    ) : (
                      p.name
                    )}
                    {p.address ? <span className="muted"> · {p.address}</span> : null}
                  </li>
                ))}
              </ul>
            )}
            {s.warnings?.map((w, i) => (
              <div key={i} className="small warn">주의: {w}</div>
            ))}
            {s.source && <div className="muted small">출처: {s.source}</div>}
          </li>
        ))}
      </ol>
      <p className="muted small">
        도구 {trace.tool_calls ?? trace.steps.length}
        {trace.tool_limit ? `/${trace.tool_limit}` : ""}회
        {trace.model_calls != null ? ` · 모델 ${trace.model_calls}${trace.model_limit ? `/${trace.model_limit}` : ""}회` : ""}
        {trace.end ? ` · 종료: ${trace.end}` : ""}
      </p>
    </details>
  );
}
