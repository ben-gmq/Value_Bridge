"""The weekly archive check (services/weekly_check, scripts/weekly_check; slice16 §1a, R14, S5, U1, U5; VB-012).
Grade 2, with U1 at the edge of Grade 1: a held project archive is the only copy of a removed project, so a lost file or
key must be reported, not missed. Each check is proven on a real stored file in a throwaway folder, tampered with,
removed, or its key destroyed; every report line is made non-empty by the event it names."""
import base64
import json
import os
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select, text

from models import BaselineArchive
from services import archive, weekly_check
from services.baseline import local_today
from tests.conftest import OWNER_URL, login
from tests.test_archive import arch  # noqa: F401 — arch is a fixture
from tests.test_baseline import bid, freeze, scope
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

API = "/api/v1"


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def frozen(client, world, ed, arch, db):
    """One frozen baseline with its SCOPE file written to this test's own folder."""
    scope(client, ed)
    b = bid(freeze(client, ed))
    archive.write_pending(*arch, limit=10)
    admin = db.execute(text("SELECT app_user_id FROM app_user WHERE email = 'admin@example.test'")).scalar_one()
    return {"b": b, "p": ed["p"], "store": arch[0], "keys": arch[1], "admin": admin, "world": world}


def run(db, f):
    db.expire_all()
    return weekly_check.run(db, f["store"], f["keys"], f["admin"], "IS test")


def scope_row(db, f, seq=1):
    db.expire_all()
    return db.scalar(select(BaselineArchive).where(BaselineArchive.baseline_id == f["b"],
                                                   BaselineArchive.archive_part == "SCOPE",
                                                   BaselineArchive.file_seq == seq))


def events(db, kind: str) -> list[tuple]:
    return [tuple(r) for r in db.execute(text("SELECT target_id, detail->>'error' FROM audit_event "
                                              "WHERE event_type = :k ORDER BY audit_event_id"), {"k": kind})]


def overwrite(f, name: str, data: bytes) -> None:
    path = f["store"].root / name
    os.chmod(path, 0o644)
    path.write_bytes(data)


def test_an_intact_file_passes_and_every_run_records_its_line(frozen, db, client):
    """R14, U5: nothing to report is still reported, and the Removals card shows when it ran."""
    rep = run(db, frozen)
    assert rep["failed_files"] == [] and rep["summary"]["failed_files"] == 0
    card = client.get(f"{API}/admin/weekly-check", headers=frozen["world"]["admin"]).json()
    assert card["last_run"]["ran_at"] is not None and card["last_run"]["stale"] is False
    assert card["last_run"]["summary"]["failed_files"] == 0
    assert client.get(f"{API}/admin/weekly-check", headers=login(client, "editor@example.test")).status_code == 403


@pytest.mark.parametrize("damage, why", [("tamper", weekly_check.DIFFERS), ("remove", weekly_check.MISSING)])
def test_a_damaged_file_is_marked_and_its_replacement_owed_then_written(frozen, db, damage, why):
    """S5: the failure goes on the row, file n + 1 is owed in the same transaction, the writer writes it, and the
    next run is clean."""
    row = scope_row(db, frozen)
    if damage == "tamper":
        overwrite(frozen, row.object_name, b"x" + frozen["store"].get(row.object_name)[1:])
    else:
        (frozen["store"].root / row.object_name).unlink()
    rep = run(db, frozen)
    assert [(x["baseline_id"], x["error"], x["replacement_file_seq"]) for x in rep["failed_files"]] == \
        [(frozen["b"], why, 2)]
    assert events(db, "ARCHIVE_CHECK_FAILED") == [(frozen["b"], why)]
    assert scope_row(db, frozen).check_failed_at is not None and scope_row(db, frozen).last_check_error == why
    assert scope_row(db, frozen, 2).written_at is None                                 # owed
    again = run(db, frozen)
    assert again["failed_files"] == [] and again["summary"]["owed_files"] == 1          # reported, not re-flagged
    archive.write_pending(frozen["store"], frozen["keys"], limit=10)
    assert scope_row(db, frozen, 2).written_at is not None
    assert run(db, frozen)["summary"]["owed_files"] == 0


def _held_archive(owner, f, pid=999):
    """Test-only: an executed ARCHIVE whose project file is stored and recorded (the ARCHIVE run is not built)."""
    ref = f["keys"].current_ref("test-a", pid, create=True)
    blob = json.dumps({"key_ref": ref, "wrapped_data_key":
                       base64.b64encode(f["keys"].wrap(ref, os.urandom(32))).decode()}).encode()
    name = f"test-a/{pid}/project-1.json.enc"
    f["store"].put_once(name, blob)
    import hashlib
    with owner.begin() as c:
        c.execute(text("ALTER TABLE project_purge DISABLE TRIGGER trg_project_purge_guard"))
    try:
        with owner.begin() as c:
            pp = c.execute(text(
                "INSERT INTO project_purge (purge_kind, project_id, client_id, project_code, reason, "
                "requested_by_user_id, requested_at, approved_by_user_id, approved_at, executed_by_user_id, "
                "executed_at, backups_age_out_on, archive_object_name, archive_sha256, archive_byte_size, "
                "archive_key_ref) VALUES ('ARCHIVE', :p, :c, 'GONE', 'two years closed', :a, now(), :b, now(), :a, "
                "now(), current_date, :n, :h, :s, :r) RETURNING project_purge_id"),
                {"p": pid, "c": f["world"]["client_id"], "a": f["admin"], "b": f["world"]["users"]["owner"], "n": name,
                 "h": hashlib.sha256(blob).hexdigest(), "s": len(blob), "r": ref}).scalar_one()
    finally:
        with owner.begin() as c:
            c.execute(text("ALTER TABLE project_purge ENABLE TRIGGER trg_project_purge_guard"))
    return pp, name, ref


def test_a_held_project_archive_is_checked_and_a_lost_key_or_file_reported(frozen, db, owner, client):
    """U1, criterion 26: the only copy of an archived project — object, size, sha256 and key — every week."""
    pp, name, ref = _held_archive(owner, frozen)
    held = run(db, frozen)["held_archives"]
    assert held == [{"project_purge_id": pp, "project_code": "GONE", "ok": True, "error": None}]
    assert db.execute(text("SELECT archive_checked_at IS NOT NULL AND archive_check_error IS NULL FROM project_purge "
                           "WHERE project_purge_id = :p"), {"p": pp}).scalar()
    frozen["keys"].destroy(ref.split("@")[0])
    rep = run(db, frozen)
    assert rep["held_archives"][0]["error"] == weekly_check.KEY_GONE and rep["summary"]["held_failing"] == 1
    card = client.get(f"{API}/admin/weekly-check", headers=frozen["world"]["admin"]).json()
    assert [h["error"] for h in card["held_failing"]] == [weekly_check.KEY_GONE]
    assert events(db, "ARCHIVE_HELD_CHECK_FAILED") == [(pp, weekly_check.KEY_GONE)]     # kept past a later pass
    overwrite(frozen, name, b"tampered")
    assert run(db, frozen)["held_archives"][0]["error"] == weekly_check.DIFFERS


def test_an_archive_being_deleted_is_not_reported_failing(frozen, db, owner):
    """Sara L2: once an approved DELETE_ARCHIVE starts destroying keys, the lost key is the deletion, not a failure."""
    pp, _, ref = _held_archive(owner, frozen)
    with owner.begin() as c:
        c.execute(text("ALTER TABLE project_purge DISABLE TRIGGER trg_project_purge_guard"))
    try:
        with owner.begin() as c:
            c.execute(text(
                "INSERT INTO project_purge (purge_kind, archive_purge_id, project_id, client_id, project_code, reason, "
                "requested_by_user_id, requested_at, approved_by_user_id, approved_at, destroy_started_at) "
                "VALUES ('DELETE_ARCHIVE', :pp, 999, :c, 'GONE', 'contract end', :a, now(), :b, now(), now())"),
                {"pp": pp, "c": frozen["world"]["client_id"], "a": frozen["admin"],
                 "b": frozen["world"]["users"]["owner"]})
    finally:
        with owner.begin() as c:
            c.execute(text("ALTER TABLE project_purge ENABLE TRIGGER trg_project_purge_guard"))
    frozen["keys"].destroy(ref.split("@")[0])
    rep = run(db, frozen)
    assert rep["held_archives"] == [] and rep["summary"]["held_failing"] == 0
    assert events(db, "ARCHIVE_HELD_CHECK_FAILED") == []


def test_a_mis_set_folder_checks_nothing(frozen, db, tmp_path):
    """Sara M1: a wrong, empty or unreadable folder stops the run before any file is marked failed for good."""
    from services.archive_store import LocalKeys, LocalStore
    instance = scope_row(db, frozen).object_name.split("/")[0]
    weekly_check.check_reachable(db, frozen["store"], frozen["keys"], instance)          # the right folders pass
    (tmp_path / "empty").mkdir()
    for store, keys in [(LocalStore(tmp_path / "typo"), frozen["keys"]), (frozen["store"], LocalKeys(tmp_path / "x")),
                        (LocalStore(tmp_path / "empty"), frozen["keys"])]:
        with pytest.raises(weekly_check.Unreachable):
            weekly_check.check_reachable(db, store, keys, instance)
    path = frozen["store"].root / scope_row(db, frozen).object_name
    os.chmod(path, 0)
    try:
        with pytest.raises(PermissionError):
            run(db, frozen)
    finally:
        os.chmod(path, 0o444)
    db.rollback()
    assert scope_row(db, frozen).check_failed_at is None and events(db, "ARCHIVE_CHECK_FAILED") == []


def test_the_report_names_due_reopened_and_unfinished_projects(frozen, db, owner, client):
    """§1a: due for archiving (two years after closing), reopened since the LAST run only, unfinished removals."""
    h, p = frozen["world"]["admin"], frozen["world"]["p_sales"]

    def rv():
        return client.get(f"{API}/projects/{p}", headers=h).json()["row_version"]
    client.patch(f"{API}/projects/{p}/status", headers=h, json={"status_code": "CLOSED", "row_version": rv()})
    with owner.begin() as c:                                                            # test-only: closed long ago
        c.execute(text("UPDATE project SET closed_on = :d WHERE project_id = :p"),
                  {"d": local_today() - timedelta(days=800), "p": p})
    first = run(db, frozen)
    assert [d["project_code"] for d in first["due_for_archiving"]] == ["SALES"]
    client.post(f"{API}/projects/{p}/reopen", headers=h, json={"status_code": "ACTIVE", "row_version": rv()})
    second = run(db, frozen)
    assert [r["project_code"] for r in second["reopened_since_last_run"]] == ["SALES"]
    assert second["due_for_archiving"] == []
    assert run(db, frozen)["reopened_since_last_run"] == []                            # not reported twice
    from tests.admin_team import owner_user
    from tests.test_project_purge_record import promote
    promote(owner, owner_user(owner, "a2.purge@example.test"))
    client.post(f"{API}/projects/{frozen['world']['p_fin']}/purge-requests", headers=h,
                json={"kind": "DELETE", "reason": "Contract clause 9.2", "confirm_text": "ACME/FIN"})
    assert [(u["project_code"], u["state"]) for u in run(db, frozen)["unfinished_removals"]] == [("FIN", "OPEN")]


def test_a_run_over_eight_days_old_reads_as_stale(frozen, db, owner, client):
    """U5: the card warns when the check has not run for 8 days."""
    assert client.get(f"{API}/admin/weekly-check", headers=frozen["world"]["admin"]).json()["last_run"]["stale"] is True
    with owner.begin() as c:                                                            # a run nine days ago
        c.execute(text("INSERT INTO audit_event (event_type, target_table, detail, occurred_at) VALUES "
                       "('WEEKLY_CHECK_RAN', 'weekly_check', '{\"summary\": {}}', now() - interval '9 days')"))
    assert weekly_check.last_run(db)["stale"] is True
    run(db, frozen)
    assert weekly_check.last_run(db)["stale"] is False


def test_the_script_exits_1_only_when_a_file_or_held_archive_failed(frozen, db, monkeypatch, capsys):
    """VB-005 (sara L5): IS schedules the script and alerts on its exit code — 0 when all is well, 1 on a failure."""
    from scripts import weekly_check as script

    def main_exit():
        monkeypatch.setattr("sys.argv", ["weekly_check", "--actor-email", "admin@example.test", "--operator", "IS"])
        with pytest.raises(SystemExit) as out:
            script.main()
        return out.value.code
    assert main_exit() == 0
    row = scope_row(db, frozen)
    overwrite(frozen, row.object_name, b"x" + frozen["store"].get(row.object_name)[1:])
    assert main_exit() == 1
    assert "FAILED   baseline" in capsys.readouterr().out


def test_the_operator_report_prints_every_section(frozen, db, owner):
    from scripts.weekly_check import _lines
    _held_archive(owner, frozen)
    text_out = "\n".join(_lines(run(db, frozen)))
    assert text_out.startswith("Weekly archive check — 0 due") and "HELD     GONE" in text_out


def test_the_report_lists_rejected_and_failed_imports_without_failing_the_run(frozen, db, owner, monkeypatch, capsys):
    """Slice 1e P8 / N7: per target, the last 7 days' rejected batches and failed commits; information only."""
    from scripts import weekly_check as script
    with owner.begin() as c:
        p = frozen["p"]
        rejected = c.execute(text("SELECT code_id FROM code_master WHERE category = 'IMPORT_STATUS' AND code = 'REJECTED' "
                                  "AND project_id IS NULL")).scalar_one()
        ids = [c.execute(text("INSERT INTO import_batch (project_id, target_entity, file_name, uploaded_by_user_id, "
                              "status_code_id) VALUES (:p, :t, 'x.xlsx', :u, :s) RETURNING import_batch_id"),
                         {"p": p, "t": t, "u": frozen["admin"], "s": rejected}).scalar_one()
               for t in ("ISSUE", "ISSUE", "FUNCTION_REQUIREMENT")]
        c.execute(text("INSERT INTO audit_event (event_type, app_user_id, project_id, target_table, target_id, detail) "
                       "VALUES ('IMPORT_COMMIT_FAILED', :u, :p, 'import_batch', :b, '{}')"),
                  {"u": frozen["admin"], "p": p, "b": ids[0]})
    rep = run(db, frozen)
    assert rep["imports"] == [{"target": "FUNCTION_REQUIREMENT", "rejected": 1, "failed_commits": 0},
                              {"target": "ISSUE", "rejected": 2, "failed_commits": 1}]
    monkeypatch.setattr("sys.argv", ["weekly_check", "--actor-email", "admin@example.test", "--operator", "IS"])
    with pytest.raises(SystemExit) as out:
        script.main()
    assert out.value.code == 0                                                        # N7: never the exit code
    assert "IMPORTS  ISSUE: 2 rejected, 1 failed commit(s)" in capsys.readouterr().out
