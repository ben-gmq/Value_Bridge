"""Slice 10d, migration 0052: one RACI per process (D-64; docs/slice10d_raci_schema.md §3–§5; spec §8 Grade 1;
design review 10d round 1, items 1–8).

A pre-10d database is rebuilt at head with the new guard dropped (fk_bnor_node_as_is), to-be step roles planted
as the owner (the API refuses them now), and — where a test needs it — a baseline frozen or a step retired with
its dependents through the real API. The chain then steps back to 0051 and up again, so 0052 runs on that data.
Proved: per-project counts; every moved role is on its BR or named as a lost Accountable; the BR's Accountable
wins (live and retired-with-step); codes match by resolved behaviour; a to-be step with no BR blocks with the
list; retired-with-step roles come back with a restore; a re-run adds nothing and writes no event; old
baselines still verify and their diff shows each moved role once; the guard, the 409 and copy_set."""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from services.freeze_set import CURRENT_HASH_SPEC
from services.raci import TO_BE_STEP
from tests.conftest import BACKEND, OWNER_URL
from tests.test_baseline import bid, diff, freeze, scope
from tests.test_charts_7c import step_in
from tests.test_scope_api import API, _org_role, ed, node  # noqa: F401 — ed is a fixture
from tests.test_step_retire import _br, restore, retire, retire_br


def _cfg() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    return cfg


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    command.upgrade(_cfg(), "head")                      # never leave the shared schema behind head
    eng.dispose()


def q(eng, sql, **kw):
    with eng.connect() as c:
        return c.execute(text(sql), kw).all()


def x(eng, sql, **kw):
    with eng.begin() as c:
        return c.execute(text(sql), kw)


def unguard(eng):
    """A pre-10d database: the step-role table without the D-64 guard (0052's downgrade drops it IF EXISTS)."""
    x(eng, "ALTER TABLE bfc_node_org_role DROP CONSTRAINT fk_bnor_node_as_is")


def migrate():
    """Back to 0051 and up again. 0053's downgrade (slice 13b) refuses while a baseline records its DFD rule, so a
    baseline frozen here first becomes what it stands for — one frozen before 13b, with no rule on its header."""
    cfg = _cfg()
    eng = create_engine(OWNER_URL)
    x(eng, "ALTER TABLE baseline DISABLE TRIGGER trg_baseline_header_guard; "
           "UPDATE baseline SET dfd_rule_to_be = NULL, dfd_rule_as_is = NULL WHERE dfd_rule_to_be IS NOT NULL; "
           "ALTER TABLE baseline ENABLE TRIGGER trg_baseline_header_guard")
    eng.dispose()
    command.downgrade(cfg, "0051")
    command.upgrade(cfg, "head")


def code_id(eng, code, project=None):
    return q(eng, "SELECT code_id FROM code_master WHERE category = 'RACI_TYPE' AND code = :c "
                  "AND project_id IS NOT DISTINCT FROM :p", c=code, p=project)[0][0]


def plant(eng, p, step_id, org_role_id, code, user):
    """A live step role, written as pre-10d code did, with the global code."""
    return x(eng, "INSERT INTO bfc_node_org_role (project_id, bfc_node_id, org_role_id, raci_code_id, raci_behaviour, "
                  "created_by) SELECT :p, :s, :r, code_id, behaviour_code, :u FROM code_master "
                  "WHERE category = 'RACI_TYPE' AND code = :c AND project_id IS NULL RETURNING bfc_node_org_role_id",
             p=p, s=step_id, r=org_role_id, c=code, u=user).scalar()


def override(eng, p, code, label, behaviour):
    return x(eng, "INSERT INTO code_master (project_id, category, code, label, behaviour_code, sort_order) "
                  "VALUES (:p, 'RACI_TYPE', :c, :l, :b, 9) RETURNING code_id", p=p, c=code, l=label, b=behaviour).scalar()


def br_role(client, ed, br_id, org_role, raci):
    r = client.post(f"{API}/business-requirements/{br_id}/org-roles", headers=ed["h"],
                    json={"org_role_id": org_role["org_role_id"], "raci_code": raci})
    assert r.status_code == 201, r.text
    return r.json()


def unlink_br_role(client, ed, row):
    r = client.delete(f"{API}/business-requirements/{row['br_id']}/org-roles/{row['br_org_role_id']}",
                      headers=ed["h"], params={"row_version": row["row_version"]})
    assert r.status_code == 204, r.text


def step_role(client, ed, step, org_role, raci, expect=201):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/org-roles", headers=ed["h"],
                    json={"org_role_id": org_role["org_role_id"], "raci_code": raci})
    assert r.status_code == expect, r.text
    return r.json()


def live_br_roles(eng, br_id):
    return {(o, b) for o, b in q(eng, "SELECT org_role_id, raci_behaviour FROM br_org_role "
                                      "WHERE br_id = :b AND is_active", b=br_id)}


def per_project(eng, sql):
    return dict(q(eng, sql + " GROUP BY 1"))


LIVE_TO_BE_STEP_ROLES = ("SELECT r.project_id, count(*) FROM bfc_node_org_role r JOIN bfc_node n USING (bfc_node_id) "
                         "WHERE r.is_active AND n.bfc_set_code = 'TO_BE'")
LIVE_BR_ROLES = "SELECT project_id, count(*) FROM br_org_role WHERE is_active"
EVENTS = "SELECT project_id, app_user_id, detail FROM audit_event WHERE event_type = 'RACI_MERGED_TO_BR' ORDER BY 1"


def tree_of(client, ed, step_name="Take order"):
    a = node(client, ed, "Sales")
    g = node(client, ed, "Order to cash", a["bfc_node_id"])
    return node(client, ed, step_name, g["bfc_node_id"], is_process=True), g


# ---- the merge --------------------------------------------------------------------------------------------------

def test_every_live_to_be_step_role_lands_on_its_br_or_is_named_and_the_brs_accountable_wins(
        client, ed, world, owner, capsys):
    u = world["users"]["editor"]
    p1, p2 = ed["p"], world["p_sales"]
    ed2 = {"h": ed["h"], "p": p2}
    s1, g = tree_of(client, ed)
    s2 = node(client, ed, "Ship order", g["bfc_node_id"], is_process=True)
    br1, br2 = _br(client, ed, s1["bfc_node_id"]), _br(client, ed, s2["bfc_node_id"])
    cfo, clerk, audit, ops = (_org_role(client, ed, c) for c in ("CFO", "CLERK", "AUDIT", "OPS"))
    br1_a = br_role(client, ed, br1["br_id"], cfo, "A")
    br_role(client, ed, br1["br_id"], audit, "C")
    gone = br_role(client, ed, br1["br_id"], ops, "I")
    unlink_br_role(client, ed, gone)                                   # retired: the merge restores it
    _a, _b, old = step_in(client, ed, "AS_IS", ("Old area", "Old function"), "Old step")
    as_is_role = step_role(client, ed, old, cfo, "A")                  # as-is keeps its own RACI
    s5, _ = tree_of(client, ed2, "Pay invoice")
    mgr = _org_role(client, ed2, "MGR")
    unguard(owner)
    planted = {"a_clerk": plant(owner, p1, s1["bfc_node_id"], clerk["org_role_id"], "A", u),     # conflict
               "r_clerk": plant(owner, p1, s1["bfc_node_id"], clerk["org_role_id"], "R", u),     # copied
               "c_audit": plant(owner, p1, s1["bfc_node_id"], audit["org_role_id"], "C", u),     # already
               "i_ops": plant(owner, p1, s1["bfc_node_id"], ops["org_role_id"], "I", u),         # restored
               "a_cfo2": plant(owner, p1, s2["bfc_node_id"], cfo["org_role_id"], "A", u),        # copied
               "r_mgr": plant(owner, p2, s5["bfc_node_id"], mgr["org_role_id"], "R", u)}         # copied, project 2
    assert per_project(owner, LIVE_TO_BE_STEP_ROLES) == {p1: 5, p2: 1}
    br_before = per_project(owner, LIVE_BR_ROLES)
    assert br_before == {p1: 2}
    capsys.readouterr()

    migrate()

    assert per_project(owner, LIVE_TO_BE_STEP_ROLES) == {}             # none left, in either project
    assert per_project(owner, LIVE_BR_ROLES) == {p1: 2 + 3, p2: 1}      # + R clerk, I ops (restored), A cfo
    assert live_br_roles(owner, br1["br_id"]) == {(cfo["org_role_id"], "ACCOUNTABLE"),
                                                  (audit["org_role_id"], "CONSULTED"),
                                                  (ops["org_role_id"], "INFORMED"),
                                                  (clerk["org_role_id"], "RESPONSIBLE")}
    assert live_br_roles(owner, br2["br_id"]) == {(cfo["org_role_id"], "ACCOUNTABLE")}
    assert q(owner, "SELECT is_active FROM br_org_role WHERE br_org_role_id = :i",
             i=gone["br_org_role_id"])[0][0] is True                    # the same row, not a new one
    # every step row retired once, one stamp, no actor; the as-is row untouched
    rows = q(owner, "SELECT bfc_node_org_role_id, is_active, deleted_at, deleted_by FROM bfc_node_org_role "
                    "WHERE bfc_node_org_role_id = ANY(:ids)", ids=list(planted.values()))
    assert len(rows) == 6 and {r[1] for r in rows} == {False} and len({r[2] for r in rows}) == 1
    assert {r[3] for r in rows} == {None}
    assert q(owner, "SELECT is_active FROM bfc_node_org_role WHERE bfc_node_org_role_id = :i",
             i=as_is_role["bfc_node_org_role_id"])[0][0] is True
    # the event: one per project, ids traceable both ways
    ev = {p: (a, d) for p, a, d in q(owner, EVENTS)}
    assert sorted(ev) == sorted([p1, p2]) and {a for a, _ in ev.values()} == {None}
    d1, d2 = ev[p1][1], ev[p2][1]
    assert d1["decision"] == "D-64" and d1["migration"] == "0052"
    assert sorted(d1["retired"]) == sorted(v for k, v in planted.items() if k != "r_mgr")
    assert {s for s, _ in d1["copied"]} == {planted["r_clerk"], planted["a_cfo2"]}
    assert d1["restored"] == [[planted["i_ops"], gone["br_org_role_id"]]]
    assert [s for s, _ in d1["already"]] == [planted["c_audit"]]
    assert d1["conflicts"] == [{"kind": "LIVE", "step_role_id": planted["a_clerk"], "br_id": br1["br_id"],
                                "dropped_org_role_id": clerk["org_role_id"],
                                "kept_br_org_role_id": br1_a["br_org_role_id"]}]
    assert [s for s, _ in d2["copied"]] == [planted["r_mgr"]] and d2["retired"] == [planted["r_mgr"]]
    # every moved role is on its BR, or named as the Accountable the BR won over
    for name, sid in planted.items():
        org, beh, br = q(owner, "SELECT r.org_role_id, r.raci_behaviour, b.br_id FROM bfc_node_org_role r "
                                "JOIN business_requirement b ON b.bfc_node_id = r.bfc_node_id AND b.is_active "
                                "WHERE r.bfc_node_org_role_id = :i", i=sid)[0]
        named = sid in {c["step_role_id"] for d in (d1, d2) for c in d["conflicts"]}
        assert ((org, beh) in live_br_roles(owner, br)) != named, name
    out = capsys.readouterr().out
    assert f"{br1['br_number']} keeps CFO; the step's CLERK was not copied" in out


def test_codes_match_by_resolved_behaviour_and_a_retired_accountable_never_beats_a_live_one(
        client, ed, world, owner):
    """DR10d-2: a project override is its own code_master row. The step's global R and the BR's override R are
    the same role; a copy takes the override; restoring a retired (X, A) while (Y, A) is live is a conflict."""
    u, p = world["users"]["editor"], ed["p"]
    s1, _ = tree_of(client, ed)
    br = _br(client, ed, s1["bfc_node_id"])
    cfo, clerk, audit = (_org_role(client, ed, c) for c in ("CFO", "CLERK", "AUDIT"))
    old_a = br_role(client, ed, br["br_id"], clerk, "A")
    unlink_br_role(client, ed, old_a)                                  # (CLERK, A) retired
    br_role(client, ed, br["br_id"], cfo, "A")                         # (CFO, A) live
    r_over = override(owner, p, "R", "Does it", "RESPONSIBLE")
    c_over = override(owner, p, "C", "Asked", "CONSULTED")
    via_override = br_role(client, ed, br["br_id"], clerk, "R")        # resolves to the project's R
    assert q(owner, "SELECT raci_code_id FROM br_org_role WHERE br_org_role_id = :i",
             i=via_override["br_org_role_id"])[0][0] == r_over
    unguard(owner)
    a = plant(owner, p, s1["bfc_node_id"], clerk["org_role_id"], "A", u)
    r = plant(owner, p, s1["bfc_node_id"], clerk["org_role_id"], "R", u)
    c = plant(owner, p, s1["bfc_node_id"], audit["org_role_id"], "C", u)

    migrate()                                                          # no uq_bror_one_accountable error

    rows = q(owner, "SELECT org_role_id, raci_behaviour, raci_code_id FROM br_org_role "
                    "WHERE br_id = :b AND is_active ORDER BY 1, 2", b=br["br_id"])
    assert [(o, b) for o, b, _ in rows if b == "ACCOUNTABLE"] == [(cfo["org_role_id"], "ACCOUNTABLE")]
    assert [k for o, b, k in rows if b == "RESPONSIBLE"] == [r_over]                     # one, not two
    assert [k for o, b, k in rows if b == "CONSULTED"] == [c_over]                       # the resolved code
    assert q(owner, "SELECT is_active FROM br_org_role WHERE br_org_role_id = :i",
             i=old_a["br_org_role_id"])[0][0] is False
    (_, _, d), = q(owner, EVENTS)
    assert [x["step_role_id"] for x in d["conflicts"]] == [a]
    assert [s for s, _ in d["already"]] == [r] and [s for s, _ in d["copied"]] == [c]
    assert code_id(owner, "C") != c_over


def test_a_to_be_step_with_roles_and_no_live_br_blocks_with_the_list(client, ed, world, owner, db):
    u, p = world["users"]["editor"], ed["p"]
    s1, g = tree_of(client, ed)
    s2 = node(client, ed, "Ship order", g["bfc_node_id"], is_process=True)
    clerk = _org_role(client, ed, "CLERK")
    retire_br(client, ed, s1["bfc_node_id"])                           # legal: the first step of a demote
    unguard(owner)
    bad = plant(owner, p, s1["bfc_node_id"], clerk["org_role_id"], "R", u)
    plant(owner, p, s2["bfc_node_id"], clerk["org_role_id"], "R", u)
    # DR10d-4: the read-only pre-check names it before deploy
    from scripts import precheck_0052
    found = precheck_0052.find(db)
    assert [(r.bfc_node_id, list(r.step_role_ids)) for r in found] == [(s1["bfc_node_id"], [bad])]
    cfg = _cfg()
    command.downgrade(cfg, "0051")
    with pytest.raises(Exception, match="0052 stopped") as e:
        command.upgrade(cfg, "head")
    assert f"{s1['hier_code']} Take order" in str(e.value) and str(bad) in str(e.value)
    assert "Ship order" not in str(e.value)
    assert q(owner, "SELECT version_num FROM alembic_version")[0][0] == "0051"            # nothing applied
    assert q(owner, "SELECT count(*) FROM bfc_node_org_role WHERE is_active")[0][0] == 2
    assert q(owner, "SELECT count(*) FROM br_org_role")[0][0] == 0
    x(owner, "UPDATE bfc_node_org_role SET is_active = false, deleted_at = now() WHERE bfc_node_org_role_id = :i",
      i=bad)                                                            # fixed by hand
    command.upgrade(cfg, "head")
    assert live_br_roles(owner, _br(client, ed, s2["bfc_node_id"])["br_id"]) == {(clerk["org_role_id"], "RESPONSIBLE")}
    assert precheck_0052.find(db) == []


# ---- history: roles retired with their step [Q-3], DR10d items 1, 5, 6, 8 -------------------------------------

def test_roles_retired_with_their_step_come_back_on_the_br_with_one_accountable_and_a_rerun_adds_nothing(
        client, ed, world, owner):
    u, p = world["users"]["editor"], ed["p"]
    s4, g = tree_of(client, ed)
    s6 = node(client, ed, "Ship order", g["bfc_node_id"], is_process=True)
    br4, br6 = _br(client, ed, s4["bfc_node_id"]), _br(client, ed, s6["bfc_node_id"])
    cfo, clerk, audit, ops = (_org_role(client, ed, c) for c in ("CFO", "CLERK", "AUDIT", "OPS"))
    br_role(client, ed, br4["br_id"], cfo, "A")
    br_role(client, ed, br4["br_id"], ops, "R")
    by_hand = br_role(client, ed, br4["br_id"], clerk, "I")
    unlink_br_role(client, ed, by_hand)                                # its own, earlier stamp
    unguard(owner)
    h = {"a_clerk": plant(owner, p, s4["bfc_node_id"], clerk["org_role_id"], "A", u),    # BR's A=CFO wins
         "r_ops": plant(owner, p, s4["bfc_node_id"], ops["org_role_id"], "R", u),        # already on the BR
         "c_audit": plant(owner, p, s4["bfc_node_id"], audit["org_role_id"], "C", u),    # carried
         "i_clerk": plant(owner, p, s4["bfc_node_id"], clerk["org_role_id"], "I", u)}    # grain taken: not carried
    lost = plant(owner, p, s6["bfc_node_id"], ops["org_role_id"], "C", u)
    assert retire(client, ed, s4["bfc_node_id"]).status_code == 204     # the pre-10d code lists step roles
    assert retire(client, ed, s6["bfc_node_id"]).status_code == 204
    x(owner, "UPDATE business_requirement SET deleted_at = deleted_at - interval '1 second' WHERE br_id = :b",
      b=br6["br_id"])                                                  # no BR with the event's stamp: unplaced
    at = q(owner, "SELECT deleted_at FROM bfc_node WHERE bfc_node_id = :n", n=s4["bfc_node_id"])[0][0]

    migrate()

    rows = q(owner, "SELECT org_role_id, raci_behaviour, is_active, deleted_at, deleted_by, created_by "
                    "FROM br_org_role WHERE br_id = :b AND deleted_at = :at", b=br4["br_id"], at=at)
    assert {(o, b) for o, b, *_ in rows} == {(cfo["org_role_id"], "ACCOUNTABLE"), (ops["org_role_id"], "RESPONSIBLE"),
                                             (audit["org_role_id"], "CONSULTED")}
    assert {r[2] for r in rows} == {False} and {r[4] for r in rows} == {u}
    (_, _, d), = q(owner, EVENTS)
    new = q(owner, "SELECT br_org_role_id FROM br_org_role WHERE br_id = :b AND org_role_id = :o",
            b=br4["br_id"], o=audit["org_role_id"])[0][0]
    assert d["history_copied"] == [[h["c_audit"], new]]
    assert d["not_carried"] == [[h["i_clerk"], by_hand["br_org_role_id"]]]
    assert d["unplaced"] == [lost]
    assert [(c["kind"], c["step_role_id"]) for c in d["conflicts"]] == [("RETIRED_WITH_STEP", h["a_clerk"])]
    assert d["retired"] == [] and d["copied"] == []

    # DR10d-1/8: the undo works and brings back exactly one Accountable; step roles of a to-be step stay retired
    r = restore(client, ed, s4["bfc_node_id"])
    assert r.status_code == 200, r.text
    got = client.get(f"{API}/business-requirements/{br4['br_id']}/org-roles", headers=ed["h"]).json()
    assert sorted((g["org_role_id"], g["raci_behaviour"]) for g in got) == sorted(
        [(cfo["org_role_id"], "ACCOUNTABLE"), (ops["org_role_id"], "RESPONSIBLE"), (audit["org_role_id"], "CONSULTED")])
    assert q(owner, "SELECT count(*) FROM bfc_node_org_role WHERE bfc_node_id = :n AND is_active",
             n=s4["bfc_node_id"])[0][0] == 0
    assert client.get(f"{API}/bfc-nodes/{s4['bfc_node_id']}/org-roles", headers=ed["h"]).json() == []

    # DR10d-5: a re-run after a downgrade changes nothing and writes no event
    snap = [q(owner, f"SELECT count(*), count(*) FILTER (WHERE is_active), coalesce(sum(row_version), 0) FROM {t}")
            for t in ("br_org_role", "bfc_node_org_role")]
    migrate()
    assert [q(owner, f"SELECT count(*), count(*) FILTER (WHERE is_active), coalesce(sum(row_version), 0) FROM {t}")
            for t in ("br_org_role", "bfc_node_org_role")] == snap
    assert len(q(owner, EVENTS)) == 1


def test_a_rerun_of_a_plain_merge_adds_nothing_twice(client, ed, world, owner):
    u, p = world["users"]["editor"], ed["p"]
    s1, _ = tree_of(client, ed)
    clerk = _org_role(client, ed, "CLERK")
    unguard(owner)
    plant(owner, p, s1["bfc_node_id"], clerk["org_role_id"], "R", u)
    migrate()
    snap = q(owner, "SELECT (SELECT count(*) FROM br_org_role), (SELECT count(*) FROM bfc_node_org_role), "
                    "(SELECT count(*) FROM audit_event)")
    migrate()
    assert q(owner, "SELECT (SELECT count(*) FROM br_org_role), (SELECT count(*) FROM bfc_node_org_role), "
                    "(SELECT count(*) FROM audit_event)") == snap


# ---- baselines (§4, Q-6) --------------------------------------------------------------------------------------

def test_a_pre_10d_baseline_still_verifies_and_its_diff_shows_each_moved_role_once(client, ed, world, owner):
    u, p = world["users"]["editor"], ed["p"]
    w = scope(client, ed)
    cfo, clerk = _org_role(client, ed, "CFO"), _org_role(client, ed, "CLERK")
    br_role(client, ed, w["br1"]["br_id"], cfo, "A")
    unguard(owner)
    moved = [plant(owner, p, w["s1"]["bfc_node_id"], clerk["org_role_id"], "A", u),     # BR keeps CFO
             plant(owner, p, w["s1"]["bfc_node_id"], clerk["org_role_id"], "R", u),
             plant(owner, p, w["s2"]["bfc_node_id"], cfo["org_role_id"], "C", u)]
    v10 = freeze(client, ed)
    assert v10["counts"]["bfc_node_org_role"] == 3 and v10["baseline"]["hash_spec_version"] == 2

    migrate()

    assert CURRENT_HASH_SPEC == 2                                       # no spec bump (§4)
    detail = client.get(f"{API}/baselines/{bid(v10)}", headers=ed["h"]).json()
    assert detail["intact"] is True and detail["counts"]["bfc_node_org_role"] == 3
    d = diff(client, ed, bid(v10), "live")
    step_rows = d["entities"]["bfc_node_org_role"]["rows"]
    assert sorted(r["source_id"] for r in step_rows) == sorted(moved)                  # each once
    assert {r["change"] for r in step_rows} == {"REMOVED"}
    br_rows = d["entities"]["br_org_role"]["rows"]
    assert [r["change"] for r in br_rows] == ["ADDED", "ADDED"]                        # not the lost A
    v11 = freeze(client, ed)                                           # a freeze after 0052 still works
    assert v11["counts"]["bfc_node_org_role"] == 0 and v11["counts"]["br_org_role"] == 3
    d2 = diff(client, ed, bid(v10), bid(v11))
    assert len(d2["entities"]["bfc_node_org_role"]["rows"]) == 3 and len(d2["entities"]["br_org_role"]["rows"]) == 2


# ---- the guard and the code (§3, spec §4) -------------------------------------------------------------------------

def test_step_roles_are_for_as_is_steps_only_in_the_service_and_the_database(client, ed, world, owner, db):
    u, p = world["users"]["editor"], ed["p"]
    s1, _ = tree_of(client, ed)
    _a, _b, old = step_in(client, ed, "AS_IS", ("Old area", "Old function"), "Old step")
    clerk = _org_role(client, ed, "CLERK")
    assert step_role(client, ed, old, clerk, "A")["raci_behaviour"] == "ACCOUNTABLE"     # as-is: unchanged
    r = client.post(f"{API}/bfc-nodes/{s1['bfc_node_id']}/org-roles", headers=ed["h"],
                    json={"org_role_id": clerk["org_role_id"], "raci_code": "R"})
    assert r.status_code == 409 and r.json()["detail"] == TO_BE_STEP
    # a retired pre-10d row on the to-be step: re-linking it is the same 409, never a 500 from the FK
    x(owner, "INSERT INTO bfc_node_org_role (project_id, bfc_node_id, org_role_id, raci_code_id, raci_behaviour, "
             "created_by, is_active, deleted_at) VALUES (:p, :s, :r, :c, 'RESPONSIBLE', :u, false, now())",
      p=p, s=s1["bfc_node_id"], r=clerk["org_role_id"], c=code_id(owner, "R"), u=u)   # retired: not checked
    r = client.post(f"{API}/bfc-nodes/{s1['bfc_node_id']}/org-roles", headers=ed["h"],
                    json={"org_role_id": clerk["org_role_id"], "raci_code": "R"})
    assert r.status_code == 409 and r.json()["detail"] == TO_BE_STEP
    assert client.get(f"{API}/bfc-nodes/{s1['bfc_node_id']}/org-roles", headers=ed["h"]).json() == []
    # the database refuses a live or restored to-be step role, as the app role
    with pytest.raises(IntegrityError, match="fk_bnor_node_as_is"):
        db.execute(text("INSERT INTO bfc_node_org_role (project_id, bfc_node_id, org_role_id, raci_code_id, "
                        "raci_behaviour, created_by) VALUES (:p, :s, :r, :c, 'CONSULTED', :u)"),
                   {"p": p, "s": s1["bfc_node_id"], "r": clerk["org_role_id"], "c": code_id(owner, "C"), "u": u})
    db.rollback()
    with pytest.raises(IntegrityError, match="fk_bnor_node_as_is"):
        db.execute(text("UPDATE bfc_node_org_role SET is_active = true, deleted_at = NULL WHERE bfc_node_id = :s"),
                   {"s": s1["bfc_node_id"]})
    db.rollback()


def test_an_as_is_step_retired_with_its_roles_restores_them(client, ed):
    _a, _b, old = step_in(client, ed, "AS_IS", ("Old area", "Old function"), "Old step")
    clerk = _org_role(client, ed, "CLERK")
    row = step_role(client, ed, old, clerk, "R")
    assert retire(client, ed, old["bfc_node_id"]).status_code == 204
    assert restore(client, ed, old["bfc_node_id"]).status_code == 200
    got = client.get(f"{API}/bfc-nodes/{old['bfc_node_id']}/org-roles", headers=ed["h"]).json()
    assert [g["bfc_node_org_role_id"] for g in got] == [row["bfc_node_org_role_id"]]


def _copy(client, ed, to_set, from_set):
    url = f"{API}/projects/{ed['p']}/bfc-sets/{to_set}/copy-from/{from_set}"
    prev = client.post(url, headers=ed["h"], json={}).json()
    r = client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 200 and r.json()["applied"], r.text
    return prev


def _process_of(client, ed, bfc_set):
    tree = client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"], params={"bfc_set": bfc_set}).json()
    return next(n for n in tree if n["is_process"])


def test_copying_as_is_into_to_be_puts_the_step_roles_on_the_new_br(client, ed):
    _a, _b, old = step_in(client, ed, "AS_IS")
    cfo, clerk = _org_role(client, ed, "CFO"), _org_role(client, ed, "CLERK")
    step_role(client, ed, old, cfo, "A")
    step_role(client, ed, old, clerk, "R")
    assert _copy(client, ed, "TO_BE", "AS_IS")["step_roles"] == 2
    new = _process_of(client, ed, "TO_BE")
    br = _br(client, ed, new["bfc_node_id"])
    got = client.get(f"{API}/business-requirements/{br['br_id']}/org-roles", headers=ed["h"]).json()
    assert sorted((g["org_role_id"], g["raci_code"]) for g in got) == sorted(
        [(cfo["org_role_id"], "A"), (clerk["org_role_id"], "R")])
    assert client.get(f"{API}/bfc-nodes/{new['bfc_node_id']}/org-roles", headers=ed["h"]).json() == []


def test_copying_to_be_into_as_is_puts_the_br_roles_on_the_new_step(client, ed):
    _a, _b, s = step_in(client, ed)
    br = _br(client, ed, s["bfc_node_id"])
    cfo, audit = _org_role(client, ed, "CFO"), _org_role(client, ed, "AUDIT")
    br_role(client, ed, br["br_id"], cfo, "A")
    gone = br_role(client, ed, br["br_id"], audit, "I")
    unlink_br_role(client, ed, gone)                                   # retired: not copied
    br_role(client, ed, br["br_id"], audit, "C")
    assert _copy(client, ed, "AS_IS", "TO_BE")["step_roles"] == 2
    new = _process_of(client, ed, "AS_IS")
    got = client.get(f"{API}/bfc-nodes/{new['bfc_node_id']}/org-roles", headers=ed["h"]).json()
    assert sorted((g["org_role_id"], g["raci_code"]) for g in got) == sorted(
        [(cfo["org_role_id"], "A"), (audit["org_role_id"], "C")])
