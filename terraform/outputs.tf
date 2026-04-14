# =============================================================================
# outputs.tf — Values emitted after `terraform apply`
#
# Use these to configure .env for local dev or to wire up CI/CD pipelines.
# Sensitive outputs are marked so Terraform redacts them in logs.
# =============================================================================

# ── AlloyDB ───────────────────────────────────────────────────────────────────

output "alloydb_cluster_id" {
  description = "Full AlloyDB cluster resource name."
  value       = google_alloydb_cluster.main.id
}

output "alloydb_ip" {
  description = "Private IP address of the AlloyDB primary instance. Set as ALLOYDB_IP in .env for local dev via VPN/proxy."
  value       = google_alloydb_instance.primary.ip_address
}

output "alloydb_connection_name" {
  description = "AlloyDB connection name for the Cloud SQL Python Connector (project/region/cluster/instance)."
  value       = "${var.project_id}/${var.region}/${var.cluster_name}/${var.instance_name}"
}

# ── Cloud Run ─────────────────────────────────────────────────────────────────

output "cloud_run_url" {
  description = "Public HTTPS URL of the deployed HyperVault Streamlit dashboard."
  value       = google_cloud_run_v2_service.app.uri
}

output "cloud_run_service_name" {
  description = "Cloud Run service name (useful for gcloud run deploy --service)."
  value       = google_cloud_run_v2_service.app.name
}

# ── IAM ───────────────────────────────────────────────────────────────────────

output "service_account_email" {
  description = "Email of the Cloud Run service account. Use this to grant additional permissions."
  value       = google_service_account.cloud_run.email
}

output "alloydb_service_agent_email" {
  description = "AlloyDB Google-managed service agent email (has roles/aiplatform.user)."
  value       = local.alloydb_service_agent
}

# ── Networking ────────────────────────────────────────────────────────────────

output "vpc_network_id" {
  description = "Self-link of the VPC network."
  value       = google_compute_network.vpc.self_link
}

output "vpc_connector_id" {
  description = "Serverless VPC Access connector ID used by Cloud Run."
  value       = google_vpc_access_connector.connector.id
}

# ── Secret Manager ────────────────────────────────────────────────────────────

output "db_password_secret_id" {
  description = "Secret Manager secret ID holding the AlloyDB password."
  value       = google_secret_manager_secret.db_password.secret_id
}

# ── Convenience .env block ────────────────────────────────────────────────────
#
# After `terraform output -raw env_block` you can paste this directly into .env.

output "env_block" {
  description = "Ready-to-paste .env block for local development."
  sensitive   = true # Contains the connection name; redacted in CI logs.
  value       = <<-ENV
    GOOGLE_CLOUD_PROJECT=${var.project_id}
    GOOGLE_CLOUD_LOCATION=${var.region}
    ALLOYDB_CLUSTER=${var.cluster_name}
    ALLOYDB_INSTANCE=${var.instance_name}
    ALLOYDB_REGION=${var.region}
    ALLOYDB_DATABASE=${var.db_name}
    ALLOYDB_USER=postgres
    ALLOYDB_CONNECTION_NAME=${var.project_id}/${var.region}/${var.cluster_name}/${var.instance_name}
    ALLOYDB_IP=${google_alloydb_instance.primary.ip_address}
    VERTEX_AI_MODEL=${var.vertex_ai_model}
    VERTEX_AI_EMBEDDING_MODEL=${var.vertex_embedding_model}
    VERTEX_AI_ENDPOINT_REGION=${var.region}
  ENV
}
