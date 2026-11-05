"""Local-only CLI for named operators and revocable API tokens.

Usage: docker compose exec -T api python -m app.security.manage_users ...
Never pass tokens on the command line. New tokens are printed exactly once.
"""
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.session import session_factory
from app.models.identity import Operator, OperatorToken
from app.models.audit import AuditLog
from app.security.api_key import ROLE_LEVEL, fingerprint, new_token

USERNAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
TOKEN_LABEL = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_ACTIVE_TOKENS = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local OIP operator/key administration")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Create a named user and issue its first token")
    create.add_argument("username")
    create.add_argument("--role", choices=ROLE_LEVEL, required=True)
    create.add_argument("--days", type=int, default=30)
    issue = sub.add_parser("issue", help="Issue a new token for an existing user")
    issue.add_argument("username")
    issue.add_argument("--days", type=int, default=30)
    issue.add_argument("--label", default="console", help="Non-sensitive token purpose, 1-32 characters")
    rotate = sub.add_parser("rotate", help="Atomically replace a token by UUID (prints a new token once)")
    rotate.add_argument("token_id", type=uuid.UUID)
    rotate.add_argument("--days", type=int, default=30)
    rotate.add_argument("--label", help="Optional new non-sensitive purpose label")
    revoke = sub.add_parser("revoke", help="Revoke a token by UUID, not by secret")
    revoke.add_argument("token_id", type=uuid.UUID)
    disable = sub.add_parser("disable", help="Disable an operator and revoke all tokens (protect last admin)")
    disable.add_argument("username")
    enable = sub.add_parser("enable", help="Re-enable an operator (no tokens issued)")
    enable.add_argument("username")
    set_role = sub.add_parser("set-role", help="Change a role and revoke all existing tokens")
    set_role.add_argument("username")
    set_role.add_argument("--role", choices=ROLE_LEVEL, required=True)
    show = sub.add_parser("list", help="Show operators and token IDs; no secrets")
    args = parser.parse_args(argv)
    if args.command in ("create", "issue", "rotate") and not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    if args.command in ("create", "issue", "disable", "enable", "set-role") and not USERNAME.fullmatch(args.username):
        parser.error("username must match ^[a-z][a-z0-9_-]{2,63}$")
    if args.command in ("issue", "rotate") and args.label is not None and not TOKEN_LABEL.fullmatch(args.label):
        parser.error("--label must match ^[a-z][a-z0-9_-]{0,31}$")

    with session_factory()() as db:
        if args.command == "list":
            for user in db.scalars(select(Operator).order_by(Operator.username)):
                print(f"{user.username} role={user.role} active={user.active}")
                for token in db.scalars(select(OperatorToken).where(OperatorToken.operator_id == user.id)):
                    print(f"  {token.id} label={token.label} expires={token.expires_at} revoked={token.revoked_at is not None}")
            return 0
        if args.command == "revoke":
            token = db.get(OperatorToken, args.token_id)
            if token is None:
                print("Token not found", file=sys.stderr)
                return 1
            token.revoked_at = datetime.now(timezone.utc)
            db.add(AuditLog(actor="local_admin_cli", action="operator.token.revoke",
                            entity_type="operator", entity_id=token.operator_id,
                            details=json.dumps({"token_id": str(token.id)})))
            db.commit()
            print("Revoked")
            return 0
        if args.command == "rotate":
            # Read identity, then lock the operator BEFORE locking the token, to
            # preserve the same ordering as issue/disable/set-role. An old
            # credential remains valid if any step of the transaction fails.
            existing = db.get(OperatorToken, args.token_id)
            if existing is None:
                print("Token not found", file=sys.stderr)
                return 1
            owner = db.scalar(select(Operator).where(Operator.id == existing.operator_id).with_for_update())
            old = db.scalar(select(OperatorToken).where(OperatorToken.id == args.token_id).with_for_update())
            now = datetime.now(timezone.utc)
            if owner is None or not owner.active or old is None or old.revoked_at is not None:
                print("Inactive or revoked token", file=sys.stderr)
                return 1
            expiry = old.expires_at.replace(tzinfo=timezone.utc) if old.expires_at.tzinfo is None else old.expires_at
            if expiry <= now:
                print("Expired token: issue a new token instead", file=sys.stderr)
                return 1
            new_plaintext = new_token()
            replacement = OperatorToken(
                operator_id=owner.id, token_hash=fingerprint(new_plaintext),
                label=args.label if args.label is not None else old.label,
                expires_at=now + timedelta(days=args.days),
            )
            old.revoked_at = now
            db.add(replacement)
            db.flush()
            db.add(AuditLog(actor="local_admin_cli", action="operator.token.rotate",
                            entity_type="operator", entity_id=owner.id,
                            details=json.dumps({"old_token_id": str(old.id),
                                                "new_token_id": str(replacement.id)}, sort_keys=True)))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                print("Database constraint failure", file=sys.stderr)
                return 1
            print(f"operator={owner.username} role={owner.role} token_id={replacement.id}")
            print(f"API_TOKEN={new_plaintext}")
            print("The replaced token is revoked; securely store the new one.", file=sys.stderr)
            return 0
        # Serialize privilege changes against other CLI processes on PostgreSQL.
        # The ordered row locks prevent two concurrent demotions/disables from
        # accidentally eliminating the final active administrator.
        if args.command in ("disable", "set-role"):
            administrators = db.scalars(
                select(Operator).where(Operator.active.is_(True), Operator.role == "ADMIN")
                .order_by(Operator.id).with_for_update()
            ).all()
        else:
            administrators = []
        user = db.scalar(select(Operator).where(Operator.username == args.username).with_for_update())
        if args.command in ("disable", "enable", "set-role"):
            if user is None:
                print("Operator not found", file=sys.stderr)
                return 1
            if args.command == "disable" and not user.active:
                print("Operator already disabled", file=sys.stderr)
                return 1
            if args.command == "enable" and user.active:
                print("Operator already enabled", file=sys.stderr)
                return 1
            if args.command == "set-role" and user.role == args.role:
                print("Role unchanged", file=sys.stderr)
                return 1
            if (args.command == "disable" or
                (args.command == "set-role" and args.role != "ADMIN")) and \
                    user.active and user.role == "ADMIN" and len(administrators) <= 1:
                print("Cannot remove the last active administrator", file=sys.stderr)
                return 1
            if args.command == "disable":
                user.active = False
                action = "operator.disable"
            elif args.command == "enable":
                user.active = True
                action = "operator.enable"
            else:
                old_role = user.role
                user.role = args.role
                action = "operator.role_change"
            revoked_count = 0
            if args.command != "enable":
                revoked_count = db.execute(
                    update(OperatorToken)
                    .where(OperatorToken.operator_id == user.id, OperatorToken.revoked_at.is_(None))
                    .values(revoked_at=datetime.now(timezone.utc))
                ).rowcount
            data = {"tokens_revoked": revoked_count}
            if args.command == "set-role":
                data.update({"previous_role": old_role, "new_role": args.role})
            db.add(AuditLog(actor="local_admin_cli", action=action,
                            entity_type="operator", entity_id=user.id,
                            details=json.dumps(data, sort_keys=True)))
            db.commit()
            print(f"Operator updated: {action}; revoked_tokens={revoked_count}")
            if args.command == "enable":
                print("Use 'issue' to create a fresh token; old tokens remain invalid.")
            return 0
        if args.command == "create":
            if user is not None:
                print("Operator already exists", file=sys.stderr)
                return 1
            user = Operator(username=args.username, role=args.role)
            db.add(user)
            db.flush()
        elif user is None or not user.active:
            print("Active operator not found", file=sys.stderr)
            return 1
        # Lock the operator row for issue/create as well: PostgreSQL serializes
        # multiple issuer processes through this row when enforcing the quota.
        if args.command == "issue":
            now = datetime.now(timezone.utc)
            active_count = db.scalar(select(func.count()).select_from(OperatorToken).where(
                OperatorToken.operator_id == user.id,
                OperatorToken.revoked_at.is_(None),
                OperatorToken.expires_at > now,
            ))
            if active_count >= MAX_ACTIVE_TOKENS:
                print(f"Active token limit reached ({MAX_ACTIVE_TOKENS}); revoke or rotate one", file=sys.stderr)
                return 1
        plaintext = new_token()
        token = OperatorToken(operator_id=user.id, token_hash=fingerprint(plaintext),
                              label=args.label if args.command == "issue" else "console",
                              expires_at=datetime.now(timezone.utc) + timedelta(days=args.days))
        db.add(token)
        db.flush()
        db.add(AuditLog(actor="local_admin_cli", action="operator.token.issue",
                        entity_type="operator", entity_id=user.id,
                        details=json.dumps({"token_id": str(token.id), "role": user.role})))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print("Database constraint failure", file=sys.stderr)
            return 1
        print(f"operator={user.username} role={user.role} token_id={token.id}")
        print(f"API_TOKEN={plaintext}")
        print("Store the token securely: it will not be shown again.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
