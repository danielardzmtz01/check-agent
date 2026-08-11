terraform {
  required_version = ">= 1.3"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Enable required GCP APIs
resource "google_project_service" "enabled_apis" {
  for_each = toset([
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# 2. Service Account for Cloud Run
resource "google_service_account" "run_sa" {
  account_id   = "${var.service_name}-sa"
  display_name = "Service Account for ADK Code Review Agent Cloud Run"
  depends_on   = [google_project_service.enabled_apis]
}

# 3. Provision the GCS Staging Bucket (Category 5: Declarative Resource Provisioning)
resource "google_storage_bucket" "staging_bucket" {
  name                        = var.staging_bucket_name
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.enabled_apis]
}

# 4. Provision the Secret Manager secret for API Key (Category 5: Declarative Resource Provisioning)
resource "google_secret_manager_secret" "api_key" {
  secret_id  = var.gemini_api_key_secret_id
  depends_on = [google_project_service.enabled_apis]
  replication {
    auto {}
  }
}

# 5. Grant Service Account access to Secret Manager
resource "google_secret_manager_secret_iam_member" "sa_secret_accessor" {
  secret_id = google_secret_manager_secret.api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run_sa.email}"
}

# 6. Cloud Run Service
resource "google_cloud_run_v2_service" "agent_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.run_sa.email

    containers {
      image = var.image_url

      ports {
        container_port = 8000
      }

      # Inject Secret securely via Environment Variable (Category 5: Secure Secret Management)
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.api_key.secret_id
            version = "latest"
          }
        }
      }

      # Persistence configuration (Category 2: Persistent Session State using Sqlite)
      env {
        name  = "SESSION_SERVICE_URI"
        value = "sqlite:////data/agent_sessions.db"
      }
      
      # Environment configurations
      env {
        name  = "PORT"
        value = "8000"
      }
    }
  }

  depends_on = [
    google_project_service.enabled_apis,
    google_storage_bucket.staging_bucket,
    google_secret_manager_secret_iam_member.sa_secret_accessor
  ]
}

# 7. Allow Unauthenticated Access (if public demo is desired)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  name     = google_cloud_run_v2_service.agent_service.name
  location = google_cloud_run_v2_service.agent_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
