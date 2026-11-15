output "ip" {
  value = google_compute_address.server.address
}

output "url_http" {
  value = "http://${google_compute_address.server.address}/api/health"
}

output "url_https" {
  value = "https://${var.domain}/api/health"
}

output "url_fallback" {
  value = "https://${local.sslip}/api/health"
}

output "registry" {
  value = local.registry
}

output "image" {
  value = local.image
}

output "bucket" {
  value = google_storage_bucket.data.name
}

output "docker_platform" {
  value = "linux/amd64"
}

output "group" {
  value = google_compute_instance_group_manager.server.name
}

output "zone" {
  value = var.zone
}
