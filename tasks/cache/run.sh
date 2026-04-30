#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ ! -f ".env" ]]; then
  cp ".env.example" ".env"
fi

docker compose up -d db cache app

echo "Waiting for app to become healthy..."
for _ in {1..60}; do
  status="$(docker inspect --format='{{.State.Health.Status}}' cache_demo_app 2>/dev/null || true)"
  if [[ "${status}" == "healthy" ]]; then
    break
  fi
  sleep 1
done

status="$(docker inspect --format='{{.State.Health.Status}}' cache_demo_app 2>/dev/null || true)"
if [[ "${status}" != "healthy" ]]; then
  echo "App is not healthy"
  docker compose logs app
  exit 1
fi

docker compose run --rm load-generator

echo "Benchmark finished. Report: ${SCRIPT_DIR}/README.md"
