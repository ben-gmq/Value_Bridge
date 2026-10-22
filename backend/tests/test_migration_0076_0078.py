"""Slice 17 migrations 0076–0078 (schema rev 3 §8). 0076's backfill records every flagged admin from their latest grant
event — BOOTSTRAP for a created admin, LEGACY for a promoted one — and records nobody it cannot prove (D2); its
downgrade refuses once a record exists that the backfill did not write."""
import pytest
from alembic import command

from tests.admin_team import run
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture

USER = ("INSERT INTO app_user (email, password_hash, display_name, is_platform_admin) VALUES (:e, 'x', :e, :a) "
        "RETURNING app_user_id")
EVENT = ("INSERT INTO audit_event (event_type, app_user_id, target_table, target_id, detail, occurred_at) "
         "VALUES (:t, :by, 'app_user', :u, CAST(:d AS jsonb), now() - make_interval(days => :days))")


def test_the_backfill_records_each_admin_it_can_prove_and_skips_the_rest(owner):
    command.downgrade(_cfg(), "0075")
    first = run(owner, USER, e="first@example.test", a=True)[0]
    x(owner, EVENT, t="FIRST_ADMIN_CREATED", by=first, u=first, d=None, days=90)
    second = run(owner, USER, e="second@example.test", a=True)[0]
    x(owner, EVENT, t="PLATFORM_ADMIN_GRANTED", by=first, u=second, d='{"rationale": "Cover"}', days=40)
    x(owner, EVENT, t="PLATFORM_ADMIN_GRANTED", by=first, u=second, d='{"rationale": "Older"}', days=60)
    unproven = run(owner, USER, e="noevent@example.test", a=True)[0]
    run(owner, USER, e="staff@example.test", a=False)
    command.upgrade(_cfg(), "0076")
    rows = q(owner, "SELECT target_user_id, grant_origin, requested_by_user_id, reason, operator_name, "
                    "approved_at < now() - interval '39 days', source_audit_event_id IS NOT NULL "
                    "FROM platform_admin_grant ORDER BY target_user_id")
    assert rows == [(first, "BOOTSTRAP", None, f"recorded by migration 0076 from audit event "
                     f"{q(owner, 'SELECT min(audit_event_id) FROM audit_event')[0][0]}", "migration 0076", True, True),
                    (second, "LEGACY", first, "Cover", "migration 0076", True, True)]
    assert unproven not in [r[0] for r in rows]                                        # D2: named in a NOTICE only


def test_a_record_the_backfill_did_not_write_refuses_the_0076_downgrade(owner):
    command.downgrade(_cfg(), "0075")
    a = run(owner, USER, e="a@example.test", a=True)[0]
    x(owner, EVENT, t="FIRST_ADMIN_CREATED", by=a, u=a, d=None, days=90)
    command.upgrade(_cfg(), "0076")
    tgt = run(owner, USER, e="t@example.test", a=False)[0]
    x(owner, "INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, requested_by_user_id) "
             "VALUES ('REQUEST', :t, 'Cover', :a)", t=tgt, a=a)
    with pytest.raises(Exception, match="backfill did not write"):
        command.downgrade(_cfg(), "0075")
    assert q(owner, "SELECT count(*) FROM platform_admin_grant")[0][0] == 2
