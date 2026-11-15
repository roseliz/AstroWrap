terraform {
  required_version = ">= 1.10"

  # See backend.hcl.example
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
}

provider "google" {
  project               = var.project
  region                = var.region
  zone                  = var.zone
  user_project_override = true
  billing_project       = var.project
  default_labels = {
    project = var.name
  }
}
