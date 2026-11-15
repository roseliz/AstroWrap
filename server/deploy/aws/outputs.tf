output "ip" {
  value = aws_eip.server.public_ip
}

output "url_http" {
  value = "http://${aws_eip.server.public_ip}/api/health"
}

output "url_https" {
  value = "https://${local.domain}/api/health"
}

output "url_fallback" {
  value = "https://${local.sslip}/api/health"
}

output "ecr" {
  value = aws_ecr_repository.server.repository_url
}

output "bucket" {
  value = aws_s3_bucket.data.id
}

output "docker_platform" {
  value = local.architecture == "arm64" ? "linux/arm64" : "linux/amd64"
}

output "group" {
  value = aws_autoscaling_group.server.name
}
