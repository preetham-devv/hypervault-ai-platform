#!/bin/bash
# ============================================================
# For quick setup only. Production: use terraform/
# See terraform/networking.tf for the production-grade equivalent
# of this script (VPC, PSA, Serverless VPC connector, firewall rules).
# ============================================================
# VPC + Private Services Access for AlloyDB
# ============================================================
set -euo pipefail

source .env 2>/dev/null || true

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env}"
REGION="${ALLOYDB_REGION:-us-central1}"
NETWORK="${VPC_NETWORK:-default}"
RANGE_NAME="${PRIVATE_IP_RANGE:-alloydb-psa-range}"

echo "▸ Configuring VPC for AlloyDB in project=$PROJECT_ID"

# Enable required APIs
gcloud services enable \
  alloydb.googleapis.com \
  aiplatform.googleapis.com \
  compute.googleapis.com \
  servicenetworking.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$PROJECT_ID" --quiet

# Allocate IP range for Private Services Access
gcloud compute addresses create "$RANGE_NAME" \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="$NETWORK" \
  --project="$PROJECT_ID" 2>/dev/null || echo "  IP range already exists"

# Create private connection
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges="$RANGE_NAME" \
  --network="$NETWORK" \
  --project="$PROJECT_ID" 2>/dev/null || echo "  VPC peering already exists"

echo "✓ VPC configured for AlloyDB"
