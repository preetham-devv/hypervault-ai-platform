# =============================================================================
# variables.tf — All configurable inputs for the HyperVault AI Platform
# =============================================================================

# ── Project & region ──────────────────────────────────────────────────────────

variable "project_id" {
  description = "GCP project ID where all resources will be created."
  type        = string
}

variable "region" {
  description = "Primary GCP region for AlloyDB, Cloud Run, and Vertex AI."
  type        = string
  default     = "us-central1"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_network" {
  description = "Name of the VPC network to use for AlloyDB private access."
  type        = string
  default     = "hypervault-vpc"
}

variable "vpc_subnet_cidr" {
  description = "CIDR block for the primary subnet used by the VPC connector."
  type        = string
  default     = "10.10.0.0/24"
}

variable "psa_range_name" {
  description = "Name of the allocated IP range for Private Services Access (AlloyDB)."
  type        = string
  default     = "alloydb-psa-range"
}

variable "psa_prefix_length" {
  description = "Prefix length for the PSA IP range. /16 gives AlloyDB enough address space."
  type        = number
  default     = 16
}

variable "vpc_connector_name" {
  description = "Name of the Serverless VPC Access connector for Cloud Run → AlloyDB traffic."
  type        = string
  default     = "hypervault-connector"
}

variable "vpc_connector_cidr" {
  description = "CIDR range used exclusively by the VPC connector (/28 required)."
  type        = string
  default     = "10.10.1.0/28"
}

# ── AlloyDB ───────────────────────────────────────────────────────────────────

variable "cluster_name" {
  description = "AlloyDB cluster name."
  type        = string
  default     = "hypervault-cluster"
}

variable "instance_name" {
  description = "AlloyDB primary instance name."
  type        = string
  default     = "hypervault-primary"
}

variable "alloydb_cpu_count" {
  description = "Number of vCPUs for the AlloyDB primary instance (2, 4, 8, 16, 32, 64)."
  type        = number
  default     = 4
}

variable "db_name" {
  description = "Name of the application database to create inside AlloyDB."
  type        = string
  default     = "hr_platform"
}

variable "db_password" {
  description = "Password for the AlloyDB 'postgres' superuser. Marked sensitive — never logged."
  type        = string
  sensitive   = true
}

# ── Vertex AI / Gemini ────────────────────────────────────────────────────────

variable "vertex_ai_model" {
  description = "Gemini model ID registered with AlloyDB google_ml integration."
  type        = string
  default     = "gemini-2.0-flash-001"
}

variable "vertex_embedding_model" {
  description = "Embedding model ID registered with AlloyDB google_ml integration."
  type        = string
  default     = "text-embedding-005"
}

# ── Cloud Run ─────────────────────────────────────────────────────────────────

variable "cloud_run_service_name" {
  description = "Name of the Cloud Run service that hosts the Streamlit dashboard."
  type        = string
  default     = "hypervault-ai-platform"
}

variable "cloud_run_image" {
  description = "Full container image URI for the Cloud Run service (e.g. gcr.io/PROJECT/IMAGE:TAG)."
  type        = string
}

variable "cloud_run_min_instances" {
  description = "Minimum number of Cloud Run instances (0 = scale to zero)."
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum number of Cloud Run instances to prevent runaway scaling."
  type        = number
  default     = 5
}

variable "cloud_run_memory" {
  description = "Memory limit per Cloud Run instance."
  type        = string
  default     = "1Gi"
}

variable "cloud_run_cpu" {
  description = "CPU limit per Cloud Run instance."
  type        = string
  default     = "1"
}

# ── Terraform state bucket (referenced in backend config docs) ────────────────

variable "tf_state_bucket" {
  description = "GCS bucket used for Terraform state. Not consumed by resources — documentation only."
  type        = string
  default     = ""
}
