project_id = "worldwalker-511816"
region     = "us-central1"

environment = "development"

service_name       = "worldwalker-dev"
service_account_id = "worldwalker-runtime-dev"
repository_id      = "worldwalker-dev"
image_name         = "worldwalker"
docker_image_tag   = "dev"

container_port = 8080

max_instance_count               = 2
max_instance_request_concurrency = 40

deploy_cloud_run      = false
allow_unauthenticated = true

use_memorystore = false

environment_variables = {
  COOKIE_SECURE             = "true"
  GEOCODER_CONTACT_EMAIL    = "sri.kotala@gmail.com"
  GOOGLE_SIGNIN_CLIENT_ID   = "1071769014661-522gkdlqh8o4gpgshdd3u6204icmq6lg.apps.googleusercontent.com"
  GOOGLE_OAUTH_REDIRECT_URI = "https://worldwalker-dev-REPLACE-ME.a.run.app/auth/google/callback"
}

secret_env_vars = {
  DATABASE_URL         = "worldwalker-dev-database-url"
  JWT_SECRET_KEY       = "worldwalker-dev-jwt-secret-key"
  TOKEN_ENCRYPTION_KEY = "worldwalker-dev-token-encryption-key"
  OLLAMA_API_KEY       = "worldwalker-dev-ollama-api-key"
  WEBHOOK_SECRET       = "worldwalker-dev-webhook-secret"

  GOOGLE_OAUTH_CLIENT_ID     = "worldwalker-dev-google-oauth-client-id"
  GOOGLE_OAUTH_CLIENT_SECRET = "worldwalker-dev-google-oauth-client-secret"

  REDIS_URL = "worldwalker-dev-redis-url"
}
