// Cloud Run 메타데이터 서버에서 대상 오디언스용 ID 토큰을 받아 캐시한다. (서버 전용)
const METADATA =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";

const cache = new Map<string, { token: string; expires: number }>();

export function isLocalBackend(url: string): boolean {
  try {
    const h = new URL(url).hostname;
    return h === "localhost" || h === "127.0.0.1" || h === "[::1]" || h === "::1";
  } catch {
    return false;
  }
}

function jwtExp(token: string): number {
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

export async function getIdToken(audience: string): Promise<string> {
  const hit = cache.get(audience);
  if (hit && hit.expires - Date.now() > 5 * 60 * 1000) return hit.token;

  const res = await fetch(`${METADATA}?audience=${encodeURIComponent(audience)}`, {
    headers: { "Metadata-Flavor": "Google" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`metadata server ${res.status}`);
  const token = (await res.text()).trim();
  cache.set(audience, { token, expires: jwtExp(token) || Date.now() + 30 * 60 * 1000 });
  return token;
}
