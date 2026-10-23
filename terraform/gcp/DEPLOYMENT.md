# WorldWalker: Deploying to Google Cloud Run

Deploys WorldWalker's single container (FastAPI + the built React frontend,
see `../../Dockerfile`) to Cloud Run using this directory's Terraform
configuration. Terraform manages the Cloud Run service, Artifact Registry
repository, runtime service account, and Secret Manager secret *containers*
- it never creates, migrates, or touches your Neon Postgres database. You
add secret values and push container images yourself, outside Terraform.

Target configuration (already set in `terraform.tfvars`):

| | |
|---|---|
| GCP project | `worldwalker-511816` |
| Region | `us-central1` |
| Terraform workspace | `gcp` |
| Cloud Run service | `worldwalker` |
| Artifact Registry repo | `worldwalker` |

**This guide never runs `terraform apply` or `terraform destroy` for you.**
Every apply/destroy command below is something you run yourself, after
reviewing the plan it prints.

---

## 1. Prerequisites and authentication

✅ [Docker](https://docs.docker.com/get-docker/) running locally (confirm with `docker ps`)
✅ [Terraform CLI](https://developer.hashicorp.com/terraform/install) >= 1.3
✅ [gcloud CLI](https://cloud.google.com/sdk/docs/install)
✅ Access to project `worldwalker-511816`

```bash
# Log in and select the project
gcloud auth login
gcloud config set project worldwalker-511816

# Terraform's Google provider uses Application Default Credentials, not
# your gcloud CLI login - this is a separate step.
gcloud auth application-default login

# Avoids a "quota project" warning on later commands
gcloud auth application-default set-quota-project worldwalker-511816

# Lets Docker read from Artifact Registry - used to verify a pushed
# image's architecture (step 5) and by the local-build fallback there,
# not for the normal build path (Cloud Build pushes directly, no local
# `docker push` needed)
gcloud auth configure-docker us-central1-docker.pkg.dev

# Sanity check
gcloud config list
```

---

## 2. Terraform initialization and workspace selection

```bash
cd terraform/gcp

terraform init

# First time only - errors harmlessly if the workspace already exists.
terraform workspace new gcp
terraform workspace select gcp

# Should print: gcp
terraform workspace show
```

Run the built-in checks before touching real infrastructure:

```bash
terraform fmt -check -diff -recursive
terraform validate
```

Both pass clean as of this guide. `terraform plan` (no `-var` flags needed -
`terraform.tfvars` already has everything) is also safe to run any time -
it's read-only:

```bash
terraform plan
```

Against a brand-new project this prints `Plan: 16 to add, 0 to change, 0 to
destroy` - nothing under this configuration's names exists yet (verified
directly: `gcloud run services list`, `gcloud artifacts repositories list`,
and `gcloud iam service-accounts list` all come back empty for this
project). If your plan instead shows changes to *existing* resources,
stop and figure out why before applying - see `README.md`'s note on
checking for resources that already exist outside this Terraform state.

---

## 3. Secure production secret setup

### 3a. What's required vs. optional

`terraform.tfvars`'s `secret_env_vars` was audited against the actual
source code (not assumed from `.env.example`) and now reflects what's
really required to start the app:

| Variable | Required? | Why |
|---|---|---|
| `DATABASE_URL` | **Yes** | App refuses to start without it (`database/session.py`) |
| `JWT_SECRET_KEY` | **Yes** | Signs every access/refresh token |
| `TOKEN_ENCRYPTION_KEY` | **Yes** | `database/encryption.py` raises at import time without it |
| `WEBHOOK_SECRET` | **Yes** | `services/google_health/webhook.py` reads this unconditionally at import time - confirmed by running the container without it: the app fails to boot at all, not just that one route |
| `OLLAMA_API_KEY` | No | Checkpoint descriptions degrade gracefully without it |
| `GOOGLE_OAUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_REDIRECT_URI` | No | Only needed for the "Connect Google Health" feature; the app boots fine without them |
| `GOOGLE_SIGNIN_CLIENT_ID` | No | "Sign in with Google" button hides itself when unset |
| `APPLE_SIGNIN_CLIENT_ID` | No | Button renders inert (not hidden) when unset - no backend callback exists yet either way |
| `OPENAI_API_KEY` | **No - confirmed unused** | Not read anywhere in the codebase; left commented out on purpose |

`WEBHOOK_SECRET` was previously commented out in `terraform.tfvars` as if
optional - that was wrong and has been fixed in this configuration; it's
active now.

### 3b. Create the secret containers (bootstrap apply)

Terraform only creates empty Secret Manager secret *containers* at this
stage (`deploy_cloud_run = false`, the current setting) - no Cloud Run
service yet:

```bash
# Review the plan: APIs, Artifact Registry repo, service account, secret containers.
terraform plan
# Type `yes` after reviewing.
terraform apply
```

### 3c. Add the actual secret values

Never put real secret values in `.tf`/`.tfvars` files or shell history.
Pipe them in instead:

```bash
PROJECT=worldwalker-511816

# DATABASE_URL - your Neon connection string. SQLAlchemy needs the
# +psycopg dialect explicitly (requirements.txt installs psycopg v3, not
# psycopg2) - take Neon's string and make sure it starts with
# postgresql+psycopg://, not postgresql:// or postgres://.
# Neon's pooled (PgBouncer, transaction-mode) connection string is safe
# to use here, verified directly (not just "should be fine" - see
# "Troubleshooting" below for how this was actually tested).
echo -n "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require" | \
  gcloud secrets versions add worldwalker-database-url --project="$PROJECT" --data-file=-

# JWT_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(48))" | \
  gcloud secrets versions add worldwalker-jwt-secret-key --project="$PROJECT" --data-file=-

# TOKEN_ENCRYPTION_KEY - a Fernet key is just 32 random bytes,
# base64-urlsafe-encoded (verified: cryptography.fernet.Fernet accepts a
# key made this way with no issue). Deliberately not
# `from cryptography.fernet import Fernet; Fernet.generate_key()` here -
# that package is only installed in this repo's venv, not in a bare
# system python3, and silently produces an empty string on failure
# (confirmed: the resulting TOKEN_ENCRYPTION_KEY="" then fails at
# container startup with a RuntimeError, not at this step).
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" | \
  gcloud secrets versions add worldwalker-token-encryption-key --project="$PROJECT" --data-file=-

# WEBHOOK_SECRET - must match whatever you register with the Google
# Health webhook subscriber (auth/register_webhook_subscription.py). If
# you haven't registered a subscription yet, generate a fresh one now
# and reuse it when you do:
python3 -c "import secrets; print('Bearer ' + secrets.token_urlsafe(32))" | \
  gcloud secrets versions add worldwalker-webhook-secret --project="$PROJECT" --data-file=-

# OLLAMA_API_KEY - optional, from https://ollama.com/settings/keys
echo -n "YOUR_OLLAMA_KEY" | \
  gcloud secrets versions add worldwalker-ollama-api-key --project="$PROJECT" --data-file=-
```

(Enabling "Connect Google Health" needs the live Cloud Run URL first, so
that's covered as a follow-up step after section 7, not here.)

**Run production database migrations now, before deploying new code**,
the same way `scripts/deploy.sh` already does for Vercel - Terraform
never touches your schema:

```bash
DATABASE_URL="<same Neon connection string as above>" \
  venv/bin/python3 -m alembic upgrade head
```

---

## 4. Docker build and local testing

Build the image (multi-stage: Node builds the frontend, Python serves
both the API and the built frontend from one process):

```bash
# Repository root.
cd ../..
docker build -t worldwalker:local .
```

Smoke-test it against your local Postgres (`docker-compose.yml`) before
pushing anywhere:

```bash
docker compose up -d

# Don't `source .env` directly - this repo's .env has at least one
# unquoted value containing a space (WEBHOOK_SECRET), which breaks when
# a shell tries to parse the whole file as script syntax (confirmed:
# `source .env` fails with "command not found: <the rest of that
# value>"). Pull out just the three variables this needs instead.
PGUSER=$(grep -E "^POSTGRES_USER=" .env | cut -d= -f2-)
PGPASS=$(grep -E "^POSTGRES_PASSWORD=" .env | cut -d= -f2-)
PGDB=$(grep -E "^POSTGRES_DB=" .env | cut -d= -f2-)

docker run --rm -p 8080:8080 \
  -e DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASS}@host.docker.internal:5432/${PGDB}" \
  -e JWT_SECRET_KEY="local-smoke-test" \
  -e TOKEN_ENCRYPTION_KEY="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" \
  -e WEBHOOK_SECRET="Bearer local-smoke-test" \
  -e COOKIE_SECURE="false" \
  --name worldwalker-smoke \
  worldwalker:local
```

In another terminal: `curl -i http://localhost:8080/api/config` should
return `200` with `{"google_client_id": "", "apple_client_id": ""}`.
`Ctrl+C` the container when done. This exact flow (build, run, signup,
authenticated request, static asset routes, `pytest`) was run against
this configuration while writing it - see the chat history for the full
output; it passed.

---

## 5. Artifact Registry image tagging and pushing

The image URI Terraform expects is built from `terraform.tfvars`:
`us-central1-docker.pkg.dev/worldwalker-511816/worldwalker/worldwalker:<docker_image_tag>`.

**Production images are built with Google Cloud Build, not a local
`docker build`.** Cloud Build's workers are natively `linux/amd64` -
Cloud Run's only supported architecture - so there's no QEMU emulation
involved and no way to accidentally push an arm64 image from an Apple
Silicon Mac. That's not a hypothetical: building locally without an
explicit `--platform` flag on an M-series Mac produces an arm64-only
image, which Cloud Run rejects at deploy time with "Container manifest
... must support amd64/linux" - a real failure hit while deploying this
project. Local `docker build` (step 4, `worldwalker:local`) stays
native-arch and fast on purpose - it's for quick local smoke testing
only, and that image is never what gets pushed or deployed.

```bash
PROJECT=worldwalker-511816
REGION=us-central1
REPO=worldwalker
# Must match docker_image_tag in terraform.tfvars.
TAG=v1

IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/worldwalker:${TAG}"

# Builds on Google's own amd64 infrastructure and pushes the result to
# $IMAGE in one step - no local `docker push` involved. Requires the
# Artifact Registry repository to already exist (created by the
# bootstrap `terraform apply` in step 3b) and the cloudbuild.googleapis.com
# API, which this Terraform config already enables.
gcloud builds submit --tag "$IMAGE" .
```

Verify the pushed image is actually `linux/amd64` before relying on it -
cheap insurance against ever repeating the arm64 mistake, and it only
inspects the remote manifest rather than pulling the image:

```bash
docker buildx imagetools inspect "$IMAGE"
```

Confirm the output shows `Platform: linux/amd64` (this needs
`gcloud auth configure-docker us-central1-docker.pkg.dev` from step 1 for
registry read access).

If Cloud Build is ever unavailable, a local build still works as a
fallback, at the cost of QEMU-emulated cross-compilation being noticeably
slower than a native build on Apple Silicon:
```bash
docker build --platform linux/amd64 -t "$IMAGE" . && docker push "$IMAGE"
```

---

## 6. Terraform plan and apply

Once the image is pushed and every secret referenced in
`secret_env_vars` has at least one version (step 3c), flip the switch in
`terraform.tfvars`:

```hcl
deploy_cloud_run = true
```

Then:

```bash
cd terraform/gcp
# Review the plan: should now show the Cloud Run service + public IAM binding.
terraform plan
# Type `yes` after reviewing.
terraform apply
```

---

## 7. Getting the URL and testing the live app

```bash
terraform output service_url
```

Open that URL. Confirm:
- The landing page loads (frontend served correctly)
- Sign up / log in works (Postgres + JWT + cookie flow)
- A trip can be created (geocoding + OSRM routing - needs outbound internet, which Cloud Run has by default)
- Hero photos on the landing page render (`/hero/*.webp` - the static-mount gap this project's Dockerfile work specifically fixed)

Cloud Run's health checks (`main.tf`'s `startup_probe`/`liveness_probe`) poll
`GET /api/config` - a real route that exercises the HTTP stack but does no
database I/O, so a transient Neon blip won't itself trigger a restart.
Without these, Cloud Run would only confirm a TCP socket is open, not
that FastAPI is actually answering requests behind it.

### Optional follow-up: enable "Connect Google Health"

This needs the live URL from above, so it has to happen after the first
deploy, not before:

1. In `terraform.tfvars`, uncomment `GOOGLE_OAUTH_CLIENT_ID` /
   `GOOGLE_OAUTH_CLIENT_SECRET` in `secret_env_vars`, and
   `GOOGLE_OAUTH_REDIRECT_URI` in `environment_variables`, setting it to
   `https://<the-service_url-from-above>/auth/google/callback`.
2. `terraform plan` then `terraform apply` - creates the two new secret
   containers and updates the Cloud Run service's env vars.
3. Add the two secret values (your OAuth client's "web" credentials -
   the same client `credentials.json` holds locally for local dev):
   ```bash
   echo -n "YOUR_CLIENT_ID" | gcloud secrets versions add worldwalker-google-oauth-client-id --project=worldwalker-511816 --data-file=-
   echo -n "YOUR_CLIENT_SECRET" | gcloud secrets versions add worldwalker-google-oauth-client-secret --project=worldwalker-511816 --data-file=-
   ```
4. Register that exact redirect URL on the OAuth client in Google Cloud Console (APIs & Services > Credentials).
5. `terraform apply` again (or redeploy - see "Updating the app" below) so the running revision actually picks up the new secret values.

---

## 8. Logs, troubleshooting, updates, rollback, and cost management

### Logs

```bash
gcloud run services logs read worldwalker --project=worldwalker-511816 --region=us-central1 --limit=100

# Live tail - this subcommand is alpha-track, not beta (verified against
# the installed gcloud CLI; `gcloud beta run services logs tail` doesn't
# exist). First run prompts to install the alpha component - accept it.
gcloud alpha run services logs tail worldwalker --project=worldwalker-511816 --region=us-central1
```

### Troubleshooting

- **Container fails to start / crashes immediately**: almost always a
  missing required secret (section 3a). Check logs for a Python
  traceback at import time - `KeyError: 'WEBHOOK_SECRET'` or
  `RuntimeError: TOKEN_ENCRYPTION_KEY is not set` are the two most likely.
- **502/503 right after deploy**: Cloud Run cold start - wait ~10-15s and
  retry. If it never clears, check whether the `startup_probe` (`main.tf`
  - polls `GET /api/config`) is failing in the revision's logs rather
  than assuming it's just a slow cold start; a probe failure means the
  app isn't answering HTTP requests at all, not just warming up.
- **`docker push`/`docker buildx imagetools inspect` denied or unauthorized**:
  re-run `gcloud auth configure-docker us-central1-docker.pkg.dev`
  (applies to the image-verification step, and to the local-build
  fallback - the normal Cloud Build path doesn't use local `docker push`
  at all).
- **`terraform apply` fails with "Cloud Run does not support image ...
  Container manifest ... must support amd64/linux"** - the pushed image is
  arm64-only, almost certainly from running a local `docker build` on an
  Apple Silicon Mac without realizing it defaults to the host
  architecture (confirmed reproducible this way; Cloud Run has no arm64
  support at all). Rebuild and push through Cloud Build instead (step
  5's `gcloud builds submit --tag "$IMAGE" .`, not a local `docker
  build`), verify with `docker buildx imagetools inspect "$IMAGE"` that
  it now reports `linux/amd64`, then re-run `terraform apply` - the
  failed resource will just retry, no state cleanup needed.
- **Image pull permission errors on deploy** (not yet seen in this
  project, since no image has been deployed through Terraform yet - this
  is standard documented GCP behavior, not independently re-verified
  here): Cloud Run's own service agent
  (`service-<PROJECT_NUMBER>@serverless-robot-prod.iam.gserviceaccount.com`)
  normally gets automatic read access to Artifact Registry repos in the
  same project when the Cloud Run API is enabled - no action needed. If
  you do see one, grant it explicitly:
  ```bash
  PROJECT_NUMBER=$(gcloud projects describe worldwalker-511816 --format='value(projectNumber)')
  gcloud artifacts repositories add-iam-policy-binding worldwalker \
    --project=worldwalker-511816 --location=us-central1 \
    --member="serviceAccount:service-${PROJECT_NUMBER}@serverless-robot-prod.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.reader"
  ```
- **"Prepared statement does not exist" errors under PgBouncer transaction
  pooling - verified NOT an issue here.** This was tested directly (not
  assumed): a local PgBouncer in `pool_mode=transaction` was put in front
  of Postgres, pinned to a *single* real backend connection
  (`default_pool_size=1`), then hit with 10 concurrent clients x 15
  sequential requests each through this app's real `DATABASE_URL`/
  SQLAlchemy/psycopg3 stack - a setup that forces a backend-connection
  swap on every single transaction. Zero errors across 150+ requests.
  The reason, confirmed by reading the installed `psycopg` package's
  source (`psycopg/_preparing.py`): SQLAlchemy's connection pool issues a
  `ROLLBACK` on every connection checkin by default
  (`pool_reset_on_return` defaults to rollback, and `database/session.py`
  doesn't override it), and psycopg3's `PrepareManager._should_discard()`
  explicitly clears its entire prepared-statement cache whenever it sees
  a ROLLBACK - exactly the event a PgBouncer backend swap would otherwise
  make unsafe. Neon's pooled connection string is safe to use with this
  app as-is; no code change or direct-connection fallback is needed.
- **`/auth/signup` or `/auth/login` 500s with `UndefinedColumn`**: migrations weren't applied - rerun step 3c's `alembic upgrade head` against the same `DATABASE_URL`.
- **IAM error making the service public ("org policy... allUsers")**: your GCP org restricts public IAM bindings. Set `allow_unauthenticated = false` and use `gcloud run services proxy worldwalker --region=us-central1` for authenticated-only access, or request an org policy exception for this project.

### Updating the app (new code)

The Cloud Run service's `image` attribute is a *tag*, not a digest -
pushing a new image under the same tag will not by itself make Terraform
create a new revision. Bump the tag every deploy:

```bash
NEW_TAG=v2
IMAGE="us-central1-docker.pkg.dev/worldwalker-511816/worldwalker/worldwalker:${NEW_TAG}"
# Same Cloud Build path as step 5 - every rebuild destined for Cloud Run
# goes through Cloud Build, not a local docker build.
gcloud builds submit --tag "$IMAGE" .

# terraform/gcp/terraform.tfvars: docker_image_tag = "v2"
terraform plan
terraform apply
```

Run any new Alembic migrations against Neon (step 3c) **before** this
apply, same as the existing Vercel deploy flow (`scripts/deploy.sh`).

### Rollback

Fastest path - shift traffic to a previous revision directly (doesn't
touch Terraform state):

```bash
gcloud run revisions list --service=worldwalker --region=us-central1
gcloud run services update-traffic worldwalker --region=us-central1 \
  --to-revisions=<PREVIOUS_REVISION_NAME>=100
```

**Do this immediately after the manual rollback above, not as cleanup
later**: `main.tf` defines no explicit `traffic` block, so Cloud Run's own
default - 100% of traffic to the latest ready revision - applies on any
future update to the service. That means the *next* `terraform apply`
for any reason at all (a secret rotation, an unrelated tfvars tweak) will
silently send traffic right back to the broken revision unless Terraform's
own state agrees with the rollback. Set `docker_image_tag` in
`terraform.tfvars` back to the tag the rolled-back-to revision was built
from, then `terraform apply`, before touching anything else.

### Cost management

- `min_instance_count = 0` - true scale-to-zero, $0 compute when idle.
- `max_instance_count = 5`, `max_instance_request_concurrency = 40` - caps worst-case cost; raise only after checking real traffic.
- Cloud Run: ~2M requests/month free, then well under $1 for typical early traffic.
- Artifact Registry: billed by storage - delete old tags periodically:
  ```bash
  gcloud artifacts docker images list us-central1-docker.pkg.dev/worldwalker-511816/worldwalker
  gcloud artifacts docker images delete us-central1-docker.pkg.dev/worldwalker-511816/worldwalker/worldwalker:v1 --delete-tags
  ```
- Secret Manager: first 6 active secret versions/month are free; this config uses 4-6.
- Neon itself is unaffected either way - this Terraform config never provisions or bills for database compute.

---

## 9. Terraform destroy and verification of cleanup

**Only run this when you intend to tear the deployment down.** It deletes
the Cloud Run service, the Artifact Registry repository (and every image
tag inside it), the runtime service account, the Secret Manager secret
containers (and all their versions), and the public IAM binding. It does
**not** disable the `run`/`artifactregistry`/`cloudbuild`/`secretmanager`
APIs (`disable_on_destroy = false` in `main.tf`, intentionally, so it
can't affect other projects/resources sharing those APIs) and it never
touches Neon.

```bash
cd terraform/gcp
# Review exactly what will be removed.
terraform plan -destroy
# Type `yes` only after reviewing.
terraform destroy
```

Verify cleanup - each of these should come back empty, except the last
which should simply no longer list worldwalker-runtime@...:

```bash
gcloud run services list --project=worldwalker-511816 --region=us-central1
gcloud artifacts repositories list --project=worldwalker-511816 --location=us-central1
gcloud secrets list --project=worldwalker-511816
gcloud iam service-accounts list --project=worldwalker-511816
```

---

## Unverified / needs your confirmation

Documented honestly rather than guessed:

- **Org policy on `allUsers`** - whether `worldwalker-511816` has a domain-restricted-sharing policy that would block the public IAM binding wasn't checked (would require org-level IAM access this session doesn't have); the plan/apply will simply fail with a clear error if so, and the fix is documented above.
- **Google Health webhook registration** - `auth/register_webhook_subscription.py` is a separate, manual script (not run by this guide or by Terraform); run it yourself once `WEBHOOK_PUBLIC_URL` (your real Cloud Run URL) and `WEBHOOK_SECRET` are both set.
- **Image-pull IAM on a real Artifact Registry repo in this project** - based on documented GCP behavior (automatic for same-project repos), not independently re-verified here since no image has actually been deployed through this Terraform config yet. The manual IAM grant above is there in case it's ever needed.
- **This entire deployment sequence has not been run end to end against real GCP** - every command has been verified individually (syntax against the installed `gcloud`/`terraform` CLIs, resource schemas via `terraform validate`/`plan`), and the app itself has been verified end-to-end in Docker against a real Postgres, but nothing has been applied to `worldwalker-511816` and no container has actually been deployed to Cloud Run. That first real run is still yours to do.

### Resolved this pass (previously listed here as unverified)

- **Neon pooled/PgBouncer transaction-pooling compatibility with psycopg3** - no longer a guess. Reproduced the exact failure precondition locally (PgBouncer pinned to one real backend connection, 10 concurrent clients, 150+ requests through this app's actual `DATABASE_URL`/SQLAlchemy/psycopg3 stack) and got zero errors, then confirmed the mechanism by reading the installed `psycopg` source. See "Troubleshooting" above.
