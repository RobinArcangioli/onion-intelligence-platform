#!/bin/sh
set -eu
version=11.21.2
archive="npm-$version.tgz"
digest=8ad8563b81e71b90ef405b140bccf3ba9b5e7884ab210bd49ee4e2f4bc6f61f5
scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
cd "$scratch"
npm pack "npm@$version" --registry=https://registry.npmjs.org/ --ignore-scripts --quiet
printf '%s  %s\n' "$digest" "$archive" | sha256sum -c -
npm install --global --offline --ignore-scripts --no-audit --no-fund "./$archive"
hash -r
test "$(npm --version)" = "$version"
