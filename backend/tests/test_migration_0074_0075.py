"""Migrations 0074 (the scoped purge bypass) and 0075 (the audit log under a purge): a clean round trip puts every frozen
table and the audit log back on fn_reject_modification, and the 0074 downgrade refuses once a purge has run — it must
never re-arm the guards under a half-run purge."""
import pytest
from alembic import command

from tests.admin_team import forget_grants
from tests.test_migration_0053 import _cfg, owner, q  # noqa: F401 — owner is a fixture
from tests.test_project_purge_record import approved, execute, promote, record_key, run, two  # noqa: F401 — fixture

USES = ("SELECT f.proname, count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_proc f ON f.oid = t.tgfoid WHERE NOT t.tgisinternal AND (t.tgtype & 8) <> 0 "
        "AND (c.relname LIKE 'baseline\\_%' OR c.relname = 'audit_event') AND c.relname <> 'baseline_archive' "
        "GROUP BY 1 ORDER BY 1")
FUNCS = ("SELECT count(*) FROM pg_proc WHERE proname IN ('fn_purge_allows', 'fn_reject_modification_purgeable', "
         "'fn_reject_modification_audit_purgeable')")


def test_a_clean_downgrade_restores_the_old_guards_and_the_upgrade_returns(owner):
    at_head = q(owner, USES)
    command.downgrade(_cfg(), "0073")
    assert q(owner, FUNCS)[0][0] == 0
    (fn, n), = q(owner, USES)
    assert fn == "fn_reject_modification" and n == sum(c for _, c in at_head)
    header = q(owner, "SELECT prosrc, proconfig FROM pg_proc WHERE proname = 'fn_baseline_header_guard'")[0]
    assert "fn_purge_allows" not in header[0] and header[1] is None
    for guard in ("fn_baseline_archive_guard", "fn_project_purge_key_guard"):
        assert "fn_purge_allows" not in q(owner, f"SELECT prosrc FROM pg_proc WHERE proname = '{guard}'")[0][0]
    command.upgrade(_cfg(), "head")
    assert q(owner, FUNCS)[0][0] == 3
    assert q(owner, USES) == at_head


def test_an_executed_purge_refuses_the_0074_downgrade(two, owner):
    promote(owner, two["a2"])
    pp = approved(owner, two, "DELETE")
    record_key(owner, pp, two["p"], f"vb-test-a-proj-{two['p']}")
    run(owner, "DELETE FROM project WHERE project_id = :p", p=two["p"])                 # bare: no child rows
    execute(owner, two, pp)
    forget_grants(owner)                                                                # slice 17: past 0076 first
    command.downgrade(_cfg(), "0074")                                                   # 0075 down is always safe
    with pytest.raises(Exception, match="a purge has been executed"):
        command.downgrade(_cfg(), "0073")
    command.upgrade(_cfg(), "head")
    assert q(owner, FUNCS)[0][0] == 3
