#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
pnpm --dir apps/web install --frozen-lockfile
mkdir -p data/materials
uv run alembic upgrade head
uv run uvicorn tiza.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
uv run python -m tiza.jobs.worker &
worker_pid=$!
pnpm --dir apps/web dev --host 127.0.0.1 &
web_pid=$!
trap 'kill "$api_pid" "$worker_pid" "$web_pid" 2>/dev/null || true' EXIT INT TERM
wait
