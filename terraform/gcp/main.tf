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

locals {
  image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}/${var.image_name}:${var.docker_image_tag}"

  runtime_environment = merge(
    var.environment_variables,
    {
      GCP_PROJECT_ID   = var.project_id
      ENVIRONMENT      = "production"
      PYTHONUNBUFFERED = "1"
    }
  )

  secret_ids = toset(values(var.secret_env_vars))
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    # services/google_health/client.py calls health.googleapis.com
    # directly - confirmed missing in production: GET /v4/users/me/
    # identity 403'd during the OAuth callback (auth/router.py's
    # google_callback -> upsert_connection_from_tokens ->
    # get_health_user_id) until this was enabled by hand.
    "health.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "worldwalker" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "WorldWalker application images"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "worldwalker-runtime"
  display_name = "WorldWalker Cloud Run runtime"
}

# Terraform creates the secret containers only. Add secret versions separately
# after this bootstrap apply; never put secret values in Terraform variables.
resource "google_secret_manager_secret" "secrets" {
  for_each = local.secret_ids

  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each = local.secret_ids

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.value].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# First apply with deploy_cloud_run=false. Build/push the image and add secret
# versions, then set deploy_cloud_run=true and apply again.
resource "google_cloud_run_v2_service" "worldwalker" {
  count = var.deploy_cloud_run ? 1 : 0

  project  = var.project_id
  name     = var.service_name
  location = var.region

  template {
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = var.max_instance_request_concurrency

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instance_count
    }

    containers {
      image = local.image_uri

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      # Without an explicit probe, Cloud Run v2 defaults to a bare TCP
      # check on container_port - that only proves a socket is open, not
      # that the FastAPI app behind it is actually serving requests.
      # /api/config (app.py) is a real route, hit on every login/signup
      # page load, that does no database I/O - cheap enough for a
      # liveness probe to poll repeatedly without adding DB load, and a
      # meaningful enough check that it genuinely exercises the HTTP
      # stack during startup.
      startup_probe {
        http_get {
          path = "/api/config"
        }
        initial_delay_seconds = 0
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/api/config"
        }
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
      }

      dynamic "env" {
        for_each = local.runtime_environment
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_artifact_registry_repository.worldwalker,
    google_secret_manager_secret_iam_member.runtime_access,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count = var.deploy_cloud_run && var.allow_unauthenticated ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.worldwalker[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "service_url" {
  value       = var.deploy_cloud_run ? google_cloud_run_v2_service.worldwalker[0].uri : null
  description = "WorldWalker Cloud Run URL; null until Cloud Run deployment is enabled"
}

output "project_id" {
  value       = var.project_id
  description = "GCP project ID"
}

output "region" {
  value       = var.region
  description = "GCP deployment region"
}

output "image_uri" {
  value       = local.image_uri
  description = "Expected WorldWalker container image URI"
}
