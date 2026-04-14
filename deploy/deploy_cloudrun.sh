#!/bin/bash
# ============================================================
# Deploy AlloyDB AI Platform to Cloud Run
# ============================================================
set -euo pipefail

source .env 2>/dev/null || true

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE_NAME:-alloydb-ai-platform}"
SA="${CLOUD_RUN_SERVICE_ACCOUNT:-}"

echo "▸ Deploying $SERVICE to Cloud Run ($REGION)"

# Build and deploy from source
gcloud run deploy "$SERVICE" \
  --source=. \
  --dockerfile=deploy/Dockerfile \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=1Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=5 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-env-vars="ALLOYDB_CONNECTION_NAME=${ALLOYDB_CONNECTION_NAME:-}" \
  --set-env-vars="ALLOYDB_DATABASE=${ALLOYDB_DATABASE:-hr_platform}" \
  --set-env-vars="ALLOYDB_USER=${ALLOYDB_USER:-postgres}" \
  ${SA:+--service-account="$SA"}

URL=$(gcloud run services describe "$SERVICE" \
  --region="$REGION" --project="$PROJECT_ID" \
  --format="value(status.url)")

echo ""
echo "✓ Deployed: $URL"
