// docs/API.md 를 따르는 개발용 목(mock) 백엔드. 실제 모델·DB 없이 화면 흐름을 확인한다.
//   node mock/server.mjs   (PORT 기본 8000)
// 시나리오 키워드: "날씨" → 날씨 답변 + 초안 제안 / "네, 작성해" → 초안 + 맛집 폼 제안 /
//   food_request → 일자별 맛집 / "오류" → 첫 시도 실패, retry:true 면 성공 / "429" → 요청 제한 / "계획 짜줘" → 조건 질문, "조건 입력 완료" → 요약+동의(plan) / regenerate:true → 마지막 쌍 교체
import http from "node:http";
import crypto from "node:crypto";

const PORT = Number(process.env.PORT || 8000);
const ID_RE = /^[A-Za-z0-9-]{16,64}$/;
const store = new Map(); // clientId -> Map(sessionId -> {id,title,updated_at,messages})
let failOnce = new Set();

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = () => new Date().toISOString();

function send(res, status, body, headers = {}) {
  const data = body === undefined ? "" : JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", ...headers });
  res.end(data);
}

const PLACES = [
  { name: "국립경주박물관", address: "경북 경주시 일정로 186", map_link: "http://place.map.kakao.com/1", lat: 35.8296, lon: 129.2282 },
  { name: "경주 대릉원", address: "경북 경주시 황남동 31-1", map_link: "http://place.map.kakao.com/2", lat: 35.8393, lon: 129.2117 },
  { name: "첨성대", address: "경북 경주시 인왕동 839-1", map_link: "http://place.map.kakao.com/3", lat: 35.8348, lon: 129.2191 },
  { name: "동궁과 월지", address: "경북 경주시 원화로 102", map_link: "http://place.map.kakao.com/4", lat: 35.8344, lon: 129.2263 },
];

function trace(steps) {
  return { steps, tool_calls: steps.length, tool_limit: 4, model_calls: steps.length + 1, model_limit: 6, end: "조회 후 답했다", grounded: true };
}

function build(body) {
  const q = body.message;
  if (q.includes("조건을 수정할게요")) {
    return { content: "어떤 조건을 바꿀까요? (목적지, 출발일, 박수, 인원, 숙소 여부)", question: q, trace: null, offer: false, draft: null, food: null, error: false };
  }
  if (q.includes("이 조건으로 계획")) {
    return {
      content: "## 여행 개요\n- 경주 2박 3일 · 성인 2명\n\n## 일정\n### 1일차 - 역사 산책\n- 오전: **국립경주박물관**\n- 오후: **첨성대**\n\n## 예상 비용\n- 숙박은 조회 시점 기준이며 변동될 수 있어요.\n\n수정하고 싶은 일차를 알려 주세요.",
      question: q, offer: false, draft: null, food: null, error: false,
      trace: trace([{ step: 1, tool: "confirm_trip_plan", args: {}, status: "success", note: "사용자 동의 확인" }, { step: 2, tool: "search_places", args: { region: "경주", category: "관광지" }, status: "success", note: "첫 검색", count: 3, places: PLACES.slice(0, 3) }]),
    };
  }
  if (q.includes("조건 입력 완료")) {
    return {
      content: "**여행 조건을 정리했어요**\n- 목적지: 경주\n- 일정: 2026-11-14 ~ 2026-11-16 (2박 3일)\n- 인원: 성인 2명\n- 숙소 조회: 필요\n\n이 조건으로 **여행 계획을 작성**할까요? 바꿀 내용이 있으면 말씀해 주세요.",
      question: q, offer: "plan", draft: null, food: null, error: false,
      trace: trace([{ step: 1, tool: "save_trip_info", args: { destination: "경주", start_date: "2026-11-14", nights: 2, adults: 2, need_stay: true }, status: "success", note: "여행 조건 저장 — 필수 항목 모두 수집" }]),
    };
  }
  if (q.includes("계획") && (q.includes("짜줘") || q.includes("세워"))) {
    return {
      content: "계획을 세우려면 몇 가지만 알려 주세요.\n1. 목적지\n2. 출발일과 몇 박인지\n3. 성인 인원\n4. 숙소 조회가 필요한지\n\n(선택) 아동 동반, 예산, 취향도 알려 주시면 반영할게요. 모두 정하셨으면 '조건 입력 완료'라고 말씀해 주세요.",
      question: q, offer: false, draft: null, food: null, error: false,
      trace: trace([{ step: 1, tool: "save_trip_info", args: {}, status: "success", note: "여행 조건 저장 — 빠진 항목: 목적지, 출발일, 몇 박인지, 성인 인원, 숙소 조회가 필요한지" }]),
    };
  }
  if (body.food_request) {
    const r = body.food_request;
    const days = [];
    for (let i = 0; i < r.days; i++) {
      const d = new Date(r.start_date + "T00:00:00Z");
      d.setUTCDate(d.getUTCDate() + i);
      const meals = [{ meal: "점심", anchor: "첨성대 근처", place: { id: `p${i}a`, name: `경주 한식당 ${i + 1}`, address: "경북 경주시 인왕동", map_link: "http://place.map.kakao.com/11", category: "한식", distance_m: 120 + i * 30, lat: 35.835 + i * 0.002, lon: 129.219 + i * 0.002 } }];
      if (i !== 0 || r.return_time > "19:00") meals.push({ meal: "저녁", anchor: "동궁과 월지 근처", place: i === 1 ? null : { id: `p${i}b`, name: `월지 식당 ${i + 1}`, address: "경북 경주시 원화로", map_link: "http://place.map.kakao.com/12", category: "분식", distance_m: 240, lat: 35.834 + i * 0.001, lon: 129.226 } });
      if (i === r.days - 1 && r.days > 2) meals.length = 0;
      days.push({ day: i + 1, date: d.toISOString().slice(0, 10), weekday: "일월화수목금토"[d.getUTCDay()], meals });
    }
    return {
      content: "일자별 맛집 추천입니다.",
      question: q, trace: null, offer: false, draft: null, error: false,
      food: { request: r, days, total_meals: days.reduce((n, d) => n + d.meals.length, 0), picked: [], failed: false,
        notes: ["끼니 기준 시각: 점심 12:00, 저녁 18:00", "아침은 영업시간을 알 수 없어 추천하지 않았어요."] },
    };
  }
  if (q.includes("네, 작성해")) {
    return {
      content: "여행 계획 초안입니다.", question: q, trace: null, offer: "food", offer_defaults: { start_date: "2026-10-24" }, food: null, error: false,
      draft: { cond: { region: "경주", date: "2026-10-25", preference: "실내 관광지" }, warnings: [], places: PLACES,
        weather_source: "Open-Meteo (https://open-meteo.com, CC-BY 4.0)", weather_state: "ok",
        packing: ["날씨에 따라 우산 · 방수 신발을 준비해주세요! (비 올 가능성이 높아요)"], time_slots: ["오전", "점심 무렵", "오후", "늦은 오후"] },
    };
  }
  if (q.includes("아니요")) {
    return { content: "알겠어요. 더 필요하면 말씀해 주세요.", question: q, trace: null, offer: false, draft: null, food: null, error: false };
  }
  if (q.includes("숙소")) {
    const link = (id) => `https://accommodation.myrealtrip.com/union/products/${id}?checkIn=2026-11-14&checkOut=2026-11-16&adultCount=2&childCount=0`;
    const stays = [
      { gid: 101, name: "경주 해변 호텔", description: "4성급 · 호텔 · 경주", price: "150,000원/박", price_with_tax: "세금포함 165,000원/박", rating: 4.5, review_count: "1,234", tags: ["무료취소", "세일페스타"], image: "", booking_link: link(101) },
      { gid: 102, name: "보문 리조트", description: "5성급 · 리조트 · 경주", price: "", price_with_tax: "", rating: 4.2, review_count: "880", tags: [], image: "", booking_link: link(102) },
    ];
    return {
      content: "경주 숙소를 찾았어요. 가격은 조회 시점 기준이라 바뀔 수 있어요.\n\n1. **경주 해변 호텔** 150,000원/박\n2. **보문 리조트**\n\n최종 가격은 예약 페이지에서 확인해 주세요.",
      question: q, offer: false, draft: null, food: null, error: false,
      trace: trace([{ step: 1, tool: "find_stays", args: { keyword: "경주", check_in: "2026-11-14", check_out: "2026-11-16", adults: 2, children: 0, domestic: true }, status: "success", note: "숙소 조회", count: 2, source: "마이리얼트립 MCP (searchStays)", queried_at: "2026-10-22T14:00:00+09:00", stays }]),
    };
  }
  if (q.includes("날씨")) {
    return {
      content: "**경주**의 3일 뒤(10/25, 일) 예보입니다. 최고 19.4°C, 최저 16.0°C, 강수확률 92%예요.\n\n이 조건으로 여행 계획 초안을 만들어 드릴까요?",
      question: q, offer: "draft", draft: null, food: null, error: false,
      trace: trace([{ step: 1, tool: "get_weather", args: { region: "경주", date: "3일 뒤" }, status: "ok", note: "날씨 조회", source: "Open-Meteo (https://open-meteo.com, CC-BY 4.0)", result: { status: "ok", date: "2026-10-25", temp_max: 19.4, temp_min: 16.0, precip_prob: 92 } }]),
    };
  }
  return {
    content: "경주의 실내 관광지를 찾았어요.\n\n1. **국립경주박물관**\n2. **경주 대릉원**\n3. **첨성대**\n\n날씨도 확인해 볼까요?",
    question: q, offer: false, draft: null, food: null, error: false,
    trace: trace([{ step: 1, tool: "search_places", args: { region: "경주", category: "실내 관광지" }, status: "success", note: "첫 검색", count: 3, places: PLACES.slice(0, 3) }]),
  };
}

function sse(res, event, data) {
  res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

async function chat(req, res, cid, body) {
  let msg = body?.message;
  if (typeof msg !== "string" || !msg.trim() || msg.length > 500) return send(res, 422, { detail: "메시지는 1~500자여야 해요." });
  if (msg.includes("429")) return send(res, 429, { detail: "요청이 너무 많아요.", retry_after: 7 }, { "retry-after": "7" });

  const sessions = store.get(cid) ?? store.set(cid, new Map()).get(cid);
  let s = body.session_id ? sessions.get(body.session_id) : null;
  if (body.session_id && !s) return send(res, 404, { detail: "대화를 찾을 수 없어요." });
  if (!s) {
    s = { id: crypto.randomBytes(6).toString("hex"), title: msg.slice(0, 30), updated_at: now(), messages: [] };
    sessions.set(s.id, s);
  }
  if (body.regenerate) {
    if (!body.session_id || body.retry) return send(res, 422, { detail: "regenerate는 기존 대화에서 retry 없이만 쓸 수 있어요." });
    const [u, a] = s.messages.slice(-2);
    if (u?.role !== "user" || a?.role !== "assistant" || u.error || a.error) return send(res, 409, { detail: "다시 생성할 답변이 없어요." });
    s.messages.splice(-2, 2);
    msg = u.content;
    body = { ...body, message: msg };
  }
  if (body.retry) {
    const l = s.messages.at(-1);
    if (l?.role === "assistant" && l.error) s.messages.splice(-2, 2);
  }

  res.writeHead(200, { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache", connection: "keep-alive" });
  sse(res, "session", { id: s.id, title: s.title });

  const key = `${cid}:${s.id}:${msg}`;
  if (msg.includes("오류") && !body.retry && !failOnce.has(key)) {
    failOnce.add(key);
    await sleep(300);
    const text = "일시적인 오류가 발생했어요. 다시 시도해 주세요.";
    s.messages.push({ role: "user", content: msg, error: true });
    s.messages.push({ role: "assistant", content: text, question: msg, trace: null, offer: false, draft: null, food: null, error: true });
    s.updated_at = now();
    sse(res, "error", { message: text, retryable: true });
    return res.end();
  }

  const m = { role: "assistant", ...build(body) };
  const label = body.food_request ? "🍽️ 맛집 찾는 중" : msg.includes("날씨") ? "🌤️ 날씨 조회 중: 경주" : "🔎 장소 검색 중: 경주 실내 관광지";
  sse(res, "status", { label, line: label });
  await sleep(500);
  if (!body.food_request && !msg.includes("네, 작성해") && !msg.includes("아니요")) {
    for (const ch of m.content.match(/[\s\S]{1,6}/g)) {
      if (res.destroyed) return; // 연결 끊김 → 저장 안 함
      sse(res, "token", { text: ch });
      await sleep(40);
    }
  } else await sleep(300);
  if (res.destroyed) return;
  s.messages.push({ role: "user", content: msg, error: false });
  s.messages.push(m);
  s.updated_at = now();
  sse(res, "final", { message: m });
  res.end();
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const p = url.pathname;
  if (p === "/healthz") return send(res, 200, { status: "ok" });
  if (p === "/readyz") return send(res, 200, { status: "ok" });
  const cid = req.headers["x-client-id"];
  if (!cid || !ID_RE.test(String(cid))) return send(res, 400, { detail: "X-Client-Id 가 필요해요." });
  const sessions = store.get(cid) ?? store.set(cid, new Map()).get(cid);

  let raw = "";
  for await (const c of req) raw += c;
  let body = null;
  try { body = raw ? JSON.parse(raw) : null; } catch { return send(res, 422, { detail: "JSON 형식이 올바르지 않아요." }); }

  if (req.method === "POST" && p === "/api/chat") return chat(req, res, cid, body);
  if (req.method === "GET" && p === "/api/sessions") {
    return send(res, 200, [...sessions.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 50).map(({ id, title, updated_at }) => ({ id, title, updated_at })));
  }
  const mm = p.match(/^\/api\/sessions\/([A-Za-z0-9_-]+)(\/offer\/dismiss)?$/);
  if (mm) {
    const s = sessions.get(mm[1]);
    if (!s) return send(res, 404, { detail: "대화를 찾을 수 없어요." });
    if (req.method === "GET" && !mm[2]) return send(res, 200, s);
    if (req.method === "DELETE" && !mm[2]) { sessions.delete(s.id); return send(res, 204); }
    if (req.method === "POST" && mm[2]) { const l = s.messages.at(-1); if (l?.role === "assistant") l.offer = false; return send(res, 204); }
  }
  send(res, 404, { detail: "not found" });
});

server.listen(PORT, () => console.log(`mock backend on http://localhost:${PORT}`));
