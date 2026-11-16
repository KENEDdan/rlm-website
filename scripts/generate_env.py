"""Print a .env for LOCAL DEVELOPMENT with freshly generated random secrets.

Usage:  python scripts/generate_env.py > .env
Production secrets are generated on the server (see docs/DEPLOYMENT.md), never on a laptop.
Uses only the standard library so it runs before any dependency is installed.
"""

import base64
import os
import secrets
import sys
from pathlib import Path


def fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def main() -> None:
    template = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    db_password = secrets.token_urlsafe(24)
    values = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DJANGO_ADMIN_URL": f"staff-{secrets.token_hex(4)}/",
        "POSTGRES_PASSWORD": db_password,
        "DATABASE_URL": f"postgres://rlm:{db_password}@db:5432/rlm",
        "FIELD_ENCRYPTION_KEYS": fernet_key(),
        "BLIND_INDEX_KEY": secrets.token_urlsafe(32),
    }
    out = []
    for line in template.splitlines():
        key = line.split("=", 1)[0]
        out.append(f"{key}={values[key]}" if key in values and not line.startswith("#") else line)
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
