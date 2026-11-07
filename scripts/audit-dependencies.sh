#!/usr/bin/env bash
# Refresh the public advisory database, then scan only locks and explicitly named local images.
set -Eeuo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if (( $# < 1 )); then
  echo 'Usage: bash scripts/audit-dependencies.sh REPORT_DIR [LOCAL_IMAGE ...]' >&2
  exit 2
fi
mkdir -p -- "$1"
reports="$(realpath -- "$1")"
shift
scanner='aquasec/trivy:0.76.2@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb'
scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
cache="${OIP_TRIVY_CACHE_DIR:-$scratch/cache}"
mkdir -p -- "$cache"
cache="$(realpath -- "$cache")"
cache_mount=(--mount "type=bind,src=$cache,dst=/cache")

for scope in build runtime test; do
  mkdir -p "$scratch/locks/$scope"
  # Expand the locked inventory into the input format Trivy recognizes.
  sed -nE 's/^([A-Za-z0-9_.-]+)(\[[^]]+\])?(==[^ ;\\]+).*$/\1\3/p' \
    "backend/requirements-$scope.lock" > "$scratch/locks/$scope/requirements.txt"
  test -s "$scratch/locks/$scope/requirements.txt"
done
cp frontend/package.json frontend/package-lock.json "$scratch/locks/"
docker run --rm "${cache_mount[@]}" "$scanner" image --cache-dir /cache --download-db-only
cp "$cache/db/metadata.json" "$reports/advisory-db.json"

scan() {
  docker run --rm --network none "${cache_mount[@]}" \
    --mount "type=bind,src=$scratch,dst=/input,readonly" "$scanner" "$@" \
    --cache-dir /cache --skip-db-update --skip-java-db-update --offline-scan \
    --scanners vuln --format json
}
scan fs --include-dev-deps /input/locks > "$reports/locks.json"
scan_reports=("$reports/locks.json")
for image in "$@"; do
  docker image inspect "$image" >/dev/null
  name="${image//[^a-zA-Z0-9_.-]/_}"
  docker image save -o "$scratch/image.tar" "$image"
  scan image --input /input/image.tar > "$reports/$name.json"
  scan_reports+=("$reports/$name.json")
done

python3 scripts/check-delivery-scan.py "$scratch/locks" "${scan_reports[@]}" | tee "$reports/gate.txt"
