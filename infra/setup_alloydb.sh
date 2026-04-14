#!/bin/bash
# ============================================================
# Provision AlloyDB cluster + instance with Vertex AI integration
# ============================================================
set -euo pipefail

source .env 2>/dev/null || true

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env}"
REGION="${ALLOYDB_REGION:-us-central1}"
CLUSTER="${ALLOYDB_CLUSTER:-ai-platform-cluster}"
INSTANCE="${ALLOYDB_INSTANCE:-ai-platform-primary}"
PASSWORD="${ALLOYDB_PASSWORD:?Set ALLOYDB_PASSWORD in .env}"
NETWORK="${VPC_NETWORK:-default}"
DATABASE="${ALLOYDB_DATABASE:-hr_platform}"

echo "▸ Creating AlloyDB cluster: $CLUSTER"

gcloud alloydb clusters create "$CLUSTER" \
  --region="$REGION" \
  --password="$PASSWORD" \
  --network="projects/$PROJECT_ID/global/networks/$NETWORK" \
  --project="$PROJECT_ID" \
  --quiet 2>/dev/null || echo "  Cluster already exists"

echo "▸ Creating primary instance: $INSTANCE"

gcloud alloydb instances create "$INSTANCE" \
  --cluster="$CLUSTER" \
  --region="$REGION" \
  --instance-type=PRIMARY \
  --cpu-count=4 \
  --project="$PROJECT_ID" \
  --quiet 2>/dev/null || echo "  Instance already exists"

# Get instance IP
INSTANCE_IP=$(gcloud alloydb instances describe "$INSTANCE" \
  --cluster="$CLUSTER" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="value(ipAddress)" 2>/dev/null)

echo "▸ AlloyDB IP: $INSTANCE_IP"

# Enable Vertex AI integration on the cluster
gcloud alloydb clusters update "$CLUSTER" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --enable-google-ml-integration \
  --quiet 2>/dev/null || echo "  ML integration already enabled"

# Create the database
echo "▸ Creating database: $DATABASE"
PGPASSWORD="$PASSWORD" psql -h "$INSTANCE_IP" -U postgres -c \
  "CREATE DATABASE $DATABASE;" 2>/dev/null || echo "  Database already exists"

# Grant Vertex AI service agent access
SA="service-$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')@gcp-sa-alloydb.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" \
  --role="roles/aiplatform.user" \
  --quiet 2>/dev/null || true

echo ""
echo "============================================"
echo "✓ AlloyDB ready"
echo "  Cluster:  $CLUSTER"
echo "  Instance: $INSTANCE"
echo "  IP:       $INSTANCE_IP"
echo "  Database: $DATABASE"
echo ""
echo "Next steps:"
echo "  1. Update ALLOYDB_IP=$INSTANCE_IP in .env"
echo "  2. psql -h $INSTANCE_IP -U postgres -d $DATABASE -f infra/create_tables.sql"
echo "  3. psql -h $INSTANCE_IP -U postgres -d $DATABASE -f infra/seed_data.sql"
echo "  4. psql -h $INSTANCE_IP -U postgres -d $DATABASE -f src/security/rls_policies.sql"
echo "  5. psql -h $INSTANCE_IP -U postgres -d $DATABASE -f src/vector_engine/batch_embeddings.sql"
echo "============================================"
