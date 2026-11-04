# syntax=docker/dockerfile:1
#
# One Dockerfile for the whole team and for every OS. Two build targets:
#   runtime : Python + uv                       -> used by the `api` service
#   agent   : runtime + llama.cpp CLI (default) -> used by the `agent` service
#
# What changes between machines is only the build args passed by compose:
#   - docker-compose.yml             -> CPU build  (Mac Intel/Apple Silicon, Windows without NVIDIA)
#   - docker-compose.windows-gpu.yml -> CUDA build (Windows + NVIDIA GPU via Docker Desktop/WSL2)
#
# Every base image is pinned by digest (multi-arch index digest, so the same pin
# works on amd64 Windows/Intel Mac AND arm64 Apple Silicon). Tags like
# "bookworm-slim" move over time; digests do not, so teammates build identical
# images. To bump a pin, see "Updating pinned versions" in README.md.
#
# The image holds only the toolchain. Project code, data and model weights are
# bind-mounted at run time, never baked in.

# debian:bookworm-slim
ARG BUILD_BASE=debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
ARG RUNTIME_BASE=debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
# ghcr.io/astral-sh/uv:0.13.7
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490
ARG PYTHON_VERSION=3.11

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------
# Stage: build the pinned llama.cpp CLI (CPU, or CUDA when GGML_CUDA=ON).
# Only built for the `agent` target; the `api` target never touches it.
# ---------------------------------------------------------------------------
FROM ${BUILD_BASE} AS llama
ARG LLAMA_CPP_REF=b12111
ARG GGML_CUDA=OFF
ARG CUDA_ARCHS=""

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Static libs => llama-cli is a single self-contained binary we can copy out.
# Curl/OpenSSL are off: model files are mounted from disk, never downloaded.
RUN git clone --depth 1 --branch "${LLAMA_CPP_REF}" https://github.com/ggml-org/llama.cpp /src \
 && cmake -S /src -B /src/build \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DLLAMA_CURL=OFF \
      -DLLAMA_OPENSSL=OFF \
      -DGGML_CUDA="${GGML_CUDA}" \
      -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHS}" \
 && cmake --build /src/build --config Release --target llama-cli -j"$(nproc)"

# ---------------------------------------------------------------------------
# Stage: runtime (Python 3.11 + uv + entrypoint)
# ---------------------------------------------------------------------------
FROM ${RUNTIME_BASE} AS runtime
ARG PYTHON_VERSION

# libgomp1: OpenMP for llama.cpp / onnxruntime. libgl1 + libglib2.0-0: needed by
# opencv, which RapidOCR pulls in.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libgomp1 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

# The virtualenv lives OUTSIDE the project folder (/opt/venv, backed by a named
# volume in compose) so a Windows/Mac ".venv" in the project never collides
# with the Linux one.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON=${PYTHON_VERSION} \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN uv python install "${PYTHON_VERSION}"

# Fail the build early if this Python lacks SQLite FTS5 (the plan's evidence ledger uses it).
RUN uv run --no-project python -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')"

# sed strips Windows CRLF line endings that git may have added on checkout;
# otherwise the "#!/bin/sh\r" shebang fails with "no such file or directory".
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "code/main.py"]

# ---------------------------------------------------------------------------
# Stage: agent = runtime + llama.cpp  (LAST stage => default build target)
# ---------------------------------------------------------------------------
FROM runtime AS agent
COPY --from=llama /src/build/bin/llama-cli /usr/local/bin/llama-cli
