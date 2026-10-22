#!/usr/bin/env bash
# 여행 챗봇 GCP 초기 설정. 여러 번 실행해도 안전하다(이미 있는 것은 건너뜀).
# 실행: Git Bash 또는 Cloud Shell에서  bash infra/setup-gcp.sh
#
# 하는 일: API 활성화 → Artifact Registry → 서비스 계정 3개 → Secret Manager → Cloud SQL(PostgreSQL)
# 하지 않는 일: Cloud Run 서비스 배포(Cloud Build가 합니다), GitHub 연결(콘솔에서 직접), 결제 연결(콘솔에서 직접)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-trip-plan-agent}"
REGION="${REGION:-asia-northeast3}"          # 서울
AR_REPO="${AR_REPO:-travel}"
DB_INSTANCE="${DB_INSTANCE:-travel-db}"
DB_NAME="${DB_NAME:-travel}"
DB_USER="${DB_USER:-travel_app}"

API_SA="travel-api-sa"      # 백엔드 실행용
WEB_SA="travel-web-sa"      # 웹 실행용
BUILD_SA="travel-build-sa"  # Cloud Build 트리거용
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"

step() { printf '\n== %s\n' "$1"; }
ok()   { printf '   OK  %s\n' "$1"; }
skip() { printf '   --  %s (이미 있음)\n' "$1"; }

step "0. 사전 확인 (프로젝트: ${PROJECT_ID}, 리전: ${REGION})"
command -v gcloud >/dev/null 2>&1 || { echo "gcloud를 찾을 수 없어요. 새 터미널을 열거나 PATH를 확인하세요."; exit 1; }
ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"
[ -n "$ACCOUNT" ] || { echo "로그인이 필요해요: gcloud auth login"; exit 1; }
echo "   로그인 계정: $ACCOUNT"
gcloud projects describe "$PROJECT_ID" --format='value(projectId)' >/dev/null || { echo "프로젝트 ${PROJECT_ID}를 찾을 수 없어요."; exit 1; }
if [ "$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')" != "True" ]; then
  echo "이 프로젝트에 결제 계정이 연결되어 있지 않아요. 콘솔 > 결제에서 연결한 뒤 다시 실행하세요."
  echo "https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}"
  exit 1
fi
gcloud config set project "$PROJECT_ID" >/dev/null

step "1. API 활성화 (처음에는 몇 분 걸려요)"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com sqladmin.googleapis.com iam.googleapis.com \
  --project "$PROJECT_ID"
ok "run, cloudbuild, artifactregistry, secretmanager, sqladmin, iam"

step "2. Artifact Registry 저장소 (컨테이너 이미지 보관)"
if gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1; then
  skip "$AR_REPO"
else
  gcloud artifacts repositories create "$AR_REPO" --repository-format=docker --location "$REGION" \
    --description="여행 챗봇 컨테이너 이미지"
  ok "$AR_REPO"
fi

step "3. 서비스 계정 (필요한 최소 권한만)"
create_sa() {
  if gcloud iam service-accounts describe "$1@${SA_DOMAIN}" >/dev/null 2>&1; then
    skip "$1"
  else
    gcloud iam service-accounts create "$1" --display-name "$2"
    ok "$1"
  fi
}
create_sa "$API_SA" "여행 챗봇 백엔드"
create_sa "$WEB_SA" "여행 챗봇 웹"
create_sa "$BUILD_SA" "여행 챗봇 Cloud Build"

bind() {  # bind <서비스 계정> <역할>
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:$1@${SA_DOMAIN}" --role "$2" --condition=None >/dev/null
}
bind "$API_SA" roles/cloudsql.client                 # Cloud SQL 접속
bind "$BUILD_SA" roles/run.admin                      # Cloud Run 배포
bind "$BUILD_SA" roles/artifactregistry.writer        # 이미지 푸시
bind "$BUILD_SA" roles/logging.logWriter              # 빌드 로그
bind "$BUILD_SA" roles/secretmanager.viewer           # 배포 때 LangSmith 키가 있는지 확인(값은 읽지 못함)
# 빌드 계정이 실행용 서비스 계정을 "대신 사용"할 수 있어야 배포할 수 있다
for sa in "$API_SA" "$WEB_SA"; do
  gcloud iam service-accounts add-iam-policy-binding "$sa@${SA_DOMAIN}" \
    --member "serviceAccount:${BUILD_SA}@${SA_DOMAIN}" --role roles/iam.serviceAccountUser >/dev/null
done
ok "역할 연결 완료"

step "4. Secret Manager"
has_version() { gcloud secrets versions list "$1" --limit 1 --format='value(name)' 2>/dev/null | grep -q .; }
ensure_secret() {
  if gcloud secrets describe "$1" >/dev/null 2>&1; then skip "시크릿 $1"; else
    gcloud secrets create "$1" --replication-policy=automatic >/dev/null; ok "시크릿 $1 생성"; fi
}
# 값은 이 터미널에 직접 입력합니다(화면에 표시되지 않고, 채팅·파일에 남지 않아요). 이미 값이 있으면 건너뜁니다.
prompt_secret() {  # prompt_secret <이름> <설명> <필수 여부 yes|no>
  ensure_secret "$1"
  if has_version "$1"; then skip "$1 값"; return; fi
  local value=""
  read -rsp "   $2 를 입력하세요$( [ "$3" = no ] && echo ' (없으면 그냥 Enter)'): " value; echo
  if [ -z "$value" ]; then
    [ "$3" = yes ] && { echo "   $1 값이 필요해요. 다시 실행해 주세요."; exit 1; }
    echo "   $1 는 건너뜁니다."; return
  fi
  printf '%s' "$value" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  ok "$1 값 저장"
}
prompt_secret OPENAI_API_KEY      "OpenAI API 키" yes
prompt_secret KAKAO_REST_API_KEY  "카카오 REST API 키" yes
prompt_secret LANGSMITH_API_KEY   "LangSmith API 키(트레이싱용, 선택)" no

step "5. Cloud SQL (PostgreSQL) — 켜져 있는 동안 계속 과금돼요"
if gcloud sql instances describe "$DB_INSTANCE" >/dev/null 2>&1; then
  skip "인스턴스 $DB_INSTANCE"
else
  echo "   인스턴스를 만들고 있어요(5~10분 걸립니다)..."
  gcloud sql instances create "$DB_INSTANCE" \
    --database-version=POSTGRES_16 --edition=ENTERPRISE --tier=db-f1-micro \
    --region "$REGION" --availability-type=zonal --storage-size=10
  ok "인스턴스 $DB_INSTANCE (db-f1-micro, 서울)"
fi
if gcloud sql databases describe "$DB_NAME" --instance "$DB_INSTANCE" >/dev/null 2>&1; then
  skip "데이터베이스 $DB_NAME"
else
  gcloud sql databases create "$DB_NAME" --instance "$DB_INSTANCE" >/dev/null; ok "데이터베이스 $DB_NAME"
fi

ensure_secret DATABASE_URL
if has_version DATABASE_URL; then
  skip "DATABASE_URL 값(비밀번호를 다시 만들지 않아요)"
else
  # 비밀번호는 무작위로 만들어 바로 시크릿에 저장하고, 화면에는 출력하지 않는다. (16진수라 URL에 안전)
  DB_PASSWORD="$(openssl rand -hex 24)"
  if gcloud sql users list --instance "$DB_INSTANCE" --format='value(name)' | tr -d '\r' | grep -qx "$DB_USER"; then
    gcloud sql users set-password "$DB_USER" --instance "$DB_INSTANCE" --password "$DB_PASSWORD" >/dev/null
  else
    gcloud sql users create "$DB_USER" --instance "$DB_INSTANCE" --password "$DB_PASSWORD" >/dev/null
  fi
  # Cloud Run은 유닉스 소켓(/cloudsql/...)으로 Cloud SQL에 접속한다
  printf '%s' "postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE}" \
    | gcloud secrets versions add DATABASE_URL --data-file=- >/dev/null
  unset DB_PASSWORD
  ok "DB 사용자 $DB_USER 와 DATABASE_URL 시크릿 저장"
fi

step "6. 백엔드 서비스 계정에 시크릿 읽기 권한"
for secret in OPENAI_API_KEY KAKAO_REST_API_KEY DATABASE_URL LANGSMITH_API_KEY; do
  if gcloud secrets describe "$secret" >/dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding "$secret" \
      --member "serviceAccount:${API_SA}@${SA_DOMAIN}" --role roles/secretmanager.secretAccessor >/dev/null
    ok "$secret"
  fi
done

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
cat <<EOF

설정이 끝났어요. 다음 순서:
  1) GitHub 연결(콘솔):  infra/setup-gcp.md 의 3단계
  2) 트리거 생성:        bash infra/create-triggers.sh
  3) main 브랜치에 push 하면 자동으로 배포됩니다.

배포 후 주소(고정 형식):
  백엔드(비공개): https://travel-api-${PROJECT_NUMBER}.${REGION}.run.app
  웹(공개):       https://travel-web-${PROJECT_NUMBER}.${REGION}.run.app
EOF
