"""Slice 16: carrying out a DELETE removal (services/purge_run, scripts/purge_project; spec §10 criteria 6, 7, 8, 10,
11, 12). Grade 1 — it destroys a client's data for good, so: every rule refuses with nothing deleted; a removal leaves
no row of the project in any table, found by a catalog query rather than a hand list; every other row in the
database is byte-identical afterwards; and a fault part-way rolls all of it back with the request still open."""
import os
from collections import Counter

import pytest
from sqlalchemy import select, text

from database import engine as app_engine
from models import AppUser
from seeds.demo_showcase import build_showcase
from services import purge_run
from tests.conftest import PW, has_state, restore_state, save_state
from tests.admin_team import owner_user
from tests.test_baseline import bid, freeze, scope
from tests.test_project_purge_record import INSERT, backdate, owner, promote, run  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


@pytest.fixture
def rich(client, world, ed, db, owner, monkeypatch):
    """The showcase project (frozen twice, every scope table) to remove; p_solo frozen; the world's other projects;
    two platform admins with a1 the requester and a2 (granted 31 days ago) the approver; a stamped database.
    Built once per worker, then restored for every later test (conftest.save_state / restore_state, which prove the
    copy row for row): the build is ~8-12 s of services, the restore well under one. `world` and `ed` still run first,
    on a fresh database, so their ids and logins are the build's own."""
    from config import get_settings
    monkeypatch.setattr(get_settings(), "vb_instance_id", "test-a")                    # this host's id (sara H2)
    if has_state("rich"):
        restore_state("rich")
        return {**_RICH, "world": world}
    admin = db.scalar(select(AppUser).where(AppUser.email == "admin@example.test"))
    victim = build_showcase(db, admin, "example.test", PW)
    db.commit()
    scope(client, ed)
    bid(freeze(client, ed))
    a2 = owner_user(owner, "a2.purge@example.test")                # not made by a1 (AR-24)
    promote(owner, a2)
    run(owner, "INSERT INTO vb_instance (instance_id) VALUES ('test-a')")
    client_id = run(owner, "SELECT client_id FROM project WHERE project_id = :p", p=victim)[0]
    for p in (victim, world["p_sales"]):                                               # code-list overrides
        for cat in ("ISSUE_TYPE", "PROJECT_COMPONENT"):
            run(owner, "INSERT INTO code_master (project_id, category, code, label, created_by) "
                       "VALUES (:p, :c, 'LOCAL', 'Local', :u)", p=p, c=cat, u=admin.app_user_id)
    _RICH.update({"p": victim, "c": client_id, "a1": admin.app_user_id, "a2": a2,
                  "a2_email": "a2.purge@example.test", "code": "KAITO/CSR27"})
    save_state("rich")
    return {**_RICH, "world": world}


_RICH: dict = {}


def request(t, kind="DELETE", approve=True, hours=25):
    pp = run(app_engine, INSERT.replace("'X'", "'CSR27'"), k=kind, p=t["p"], c=t["c"], r=t["a1"], a=None)[0]
    if approve:
        run(app_engine, "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u "
                        "WHERE project_purge_id = :pp", u=t["a2"], pp=pp)
        backdate(owner_engine(), pp, hours=hours)
    return pp


def owner_engine():
    from tests.conftest import owner_engine as eng
    return eng()


def snapshot(eng) -> dict[str, Counter]:
    """Every row of every table, as text — a multiset per table."""
    with eng.connect() as c:
        tables = [r[0] for r in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))]
        return {t: Counter(r[0] for r in c.execute(text(f"SELECT md5(x::text) FROM {t} x"))) for t in tables}


def purge(eng, pp, email, typed=None):
    with eng.begin() as c:
        return purge_run.execute(c, pp, email, lambda plan: plan.expected if typed is None else typed)


def test_a_removal_takes_every_row_of_the_project_and_leaves_every_other_row_as_it_was(rich, owner):
    pp = request(rich)
    before = snapshot(owner)
    plan = purge(owner, pp, rich["a2_email"])
    after = snapshot(owner)
    for t, rows in before.items():
        gone, new = rows - after[t], after[t] - rows
        if t in purge_run.KEEP or t == "audit_event":
            continue
        assert not new, f"{t} gained or changed rows"
        assert sum(gone.values()) == plan.counts.get(t, 0), t                           # exactly the counted rows
    assert sum((after["audit_event"] - before["audit_event"]).values()) == 1            # PROJECT_PURGED only
    assert sum((before["audit_event"] - after["audit_event"]).values()) == plan.counts["audit_event"]
    # Criterion 7, by a catalog query over every table: nothing with the project's id is left outside the keep list.
    for (t,) in run_all(owner, "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
                               "AND column_name = 'project_id'"):
        if t not in purge_run.KEEP:
            assert run(owner, f"SELECT count(*) FROM {t} WHERE project_id = :p", p=rich["p"])[0] == 0, t
    # The record: executed by a2, keys outstanding (destruction not yet approved), PROJECT_PURGED with no project_id.
    assert run(owner, "SELECT executed_by_user_id = :u AND backups_age_out_on IS NOT NULL FROM project_purge "
                      "WHERE project_purge_id = :pp", u=rich["a2"], pp=pp)[0]
    assert run(owner, "SELECT count(*), bool_and(destroyed_at IS NULL) FROM project_purge_key "
                      "WHERE project_purge_id = :pp", pp=pp) == (1, True)
    ev = run(owner, "SELECT project_id, app_user_id, detail FROM audit_event WHERE event_type = 'PROJECT_PURGED'")
    assert ev[0] is None and ev[1] == rich["a2"]
    assert ev[2]["project_code"] == "CSR27" and ev[2]["client_code"] == "KAITO" and ev[2]["counts"]["project"] == 1
    assert ev[2]["requested_by_user_id"] == rich["a1"] and ev[2]["approved_by_user_id"] == rich["a2"]
    # Coverage: the removal really reached the scope, the baselines and their files.
    reached = {t for t, n in plan.counts.items() if n}
    assert {"project", "bfc_node", "business_requirement", "baseline", "baseline_archive", "baseline_bfc_node",
            "code_master", "project_sequence", "project_component", "audit_event"} <= reached, sorted(reached)
    print("tables the removal had no rows of:", sorted(set(plan.counts) - reached))


def run_all(eng, sql, **kw):
    with eng.begin() as c:
        return c.execute(text(sql), kw).all()


@pytest.mark.parametrize("case, msg", [
    ("unapproved", "no second platform admin"), ("young", "less than 24 hours"),
    ("requester runs", "requester cannot also run"), ("not an admin", "not a live platform admin"),
    ("approver demoted", "no longer a live platform admin"), ("wrong code", "did not match"),
    ("archive", "DELETE requests only"), ("no request", "no open removal request")])
def test_every_rule_refuses_with_nothing_deleted(rich, owner, case, msg):
    pp = request(rich, kind="ARCHIVE" if case == "archive" else "DELETE", approve=case != "unapproved",
                 hours=23.98 if case == "young" else 25)
    email = {"requester runs": "admin@example.test", "not an admin": "editor@example.test"}.get(case,
                                                                                               rich["a2_email"])
    if case == "approver demoted":
        run(owner, "UPDATE app_user SET is_platform_admin = false WHERE app_user_id = :u", u=rich["a2"])
        promote(owner, rich["world"]["users"]["outsider"])                             # still two admins
        email = "outsider@example.test"
    before = snapshot(owner)
    with pytest.raises(purge_run.Refused, match=msg):
        purge(owner, pp + 99 if case == "no request" else pp, email, typed="KAITO/CSR2" if case == "wrong code" else None)
    after = snapshot(owner)
    assert {t: r for t, r in after.items() if t != "app_user"} == {t: r for t, r in before.items() if t != "app_user"}


def test_a_cancelled_request_is_refused_by_the_script_itself(rich, owner):
    """sara L-g. (Its "fewer than two admins" line is a second wall: a live requester and a different live approver
    already make two, so it cannot be reached on its own.)"""
    pp = request(rich)
    run(app_engine, "UPDATE project_purge SET cancelled_at = now(), cancelled_by_user_id = :u "
                    "WHERE project_purge_id = :pp", u=rich["a1"], pp=pp)
    before = snapshot(owner)
    with pytest.raises(purge_run.Refused, match="no open removal request"):
        purge(owner, pp, rich["a2_email"])
    assert snapshot(owner) == before


def test_a_cascading_reference_or_a_stray_delete_trigger_stops_the_run(rich, owner, monkeypatch):
    """sara M-A: the proof counts rows, so nothing may change a row it does not count."""
    pp = request(rich)
    with owner.connect() as c:
        tx = c.begin()
        c.execute(text("CREATE TABLE test_cascade (id int PRIMARY KEY, stakeholder_id bigint "
                       "REFERENCES stakeholder ON DELETE SET NULL)"))
        with pytest.raises(purge_run.Refused, match="test_cascade"):
            purge_run.execute(c, pp, rich["a2_email"], lambda plan: plan.expected)
        tx.rollback()
    monkeypatch.setattr(purge_run, "DELETE_GUARDS", ())
    with pytest.raises(purge_run.Refused, match="trigger trg_baseline_"):
        purge(owner, pp, rich["a2_email"])


def test_a_template_pointing_at_this_projects_override_stops_the_run(rich, owner):
    """The company template list may point at the library, never at a project's own code (`_library_refs_clear`)."""
    pp = request(rich)
    run(owner, "INSERT INTO project_template_component (template_code_id, component_code_id) "
               "SELECT (SELECT code_id FROM code_master WHERE category = 'PROJECT_TEMPLATE' AND project_id IS NULL "
               "        ORDER BY code_id LIMIT 1), code_id FROM code_master "
               "WHERE category = 'PROJECT_COMPONENT' AND project_id = :p", p=rich["p"])
    before = snapshot(owner)
    with pytest.raises(purge_run.Refused, match="overrides"):
        purge(owner, pp, rich["a2_email"])
    assert snapshot(owner) == before


def test_the_app_role_can_never_run_a_removal(rich):
    pp = request(rich)
    with pytest.raises(purge_run.Refused, match="owner role"):
        purge(app_engine, pp, rich["a2_email"])


def test_a_table_in_no_list_or_a_false_no_data_claim_stops_the_run(rich, owner, monkeypatch):
    pp = request(rich)
    monkeypatch.setattr(purge_run, "NO_PROJECT_DATA", tuple(t for t in purge_run.NO_PROJECT_DATA if t != "program"))
    with pytest.raises(purge_run.Refused, match="Tables in no list"):
        purge(owner, pp, rich["a2_email"])
    monkeypatch.setattr(purge_run, "NO_PROJECT_DATA", (*purge_run.NO_PROJECT_DATA, "program", "stakeholder"))
    with pytest.raises(purge_run.Refused, match="stakeholder"):
        purge(owner, pp, rich["a2_email"])


def test_a_wrong_predicate_part_way_rolls_everything_back_and_the_request_stays_open(rich, owner, monkeypatch):
    """Schema §8's planted fault: a delete rule that reaches other projects' rows is counted by the same wrong rule,
    so only the proof's independent rule (the table's own project_id) can catch it — after every table was deleted.
    The whole transaction rolls back."""
    pp = request(rich)
    real = purge_run.classify

    def wrong(c):
        got = real(c)
        got.predicates["project_member"] = "true"                                     # every project's members
        return got
    monkeypatch.setattr(purge_run, "classify", wrong)
    before = snapshot(owner)
    with pytest.raises(purge_run.Refused, match="project_member"):
        purge(owner, pp, rich["a2_email"])
    assert snapshot(owner) == before
    assert run(owner, "SELECT executed_at IS NULL AND cancelled_at IS NULL FROM project_purge "
                      "WHERE project_purge_id = :pp", pp=pp)[0]


def test_a_failure_part_way_leaves_every_row_and_the_request_open(rich, owner, monkeypatch):
    """Criterion 12: a fault forced after a dozen tables are already deleted rolls all of it back."""
    pp = request(rich)
    real, calls = purge_run._delete, []

    def failing(c, step, preds, p):
        calls.append(step)
        if len(calls) == 12:
            raise RuntimeError("forced failure part-way")
        return real(c, step, preds, p)
    monkeypatch.setattr(purge_run, "_delete", failing)
    before = snapshot(owner)
    with pytest.raises(RuntimeError, match="part-way"):
        purge(owner, pp, rich["a2_email"])
    assert snapshot(owner) == before
    assert run(owner, "SELECT executed_at IS NULL FROM project_purge WHERE project_purge_id = :pp", pp=pp)[0]


def test_the_project_setting_ends_with_the_transaction(rich, owner):
    """sara L3: the scoped setting is transaction-local, so a reused owner connection never carries it on."""
    pp = request(rich)
    with owner.connect() as c:
        with c.begin():
            purge_run.execute(c, pp, rich["a2_email"], lambda plan: plan.expected)
        assert c.scalar(text("SELECT current_setting('vb.purge_project_id', true)")) in ("", None)


def test_the_delete_order_puts_children_first_and_the_project_with_its_code_overrides(owner):
    with owner.connect() as c:
        got = purge_run.classify(c)
    flat = [t for s in got.steps for t in ((s,) if isinstance(s, str) else s)]
    assert flat.index("baseline_archive") < flat.index("baseline")
    assert flat.index("baseline_bfc_node") < flat.index("baseline")
    assert flat.index("import_row") < flat.index("import_batch")
    assert flat.index("audit_event") < flat.index("project")
    assert ("code_master", "project") in got.steps                                      # one statement (schema §8 row 13)
    assert "import_batch_id" in got.predicates["import_row"]


# ---- the keys: destroyed only after the removal has committed (criterion 9; Q-71; Ben 2026-10-22) --------------

@pytest.fixture
def vault(rich, tmp_path, monkeypatch):
    """This test's own throwaway archive and key folders, with every owed file of every baseline written."""
    from config import get_settings
    from services import archive
    from services.archive_store import LocalKeys, LocalStore
    s = get_settings()
    monkeypatch.setattr(s, "vb_instance_id", "test-a")
    monkeypatch.setattr(s, "vb_archive_dir", str(tmp_path / "files"))
    monkeypatch.setattr(s, "vb_archive_key_dir", str(tmp_path / "keys"))
    store, keys = LocalStore(tmp_path / "files"), LocalKeys(tmp_path / "keys")
    assert archive.write_pending(store, keys, limit=100)["failed"] == 0
    return {"store": store, "keys": keys, "root": tmp_path,
            "mine": store.names(f"test-a/{rich['p']}/"), "theirs": store.names(f"test-a/{rich['world']['p_solo']}/")}


def vault_state(v) -> tuple:
    files = sorted(str(p.relative_to(v["root"])) for p in v["root"].rglob("*") if p.is_file())
    return tuple(files)


def verifies(v, name) -> str | None:
    from services.archive import verify_file
    return verify_file(v["store"].get(name), v["keys"])["first_mismatch"]


def remove(rich, v, pp, typed=None):
    return purge_run.remove(owner_engine(), pp, rich["a2_email"],
                            lambda plan: plan.expected if typed is None else typed, v["store"], v["keys"])


def test_a_removal_destroys_its_keys_after_the_commit_and_its_files_never_read_again(rich, vault, owner):
    assert vault["mine"] and vault["theirs"]
    assert all(verifies(vault, f) is None for f in vault["mine"] + vault["theirs"])
    pp = request(rich)
    plan, results = remove(rich, vault, pp)
    name = f"vb-test-a-proj-{rich['p']}"
    assert [(k.key_name, k.destroyed, k.was_present) for k in results] == [(name, True, True)]
    assert results[0].proof_object_name in vault["mine"]
    assert not list((vault["root"] / "keys").glob(f"{name}@*"))                         # gone, every version
    assert all(verifies(vault, f) == "key: unavailable" for f in vault["mine"])
    assert all(verifies(vault, f) is None for f in vault["theirs"])                     # another project untouched
    assert vault["store"].exists(f"test-a/purged/{rich['p']}")                          # the tombstone
    assert run(owner, "SELECT destroyed_at IS NOT NULL AND was_present AND destroyed_by_purge_id = :pp "
                      "AND proof_object_name IS NOT NULL FROM project_purge_key WHERE project_purge_id = :pp",
               pp=pp)[0]
    ev = run(owner, "SELECT project_id, detail FROM audit_event WHERE event_type = 'PURGE_KEYS_DESTROYED'")
    assert ev[0] is None and [(k["key_name"], k["was_present"]) for k in ev[1]["keys"]] == [(name, True)]


@pytest.mark.parametrize("case", ["unapproved", "young", "wrong code", "fault part-way", "archive kind"])
def test_a_refused_or_failed_removal_touches_no_key_and_no_file(rich, vault, owner, monkeypatch, case):
    """Ren 2026-10-22: never before the approval and 24-hour conditions; a failed run leaves keys and files intact."""
    pp = request(rich, kind="ARCHIVE" if case == "archive kind" else "DELETE", approve=case != "unapproved",
                 hours=23.98 if case == "young" else 25)
    if case == "fault part-way":
        real, calls = purge_run._delete, []

        def failing(c, step, preds, p):
            calls.append(step)
            if len(calls) == 12:
                raise RuntimeError("forced failure part-way")
            return real(c, step, preds, p)
        monkeypatch.setattr(purge_run, "_delete", failing)
    before = vault_state(vault)
    with pytest.raises((purge_run.Refused, RuntimeError)):
        remove(rich, vault, pp, typed="KAITO/CSR2" if case == "wrong code" else None)
    assert vault_state(vault) == before
    assert all(verifies(vault, f) is None for f in vault["mine"])
    assert run(owner, "SELECT count(*) FROM project_purge_key")[0] == 0


def test_keys_are_destroyed_only_for_a_delete_that_was_carried_out(rich, vault, owner):
    pp = request(rich)
    before = vault_state(vault)
    with pytest.raises(purge_run.Refused, match="has been carried out"):
        purge_run.destroy_keys(owner, pp, rich["a2_email"], vault["store"], vault["keys"])
    with pytest.raises(purge_run.Refused, match="owner role"):
        purge_run.destroy_keys(app_engine, pp, rich["a2_email"], vault["store"], vault["keys"])
    assert vault_state(vault) == before


def test_a_key_that_fails_to_go_stays_outstanding_and_a_second_run_finishes(rich, vault, owner, monkeypatch):
    pp = request(rich)
    real = vault["keys"].destroy
    monkeypatch.setattr(vault["keys"], "destroy", lambda name: (_ for _ in ()).throw(OSError("vault unreachable")))
    with pytest.raises(OSError):
        remove(rich, vault, pp)
    assert run(owner, "SELECT executed_at IS NOT NULL FROM project_purge WHERE project_purge_id = :pp", pp=pp)[0]
    assert run(owner, "SELECT bool_and(destroyed_at IS NULL) FROM project_purge_key "
                      "WHERE project_purge_id = :pp", pp=pp)[0]                       # outstanding, visible
    assert vault["store"].exists(f"test-a/purged/{rich['p']}")                          # tombstone came first
    monkeypatch.setattr(vault["keys"], "destroy", real)
    results = purge_run.destroy_keys(owner, pp, rich["a2_email"], vault["store"], vault["keys"])
    assert [k.destroyed for k in results] == [True]
    assert all(verifies(vault, f) == "key: unavailable" for f in vault["mine"])


def test_another_instances_key_is_never_destroyed(rich, vault, owner, monkeypatch):
    """S2: a name outside this instance's prefix is reported for the operator and left alone."""
    pp = request(rich)
    real = purge_run._key_names
    monkeypatch.setattr(purge_run, "_key_names",
                        lambda c, p, i: {**real(c, p, i), f"vb-prod-proj-{p}": [f"vb-prod-proj-{p}@1"]})
    other = vault["root"] / "keys" / f"vb-prod-proj-{rich['p']}@1"
    other.write_bytes(os.urandom(32))
    plan, results = remove(rich, vault, pp)
    got = {k.key_name: k.destroyed for k in results}
    assert got == {f"vb-prod-proj-{rich['p']}": False, f"vb-test-a-proj-{rich['p']}": True}
    assert other.exists()
    assert run(owner, "SELECT count(*) FROM project_purge_key WHERE destroyed_at IS NULL")[0] == 1
    assert run(owner, "SELECT count(*) FROM audit_event WHERE event_type = 'PURGE_KEYS_DESTROYED'")[0] == 0


def _solo_key(rich, vault):
    return vault["root"] / "keys" / f"vb-test-a-proj-{rich['world']['p_solo']}@1"


def test_an_archive_record_naming_another_projects_key_stops_the_removal(rich, vault, owner):
    """sara H1: the app role can write an owed row's key_ref; a ref to another project's key stops the run before
    anything is deleted, and that project's key survives."""
    pp = request(rich)
    solo = rich["world"]["p_solo"]
    run(owner, "ALTER TABLE baseline_archive DISABLE TRIGGER trg_baseline_archive_guard; "
               f"UPDATE baseline_archive SET key_ref = 'vb-test-a-proj-{solo}@1' WHERE baseline_id = "
               f"(SELECT min(baseline_id) FROM baseline_archive WHERE project_id = {rich['p']}); "
               "ALTER TABLE baseline_archive ENABLE TRIGGER trg_baseline_archive_guard")
    before, files = snapshot(owner), vault_state(vault)
    with pytest.raises(purge_run.Refused, match="another project's key"):
        remove(rich, vault, pp)
    assert snapshot(owner) == before and vault_state(vault) == files
    assert _solo_key(rich, vault).exists()


def test_only_this_projects_own_key_is_ever_destroyed(rich, vault, owner, monkeypatch):
    """sara H1: even a recorded name of another project on this instance is reported, never destroyed."""
    pp = request(rich)
    solo = rich["world"]["p_solo"]
    real = purge_run._key_names
    monkeypatch.setattr(purge_run, "_key_names",
                        lambda c, p, i: {**real(c, p, i), f"vb-test-a-proj-{solo}": [f"vb-test-a-proj-{solo}@1"]})
    plan, results = remove(rich, vault, pp)
    assert {k.key_name: k.destroyed for k in results} == {f"vb-test-a-proj-{rich['p']}": True,
                                                          f"vb-test-a-proj-{solo}": False}
    assert _solo_key(rich, vault).exists()
    assert all(verifies(vault, f) is None for f in vault["theirs"])


def test_a_host_whose_instance_id_differs_from_the_stamp_destroys_nothing(rich, vault, owner, monkeypatch):
    """sara H2: a restored copy still stamped as another environment never runs a removal or touches a key."""
    from config import get_settings
    pp = request(rich)
    monkeypatch.setattr(get_settings(), "vb_instance_id", "other")
    before, files = snapshot(owner), vault_state(vault)
    with pytest.raises(purge_run.Refused, match="stamped"):
        remove(rich, vault, pp)
    assert snapshot(owner) == before and vault_state(vault) == files
    monkeypatch.setattr(get_settings(), "vb_instance_id", "test-a")
    remove(rich, vault, pp)                                                             # the removal itself, then
    monkeypatch.setattr(get_settings(), "vb_instance_id", "other")
    with pytest.raises(purge_run.Refused, match="stamped"):                             # a later key run checks too
        purge_run.destroy_keys(owner, pp, rich["a2_email"], vault["store"], vault["keys"])


def test_a_key_that_still_decrypts_stops_the_run_and_stays_outstanding(rich, vault, owner, monkeypatch):
    """sara M2: the safety stop — a vault that says "destroyed" but still decrypts — is never recorded as destroyed."""
    pp = request(rich)
    monkeypatch.setattr(vault["keys"], "destroy", lambda name: True)                    # lies: removes nothing
    with pytest.raises(purge_run.Refused, match="still decrypts"):
        remove(rich, vault, pp)
    assert run(owner, "SELECT bool_and(destroyed_at IS NULL) FROM project_purge_key "
                      "WHERE project_purge_id = :pp", pp=pp)[0]
    assert run(owner, "SELECT count(*) FROM audit_event WHERE event_type = 'PURGE_KEYS_DESTROYED'")[0] == 0
    assert all(verifies(vault, f) is None for f in vault["mine"])
