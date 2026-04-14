# =============================================================================
# networking.tf — VPC, Private Services Access, and Serverless VPC connector
#
# Architecture:
#   Cloud Run → VPC connector → private subnet → PSA peering → AlloyDB
#
# AlloyDB requires Private Services Access (VPC peering to Google's network).
# Cloud Run requires a Serverless VPC Access connector to reach private IPs.
# =============================================================================

# ── VPC network ───────────────────────────────────────────────────────────────

resource "google_compute_network" "vpc" {
  provider = google

  name                    = var.vpc_network
  auto_create_subnetworks = false # Custom subnets only — no default /20 ranges

  depends_on = [google_project_service.apis]
}

# ── Primary subnet (used by VPC connector and general workloads) ──────────────

resource "google_compute_subnetwork" "primary" {
  provider = google

  name          = "${var.vpc_network}-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.vpc_subnet_cidr

  # Enable flow logs for security auditing and traffic visibility.
  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# ── Private Services Access — IP range for AlloyDB ───────────────────────────
#
# AlloyDB lives in Google's managed VPC. PSA creates a peering between
# our VPC and Google's so AlloyDB gets a private IP reachable from our subnet.

resource "google_compute_global_address" "psa_range" {
  provider = google

  name          = var.psa_range_name
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.psa_prefix_length
  network       = google_compute_network.vpc.id

  depends_on = [google_project_service.apis]
}

resource "google_service_networking_connection" "psa_connection" {
  provider = google

  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa_range.name]

  depends_on = [google_project_service.apis]
}

# ── Serverless VPC Access connector ──────────────────────────────────────────
#
# Cloud Run instances are not inside the VPC by default. This connector
# provides a tunnel so Cloud Run can reach AlloyDB's private IP.
# The /28 is exclusively for the connector — do not use it elsewhere.

resource "google_vpc_access_connector" "connector" {
  provider = google

  name          = var.vpc_connector_name
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = var.vpc_connector_cidr

  # Scale connector to match Cloud Run traffic.
  min_instances = 2
  max_instances = 10
  machine_type  = "e2-micro"

  depends_on = [
    google_project_service.apis,
    google_compute_network.vpc,
  ]
}

# ── Firewall: allow Cloud Run connector → AlloyDB (port 5432) ────────────────

resource "google_compute_firewall" "allow_alloydb_from_connector" {
  provider = google

  name    = "${var.vpc_network}-allow-alloydb"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  # Traffic originates from the VPC connector's /28 CIDR.
  source_ranges = [var.vpc_connector_cidr]
  target_tags   = ["alloydb-client"]

  description = "Allow Serverless VPC connector to reach AlloyDB on port 5432."
}

# ── Firewall: deny all other ingress (default-deny posture) ──────────────────

resource "google_compute_firewall" "deny_all_ingress" {
  provider = google

  name      = "${var.vpc_network}-deny-all-ingress"
  network   = google_compute_network.vpc.name
  priority  = 65534 # Lowest priority — catch-all after explicit allows

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  description   = "Default-deny all ingress. Explicit allow rules take precedence."
}
