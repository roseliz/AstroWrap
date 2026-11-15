# Monitoring, same as ../aws/monitoring.tf:
# - logs: output of the startup script ("google_metadata_script_runner" log) and of the containers (Docker gcplogs
#   driver, "gcplogs-docker-driver" log) in Cloud Logging (50 GiB free per month);
# - uptime check of the API every 5 minutes from 3 regions, email alert if it fails for ~10 minutes;
# - monthly budget: one email at each step of var.budget_step (50 CAD), up to var.budget_max.

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "${var.name}: alerts"
  type         = "email"
  labels       = { email_address = var.alert_email }
  depends_on   = [google_project_service.api]
}

# Target: the sslip.io address (same machine, same Caddy), which does not depend on the domain's DNS
resource "google_monitoring_uptime_check_config" "api" {
  display_name     = "${var.name}: /api/health"
  timeout          = "15s"
  period           = "300s"
  selected_regions = ["USA_VIRGINIA", "USA_OREGON", "USA_IOWA"]

  http_check {
    path         = "/api/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }
  monitored_resource {
    type   = "uptime_url"
    labels = { project_id = var.project, host = local.sslip }
  }
  content_matchers {
    content = "\"ready\":true"
  }
  depends_on = [google_project_service.api]
}

resource "google_monitoring_alert_policy" "api_down" {
  display_name = "${var.name}: API down"
  combiner     = "OR"
  conditions {
    display_name = "The API has not answered \"ready\" for ~10 minutes"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.api.uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1 # more than one region failing
      duration        = "600s"
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
      }
    }
  }
  notification_channels = google_monitoring_notification_channel.email[*].id
}

# Costs counted BEFORE the trial credits (EXCLUDE_ALL_CREDITS): shows what the machine uses of the credits, not only
# what would be billed. The budget is set on the billing account: it needs the "Billing Account Costs Manager" role
# (or administrator). The administrators of the account receive the emails as well.
resource "google_billing_budget" "monthly" {
  count           = var.billing_account != "" ? 1 : 0
  billing_account = var.billing_account
  display_name    = "${var.name}: steps of ${var.budget_step} ${var.budget_currency}"

  budget_filter {
    projects               = ["projects/${data.google_project.project.number}"]
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
    calendar_period        = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_max)
    }
  }

  dynamic "threshold_rules" {
    for_each = range(var.budget_step, var.budget_max + 1, var.budget_step)
    content {
      threshold_percent = threshold_rules.value / var.budget_max
      spend_basis       = "CURRENT_SPEND"
    }
  }

  all_updates_rule {
    monitoring_notification_channels = google_monitoring_notification_channel.email[*].id
    disable_default_iam_recipients   = false
  }
  depends_on = [google_project_service.api]
}
