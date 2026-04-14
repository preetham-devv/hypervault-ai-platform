# =============================================================================
# iam.tf — Service accounts and IAM bindings
#
# Two service accounts:
#   1. cloud_run_sa  — identity for the Cloud Run service
#   2. (alloydb_sa)  — Google-managed; we only bind roles to it, not create it
#
# Principle of least privilege: each SA gets only the roles it needs.
# =============================================================================

# ── Cloud Run service account ─────────────────────────────────────────────────

resource "google_service_account" "cloud_run" {
  account_id   = "${var.cloud_run_service_name}-sa"
  display_name = "HyperVault Cloud Run Service Account"
  description  = "Identity used by the Cloud Run service to access AlloyDB and Vertex AI."
  project      = var.project_id
}

# Cloud Run SA → AlloyDB: connect to the cluster as a client.
resource "google_project_iam_member" "cloud_run_alloydb_client" {
  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud Run SA → AlloyDB: read database instances (needed by the connector).
resource "google_project_iam_member" "cloud_run_alloydb_viewer" {
  project = var.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud Run SA → Vertex AI: call Gemini and embedding models directly.
# Required when the Python app calls Vertex AI outside of AlloyDB (e.g. GeminiClient).
resource "google_project_iam_member" "cloud_run_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud Run SA → Secret Manager: read the DB password secret at runtime.
resource "google_project_iam_member" "cloud_run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud Run SA → Cloud Run itself: invoke the service (for health checks etc.)
resource "google_project_iam_member" "cloud_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# ── AlloyDB service agent — Vertex AI access ──────────────────────────────────
#
# The AlloyDB service agent is Google-managed (not created here).
# We bind roles/aiplatform.user so AlloyDB can call Vertex AI from SQL
# via google_ml.predict() and google_ml.embedding().

locals {
  # Service agent email follows a deterministic pattern: service-<project_number>@...
  alloydb_service_agent = "service-${data.google_project.project.number}@gcp-sa-alloydb.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "alloydb_sa_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${local.alloydb_service_agent}"

  depends_on = [google_project_service.apis]
}

# ── Secret Manager — store DB password for runtime access ─────────────────────
#
# The password is written once from the Terraform variable.
# Cloud Run reads it via Secret Manager rather than an env var to avoid
# the secret appearing in Cloud Run revision configuration (visible in Console).

resource "google_secret_manager_secret" "db_password" {
  secret_id = "hypervault-db-password"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password # sensitive — never logged by Terraform
}

# ── Allow unauthenticated Cloud Run invocations (public dashboard) ────────────
#
# Remove this block if the dashboard should be internal-only. To restrict,
# delete this resource and add IAP or a load balancer with Cloud Armor.

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
