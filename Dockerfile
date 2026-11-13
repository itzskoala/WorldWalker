FROM node:24-slim AS frontend-build
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-install-project

COPY backend ./backend

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN useradd --create-home --shell /usr/sbin/nologin worldwalker \
    && chown -R worldwalker:worldwalker /app
USER worldwalker

EXPOSE 8080

CMD ["sh", "-c", "exec .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
