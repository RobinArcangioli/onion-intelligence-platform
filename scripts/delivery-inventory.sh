#!/usr/bin/env bash
# Version inventory from clean candidate images. Runs without networking or service startup.
set -Eeuo pipefail
prefix="${1:?Usage: bash scripts/delivery-inventory.sh IMAGE_REPOSITORY}"
for target in backend backend-test frontend-build gateway tor postgres; do
  printf '\n[%s]\n' "$target"
  docker image inspect --format '{{.Os}}/{{.Architecture}}' "$prefix:$target"
  docker run --rm --network none --entrypoint sh "$prefix:$target" -ec '
    case "$1" in
      backend|backend-test)
        python --version
        python -m pip list --format=freeze
        ;;
      frontend-build)
        node --version
        npm --version
        packages="$(npm ls --all --parseable)"
        printf "%s\n" "$packages" | while IFS= read -r package; do
          node -p "const p = require(process.argv[1]); p.name + \"==\" + p.version" "$package/package.json"
        done | sort
        ;;
      gateway) nginx -v 2>&1 ;;
      tor) tor --version ;;
      postgres) postgres --version ;;
    esac
    if command -v apk >/dev/null; then
      installed="$(apk --no-network --repositories-file /dev/null info -v)"
    else
      installed="$(dpkg-query -W)"
    fi
    printf "%s\n" "$installed" | sort
  ' sh "$target"
done
