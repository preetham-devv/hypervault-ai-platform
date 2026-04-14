# =============================================================================
# cloud_run.tf — Cloud Run v2 service for the HyperVault Streamlit dashboard
#
# Traffic flow:
#   Internet → Cloud Run → VPC connector → AlloyDB (private IP)
#                       ↘ Vertex AI (public, via google APIs)
# =============================================================================

resource "google_cloud_run_v2_service" "app" {
  provider = google

  name     = var.cloud_run_service_name
  location = var.region
  project  = var.project_id

  # INTERNAL_AND_CLOUD_LOAD_BALANCING restricts direct invocations to internal
  # traffic and load balancers — change to "EXTERNAL" only if you need raw
  # public access without a load balancer in front.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    # ── Identity ───────────────────────────────────────────────────────────────
    service_account = google_service_account.cloud_run.email

    # ── Scaling ────────────────────────────────────────────────────────────────
    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    # ── VPC networking ─────────────────────────────────────────────────────────
    # Route all egress through the VPC connector so AlloyDB's private IP
    # is reachable. "ALL_TRAFFIC" ensures Vertex AI calls also go through
    # the VPC (important if you add private Google APIs / VPC Service Controls).
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "ALL_TRAFFIC"
    }

    # ── Container ──────────────────────────────────────────────────────────────
    containers {
      image = var.cloud_run_image

      # ── Resources ────────────────────────────────────────────────────────────
      resources {
        limits = {
          memory = var.cloud_run_memory
          cpu    = var.cloud_run_cpu
        }
        # cpu_idle = false keeps CPU allocated between requests — required for
        # Streamlit's long-running WebSocket connections.
        cpu_idle          = false
        startup_cpu_boost = true
      }

      # ── Environment variables ─────────────────────────────────────────────────
      # Non-sensitive config is passed as plain env vars.
      # The DB password is injected from Secret Manager (see env block below).

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "ALLOYDB_CLUSTER"
        value = var.cluster_name
      }
      env {
        name  = "ALLOYDB_INSTANCE"
        value = var.instance_name
      }
      env {
        name  = "ALLOYDB_REGION"
        value = var.region
      }
      env {
        name  = "ALLOYDB_DATABASE"
        value = var.db_name
      }
      env {
        name  = "ALLOYDB_USER"
        value = "postgres"
      }
      env {
        name  = "ALLOYDB_CONNECTION_NAME"
        # AlloyDB connection name format: project/region/cluster/instance
        value = "${var.project_id}/${var.region}/${var.cluster_name}/${var.instance_name}"
      }
      env {
        name  = "VERTEX_AI_MODEL"
        value = var.vertex_ai_model
      }
      env {
        name  = "VERTEX_AI_EMBEDDING_MODEL"
        value = var.vertex_embedding_model
      }
      env {
        name  = "VERTEX_AI_ENDPOINT_REGION"
        value = var.region
      }
      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      # ── Sensitive env vars from Secret Manager ────────────────────────────────
      env {
        name = "ALLOYDB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      # ── Startup probe ─────────────────────────────────────────────────────────
      # Streamlit takes a few seconds to start — give it up to 30s before
      # Cloud Run marks the instance as failed.
      startup_probe {
        http_get {
          path = "/_stcore/health"
          port = 8501
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6 # 30s total (6 × 5s)
        timeout_seconds       = 3
      }

      # ── Liveness probe ────────────────────────────────────────────────────────
      liveness_probe {
        http_get {
          path = "/_stcore/health"
          port = 8501
        }
        period_seconds    = 30
        failure_threshold = 3
        timeout_seconds   = 5
      }

      ports {
        container_port = 8501 # Streamlit default port
      }
    }

    # ── Request timeout ────────────────────────────────────────────────────────
    # Gemini reasoning calls can take several seconds. 300s covers the p99.
    timeout = "300s"

    # ── Annotations ───────────────────────────────────────────────────────────
    annotations = {
      "autoscaling.knative.dev/maxScale" = tostring(var.cloud_run_max_instances)
    }
  }

  # Route 100% of traffic to the latest revision automatically.
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_alloydb_instance.primary,
    google_vpc_access_connector.connector,
    google_service_account.cloud_run,
    google_secret_manager_secret_version.db_password,
    google_project_iam_member.cloud_run_alloydb_client,
    google_project_iam_member.cloud_run_vertex_user,
    google_project_iam_member.cloud_run_secret_accessor,
  ]
}
