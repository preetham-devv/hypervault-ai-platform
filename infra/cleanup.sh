#!/bin/bash
# ============================================================
# Teardown all resources to avoid billing
# ============================================================
set -euo pipefail

source .env 2>/dev/null || true

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?}"
REGION="${ALLOYDB_REGION:-us-central1}"
CLUSTER="${ALLOYDB_CLUSTER:-ai-platform-cluster}"
CR_SERVICE="${CLOUD_RUN_SERVICE_NAME:-alloydb-ai-platform}"

echo "⚠  This will DELETE all resources in project=$PROJECT_ID"
read -p "Continue? (y/N) " -n 1 -r
echo
[[ $REPLY =~ ^[Yy]$ ]] || exit 0

echo "▸ Deleting Cloud Run service..."
gcloud run services delete "$CR_SERVICE" \
  --region="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true

echo "▸ Deleting AlloyDB instance..."
gcloud alloydb instances delete "${ALLOYDB_INSTANCE:-ai-platform-primary}" \
  --cluster="$CLUSTER" --region="$REGION" \
  --project="$PROJECT_ID" --quiet 2>/dev/null || true

echo "▸ Deleting AlloyDB cluster..."
gcloud alloydb clusters delete "$CLUSTER" \
  --region="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true

echo "✓ All resources deleted"
