"""Test helpers for slice 17: a team of admins made the way AR-16 / AR-24 / AR-25 allow, on the test database only.

- `seed_bootstrap(owner, uid)`: the setup admin's BOOTSTRAP row, as 0078's trigger writes it; before 0078 the test
  writes it with the guard switched off for that one statement (test-only, as `backdate`).
- `owner_user(owner, email)`: an account made by the owner (created_by NULL), so no admin is its creator.
- `legacy(owner, uid, asker, days)`: the IS LEGACY grant (AR-19, AR-25) — owner, operator, asking admin; backdated
  `days` (allowed on this database by fn_backdating_allowed) — and the flag, in one transaction.
The team: a1 the setup admin; a2 owner-made, granted at a1's request; a3 owner-made, granted at a2's request.
Independent pairs (neither made the other): (a1, a3) only."""
from sqlalchemy import text

from auth.security import hash_password
from tests.conftest import PW


def run(eng, sql, **kw):
    with eng.begin() as c:
        r = c.execute(text(sql), kw)
        return r.first() if r.returns_rows else None


def seed_bootstrap(owner, uid: int) -> None:
    if run(owner, "SELECT count(*) FROM platform_admin_grant WHERE target_user_id = :u", u=uid)[0]:
        return                                                        # 0078's trigger already wrote it
    run(owner, "ALTER TABLE platform_admin_grant DISABLE TRIGGER trg_platform_admin_grant_guard")
    try:                                     # three transactions: the deferred trigger holds the table until commit
        run(owner, "INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, operator_name, "
                   "requested_at, approved_at, approved_xact) VALUES ('BOOTSTRAP', :u, 'setup', 'test', "
                   "now() - interval '400 days', now() - interval '400 days', pg_current_xact_id())", u=uid)
    finally:
        run(owner, "ALTER TABLE platform_admin_grant ENABLE TRIGGER trg_platform_admin_grant_guard")


def forget_grants(owner) -> None:
    """Test-only: a migration test that steps below 0076 to prove an older guard empties the grant record first (0076's
    own downgrade refuses while records it did not write exist — proven in test_migration_0076_0078)."""
    run(owner, "TRUNCATE platform_admin_grant")


def owner_user(owner, email: str, kind: str = "USER") -> int:
    return run(owner, "INSERT INTO app_user (email, password_hash, display_name, user_kind) "
                      "VALUES (:e, :h, :n, :k) RETURNING app_user_id",
               e=email, h=hash_password(PW), n=email.split("@")[0].title(), k=kind)[0]


def legacy(owner, uid: int, asker: int, days: int = 0, operator: str = "IS test") -> int:
    """The single fixture path (S3): the IS command's own function."""
    from seeds.owner_grant import legacy_grant
    with owner.begin() as c:
        return legacy_grant(c, uid, "IS grant for a test", operator, asker, days)


def team(owner, world, days: int = 31) -> dict:
    a1 = run(owner, "SELECT app_user_id FROM app_user WHERE email = 'admin@example.test'")[0]
    seed_bootstrap(owner, a1)
    a2 = owner_user(owner, "a2@example.test")
    legacy(owner, a2, a1, days)
    a3 = owner_user(owner, "a3@example.test")
    legacy(owner, a3, a2, days)
    return {"a1": a1, "a2": a2, "a3": a3, "users": world["users"]}
