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
  echo "[entrypoint] no uv.lock / pyproject.toml / requirements.txt in /workspace - skipping dependency install" >&2
fi

exec "$@"
