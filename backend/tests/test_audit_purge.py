"""Slice 16, migration 0075: the audit log under a purge (schema §4, §5; spec §18 S8; Q-69 b, AR-3). Grade 1 — the
audit log is append-only by design: only the owner-run purge of one approved, aged request may delete that project's
own rows, never a removal event, and nobody may ever change a row."""
from database import engine as app_engine
from tests.test_project_purge_record import backdate, owner, run  # noqa: F401 — owner is a fixture
from tests.test_purge_bypass import approve, frozen, purge_refused, purge_tx, request  # noqa: F401 — frozen is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

KEPT = ("PURGE_REQUESTED", "PURGE_APPROVED", "PURGE_CANCELLED", "PURGE_ARCHIVE_WRITTEN", "PROJECT_PURGED",
        "PURGE_KEYS_DESTROYED", "PURGE_ARCHIVE_DELETED")
KEPT_EVENT = ("INSERT INTO audit_event (event_type, app_user_id, project_id, target_table, target_id) "
              "VALUES ('PROJECT_PURGED', :u, :p, 'project_purge', 1)")


def test_a_purge_deletes_the_projects_audit_rows_but_never_a_removal_event(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    own = f"DELETE FROM audit_event WHERE project_id = {frozen['p']}"
    assert "immutable" in purge_refused(owner, frozen["p"], own)                        # not yet 24 hours
    backdate(owner, pp)
    assert "immutable" in purge_refused(owner, None, own)                               # no setting
    assert purge_tx(owner, frozen["p"], own) > 0                                        # the project's own rows go
    assert "immutable" in purge_refused(owner, frozen["p"], "DELETE FROM audit_event "
                                                            f"WHERE project_id = {frozen['other']}")
    assert "immutable" in purge_refused(owner, frozen["p"], "UPDATE audit_event SET detail = NULL "
                                                            f"WHERE project_id = {frozen['p']}")
    assert "permission denied" in purge_refused(app_engine, frozen["p"], own)
    run(owner, KEPT_EVENT, u=frozen["a1"], p=frozen["p"])                               # a mis-written removal event
    assert "immutable" in purge_refused(owner, frozen["p"], own)                        # survives, so the purge stops


def test_every_kept_removal_event_is_named_in_the_audit_trigger(owner):
    src = run(owner, "SELECT prosrc FROM pg_proc WHERE proname = 'fn_reject_modification_audit_purgeable'")[0]
    assert all(f"'{event}'" in src for event in KEPT)
    assert "LIKE" not in src                                                            # S8: by name, not pattern
    trig = run(owner, "SELECT f.proname FROM pg_trigger t JOIN pg_proc f ON f.oid = t.tgfoid "
                      "WHERE t.tgname = 'trg_audit_event_immutable'")[0]
    assert trig == "fn_reject_modification_audit_purgeable"
