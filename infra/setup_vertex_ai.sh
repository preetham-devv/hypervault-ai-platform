#!/usr/bin/env bash
# infra/setup_vertex_ai.sh
# Registers Gemini Flash and text-embedding models with AlloyDB's google_ml
# integration so they can be called via google_ml.predict() and
# google_ml.embedding() without leaving the database.
#
# Usage:
#   bash infra/setup_vertex_ai.sh

set -euo pipefail

if [[ -f .env ]]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Must set GOOGLE_CLOUD_PROJECT}"
REGION="${VERTEX_AI_LOCATION:-us-central1}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.0-flash-001}"
EMBEDDING_MODEL="${EMBEDDING_MODEL_ID:-text-embedding-005}"

echo "==> [1/3] Granting Vertex AI User role to AlloyDB service account"
ALLOYDB_SA="service-$(gcloud projects describe "${PROJECT_ID}" \
  --format='value(projectNumber)')@gcp-sa-alloydb.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${ALLOYDB_SA}" \
  --role="roles/aiplatform.user" \
  --condition=None

echo "==> [2/3] Registering models in AlloyDB google_ml catalog"
echo "    Run the following SQL against your AlloyDB instance:"

cat <<SQL
-- Register Gemini Flash for google_ml.predict()
CALL google_ml.create_model(
    model_id         => '${GEMINI_MODEL}',
    model_provider   => 'google',
    model_type       => 'text_generation',
    model_qualified_name => 'publishers/google/models/${GEMINI_MODEL}',
    model_region     => '${REGION}'
);

-- Register text-embedding for google_ml.embedding()
CALL google_ml.create_model(
    model_id         => '${EMBEDDING_MODEL}',
    model_provider   => 'google',
    model_type       => 'text_embedding',
    model_qualified_name => 'publishers/google/models/${EMBEDDING_MODEL}',
    model_region     => '${REGION}'
);

-- Verify
SELECT model_id, model_type, model_provider
FROM google_ml.model_info
ORDER BY model_id;
SQL

echo ""
echo "==> [3/3] Creating Secret Manager secrets for production credentials"
echo "    Storing DB password in Secret Manager (recommended over .env in prod)"

gcloud secrets create alloydb-ai-db-password \
  --replication-policy="automatic" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "Secret already exists"

echo "    To set the secret value:"
echo "    echo -n 'YOUR_PASSWORD' | gcloud secrets versions add alloydb-ai-db-password --data-file=-"
echo ""
echo "==> Done. Vertex AI models registered and IAM configured."
