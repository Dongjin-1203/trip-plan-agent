/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // gzip이 SSE 토큰을 모아서 보내지 않도록 압축을 끈다(압축은 앞단 Cloud Run/CDN이 담당).
  compress: false,
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
