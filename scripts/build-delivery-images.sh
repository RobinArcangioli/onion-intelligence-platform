#!/usr/bin/env bash
# Clean candidate builds only. Compose services and host ports are untouched.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
prefix="${1:?Usage: bash scripts/build-delivery-images.sh IMAGE_REPOSITORY}"
options=(--pull --no-cache)
docker build "${options[@]}" --target runtime -t "$prefix:backend" backend
docker build "${options[@]}" --target test -t "$prefix:backend-test" backend
docker build "${options[@]}" --target build -t "$prefix:frontend-build" -f frontend/Dockerfile .
docker build "${options[@]}" -t "$prefix:gateway" -f frontend/Dockerfile .
docker build "${options[@]}" -t "$prefix:tor" infrastructure/tor
postgres="$(awk '$1 == "image:" && $2 ~ /^postgres:/ { print $2 }' compose.yaml)"
test -n "$postgres"
docker pull "$postgres"
docker tag "$postgres" "$prefix:postgres"
