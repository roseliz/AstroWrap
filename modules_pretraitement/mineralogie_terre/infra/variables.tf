variable "region" {
  description = "Region of the NASA EMIT buckets"
  type        = string
  default     = "us-west-2"
  validation {
    condition     = var.region == "us-west-2"
    error_message = "EMIT data is in us-west-2: any other region makes direct S3 reads impossible and transfers paid."
  }
}

variable "alert_email" {
  description = "Address that receives the budget alerts (no default: pass it with -var or TF_VAR_alert_email)"
  type        = string
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "run_name" {
  description = "Name of the run (pilot, full...): prefix of the results and of the state in the bucket"
  type        = string
  default     = "pilot"
  validation {
    condition     = can(regex("^[a-z0-9_-]+$", var.run_name))
    error_message = "Lower-case letters, digits, - and _ only."
  }
}

variable "granule_list" {
  description = "Local Parquet list of the granules to process (granule, version, url_min, url_unc, url_masque)"
  type        = string
}

variable "start" {
  description = "true: the machines run; false: everything is created but no machine starts"
  type        = bool
  default     = true
}

variable "instance_types" {
  description = "Accepted instance types (2 vCPU): AWS picks the cheapest and least interrupted one. On a free-plan account, only free-tier-eligible types start (aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true)"
  type        = list(string)
  default     = ["m7i-flex.large", "c7i-flex.large"]
}

variable "machines" {
  description = "Number of machines on the same list (each in its own random order, never redoing what another wrote)"
  type        = number
  default     = 1
  validation {
    condition     = var.machines >= 1 && var.machines <= 10
    error_message = "Between 1 and 10 machines (account Spot quota: 32 vCPU)."
  }
}

variable "spot" {
  description = "true: Spot; false: on demand (~2 times more expensive, if Spot is refused on the account)"
  type        = bool
  default     = true
}

variable "parallel" {
  description = "Granules processed at the same time on each machine"
  type        = number
  default     = 4
}

variable "max_hours" {
  description = "Forced stop of the processing after this duration (cost safeguard)"
  type        = number
  default     = 36
}

variable "max_starts" {
  description = "Stop when more machines than this have been started for one run (interruptions or crashes)"
  type        = number
  default     = 8
}

variable "ssm_prefix" {
  description = "Prefix of the two SSM parameters (SecureString) created by credentials.sh, outside Terraform"
  type        = string
  default     = "/mineralogie_terre/"
}
