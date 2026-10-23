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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import session_factory
from app.models.identity import Operator, OperatorToken
from app.models.audit import AuditLog
from app.security.api_key import ROLE_LEVEL, fingerprint, new_token

USERNAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


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
    revoke = sub.add_parser("revoke", help="Revoke a token by UUID, not by secret")
    revoke.add_argument("token_id", type=uuid.UUID)
    disable = sub.add_parser("disable", help="Disable an operator and all their tokens")
    disable.add_argument("username")
    show = sub.add_parser("list", help="Show operators and token IDs; no secrets")
    args = parser.parse_args(argv)
    if args.command in ("create", "issue") and not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    if args.command in ("create", "issue", "disable") and not USERNAME.fullmatch(args.username):
        parser.error("username must match ^[a-z][a-z0-9_-]{2,63}$")

    with session_factory()() as db:
        if args.command == "list":
            for user in db.scalars(select(Operator).order_by(Operator.username)):
                print(f"{user.username} role={user.role} active={user.active}")
                for token in db.scalars(select(OperatorToken).where(OperatorToken.operator_id == user.id)):
                    print(f"  {token.id} expires={token.expires_at} revoked={token.revoked_at is not None}")
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
        user = db.scalar(select(Operator).where(Operator.username == args.username))
        if args.command == "disable":
            if user is None:
                print("Operator not found", file=sys.stderr)
                return 1
            user.active = False
            db.add(AuditLog(actor="local_admin_cli", action="operator.disable",
                            entity_type="operator", entity_id=user.id, details="{}"))
            db.commit()
            print("Operator disabled")
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
        plaintext = new_token()
        token = OperatorToken(operator_id=user.id, token_hash=fingerprint(plaintext),
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
