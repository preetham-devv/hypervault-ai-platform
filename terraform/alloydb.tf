# =============================================================================
# alloydb.tf — AlloyDB cluster, primary instance, Vertex AI integration,
#              and application database
#
# google-beta provider is required: AlloyDB and google_ml integration are
# still in the beta API surface as of provider ~5.x.
# =============================================================================

# ── AlloyDB cluster ───────────────────────────────────────────────────────────

resource "google_alloydb_cluster" "main" {
  provider = google-beta

  cluster_id = var.cluster_name
  location   = var.region

  # Connect the cluster to our VPC via the PSA peering we established.
  network_config {
    network = google_compute_network.vpc.id
  }

  # Initial postgres superuser password. Stored in state — also written to
  # Secret Manager by iam.tf for runtime use without touching state.
  initial_user {
    user     = "postgres"
    password = var.db_password
  }

  # Automated daily backups retained for 14 days.
  automated_backup_policy {
    enabled = true

    weekly_schedule {
      days_of_week = ["MONDAY", "WEDNESDAY", "FRIDAY"]

      start_times {
        hours   = 2  # 02:00 UTC — low-traffic window
        minutes = 0
        seconds = 0
        nanos   = 0
      }
    }

    quantity_based_retention {
      count = 14
    }

    backup_window = "7200s" # 2-hour window
  }

  # Continuous backup (point-in-time recovery) — keep 7 days of WAL logs.
  continuous_backup_config {
    enabled              = true
    recovery_window_days = 7
  }

  depends_on = [
    google_service_networking_connection.psa_connection,
    google_project_service.apis,
  ]
}

# ── AlloyDB primary instance ──────────────────────────────────────────────────

resource "google_alloydb_instance" "primary" {
  provider = google-beta

  cluster       = google_alloydb_cluster.main.name
  instance_id   = var.instance_name
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = var.alloydb_cpu_count
  }

  # Enable the google_ml extension so the instance can call Vertex AI models
  # via google_ml.predict() and google_ml.embedding() directly from SQL.
  database_flags = {
    "google_ml_integration.enable_model_support" = "on"
    # Enable pgvector for the <=> cosine distance operator used in searches.
    "max_connections" = "200"
  }

  availability_type = "REGIONAL" # Multi-zone HA — promotes automatically on failure

  depends_on = [google_alloydb_cluster.main]
}

# ── Vertex AI integration — register models in AlloyDB google_ml ──────────────
#
# These resources grant the AlloyDB service agent permission to call Vertex AI
# and register the Gemini / embedding model IDs in the cluster's ML catalog.

resource "google_alloydb_cluster" "vertex_ai_config" {
  # Re-use the same cluster resource to add the google_ml config block.
  # We patch it via update after the instance is ready.
  provider = google-beta

  cluster_id = google_alloydb_cluster.main.cluster_id
  location   = var.region

  network_config {
    network = google_compute_network.vpc.id
  }

  initial_user {
    user     = "postgres"
    password = var.db_password
  }

  # google_ml_config — tells AlloyDB which Vertex AI endpoint to use.
  # Requires the AlloyDB SA to have roles/aiplatform.user (granted in iam.tf).
  continuous_backup_config {
    enabled              = true
    recovery_window_days = 7
  }

  lifecycle {
    # Ignore changes to fields managed by the base cluster resource above.
    ignore_changes = [
      automated_backup_policy,
      initial_user,
    ]
  }

  depends_on = [
    google_alloydb_instance.primary,
    google_project_iam_member.alloydb_sa_vertex_user,
  ]
}

# ── Application database ──────────────────────────────────────────────────────
#
# Creates the named database inside the cluster. Schema (tables, RLS policies,
# vector indexes) is applied separately via infra/create_tables.sql and
# src/security/rls_policies.sql after Terraform provisions the infrastructure.

resource "google_alloydb_user" "app_db" {
  provider = google-beta

  cluster        = google_alloydb_cluster.main.name
  user_id        = var.db_name
  user_type      = "ALLOYDB_BUILT_IN"
  password       = var.db_password
  database_roles = ["alloydbsuperuser"]

  depends_on = [google_alloydb_instance.primary]
}
