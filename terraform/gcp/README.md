# WorldWalker GCP Terraform starter

This is a fresh Terraform configuration for WorldWalker in GCP project `worldwalker-511816`, region `us-central1`. It does not create or migrate a database; `DATABASE_URL` should point to the existing Neon database.

## Before using

1. Review the application code and confirm every environment-variable name in `terraform.tfvars.example` is actually read by the production backend. Remove unused secrets and add any required missing variables.
2. Confirm the container's listening port. The example assumes port `8080` (for example, Nginx serving the frontend and proxying to FastAPI). Change `container_port` if the container listens on a different port.
3. Check whether the Artifact Registry repository, service account, secret containers, or Cloud Run service already exist. If any exist outside this new Terraform state, import them or adapt the configuration before applying. Do not attempt to recreate existing resources blindly.
4. Ensure Terraform state is stored securely. Terraform state can contain infrastructure metadata and should not be committed.

## Bootstrap and deploy

From the repository root, copy these files into `terraform/gcp/` and use the included `terraform.tfvars` as a starting template (review the placeholder contact email and the app environment variable names):

Then, from `terraform/gcp`:

```bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan
```

Review the plan. The initial configuration has `deploy_cloud_run = false`, so the first apply should create APIs, the Artifact Registry repository, the runtime service account, secret containers, and secret access grants only:

```bash
terraform apply
```

Next, from the repository root, build and push the image (requires a Dockerfile and a working Cloud Build setup):

```bash
gcloud config set project worldwalker-511816
gcloud builds submit --tag us-central1-docker.pkg.dev/worldwalker-511816/worldwalker/worldwalker:v1 .
```

Add the required secret versions to Secret Manager using secure input methods; do not place secret values in `.tf`, `.tfvars`, shell command arguments, or source control. For example, create/add each secret value using the Google Cloud Console's Secret Manager UI or an approved secure workflow.

Once every referenced secret has a version and the image exists, edit `terraform.tfvars` and set:

```hcl
deploy_cloud_run = true
```

Then run:

```bash
terraform plan
terraform apply
terraform output service_url
```

## Important notes

- Public invocation is enabled by default because this is a public web application. Your backend must enforce user authentication and ownership checks for private data. Set `allow_unauthenticated = false` only if you intentionally want IAM-level access restrictions.
- Cloud Run uses the latest secret version at instance startup. Ensure the named secrets exist and have versions before deploying.
- The example uses one vCPU, 1 GiB memory, up to five instances, and up to 40 concurrent requests per instance. Adjust after testing real workload and memory needs.
- This starter does not configure a custom domain, VPC, Cloud SQL, database migration, OAuth redirect URI, or CI/CD pipeline.
- The Terraform provider is pinned to the Google provider v5 line for compatibility with the previous configuration. Provider version upgrades should be reviewed separately.
