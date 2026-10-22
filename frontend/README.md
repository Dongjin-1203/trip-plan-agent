# 여행 챗봇 웹 (Next.js)

브라우저 → **Next.js 서버(BFF, `app/api/[...path]`)** → FastAPI 백엔드. API 계약은 `../docs/API.md`.
브라우저는 같은 출처의 `/api/*`만 호출하고, 백엔드 주소·토큰은 서버에만 있습니다. 익명 ID는 `middleware.ts`가 httpOnly 쿠키(`cid`)로 발급합니다.

## 로컬 실행

Node.js 20 이상(LTS)이 필요합니다.

```bash
cd frontend
cp .env.example .env.local      # BACKEND_URL=http://localhost:8000
npm install
npm run dev                      # http://localhost:3000
```

백엔드는 둘 중 하나로 띄웁니다.

```bash
# 실제 백엔드 (backend/ 에서)
uvicorn api.main:app --port 8000

# 또는 API.md 를 따르는 목(mock) 서버
npm run mock
```

목 서버 키워드: `날씨`(초안 제안), `네, 작성해`(초안), `오류`(첫 시도 실패 → 다시 시도), `429`(요청 제한 안내).

## 빌드·배포

```bash
npm run build && npm start
```

`next.config.mjs`가 `output: "standalone"`이고 `Dockerfile`은 Cloud Run의 `PORT`를 씁니다.
운영에서는 환경변수 `BACKEND_URL`에 비공개 백엔드 Cloud Run 주소를 지정하면, BFF가 메타데이터 서버에서 ID 토큰을 받아 `Authorization: Bearer`를 붙입니다(웹 서비스 계정에 백엔드 `roles/run.invoker` 필요). `localhost` 주소일 때는 인증 없이 호출합니다.

지도는 OpenStreetMap 타일(키 불필요)을 쓰며 지도 아래에 출처가 표시됩니다.
