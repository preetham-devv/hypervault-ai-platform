# =============================================================================
# main.tf — Provider configuration and Terraform backend
#
# Requires:
#   - A GCS bucket for state (set TF_BACKEND_BUCKET env var or edit below)
#   - Application Default Credentials with Owner / Editor on the project
#
# Init:
#   terraform init \
#     -backend-config="bucket=<YOUR_STATE_BUCKET>" \
#     -backend-config="prefix=hypervault-ai-platform"
# =============================================================================

terraform {
  required_version = ">= 1.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # GCS remote backend — state is locked automatically via Cloud Storage.
  # Pass bucket/prefix at init time; never hard-code a bucket name here.
  backend "gcs" {
    # bucket and prefix are supplied via -backend-config flags or a
    # backend.hcl file so they can vary per environment without editing code.
  }
}

# ── Primary provider ──────────────────────────────────────────────────────────
provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Beta provider (required for AlloyDB and some Vertex AI resources) ─────────
provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ── Project data source ───────────────────────────────────────────────────────
# Used throughout to derive project_number without hard-coding it.
data "google_project" "project" {
  project_id = var.project_id
}

# ── Enable required APIs ──────────────────────────────────────────────────────
# Declared here once so every other resource can depend on them.
resource "google_project_service" "apis" {
  for_each = toset([
    "alloydb.googleapis.com",
    "aiplatform.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
    "iam.googleapis.com",
  ])

  project                    = var.project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}
