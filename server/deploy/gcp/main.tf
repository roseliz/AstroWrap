data "google_project" "project" {}

locals {
  sslip         = "${replace(google_compute_address.server.address, ".", "-")}.sslip.io"
  registry      = "${var.region}-docker.pkg.dev/${var.project}/${google_artifact_registry_repository.server.repository_id}"
  image         = "${local.registry}/server:${var.image_tag}"
  caddy_domains = join(", ", distinct([var.domain, local.sslip]))
}

resource "google_project_service" "api" {
  for_each = toset([
    "compute.googleapis.com", "artifactregistry.googleapis.com", "storage.googleapis.com",
    "logging.googleapis.com", "monitoring.googleapis.com", "billingbudgets.googleapis.com",
    "iam.googleapis.com", "cloudresourcemanager.googleapis.com", "iap.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# Image and data
resource "google_artifact_registry_repository" "server" {
  repository_id          = var.name
  location               = var.region
  format                 = "DOCKER"
  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-2"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }
  cleanup_policies {
    id     = "delete-the-rest"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }
  depends_on = [google_project_service.api]
}

resource "google_storage_bucket" "data" {
  name                        = "${var.name}-${data.google_project.project.number}"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  depends_on                  = [google_project_service.api]
}

# IP and firewall
resource "google_compute_address" "server" {
  name       = var.name
  region     = var.region
  depends_on = [google_project_service.api]
}

resource "google_compute_firewall" "web" {
  name          = "${var.name}-web"
  network       = "default"
  description   = "Inbound HTTP and HTTPS (Caddy); also Google's health probes"
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.name]
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
  depends_on = [google_project_service.api]
}

# SSH via IAP
resource "google_compute_firewall" "ssh_iap" {
  name          = "${var.name}-ssh-iap"
  network       = "default"
  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = [var.name]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  depends_on = [google_project_service.api]
}

# Machine permissions
resource "google_service_account" "machine" {
  account_id   = var.name
  display_name = "API server (VM)"
  depends_on   = [google_project_service.api]
}

resource "google_artifact_registry_repository_iam_member" "read_image" {
  repository = google_artifact_registry_repository.server.name
  location   = var.region
  role       = "roles/artifactregistry.reader"
  member     = google_service_account.machine.member
}

resource "google_storage_bucket_iam_member" "read_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectViewer"
  member = google_service_account.machine.member
}

resource "google_project_iam_member" "machine" {
  for_each = toset(["roles/logging.logWriter", "roles/monitoring.metricWriter"])
  project  = var.project
  role     = each.value
  member   = google_service_account.machine.member
}

# Machine
resource "google_compute_instance_template" "server" {
  name_prefix  = "${var.name}-"
  machine_type = var.machine_type
  tags         = [var.name]

  disk {
    boot         = true
    source_image = "debian-cloud/debian-12"
    disk_type    = "pd-balanced"
    disk_size_gb = 10
    auto_delete  = true
  }

  # Data disk, kept
  disk {
    device_name  = var.data_device_name
    disk_type    = "pd-balanced"
    disk_size_gb = var.data_disk_gb
    auto_delete  = false
    boot         = false
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.server.address
    }
  }

  service_account {
    email  = google_service_account.machine.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup.sh.tftpl", {
      registry = "${var.region}-docker.pkg.dev"
      image    = local.image
      bucket   = google_storage_bucket.data.name
      device   = var.data_device_name
      domains  = local.caddy_domains
      cors     = var.cors
    })
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Auto-healing
resource "google_compute_health_check" "api" {
  name                = "${var.name}-api"
  check_interval_sec  = 90
  timeout_sec         = 15
  healthy_threshold   = 1
  unhealthy_threshold = 10
  http_health_check {
    port         = 80
    request_path = "/api/health"
    response     = "\"ready\":true"
  }
  depends_on = [google_project_service.api]
}

resource "google_compute_instance_group_manager" "server" {
  name               = var.name
  base_instance_name = var.name
  zone               = var.zone
  target_size        = 1

  version {
    instance_template = google_compute_instance_template.server.self_link_unique
  }

  stateful_disk {
    device_name = var.data_device_name
    delete_rule = "NEVER"
  }

  auto_healing_policies {
    health_check      = google_compute_health_check.api.id
    initial_delay_sec = 1200
  }

  # Single data disk
  update_policy {
    type                  = "PROACTIVE"
    minimal_action        = "REPLACE"
    replacement_method    = "RECREATE"
    max_surge_fixed       = 0
    max_unavailable_fixed = 1
  }
}
