variable "name" {
  description = "Resource base name"
  type        = string
}

variable "project" {
  type = string
}

variable "region" {
  type    = string
  default = "northamerica-northeast1"
}

variable "zone" {
  type    = string
  default = "northamerica-northeast1-a"
}

variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "data_disk_gb" {
  type    = number
  default = 10
}

variable "data_device_name" {
  description = "Stateful disk device name"
  type        = string
  default     = "data"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "domain" {
  description = "API domain"
  type        = string
  default     = "api-gcp.astrowrap.earth"
}

variable "cors" {
  description = "Allowed origins"
  type        = string
  default     = "https://astrowrap.earth,https://www.astrowrap.earth"
}

variable "alert_email" {
  type    = string
  default = ""
}

variable "billing_account" {
  description = "Empty: no budget"
  type        = string
  default     = ""
}

variable "budget_currency" {
  type    = string
  default = "CAD"
}

variable "budget_step" {
  type    = number
  default = 50
}

variable "budget_max" {
  type    = number
  default = 200
}
