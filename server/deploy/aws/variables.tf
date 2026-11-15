variable "name" {
  description = "Resource base name"
  type        = string
}

variable "region" {
  type    = string
  default = "ca-central-1"
}

variable "zone" {
  type    = string
  default = "ca-central-1a"
}

variable "instance_type" {
  type    = string
  default = "t4g.small"
}

variable "data_disk_gb" {
  type    = number
  default = 10
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "domain" {
  description = "API domain (empty: sslip.io only)"
  type        = string
  default     = "api.astrowrap.earth"
}

variable "alert_email" {
  type    = string
  default = ""
}

variable "budget_usd" {
  type    = number
  default = 1
}

variable "cors" {
  description = "Allowed origins"
  type        = string
  default     = "https://astrowrap.earth,https://www.astrowrap.earth"
}
