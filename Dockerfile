# syntax=docker/dockerfile:1
# Shared toolchain only. Model inference uses an explicitly configured API;
# this image does not compile an inference server or contain model weights.

ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490
ARG RUNTIME_BASE=debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
ARG PYTHON_VERSION=3.11

FROM ${UV_IMAGE} AS uv
FROM ${RUNTIME_BASE} AS runtime
ARG PYTHON_VERSION

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libgomp1 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON=${PYTHON_VERSION} \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN uv python install "${PYTHON_VERSION}" \
 && uv run --no-project python -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')"

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
 && chmod +x /usr/local/bin/entrypoint.sh \
 && useradd --create-home --uid 10001 slam

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["pytest", "-q"]
