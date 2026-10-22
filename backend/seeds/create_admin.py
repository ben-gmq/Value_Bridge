"""Create one of the first two platform administrators from the command line (AR-16) — as the owner, by Fortience IS
(AR-22), in any environment where first-run setup is switched off (sara H1, Azure). Run from backend/:
    python -m seeds.create_admin --email a@ftc-domain --name "Ada Admin" --operator "<your name>" \\
        [--actor-email <the live admin who asked — required once one exists>]
It connects with MIGRATION_DATABASE_URL. The database records it as a BOOTSTRAP grant naming the operator and the
asking admin, and refuses once two people have ever been granted admin rights: every further admin comes through a
request a second admin approves, or an IS grant (seeds.owner_grant). The password is read from a prompt, never from
argv or the environment, and never echoed."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from auth.security import hash_password  # noqa: E402
from config import get_settings  # noqa: E402
from services.user_admin import MIN_PASSWORD, check_ftc_address  # noqa: E402

GRANTED = ("SELECT GREATEST((SELECT count(DISTINCT target_user_id) FROM platform_admin_grant "
           "WHERE approved_at IS NOT NULL), (SELECT count(*) FROM app_user WHERE is_active AND is_platform_admin))")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--operator", required=True)
    ap.add_argument("--actor-email")
    args = ap.parse_args()
    check_ftc_address(args.email)
    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.connect() as c:
            if c.scalar(text(GRANTED)) >= 2:                           # the database refuses too; say it first
                raise SystemExit("Two admins have already been granted: ask a platform admin to request admin rights, "
                                 "or record an IS grant with seeds.owner_grant.")
        pw = getpass.getpass("Password: ")
        if len(pw) < MIN_PASSWORD or pw != getpass.getpass("Repeat: "):
            raise SystemExit(f"Passwords must match and be at least {MIN_PASSWORD} characters")
        with eng.begin() as c:
            actor = None
            if args.actor_email:
                actor = c.scalar(text("SELECT app_user_id FROM app_user WHERE lower(email) = lower(:e)"),
                                 {"e": args.actor_email})
                if actor is None:
                    raise SystemExit("No user with the --actor-email address.")
            c.execute(text("SELECT set_config('vb.operator', :o, true), set_config('vb.grant_actor_id', :a, true)"),
                      {"o": args.operator, "a": str(actor) if actor else ""})
            uid = c.execute(text("INSERT INTO app_user (email, display_name, password_hash, is_platform_admin, "
                                 "user_kind) VALUES (:e, :n, :h, true, 'USER') RETURNING app_user_id"),
                            {"e": args.email.strip(), "n": args.name.strip(), "h": hash_password(pw)}).scalar_one()
            c.execute(text("INSERT INTO audit_event (event_type, app_user_id, target_table, target_id) "
                           "VALUES ('ADMIN_CREATED_BY_CLI', :a, 'app_user', :u)"), {"a": actor or uid, "u": uid})
    finally:
        eng.dispose()
    print(f"Created platform administrator {args.email} (id {uid}), recorded as run by {args.operator}.")


if __name__ == "__main__":
    main()
