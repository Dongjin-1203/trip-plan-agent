#!/usr/bin/env bash
# GitHub push → Cloud Build 자동 배포 트리거 2개(백엔드·웹)를 만든다. 여러 번 실행해도 안전하다.
# 먼저 콘솔에서 GitHub 연결(2세대)을 만들어야 한다: infra/setup-gcp.md 3단계
# 실행: bash infra/create-triggers.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-trip-plan-agent}"
REGION="${REGION:-asia-northeast3}"
CONNECTION="${CONNECTION:-github-conn}"                    # 콘솔에서 만든 연결 이름
REPO_RESOURCE="${REPO_RESOURCE:-Dongjin-1203-trip-plan-agent}"  # 연결에 등록된 저장소 이름(보통 소유자-저장소)
BRANCH="${BRANCH:-main}"
BUILD_SA="travel-build-sa@${PROJECT_ID}.iam.gserviceaccount.com"
REPO="projects/${PROJECT_ID}/locations/${REGION}/connections/${CONNECTION}/repositories/${REPO_RESOURCE}"

command -v gcloud >/dev/null 2>&1 || { echo "gcloud를 찾을 수 없어요."; exit 1; }

echo "== 연결된 저장소 확인"
if ! gcloud builds repositories list --connection "$CONNECTION" --region "$REGION" --project "$PROJECT_ID" \
     --format='value(name)' 2>/dev/null | grep -q "/repositories/${REPO_RESOURCE}\$"; then
  echo "연결 '${CONNECTION}'에서 저장소 '${REPO_RESOURCE}'를 찾지 못했어요. 지금 연결된 저장소:"
  gcloud builds repositories list --connection "$CONNECTION" --region "$REGION" --project "$PROJECT_ID" \
    --format='value(name)' 2>&1 | sed 's|.*/repositories/|   - |' || true
  echo "REPO_RESOURCE=<위 이름> bash infra/create-triggers.sh 로 다시 실행하세요."
  exit 1
fi

create_trigger() {  # create_trigger <이름> <빌드 설정 파일> <감시할 경로>
  local name="$1" config="$2" paths="$3"
  if gcloud builds triggers describe "$name" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "   --  $name (이미 있음)"
    return
  fi
  gcloud builds triggers create github \
    --name "$name" --region "$REGION" --project "$PROJECT_ID" \
    --repository "$REPO" --branch-pattern "^${BRANCH}\$" \
    --build-config "$config" --included-files "$paths" \
    --service-account "projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}"
  echo "   OK  $name"
}

echo "== 트리거 생성 (브랜치: ${BRANCH})"
# 백엔드 파일이 바뀌면 백엔드만, 프론트 파일이 바뀌면 웹만 배포한다
create_trigger travel-api-deploy infra/cloudbuild.backend.yaml  "backend/**,infra/cloudbuild.backend.yaml"
create_trigger travel-web-deploy infra/cloudbuild.frontend.yaml "frontend/**,infra/cloudbuild.frontend.yaml"

echo
echo "완료. 이제 ${BRANCH} 브랜치에 push 하면 자동으로 배포됩니다."
echo "빌드 진행 상황: https://console.cloud.google.com/cloud-build/builds;region=${REGION}?project=${PROJECT_ID}"
