# syntax=docker/dockerfile:1
# App image: build frontend + install Python deps on top of prebuilt base image.

ARG BASE_IMAGE=smart-doc-flow-runtime-base:bookworm

FROM node:20-bookworm AS frontend-builder
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
# Lockfile currently contains a peer-deps conflict (react 19 vs lucide-react 0.292.0),
# so Docker build uses legacy peer resolution to keep parity with local install.
RUN --mount=type=cache,target=/root/.npm \
    npm install --legacy-peer-deps
COPY frontend/ ./
ENV NODE_ENV=production
RUN npm run build

FROM ${BASE_IMAGE} AS runtime

WORKDIR /app
ARG INSTALL_APP_DEPS=1

# Requirement files only (so nested `-r` paths in docker/requirements-app.txt resolve during pip).
COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/app/modules/module2/requirements.txt /app/backend/app/modules/module2/requirements.txt
COPY backend/app/modules/module3/requirements.txt /app/backend/app/modules/module3/requirements.txt
COPY backend/app/modules/module4/requirements.txt /app/backend/app/modules/module4/requirements.txt
COPY docker/requirements-app.txt /app/docker/requirements-app.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    bash -lc 'set -euo pipefail; \
      python -m pip install --upgrade pip setuptools wheel; \
      if [ "${INSTALL_APP_DEPS}" = "1" ]; then \
        pip install --no-cache-dir -r /app/docker/requirements-app.txt; \
        pip install --no-cache-dir "werkzeug>=3.0.0"; \
      else \
        echo "Skipping Python dependency install (INSTALL_APP_DEPS=${INSTALL_APP_DEPS})"; \
      fi'

COPY backend /app/backend

COPY --from=frontend-builder /src/frontend/dist /app/frontend/dist

RUN mkdir -p /app/runtime-data \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app/runtime-data /app/frontend/dist

ENV SMART_DOC_FLOW_RUNTIME_ROOT=/app \
    SMART_DOC_FLOW_DATA_ROOT=/app/runtime-data \
    GATEWAY_FRONTEND_DIST_DIR=/app/frontend/dist \
    MODULE2_SOFFICE_PATH=/usr/bin/soffice

USER appuser

EXPOSE 3001

WORKDIR /app
CMD ["python", "backend/run_service.py", "backend"]
