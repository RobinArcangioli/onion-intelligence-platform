#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../backend"
python -m pip install --require-hashes --only-binary=:all: -r requirements-build.lock -r requirements-test.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
