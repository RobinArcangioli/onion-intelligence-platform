# OIP M1-C — CI without automatic OVH deployment

**Deployment status:** M1-A monitoring verified on `vps-ovh`. Automatic backups (M1-B) are **deferred by the owner**. No new database migrations, destructive changes, production upgrades or automatic rollback are authorized while recoverability is not revalidated. Tor remains disabled pending the provider's contractual approval.

## What the incremental update does

- Adds `scripts/ci-index-audit.py`, a **read-only** check of Git's staged/index contents that reuses existing forbidden-path and recognizable credential patterns. It does not inspect history, print secret bytes, transmit data, start Docker or connect to OVH.
- Extends `.github/workflows/oip-ci.yml` to run the source tree gate **before** dependencies/tests. Other jobs continue to run backend tests, OVH policy tests, unit tests and frontend build, with `contents: read` and no deploy credentials.
- Adds unit tests of the safety gate, including an accidentally staged `.env`, a token shape and a missing npm lockfile.

## How to validate locally

On a genuine Git worktree (not a ZIP-only extract):

```bash
python3 scripts/ci-index-audit.py
python3 -m unittest discover -s deploy/ovh/tests -q
python3 scripts/verify-manifest.py
```

The last command requires the updated `RELEASE_SHA256SUMS.txt` manifest from the same delivery. **Do not copy the ZIP to a stale Git worktree and then expect its index to include new files**: in a Git clone, stage the new files first before `ci-index-audit.py`. Do not add `.env` or credentials.

## GitHub is already public; do not push by default

The connected repository was observed as **public** on 2026-10-24 (`RobinArcangioli/onion-intelligence-platform`, default `main`). The M1 CI workflow was absent from that branch at inspection time. An earlier `pre-push-audit.py` reports historical numbered-doc remnants. This index-only scan is not sufficient to declare history clean. Before changing the public repo: conduct the *full* history/secret/license review, confirm owner's intended publication and license, and authorize the actual push/PR separately. Neither this patch nor its tests publishes code.

## Operational safety

This update is **source-only**. It is not needed on the running VPS, changes no application/runtime configuration, creates no `systemd` unit, uses no SSH/network connection, leaves `oip-monitor.timer` active and `oip-backup.timer` disabled. No `deploy.sh deploy`, `docker compose up`, Alembic, DB recreation, Tor, firewall edits or DNS changes.

This is not a green light to upgrade the running application. To upgrade or migrate later, complete an encrypted offsite backup and a real recovery rehearsal, then follow the existing operator runbook and `deploy.sh` guard.
