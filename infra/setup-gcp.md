# GCP 배포 가이드

GitHub 저장소 `Dongjin-1203/trip-plan-agent`에 push하면 Cloud Build가 자동으로 Cloud Run에 배포하도록 설정합니다.

| 항목 | 값 |
|---|---|
| GCP 프로젝트 | `trip-plan-agent` (번호 `23572623744`) |
| 리전 | `asia-northeast3` (서울) |
| 웹 | Cloud Run `travel-web` — 공개 |
| 백엔드 | Cloud Run `travel-api` — **비공개**(웹 서비스 계정만 호출 가능) |
| DB | Cloud SQL PostgreSQL 16 `travel-db` (`db-f1-micro`) |
| 비밀 값 | Secret Manager (`OPENAI_API_KEY`, `KAKAO_REST_API_KEY`, `LANGSMITH_API_KEY`, `DATABASE_URL`) |

```
브라우저 → travel-web(공개) ──ID 토큰──▶ travel-api(비공개) → Cloud SQL / OpenAI / 카카오 / Open-Meteo
```

## 비용 주의
- **Cloud SQL은 요청이 없어도 켜져 있는 동안 계속 과금**됩니다(가장 작은 사양이지만 0원이 아니에요). 쓰지 않을 때는 인스턴스를 중지(`gcloud sql instances patch travel-db --activation-policy=NEVER`)하거나 삭제하세요.
- Cloud Run은 요청이 없으면 0으로 줄지만, 요청이 많으면 OpenAI·카카오 사용량이 늘어납니다. 그래서 **요청 횟수 제한**(사용자별 분당 8회·일 150회, IP별 분당 30회)과 `--max-instances 3`을 걸어 두었습니다.
- 시작 전에 **예산 알림**을 만드는 걸 권합니다: 콘솔 → 결제 → 예산 및 알림 → 월 예산(예: 1만 원)과 50%·90% 알림.

## 1단계. 결제 연결 (직접 해야 해요)
지금 프로젝트에는 **결제 계정이 연결되어 있지 않습니다.** 연결 전에는 Cloud Run·Cloud SQL·Cloud Build를 켤 수 없어요.

1. https://console.cloud.google.com/billing/linkedaccount?project=trip-plan-agent 접속
2. 결제 계정을 선택하거나 새로 만들어 프로젝트에 연결
3. 확인:
   ```bash
   gcloud billing projects describe trip-plan-agent --format="value(billingEnabled)"
   ```
   `True`가 나오면 됩니다.

## 2단계. 초기 설정 스크립트 실행
Git Bash(또는 Cloud Shell)에서 저장소 루트로 이동해 실행합니다.

```bash
bash infra/setup-gcp.sh
```
- API 활성화, 이미지 저장소, 서비스 계정 3개, Cloud SQL, 시크릿을 만듭니다. **여러 번 실행해도 안전**합니다.
- 중간에 **OpenAI·카카오·LangSmith 키를 물어봅니다.** 터미널에 직접 붙여넣으세요(화면에 표시되지 않고 어디에도 기록되지 않습니다). LangSmith는 없으면 Enter.
- Cloud SQL 생성에 5~10분 걸립니다.
- DB 비밀번호는 스크립트가 무작위로 만들어 Secret Manager에만 저장하고 화면에 출력하지 않습니다.

## 3단계. GitHub 연결 (콘솔에서 직접)
Cloud Build가 GitHub 저장소를 읽으려면 한 번 연결해야 합니다(브라우저 로그인이 필요해서 스크립트로 할 수 없어요).

1. https://console.cloud.google.com/cloud-build/repositories/2nd-gen?project=trip-plan-agent 접속
2. **호스트 만들기(연결)** → **GitHub** 선택 → 리전 `asia-northeast3`, 이름 `github-conn`
3. GitHub 로그인 창에서 **Google Cloud Build 앱 설치**를 허용하고 `Dongjin-1203/trip-plan-agent` 저장소를 선택
4. **저장소 연결**에서 `trip-plan-agent`를 연결 (등록 이름은 보통 `Dongjin-1203-trip-plan-agent`)

## 4단계. 트리거 만들기
```bash
bash infra/create-triggers.sh
```
- `backend/**`가 바뀌면 백엔드만, `frontend/**`가 바뀌면 웹만 자동 배포되는 트리거 2개가 만들어집니다.
- 연결/저장소 이름이 다르면 스크립트가 지금 연결된 이름을 보여줍니다. `CONNECTION=... REPO_RESOURCE=... bash infra/create-triggers.sh`로 바꿔 실행하세요.

## 5단계. 코드 올리기 → 자동 배포
`main` 브랜치에 push하면 트리거가 실행됩니다. 진행 상황:
https://console.cloud.google.com/cloud-build/builds;region=asia-northeast3?project=trip-plan-agent

첫 배포 순서: **백엔드를 먼저**(웹이 호출할 대상), 그다음 웹. 두 트리거는 서로 독립이라 처음엔 백엔드 → 웹 순서로 push하거나, 한 번에 push한 뒤 웹이 실패하면 **다시 실행**(재시도)하세요.

## 6단계. 배포 확인
```bash
# 웹 주소 (공개)
gcloud run services describe travel-web --region asia-northeast3 --format="value(status.url)"

# 백엔드는 비공개이므로 인증 없이 부르면 403이어야 합니다
# (참고: /healthz 는 Cloud Run이 가로채는 경로라 404가 나오니 /readyz 로 확인합니다)
curl -s -o /dev/null -w "%{http_code}\n" "$(gcloud run services describe travel-api --region asia-northeast3 --format='value(status.url)')/readyz"
```
- 웹 주소를 브라우저로 열어 **장소 → 날씨 → 초안 → 맛집 폼** 순서로 써 보세요.
- 시크릿 창(다른 쿠키)에서 열었을 때 **이전 대화가 보이지 않아야** 합니다.
- 한도를 넘기면(분당 8회) "요청이 너무 많아요" 안내가 나옵니다.

## 문제가 생겼을 때
| 증상 | 확인 |
|---|---|
| 빌드가 `pytest`에서 실패 | 빌드 로그의 실패한 테스트 이름 확인 |
| 백엔드 배포 후 `502/503` | `gcloud run services logs read travel-api --region asia-northeast3 --limit 50` |
| DB 오류 | `DATABASE_URL` 시크릿 값 존재 여부, 서비스 계정의 `roles/cloudsql.client` |
| 웹이 "백엔드에 연결할 수 없음" | 백엔드 `roles/run.invoker`에 `travel-web-sa`가 있는지: `gcloud run services get-iam-policy travel-api --region asia-northeast3` |
| 키 오류 | Secret Manager에 해당 시크릿의 **버전**이 있는지 (값을 바꾸면 새 버전을 추가하고 재배포) |
| LangSmith에 트레이스가 없음 | `LANGSMITH_API_KEY` 시크릿에 값이 있었는지(없으면 트레이싱이 꺼진 채 배포됨) |

## 정리(삭제)
쓰지 않으면 비용이 나가는 것부터 지웁니다.
```bash
gcloud sql instances delete travel-db
gcloud run services delete travel-web --region asia-northeast3
gcloud run services delete travel-api --region asia-northeast3
```
