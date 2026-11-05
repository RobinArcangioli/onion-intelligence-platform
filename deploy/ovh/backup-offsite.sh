#!/usr/bin/env bash
# Encrypted PostgreSQL backup streamed to a separate SSH backup host.
# NO local plaintext dump, NO Tor, NO database modifications.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT"
for cmd in age ssh docker date; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
: "${OIP_BACKUP_RECIPIENT:?Specify a public age recipient}"
: "${OIP_BACKUP_SSH_TARGET:?Specify a preconfigured SSH user@backuphost alias}"
: "${OIP_BACKUP_REMOTE_DIR:?Specify an existing or creatable absolute remote directory}"
[[ "$OIP_BACKUP_RECIPIENT" == age1* ]] || { echo 'Use a public age1 recipient' >&2; exit 1; }
[[ "$OIP_BACKUP_SSH_TARGET" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$ ]] || { echo 'Invalid backup SSH target' >&2; exit 1; }
[[ "$OIP_BACKUP_REMOTE_DIR" =~ ^/[a-zA-Z0-9_./-]+$ && "$OIP_BACKUP_REMOTE_DIR" != *..* ]] || { echo 'Invalid backup directory' >&2; exit 1; }
[[ -f .env && ! -L .env ]] || { echo 'Missing root .env' >&2; exit 1; }
[[ -z "${COMPOSE_PROFILES:-}" ]] || { echo 'Profile overrides forbidden' >&2; exit 1; }
name="oip-$(date -u +%Y%m%dT%H%M%SZ).dump.age"
# A two-phase remote commit avoids publishing an incomplete but valid .age file
# if pg_dump or age fails after the SSH writer has received some bytes.
# The destination is a dedicated Linux account and must be on another host.
remote_file="${OIP_BACKUP_REMOTE_DIR}/${name}"
remote_partial="${OIP_BACKUP_REMOTE_DIR}/.${name}.partial.$$"
remote_stage="set -eu; umask 077; mkdir -p '${OIP_BACKUP_REMOTE_DIR}'; test ! -e '${remote_file}'; test ! -e '${remote_partial}'; (set -C; cat > '${remote_partial}'); test -s '${remote_partial}'"
ssh_args=(-o BatchMode=yes -o StrictHostKeyChecking=yes)
if ! (set -o pipefail;
  docker compose --project-name onion-intelligence-platform --env-file "$ROOT/.env" \
    -f "$ROOT/compose.yaml" -f "$ROOT/deploy/ovh/compose.private.yaml" \
    exec -T db sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
    | age -r "$OIP_BACKUP_RECIPIENT" \
    | ssh "${ssh_args[@]}" -- "$OIP_BACKUP_SSH_TARGET" "$remote_stage"
); then
  # Best-effort cleanup; keep the original failure status. No finalized archive.
  ssh "${ssh_args[@]}" -- "$OIP_BACKUP_SSH_TARGET" \
    "rm -f -- '${remote_partial}'" >/dev/null 2>&1 || true
  echo 'NO-GO: encrypted transfer failed (no completed archive was published)' >&2
  exit 1
fi
# Only after the entire pipe succeeded can the file become an archive.
# mv -n protects against collisions; the final test catches a refused move.
remote_commit="set -eu; test -s '${remote_partial}'; test ! -e '${remote_file}'; mv -n -- '${remote_partial}' '${remote_file}'; test -s '${remote_file}'; test ! -e '${remote_partial}'"
ssh "${ssh_args[@]}" -- "$OIP_BACKUP_SSH_TARGET" "$remote_commit"
# Only a completed encrypted transfer counts as fresh. This is NOT a restore proof.
# Do not write a success marker if the pipe (pg_dump/age/ssh) failed.
if [[ -d /var/lib/oip-monitor && ! -L /var/lib/oip-monitor ]]; then
  stamp_tmp="$(mktemp /var/lib/oip-monitor/.backup-ok.XXXXXXXX)"
  trap 'rm -f -- "$stamp_tmp"' EXIT
  printf '%s\n' "$name" > "$stamp_tmp"
  chmod 0600 "$stamp_tmp"
  mv -f -- "$stamp_tmp" /var/lib/oip-monitor/last-backup-ok
  trap - EXIT
else
  echo 'WARN: freshness marker directory unavailable; install systemd units first' >&2
fi
printf 'PASS: encrypted backup streamed offsite (restore rehearsal still required): %s\n' "$name"
