#!/usr/bin/env bash
# Explicit online update of the Python locks from public PyPI.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../backend"
if [[ "$(uv --version | cut -d ' ' -f 2)" != 0.13.7 ]]; then
  echo 'Python lock generation requires uv 0.13.7.' >&2
  exit 2
fi
options=(--python-version 3.12 --universal --generate-hashes --only-binary :all: --no-header)
uv --no-config pip compile "${options[@]}" --upgrade --output-file requirements-runtime.lock pyproject.toml
uv --no-config pip compile "${options[@]}" --upgrade --constraint requirements-runtime.lock \
  --extra dev --output-file requirements-test.lock pyproject.toml
uv --no-config pip compile "${options[@]}" --upgrade --group build --output-file requirements-build.lock
