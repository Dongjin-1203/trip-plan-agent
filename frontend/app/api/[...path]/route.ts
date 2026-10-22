import { NextRequest } from "next/server";
import { getIdToken, isLocalBackend } from "@/lib/idtoken";

// 브라우저 → (여기: BFF) → 비공개 백엔드. SSE는 body 스트림을 그대로 넘긴다.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FORWARD_REQUEST_HEADERS = ["content-type", "accept"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "retry-after"];
const ALLOWED = /^(chat|sessions(\/[A-Za-z0-9_-]+(\/offer\/dismiss)?)?)$/;

function json(status: number, detail: string, extra: HeadersInit = {}) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

function clientIp(req: NextRequest): string | null {
  // Cloud Run은 실제 접속자 IP를 X-Forwarded-For 목록의 "맨 끝"에 붙인다. 앞쪽 값은 접속자가 임의로 보낼 수 있어서
  // 첫 번째 값을 쓰면 IP별 요청 제한을 속일 수 있다.
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",").pop()?.trim() || null;
  return req.headers.get("x-real-ip");
}

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const sub = path.join("/");
  if (!ALLOWED.test(sub)) return json(404, "찾을 수 없는 주소예요.");

  const backend = process.env.BACKEND_URL?.replace(/\/+$/, "");
  if (!backend) return json(500, "서버 설정이 아직 끝나지 않았어요.");

  // 미들웨어가 넣은 값만 신뢰한다.
  const cid = req.headers.get("x-client-id");
  if (!cid) return json(400, "사용자 식별에 실패했어요. 새로고침해 주세요.");

  const headers = new Headers();
  for (const k of FORWARD_REQUEST_HEADERS) {
    const v = req.headers.get(k);
    if (v) headers.set(k, v);
  }
  headers.set("X-Client-Id", cid);
  const ip = clientIp(req);
  if (ip) headers.set("X-Client-Ip", ip);

  if (!isLocalBackend(backend)) {
    try {
      headers.set("Authorization", `Bearer ${await getIdToken(new URL(backend).origin)}`);
    } catch {
      return json(502, "백엔드 인증에 실패했어요. 잠시 후 다시 시도해 주세요.");
    }
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(`${backend}/api/${sub}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // @ts-expect-error Node(undici) 스트리밍 요청 본문에 필요
      duplex: "half",
      signal: req.signal,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return json(502, "백엔드에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.");
  }

  const out = new Headers();
  for (const k of FORWARD_RESPONSE_HEADERS) {
    const v = upstream.headers.get(k);
    if (v) out.set(k, v);
  }
  out.set("Cache-Control", "no-cache, no-transform");
  out.set("X-Accel-Buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as DELETE };
