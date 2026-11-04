#!/bin/sh
# Installs project dependencies into /opt/venv, then runs the requested command.
set -e
cd /workspace

if [ -f uv.lock ]; then
  uv sync --frozen            # reproducible: exactly what uv.lock says
elif [ -f pyproject.toml ]; then
  uv sync
elif [ -f requirements.txt ]; then
  [ -x /opt/venv/bin/python ] || uv venv /opt/venv
  uv pip install --python /opt/venv/bin/python -r requirements.txt
else
  # The Compose volume mounted at /opt/venv is empty on a new machine. Create a
  # minimal environment even before the application dependency file exists so
  # `python` is available for the foundation smoke check.
  [ -x /opt/venv/bin/python ] || uv venv /opt/venv --python "${UV_PYTHON:-3.11}"
  echo "[entrypoint] no dependency manifest yet - initialized Python environment only" >&2
fi

exec "$@"
