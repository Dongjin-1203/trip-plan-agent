import { NextRequest, NextResponse } from "next/server";

const COOKIE = "cid";
const ID_RE = /^[A-Za-z0-9-]{16,64}$/;
const ONE_YEAR = 60 * 60 * 24 * 365;

// 익명 ID(브라우저별)를 발급한다. 요청에 실려 온 x-client-id 는 항상 버리고
// 쿠키 값(또는 새로 만든 값)으로 덮어써서 BFF가 신뢰할 수 있는 값만 쓰게 한다.
export function middleware(req: NextRequest) {
  const existing = req.cookies.get(COOKIE)?.value;
  const cid = existing && ID_RE.test(existing) ? existing : crypto.randomUUID();

  const headers = new Headers(req.headers);
  headers.set("x-client-id", cid);
  const res = NextResponse.next({ request: { headers } });

  if (cid !== existing) {
    const proto = req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "");
    res.cookies.set(COOKIE, cid, {
      httpOnly: true,
      secure: proto === "https",
      sameSite: "lax",
      path: "/",
      maxAge: ONE_YEAR,
    });
  }
  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.svg).*)"],
};
