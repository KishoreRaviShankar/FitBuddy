"""Run `python -m app.manage create-coach` to create the first coach account."""

import argparse
from getpass import getpass

from sqlalchemy import select

from .db import SessionLocal
from .models import User
from .security import hash_password


def create_coach():
    name = input("Coach name: ").strip()
    email = input("Coach email: ").strip().lower()
    password = getpass("Password (12+ characters): ")
    confirm = getpass("Confirm password: ")
    if not 2 <= len(name) <= 100 or "@" not in email or len(email) > 254:
        raise SystemExit("Enter a valid name and email.")
    if len(password) < 12 or password != confirm:
        raise SystemExit("Passwords must match and have at least 12 characters.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("That email is already registered. Choose another email.")
        db.add(User(name=name, email=email, password_hash=hash_password(password), role="coach"))
        db.commit()
    print("Coach created. Sign in at /login.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-coach"])
    args = parser.parse_args()
    if args.command == "create-coach":
        create_coach()
