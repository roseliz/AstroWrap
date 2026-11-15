variable "name" {
  description = "Base name of every resource (registry, bucket, address, group...). Changing it replaces them."
  type        = string
  # No default: set in terraform.tfvars, so that a missing tfvars fails instead of planning a full replacement
}

variable "project" {
  description = "Google Cloud project"
  type        = string
}

variable "region" {
  description = "Montreal, close to the AWS API (ca-central-1)"
  type        = string
  default     = "northamerica-northeast1"
}

variable "zone" {
  description = "Single zone: the data disk only exists in one zone"
  type        = string
  default     = "northamerica-northeast1-a"
}

variable "machine_type" {
  # e2-standard-2: 2 vCPU without CPU credits (full speed all the time), 8 GB; ~76 CAD/month in Montreal
  description = "Compute Engine machine type (x86: linux/amd64 image)"
  type        = string
  default     = "e2-standard-2"
}

variable "data_disk_gb" {
  description = "Data disk (Parquet ~1 GB, caches)"
  type        = number
  default     = 10
}

variable "data_device_name" {
  description = "Device name of the stateful data disk in the group. Changing it gives the machine a new, empty disk."
  type        = string
  default     = "data"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "domain" {
  description = <<-EOT
    Domain name of the API (HTTPS, Let's Encrypt, by Caddy); DNS A record to the fixed address, not proxied.
    <ip-with-dashes>.sslip.io is served as well (fallback, and target of the uptime check).
  EOT
  type        = string
  default     = "api-gcp.astrowrap.earth"
}

variable "cors" {
  description = "ANALOGUES_CORS: allowed origins (comma separated); * = all"
  type        = string
  default     = "https://astrowrap.earth,https://www.astrowrap.earth"
}

variable "alert_email" {
  description = "Email of the alerts (API down, budget). Empty: no email alert."
  type        = string
  default     = ""
}

variable "billing_account" {
  description = "Billing account of the project (XXXXXX-XXXXXX-XXXXXX), for the budget. Empty: no budget."
  type        = string
  default     = ""
}

variable "budget_currency" {
  description = "Currency of the budget: must be the one of the billing account"
  type        = string
  default     = "CAD"
}

variable "budget_step" {
  description = "One alert at each spending step of the month (in budget_currency)"
  type        = number
  default     = 50
}

variable "budget_max" {
  description = "Amount of the monthly budget: alerts at budget_step, 2 × budget_step... up to this amount"
  type        = number
  default     = 200
}
