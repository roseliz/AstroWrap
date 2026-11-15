terraform {
  required_version = ">= 1.10"

  # State in a versioned GCS bucket (native GCS locking), created by hand outside Terraform (see ../DEPLOY.md):
  # independent from the AWS state (../aws, in S3), a destroy on one side never touches the other.
  # Bucket and prefix are private: backend.hcl (ignored by git, see backend.hcl.example).
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
}

# Credentials: gcloud's (GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token), see DEPLOY.md) or those of
# `gcloud auth application-default login`. API quotas are counted on the project itself (required by the budgets
# API with a user account).
provider "google" {
  project               = var.project
  region                = var.region
  zone                  = var.zone
  user_project_override = true
  billing_project       = var.project
  default_labels = {
    project = var.name # to find whatever is left after terraform destroy
  }
}
