"""Record a platform-admin grant as Fortience IS — the LEGACY path (slice17 schema rev 3 §3.2; AR-19, AR-22, AR-25). Run
from backend/, as the owner (MIGRATION_DATABASE_URL), by an IS operator:
    ./venv/bin/python -m seeds.owner_grant --email <user> --reason "<why>" --operator "<your name>" \\
        --actor-email <the platform admin who asked>
The way a fresh install's third admin is made (AR-25), and the way back when admins were lost. The database refuses it
unless the asking admin is live, did not create the account (AR-24), and the user is active and not yet an admin; its
date is the database's own except on a named test or demo database (fn_backdating_allowed, N4)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from config import get_settings  # noqa: E402


def legacy_grant(c: Connection, user_id: int, reason: str, operator: str, actor_id: int, days: int = 0) -> int:
    """In the caller's transaction on the owner connection: the LEGACY record, the flag and the audit row together
    (the deferred check refuses one without the other). `days` > 0 only where the database allows backdating."""
    if c.scalar(text("SELECT session_user")) != "vb_owner":
        raise SystemExit("Run this as the owner role (MIGRATION_DATABASE_URL).")
    if days and not c.scalar(text("SELECT fn_backdating_allowed()")):
        raise SystemExit("A grant may be backdated only on a named test or demo database (N4).")
    g = c.execute(text("INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, operator_name, "
                       "requested_by_user_id, requested_at) VALUES ('LEGACY', :u, :r, :o, :a, "
                       "now() - make_interval(days => :d)) RETURNING platform_admin_grant_id"),
                  {"u": user_id, "r": reason, "o": operator, "a": actor_id, "d": days}).scalar_one()
    c.execute(text("UPDATE app_user SET is_platform_admin = true WHERE app_user_id = :u"), {"u": user_id})
    c.execute(text("INSERT INTO audit_event (event_type, app_user_id, target_table, target_id, detail) "
                   "VALUES ('PLATFORM_ADMIN_GRANTED', :a, 'app_user', :u, CAST(:d AS jsonb))"),
              {"a": actor_id, "u": user_id, "d": json.dumps({"origin": "LEGACY", "grant_id": g, "operator": operator,
                                                             "rationale": reason})})
    return g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--operator", required=True)
    ap.add_argument("--actor-email", required=True)
    a = ap.parse_args()
    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.begin() as c:
            ids = {e: c.scalar(text("SELECT app_user_id FROM app_user WHERE lower(email) = lower(:e)"), {"e": e})
                   for e in (a.email, a.actor_email)}
            if None in ids.values():
                raise SystemExit("No user with that email.")
            g = legacy_grant(c, ids[a.email], a.reason, a.operator, ids[a.actor_email])
    finally:
        eng.dispose()
    print(f"Recorded grant {g}: {a.email} is a platform admin, asked for by {a.actor_email}, run by {a.operator}.")


if __name__ == "__main__":
    main()
