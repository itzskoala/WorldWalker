# Dockerfile
# Single-container production image for Cloud Run: FastAPI (app.py) serves
# both the JSON API (/api, /auth, /notifications) and the built React/Vite
# frontend (frontend/dist) from one process - the same split app.py's own
# routing already assumes (see its API_PREFIXES / StaticFiles mounts /
# catch-all spa() route), just without Vercel's routing layer in front of
# it. Local dev (`npm run dev` + `uvicorn app:app --reload`) and
# docker-compose.yml (local Postgres only) are unaffected by this file.
#
# Build:  docker build -t worldwalker .
# Run:    docker run -p 8080:8080 --env-file .env.docker worldwalker
#         (DATABASE_URL must point at a real reachable Postgres - Neon in
#         production, docker-compose's local Postgres for a manual smoke
#         test. Never bake DATABASE_URL or any other secret into the image.)

# ---- Stage 1: build the frontend ----
FROM node:24-slim AS frontend-build
WORKDIR /app/frontend

# Separate dependency install from source copy so `npm ci` stays cached
# across rebuilds that only change frontend/src.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend + the built frontend ----
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only the packages app.py actually imports at runtime (see data/,
# database/, etc.) - no tests/, migrations/, or dev-only scripts.
COPY app.py ./
COPY accounts ./accounts
COPY auth ./auth
COPY core ./core
COPY data ./data
COPY database ./database
COPY notifications ./notifications
COPY services ./services
COPY travel_logic ./travel_logic

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN useradd --create-home --shell /usr/sbin/nologin worldwalker \
    && chown -R worldwalker:worldwalker /app
USER worldwalker

EXPOSE 8080

# Shell form so Cloud Run's $PORT (defaults to 8080, matches
# terraform/gcp's container_port) is substituted at container start, not
# baked in at build time.
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
