variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "worldwalker"
}

variable "repository_id" {
  description = "Artifact Registry repository ID"
  type        = string
  default     = "worldwalker"
}

variable "image_name" {
  description = "Container image name"
  type        = string
  default     = "worldwalker"
}

variable "docker_image_tag" {
  description = "Image tag to deploy"
  type        = string
  default     = "v1"
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8080
}

variable "max_instance_count" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 5
}

variable "max_instance_request_concurrency" {
  description = "Maximum concurrent requests per Cloud Run instance"
  type        = number
  default     = 40
}

variable "deploy_cloud_run" {
  description = "Set true only after the image exists and required Secret Manager versions have been added"
  type        = bool
  default     = false
}

variable "allow_unauthenticated" {
  description = "Allow public HTTP requests to the app; application-level auth must still protect user data"
  type        = bool
  default     = true
}

variable "environment_variables" {
  description = "Non-secret application environment variables"
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Map of application environment variable names to Secret Manager secret IDs"
  type        = map(string)
  default     = {}
}
