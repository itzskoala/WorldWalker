project_id = "worldwalker-511816"
region     = "us-central1"

service_name     = "worldwalker"
repository_id    = "worldwalker"
image_name       = "worldwalker"
docker_image_tag = "v4"

# Confirm this matches the port your Docker container actually listens on.
container_port = 8080

max_instance_count               = 5
max_instance_request_concurrency = 40

# Bootstrap phase: keep false until the image is pushed and secret versions exist.
deploy_cloud_run      = true
allow_unauthenticated = true

environment_variables = {
  COOKIE_SECURE          = "true"
  GEOCODER_CONTACT_EMAIL = "sri.kotala@gmail.com"
  # "Sign in with Google" button (accounts/google_oauth.py) - optional,
  # app.py hides the button when unset. Not the same client as the
  # GOOGLE_OAUTH_* secrets below.
  # GOOGLE_SIGNIN_CLIENT_ID = "replace-with-your-google-signin-client-id"
  # Sign in with Apple JS - optional, app.py renders the button inert
  # (not hidden) when unset. No backend callback exists for it yet.
  # APPLE_SIGNIN_CLIENT_ID = "replace-with-your-apple-services-id"
  # Needed alongside the GOOGLE_OAUTH_CLIENT_ID/SECRET secrets below to
  # enable the "Connect Google Health" feature in production - without
  # all three, auth/google_health_auth.py falls back to credentials.json,
  # which is gitignored and never reaches this image. Confirmed in
  # production logs: FileNotFoundError: '/app/credentials.json' on
  # POST /auth/google/start - this was the root cause of "Connect"
  # failing with the generic 500 message.
  GOOGLE_OAUTH_REDIRECT_URI = "https://worldwalker-qcasgfcwha-uc.a.run.app/auth/google/callback"
}

# Keep only variables confirmed by a source-code audit to be used in production.
# Values below are Secret Manager SECRET NAMES, not secret values.
secret_env_vars = {
  DATABASE_URL         = "worldwalker-database-url"
  JWT_SECRET_KEY       = "worldwalker-jwt-secret-key"
  TOKEN_ENCRYPTION_KEY = "worldwalker-token-encryption-key"
  OLLAMA_API_KEY       = "worldwalker-ollama-api-key"
  # Required, not optional: services/google_health/webhook.py reads
  # os.environ["WEBHOOK_SECRET"] unconditionally at import time - the
  # app fails to even start without it (confirmed by running the
  # container without it: ImportError -> KeyError on module import).
  WEBHOOK_SECRET = "worldwalker-webhook-secret"

  GOOGLE_OAUTH_CLIENT_ID     = "worldwalker-google-oauth-client-id"
  GOOGLE_OAUTH_CLIENT_SECRET = "worldwalker-google-oauth-client-secret"
}
