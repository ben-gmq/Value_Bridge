"""Retire a step with its requirement and flows, and undo it (docs/step_retire_spec.md, design
§1a S3-SR). Grade 2: recoverable, but one click changes many rows — so each acceptance
criterion 1–10 has a test here, plus the round-2 build rules SR-1 (both directions) and SR-2.

Not covered here: criterion 11 (no baseline freeze exists yet, A-SR-7), and the on-screen
confirmation itself (criterion 10 is proven here at the API the screens call, and in a browser)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import BigInteger, ForeignKey, Identity, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Mapped, mapped_column

from database import SessionLocal
from models import (AuditEvent, BfcNode, BfcNodeFlow, BfcNodeOrgRole, Base)
from models.base import AuditMixin
from services import lifecycle, step_retire
from tests.conftest import OWNER_URL
from tests.test_dfd_api import ext_flow, io, party
from tests.test_process_flow_api import edge
from tests.test_scope_api import API, _org_role, ed, entity, node, tree  # noqa: F401 — ed is a fixture

OWNED_TABLES = ("bfc_node", "business_requirement", "br_data_entity", "br_org_role",
                "bfc_node_data_entity", "bfc_node_org_role", "bfc_node_external_flow", "bfc_node_flow")
PKS = {"bfc_node": "bfc_node_id", "business_requirement": "br_id",
       "br_data_entity": "br_data_entity_id", "br_org_role": "br_org_role_id",
       "bfc_node_data_entity": "bfc_node_data_entity_id", "bfc_node_org_role": "bfc_node_org_role_id",
       "bfc_node_external_flow": "bfc_node_external_flow_id", "bfc_node_flow": "bfc_node_flow_id"}


# ---- helpers ------------------------------------------------------------------------------

def _br(client, ed, node_id):
    return next(b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                      headers=ed["h"]).json() if b["bfc_node_id"] == node_id)


def preview(client, ed, step_id, headers=None):
    return client.get(f"{API}/bfc-nodes/{step_id}/retire-preview", headers=headers or ed["h"])


def retire(client, ed, step_id, confirm_hash=None, headers=None):
    h = confirm_hash or preview(client, ed, step_id).json()["confirm_hash"]
    return client.post(f"{API}/bfc-nodes/{step_id}/retire-with-dependents", headers=headers or ed["h"],
                       json={"confirm_hash": h})


def restore(client, ed, step_id, headers=None):
    return client.post(f"{API}/bfc-nodes/{step_id}/restore-with-dependents", headers=headers or ed["h"])


def plain_restore(client, ed, node_id):
    return client.patch(f"{API}/bfc-nodes/{node_id}/restore", headers=ed["h"])


def plain_retire(client, ed, node_id):
    n = client.get(f"{API}/bfc-nodes/{node_id}", headers=ed["h"]).json()
    return client.delete(f"{API}/bfc-nodes/{node_id}", headers=ed["h"], params={"row_version": n["row_version"]})


def retire_br(client, ed, node_id):
    br = _br(client, ed, node_id)
    r = client.delete(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"],
                      params={"row_version": br["row_version"]})
    assert r.status_code == 204, r.text


def step_role(client, ed, step, org_role, raci="R"):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/org-roles", headers=ed["h"],
                    json={"org_role_id": org_role["org_role_id"], "raci_code": raci})
    assert r.status_code == 201, r.text
    return r.json()


def br_role(client, ed, br, org_role, raci="A"):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/org-roles", headers=ed["h"],
                    json={"org_role_id": org_role["org_role_id"], "raci_code": raci})
    assert r.status_code == 201, r.text
    return r.json()


def br_data(client, ed, br, de, crud):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": crud})
    assert r.status_code == 201, r.text
    return r.json()


def rows_of(project_id: int) -> dict:
    """Every row of the owned tables in the project, plus the audit trail — the 'nothing changed'
    snapshot for criteria 3, 4 and 7."""
    with SessionLocal() as s:
        out = {t: s.execute(text(f"SELECT {PKS[t]}, is_active, deleted_at, row_version FROM {t} "
                                 "WHERE project_id = :p ORDER BY 1"), {"p": project_id}).all()
               for t in OWNED_TABLES}
        out["audit_event"] = s.scalar(text("SELECT count(*) FROM audit_event"))
    return out


def live(table: str, pk: int) -> bool:
    with SessionLocal() as s:
        return s.scalar(text(f"SELECT is_active FROM {table} WHERE {PKS[table]} = :i"), {"i": pk})


def summary_events(step_id: int, kind=step_retire.RETIRED) -> list[AuditEvent]:
    with SessionLocal() as s:
        return list(s.scalars(select(AuditEvent).where(
            AuditEvent.event_type == kind, AuditEvent.target_id == step_id)
            .order_by(AuditEvent.audit_event_id)))


@pytest.fixture
def full(client, ed):
    """Criterion 1's step: a BR with 2 data links and 1 role; 3 step I/O rows (two licensing the
    BR's CRUD); 1 step role; 1 external flow licensed by an I/O row; 2 arrows, one a self-loop.
    Plus a second live step it hands on to, under the same parent."""
    a = node(client, ed, "Sales")
    p = node(client, ed, "Order to cash", a["bfc_node_id"])
    s = node(client, ed, "Check credit", p["bfc_node_id"], is_process=True)
    s2 = node(client, ed, "Confirm order", p["bfc_node_id"], is_process=True)
    br = _br(client, ed, s["bfc_node_id"])
    cust, order, limit = entity(client, ed, "Customer"), entity(client, ed, "Sales order"), entity(client, ed, "Credit limit")
    brde = [br_data(client, ed, br, cust, "R"), br_data(client, ed, br, order, "C")]   # → I/O (cust, I), (order, O)
    io(client, ed, s, limit, "I")
    bank = party(client, ed, "Credit bureau")
    xf = ext_flow(client, ed, s, bank, "I", limit)                       # licensed by (limit, I)
    cfo, clerk = _org_role(client, ed, "CFO"), _org_role(client, ed, "CLERK")
    bror = br_role(client, ed, br, cfo)
    bnor = step_role(client, ed, s, clerk)
    arrows = [edge(client, ed, s, s2), edge(client, ed, s, s, "CONDITIONAL", "Recheck")]
    step_io = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/data-entities", headers=ed["h"]).json()
    owned = ({("business_requirement", br["br_id"])}
             | {("br_data_entity", r["br_data_entity_id"]) for r in brde}
             | {("br_org_role", bror["br_org_role_id"])}
             | {("bfc_node_data_entity", r["bfc_node_data_entity_id"]) for r in step_io}
             | {("bfc_node_org_role", bnor["bfc_node_org_role_id"])}
             | {("bfc_node_external_flow", xf["bfc_node_external_flow_id"])}
             | {("bfc_node_flow", e["bfc_node_flow_id"]) for e in arrows})
    assert len(step_io) == 3 and len(owned) == 11
    return {"parent": p, "s": s, "s2": s2, "br": br, "owned": owned, "arrows": arrows,
            "bnor": bnor, "cfo": cfo, "limit": limit, "orders": order}


# ---- criterion 1: the owned set, once each; one stamp; one event per row plus a summary ----------

def test_preview_lists_exactly_the_owned_rows_and_retire_takes_them_with_one_stamp(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    pv = preview(client, ed, sid).json()
    got = [(o["table"], o["id"]) for o in pv["owned"]]
    assert len(got) == len(set(got)) and set(got) == full["owned"]      # the self-loop counts once
    assert pv["blockers"] == [] and len(pv["confirm_hash"]) == 64
    assert next(o["label"] for o in pv["owned"] if o["table"] == "business_requirement") == full["br"]["br_number"]

    r = retire(client, ed, sid, pv["confirm_hash"])
    assert r.status_code == 204, r.text                                 # the tier order held the licence FKs
    everything = full["owned"] | {("bfc_node", sid)}
    with SessionLocal() as s:
        stamps = set()
        for table, pk in everything:
            is_active, deleted_at = s.execute(text(
                f"SELECT is_active, deleted_at FROM {table} WHERE {PKS[table]} = :i"), {"i": pk}).one()
            assert is_active is False, (table, pk)
            stamps.add(deleted_at)
        assert len(stamps) == 1                                          # one deleted_at for all
        (summary,) = summary_events(sid)
        per_row = list(s.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "RECORD_DELETED",
            AuditEvent.detail["action_id"].astext == summary.detail["action_id"])))
    assert {(e.target_table, e.target_id) for e in per_row} == everything and len(per_row) == 12
    assert {tuple(x) for x in summary.detail["rows"]} == everything and len(summary.detail["rows"]) == 12
    assert datetime.fromisoformat(summary.detail["deleted_at"]) == stamps.pop()
    assert summary.detail["confirm_hash"] == pv["confirm_hash"]


# ---- criterion 2: no half state, and the chart hides the step --------------------------------------

def test_after_retire_the_completeness_checks_are_clean_and_the_chart_hides_the_step(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    url = f"{API}/projects/{ed['p']}/flow-completeness"
    before = client.get(url, headers=ed["h"]).json()
    assert before["step_without_br"] == [] and before["live_link_on_retired_step"] == []
    assert retire(client, ed, sid).status_code == 204
    after = client.get(url, headers=ed["h"]).json()
    assert after["step_without_br"] == [] and after["live_link_on_retired_step"] == []
    assert sid not in {n["bfc_node_id"] for n in tree(client, ed)}
    g = client.get(f"{API}/bfc-nodes/{full['parent']['bfc_node_id']}/process-flow", headers=ed["h"]).json()
    assert [n["node_name"] for n in g["nodes"]] == ["Confirm order"] and g["edges"] == []


def test_step_without_br_is_a_warning_and_a_live_link_on_a_retired_step_is_named(client, ed, full, db):
    """SR-3: retiring the BR alone (the first step of a demote) is legal and reported. A live
    link on a retired step can only be forged below the service; the check names it."""
    s2 = full["s2"]
    retire_br(client, ed, s2["bfc_node_id"])
    url = f"{API}/projects/{ed['p']}/flow-completeness"
    got = client.get(url, headers=ed["h"]).json()
    assert [x["node_name"] for x in got["step_without_br"]] == ["Confirm order"]
    assert retire(client, ed, full["s"]["bfc_node_id"]).status_code == 204
    row = db.get(BfcNodeOrgRole, full["bnor"]["bfc_node_org_role_id"])
    lifecycle.relink(db, row.created_by, row)                  # forged: the step stays retired
    db.commit()
    got = client.get(url, headers=ed["h"]).json()
    assert got["live_link_on_retired_step"] == [
        {"table": "bfc_node_org_role", "id": full["bnor"]["bfc_node_org_role_id"]}]


# ---- criterion 3: a stale preview -------------------------------------------------------------------

def test_a_preview_taken_before_a_new_io_row_is_refused_and_nothing_is_retired(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    old = preview(client, ed, sid).json()["confirm_hash"]
    io(client, ed, full["s"], entity(client, ed, "Invoice"), "O")
    snap = rows_of(ed["p"])
    r = retire(client, ed, sid, old)
    assert r.status_code == 409 and "changed since the preview" in r.json()["detail"]
    assert rows_of(ed["p"]) == snap


# ---- criterion 4: a dependent outside the owned set blocks ----------------------------------------

@pytest.fixture
def probe_table():
    """A test-only table hanging off the step, the BR and an owned link row. It is registered in
    Base.metadata and lifecycle.LINKS is rebuilt, so the real derived rule sees it."""
    class StepRetireProbe(AuditMixin, Base):
        __tablename__ = "zz_step_retire_probe"
        probe_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
        project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
        bfc_node_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bfc_node.bfc_node_id"))
        br_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("business_requirement.br_id"))
        bfc_node_org_role_id: Mapped[int | None] = mapped_column(
            BigInteger, ForeignKey("bfc_node_org_role.bfc_node_org_role_id"))

    table = StepRetireProbe.__table__
    app_user = make_url(SessionLocal.kw["bind"].url).username
    eng = create_engine(OWNER_URL)
    saved = lifecycle.LINKS
    try:
        table.create(eng)
        with eng.begin() as c:
            c.execute(text(f"GRANT SELECT, INSERT, UPDATE ON {table.name} TO {app_user}"))
        lifecycle.LINKS = lifecycle._links()
        yield StepRetireProbe
    finally:
        lifecycle.LINKS = saved
        table.drop(eng, checkfirst=True)
        Base.metadata.remove(table)
        eng.dispose()


def test_a_dependent_on_the_step_the_br_or_an_owned_link_blocks(client, ed, full, probe_table, db, world):
    sid = full["s"]["bfc_node_id"]
    assert any(ln.child is probe_table for ln in lifecycle.dependents_of(BfcNode))
    snap = rows_of(ed["p"])
    for col, value in (("bfc_node_id", sid), ("br_id", full["br"]["br_id"]),
                       ("bfc_node_org_role_id", full["bnor"]["bfc_node_org_role_id"])):
        p = probe_table(project_id=ed["p"], created_by=world["users"]["editor"], **{col: value})
        db.add(p)
        db.commit()
        pv = preview(client, ed, sid).json()
        assert pv["blockers"] == [{"table": "zz_step_retire_probe", "id": p.probe_id,
                                   "label": "zz_step_retire_probe"}], col
        r = retire(client, ed, sid, pv["confirm_hash"])
        assert r.status_code == 409 and "zz_step_retire_probe" in r.json()["detail"], col
        lifecycle.soft_delete(p, p.created_by)                  # out of the way for the next case
        db.commit()
    assert rows_of(ed["p"]) == snap


# ---- criterion 5: restore brings back exactly the listed rows --------------------------------------

def test_restore_brings_back_exactly_the_listed_rows(client, ed, full, db):
    sid = full["s"]["bfc_node_id"]
    solo = br_role(client, ed, full["br"], _org_role(client, ed, "AUDIT"), "C")
    r = client.delete(f"{API}/business-requirements/{full['br']['br_id']}/org-roles/{solo['br_org_role_id']}",
                      headers=ed["h"], params={"row_version": solo["row_version"]})
    assert r.status_code == 204                                 # retired on its own, "the day before"
    assert retire(client, ed, sid).status_code == 204

    by_hand = db.get(BfcNodeOrgRole, full["bnor"]["bfc_node_org_role_id"])
    lifecycle.relink(db, by_hand.created_by, by_hand)          # restored by hand in between
    again = db.get(BfcNodeFlow, full["arrows"][0]["bfc_node_flow_id"])
    lifecycle.relink(db, again.created_by, again)
    db.flush()
    lifecycle.soft_delete(again, again.created_by, at=datetime.now(UTC) + timedelta(seconds=1))
    db.commit()                                                 # …and one re-retired since

    r = restore(client, ed, sid)
    assert r.status_code == 200 and r.json() == {"restored": 10}, r.text
    assert not live("br_org_role", solo["br_org_role_id"])
    assert not live("bfc_node_flow", again.bfc_node_flow_id)
    assert live("bfc_node_org_role", by_hand.bfc_node_org_role_id)
    for table, pk in full["owned"] - {("bfc_node_flow", again.bfc_node_flow_id)}:
        assert live(table, pk), (table, pk)
    assert live("bfc_node", sid)
    (done,) = summary_events(sid, step_retire.RESTORED)
    assert len(done.detail["rows"]) == 10
    assert done.detail["retire_action_id"] == summary_events(sid)[0].detail["action_id"]


# ---- criterion 6: all or nothing, and no arrow is lost ----------------------------------------------

@pytest.mark.parametrize("retire_order,restore_order", [
    ("xy", "xy"), ("xy", "yx"), ("yx", "xy"), ("yx", "yx")])
def test_two_related_steps_restore_in_either_order_and_the_arrow_survives(client, ed, full,
                                                                        retire_order, restore_order):
    x, y = full["s"]["bfc_node_id"], full["s2"]["bfc_node_id"]
    ids = {"x": x, "y": y}
    arrow = full["arrows"][0]["bfc_node_flow_id"]                  # x → y
    for k in retire_order:
        assert retire(client, ed, ids[k]).status_code == 204
    first, second = (ids[k] for k in restore_order)
    r = restore(client, ed, first)
    if r.status_code == 409:                                        # its arrow's far step is retired
        detail = r.json()["detail"]
        assert "Restore these first" in detail and ("Confirm order" in detail or "Check credit" in detail)
        assert r.headers["x-vb-error"] == "RESTORE_FIRST"
        assert not live("bfc_node", first)                         # refused as a whole
        assert restore(client, ed, second).status_code == 200
        assert restore(client, ed, first).status_code == 200
    else:
        assert r.status_code == 200, r.text
        assert restore(client, ed, second).status_code == 200
    assert live("bfc_node_flow", arrow)
    got = client.get(f"{API}/projects/{ed['p']}/flow-completeness", headers=ed["h"]).json()
    assert got["live_link_on_retired_step"] == [] and got["step_without_br"] == []


def test_restore_refuses_while_a_data_entity_is_retired_then_succeeds(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    assert retire(client, ed, sid).status_code == 204
    de = client.get(f"{API}/data-entities/{full['limit']['data_entity_id']}", headers=ed["h"]).json()
    r = client.delete(f"{API}/data-entities/{de['data_entity_id']}", headers=ed["h"],
                      params={"row_version": de["row_version"]})
    assert r.status_code == 204, r.text                            # free once the step's I/O is retired
    snap = rows_of(ed["p"])
    r = restore(client, ed, sid)
    assert r.status_code == 409 and de["de_number"] in r.json()["detail"]
    assert rows_of(ed["p"]) == snap
    assert client.patch(f"{API}/data-entities/{de['data_entity_id']}/restore", headers=ed["h"]).status_code == 200
    assert restore(client, ed, sid).status_code == 200
    assert all(live(t, pk) for t, pk in full["owned"])


# ---- criterion 7: a failure on the last row changes nothing ---------------------------------------

def _fail_on_call(monkeypatch, name: str, n: int):
    real, calls = getattr(step_retire, name), []

    def wrapped(*a, **kw):
        calls.append(1)
        if len(calls) == n:
            raise RuntimeError("forced failure on the last row")
        return real(*a, **kw)
    monkeypatch.setattr(step_retire, name, wrapped)
    return calls


def test_a_failure_on_the_last_row_of_retire_or_restore_leaves_everything_as_it_was(
        client, ed, full, monkeypatch, world):
    sid = full["s"]["bfc_node_id"]
    actor = world["users"]["editor"]
    h = preview(client, ed, sid).json()["confirm_hash"]
    snap = rows_of(ed["p"])
    calls = _fail_on_call(monkeypatch, "retire_row", 12)
    with SessionLocal() as s:
        with pytest.raises(RuntimeError):
            step_retire.retire(s, actor, s.get(BfcNode, sid), h)
    assert len(calls) == 12 and rows_of(ed["p"]) == snap          # the step was the last row
    monkeypatch.undo()

    assert retire(client, ed, sid).status_code == 204
    snap = rows_of(ed["p"])
    calls = _fail_on_call(monkeypatch, "restore_row", 12)
    with SessionLocal() as s:
        with pytest.raises(RuntimeError):
            step_retire.restore(s, actor, s.get(BfcNode, sid))
    assert len(calls) == 12 and rows_of(ed["p"]) == snap          # tier 1 came last, after the flushes
    monkeypatch.undo()
    assert restore(client, ed, sid).status_code == 200


# ---- criterion 8: the plain restore refuses a with-dependents retire, and vice versa --------------

def test_plain_restore_of_a_step_retired_with_dependents_is_refused(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    assert retire(client, ed, sid).status_code == 204
    r = plain_restore(client, ed, sid)
    assert r.status_code == 409 and "Restore with its requirement and flows" in r.json()["detail"]
    assert r.headers["x-vb-error"] == "USE_RESTORE_WITH_DEPENDENTS"
    assert not live("bfc_node", sid)

    lone = node(client, ed, "Lone step", full["parent"]["bfc_node_id"], is_process=True)
    retire_br(client, ed, lone["bfc_node_id"])
    assert plain_retire(client, ed, lone["bfc_node_id"]).status_code == 204
    r = restore(client, ed, lone["bfc_node_id"])
    assert r.status_code == 409 and r.headers["x-vb-error"] == "USE_PLAIN_RESTORE"
    assert plain_restore(client, ed, lone["bfc_node_id"]).status_code == 200


# ---- SR-1: the stamp decides, in both directions ---------------------------------------------------

def test_sr1_a_later_plain_retire_takes_the_plain_restore(client, ed, full):
    """With-dependents first, then the plain way: the old summary event no longer matches."""
    lone = node(client, ed, "Lone step", full["parent"]["bfc_node_id"], is_process=True)
    lid = lone["bfc_node_id"]
    assert retire(client, ed, lid).status_code == 204
    assert restore(client, ed, lid).status_code == 200
    retire_br(client, ed, lid)
    assert plain_retire(client, ed, lid).status_code == 204
    assert len(summary_events(lid)) == 1                          # the old event is still there
    r = restore(client, ed, lid)
    assert r.status_code == 409 and r.headers["x-vb-error"] == "USE_PLAIN_RESTORE"
    assert plain_restore(client, ed, lid).status_code == 200


def test_sr1_a_later_with_dependents_retire_takes_its_own_restore(client, ed, full):
    """The plain way first, then with dependents: only the matching restore works."""
    lone = node(client, ed, "Lone step", full["parent"]["bfc_node_id"], is_process=True)
    lid = lone["bfc_node_id"]
    retire_br(client, ed, lid)
    assert plain_retire(client, ed, lid).status_code == 204
    assert plain_restore(client, ed, lid).status_code == 200
    assert retire(client, ed, lid).status_code == 204
    r = plain_restore(client, ed, lid)
    assert r.status_code == 409 and r.headers["x-vb-error"] == "USE_RESTORE_WITH_DEPENDENTS"
    r = restore(client, ed, lid)
    assert r.status_code == 200 and r.json() == {"restored": 1}


# ---- SR-2: the step comes back through restore_node's checks ---------------------------------------

def test_sr2_a_step_restored_after_its_parent_moved_takes_the_new_code(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    assert full["s"]["hier_code"] == "01.01.01"
    assert retire(client, ed, sid).status_code == 204
    top = client.get(f"{API}/bfc-nodes/{full['parent']['parent_bfc_node_id']}", headers=ed["h"]).json()
    first = node(client, ed, "Quote", top["bfc_node_id"])       # 01.02
    moved = client.get(f"{API}/bfc-nodes/{first['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{moved['bfc_node_id']}/reorder", headers=ed["h"],
                     json={"row_version": moved["row_version"], "new_seq_no": 1})
    assert r.status_code == 200, r.text                          # "Order to cash" is now 01.02
    assert restore(client, ed, sid).status_code == 200
    back = client.get(f"{API}/bfc-nodes/{sid}", headers=ed["h"]).json()
    s2 = client.get(f"{API}/bfc-nodes/{full['s2']['bfc_node_id']}", headers=ed["h"]).json()
    assert s2["hier_code"] == "01.02.02"
    assert back["hier_code"] == "01.02.01" and back["is_active"]


def test_sr2_a_name_taken_while_retired_refuses_the_whole_restore(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    assert retire(client, ed, sid).status_code == 204
    node(client, ed, "check  CREDIT", full["parent"]["bfc_node_id"], is_process=True)
    snap = rows_of(ed["p"])
    r = restore(client, ed, sid)
    assert r.status_code == 409 and "already exists" in r.json()["detail"]
    assert rows_of(ed["p"]) == snap


# ---- criterion 9: guards --------------------------------------------------------------------------

def test_reviewers_are_refused_outsiders_see_nothing_and_a_summary_node_is_422(client, ed, full):
    sid = full["s"]["bfc_node_id"]
    body = {"confirm_hash": "0" * 64}
    for who, code in (("rv", 403), ("out", 404)):
        h = ed[who]
        assert client.get(f"{API}/bfc-nodes/{sid}/retire-preview", headers=h).status_code == code
        assert client.post(f"{API}/bfc-nodes/{sid}/retire-with-dependents", headers=h, json=body).status_code == code
        assert client.post(f"{API}/bfc-nodes/{sid}/restore-with-dependents", headers=h).status_code == code
    pid = full["parent"]["bfc_node_id"]
    assert preview(client, ed, pid).status_code == 422
    assert client.post(f"{API}/bfc-nodes/{pid}/retire-with-dependents", headers=ed["h"], json=body).status_code == 422
    assert restore(client, ed, pid).status_code == 422
    assert live("bfc_node", sid) and live("bfc_node", pid)


# ---- criterion 10: the calls the step pop-up and the node panel make --------------------------------

def test_the_screens_sequence_preview_retire_then_restore(client, ed, full):
    """The canvas pop-up and the node panel share one dialog: preview → confirm → retire; a
    retired step then offers only the with-dependents restore (the plain one answers 409)."""
    sid = full["s"]["bfc_node_id"]
    pv = preview(client, ed, sid).json()
    counts = {}
    for o in pv["owned"]:
        counts[o["table"]] = counts.get(o["table"], 0) + 1
    assert counts == {"business_requirement": 1, "br_data_entity": 2, "br_org_role": 1,
                      "bfc_node_data_entity": 3, "bfc_node_org_role": 1,
                      "bfc_node_external_flow": 1, "bfc_node_flow": 2}
    assert retire(client, ed, sid, pv["confirm_hash"]).status_code == 204
    assert retire(client, ed, sid, pv["confirm_hash"]).status_code in (409,)   # already retired
    assert plain_restore(client, ed, sid).headers["x-vb-error"] == "USE_RESTORE_WITH_DEPENDENTS"
    assert restore(client, ed, sid).json() == {"restored": 12}
    assert restore(client, ed, sid).status_code == 409                          # not retired


def test_restore_names_an_arrow_end_that_was_demoted_meanwhile(client, ed):
    """An arrow's far step demoted while this step was retired is named, not a bare FK error (sara M1)."""
    l1 = node(client, ed, "Sales")
    parent = node(client, ed, "Order capture", l1["bfc_node_id"])
    a = node(client, ed, "Receive order", parent["bfc_node_id"], is_process=True)
    b = node(client, ed, "Check credit", parent["bfc_node_id"], is_process=True)
    edge(client, ed, a, b, "SEQUENCE", None)
    assert retire(client, ed, a["bfc_node_id"]).status_code == 204
    retire_br(client, ed, b["bfc_node_id"])
    cur = client.get(f"{API}/bfc-nodes/{b['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{b['bfc_node_id']}/process", headers=ed["h"],
                     json={"is_process": False, "row_version": cur["row_version"]})
    assert r.status_code == 200, r.text
    r = restore(client, ed, a["bfc_node_id"])
    assert r.status_code == 409 and r.headers.get("X-VB-Error") == "RESTORE_FIRST"
    assert "Check credit" in r.json()["detail"] and "process step again" in r.json()["detail"]
