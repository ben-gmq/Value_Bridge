"""Create a platform administrator from the command line — the way the first admin is made in
any environment where first-run setup is switched off (sara H1, Azure). Run from backend/:
    python -m seeds.create_admin --email a@ftc-domain --name "Ada Admin"
The password is read from a prompt, never from argv or the environment, and never echoed."""
import argparse
import getpass

from auth.security import hash_password
from database import SessionLocal
from models import AppUser
from services import audit
from services.user_admin import MIN_PASSWORD, check_ftc_address


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    check_ftc_address(args.email)
    pw = getpass.getpass("Password: ")
    if len(pw) < MIN_PASSWORD or pw != getpass.getpass("Repeat: "):
        raise SystemExit(f"Passwords must match and be at least {MIN_PASSWORD} characters")
    with SessionLocal() as db:
        user = AppUser(email=args.email.strip(), display_name=args.name.strip(),
                       password_hash=hash_password(pw), is_platform_admin=True)
        db.add(user)
        db.flush()
        audit.record(db, "ADMIN_CREATED_BY_CLI", actor_id=user.app_user_id,
                     target_table="app_user", target_id=user.app_user_id)
        db.commit()
        print(f"Created platform administrator {user.email} (id {user.app_user_id})")


if __name__ == "__main__":
    main()
