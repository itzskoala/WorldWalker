#!/usr/bin/env bash
set -euo pipefail
# Deploy WorldWalker to Vercel production - always migrates the production
# database first, so deployed code never runs ahead of the schema it
# expects. (Incident 2026-09-23: eef93debeb8c/d0451e36b216 were written
# and deployed in app.py's code path without ever being run against the
# Neon production DB, so /auth/signup and /auth/login 500'd with
# psycopg.errors.UndefinedColumn until the migrations were applied by
# hand.)
#
# Requires DATABASE_URL in the environment, pointing at PRODUCTION Neon -
# never your local .env's DATABASE_URL. Get it with:
#   vercel env pull <file> --environment=production
# then export DATABASE_URL from that file (use DATABASE_URL_UNPOOLED's
# value if DATABASE_URL comes back empty - older `vercel` CLI versions
# don't decrypt Sensitive-typed vars on pull).

cd "$(dirname "$0")/.."

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set - refusing to deploy without migrating first. See this script's header for how to get production's URL." >&2
  exit 1
fi

echo "Migrating production database ($(python3 -c "from urllib.parse import urlparse; print(urlparse('$DATABASE_URL'.replace('postgres://', 'postgresql://', 1)).hostname)"))..."
venv/bin/python3 -m alembic upgrade head

echo "Migrations applied. Deploying to Vercel production..."
vercel --prod
