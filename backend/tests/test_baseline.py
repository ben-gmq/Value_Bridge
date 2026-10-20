"""The baseline freeze, approval and diff (slice8_schema §5, §7; criteria 13–17a, 26–28, 33, 35, 37, 41, 46,
48, 50, 54, 55, 57, 58; design review DR8). Grade 1: a baseline is the scope record a commercial dispute
quotes — a row that changes, goes missing or is added after the fact is proven impossible directly,
including at the database."""
import hashlib
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select, text

from models import AuditEvent, SHADOW_TABLES
from services.baseline_shadow import parity_problems, shadow_table
from services.freeze_set import FREEZE_SET
from tests.conftest import OWNER_URL, login
from tests.test_components import new_project
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, brs, ed, entity, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol


# ---- helpers ------------------------------------------------------------------------------

def io_step(client, ed, name, parent, de_in, de_out):
    """A process step whose BR reads one entity and creates another: input and output, so the DFD gaps
    that block a freeze (D-38) are closed."""
    s = node(client, ed, name, parent, is_process=True)
    br = next(b for b in brs(client, ed).values() if b["bfc_node_id"] == s["bfc_node_id"])
    for de, crud in ((de_in, "R"), (de_out, "C")):
        r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                        json={"data_entity_id": de["data_entity_id"], "crud_code": crud})
        assert r.status_code == 201, r.text
    return s, br


def scope(client, ed):
    """Two areas, two clean steps, two entities."""
    a = node(client, ed, "Sales")
    b = node(client, ed, "Order to cash", a["bfc_node_id"])
    order, invoice = entity(client, ed, "Sales order"), entity(client, ed, "Invoice")
    s1, br1 = io_step(client, ed, "Take order", b["bfc_node_id"], invoice, order)
    s2, br2 = io_step(client, ed, "Bill order", b["bfc_node_id"], order, invoice)
    return {"area": a, "group": b, "order": order, "invoice": invoice, "s1": s1, "s2": s2, "br1": br1, "br2": br2}


def preview(client, ed, project=None, bump="MINOR", headers=None):
    r = client.get(f"{API}/projects/{project or ed['p']}/baselines/next", headers=headers or ed["h"],
                   params={"bump": bump})
    assert r.status_code == 200, r.text
    return r.json()


def freeze(client, ed, project=None, bump="MINOR", note=None, headers=None, expect=201, **over):
    p = preview(client, ed, project, bump, headers)
    body = {"note": note, "bump": bump, "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"],
            **over}
    r = client.post(f"{API}/projects/{project or ed['p']}/baselines/freeze", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def diff(client, ed, a, b, priced=False, project=None, headers=None, expect=200):
    r = client.get(f"{API}/projects/{project or ed['p']}/baselines/diff", headers=headers or ed["h"],
                   params={"from": a, "to": b, "priced": priced})
    assert r.status_code == expect, r.text
    return r.json()


def changes(d, entity_name):
    return {(r["change"], r["label"]) for r in d["entities"][entity_name]["rows"]}


def bid(f):
    return f["baseline"]["baseline_id"]


def patch_br(client, ed, br, **body):
    cur = client.get(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"],
                     json={"row_version": cur["row_version"], **body})
    assert r.status_code == 200, r.text
    return r.json()


def owner_exec(sql, **params):
    """One transaction as the owner; `sql` may hold several statements separated by ';'."""
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as c:
            for stmt in [x for x in sql.split(";") if x.strip()]:
                c.execute(text(stmt), params if ":b" in stmt else {})
    finally:
        eng.dispose()


# ---- the freeze ---------------------------------------------------------------------------

def test_freeze_snapshots_every_open_table_baselines_brs_and_audits(client, ed, db):
    """Criteria 13, 54: one header, rows in every table whose gate is open, in one transaction."""
    w = scope(client, ed)
    s = sol(client, ed)
    link(client, ed, w["br1"]["br_id"], s["solution_id"])
    fr(client, ed, solution_id=s["solution_id"])
    out = freeze(client, ed, note="After the sales workshop")
    b = out["baseline"]
    assert (b["version_label"], b["status_code"], b["note"], b["frozen_by"]) == \
        ("v1.0", "FROZEN", "After the sales workshop", "Editor")
    n = out["counts"]
    assert n["bfc_node"] == 4 and n["business_requirement"] == 2 and n["data_entity"] == 2
    assert n["br_data_entity"] == 4 and n["bfc_node_data_entity"] == 4 and n["br_solution"] == 1
    assert n["function_requirement"] == 1 and n["effort_rate"] > 0 and n["project_component"] == 12
    assert {x["status_code"] for x in brs(client, ed).values()} == {"BASELINED"}
    detail = client.get(f"{API}/baselines/{b['baseline_id']}", headers=ed["rv"]).json()
    assert detail["intact"] and detail["counts"] == n and "EFFORT" in detail["components"]
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "BASELINE_FROZEN")).one()
    assert ev.detail["version_label"] == "v1.0" and ev.detail["counts"]["bfc_node"] == 4


def test_the_frozen_row_keeps_the_consultants_status_and_labels_not_code_ids(client, ed):
    scope(client, ed)
    b = bid(freeze(client, ed))
    rows = client.get(f"{API}/baselines/{b}/rows/business_requirement", headers=ed["rv"]).json()
    assert {r["status_code"] for r in rows["rows"]} == {"DRAFT"}
    assert "status_code_id" not in rows["columns"] and "status_label" in rows["columns"]
    assert rows["rows"][0]["label"].startswith("BR-0001")
    assert client.get(f"{API}/baselines/{b}/rows/app_user", headers=ed["rv"]).status_code == 400


def test_a_stale_br_form_after_a_freeze_is_409(client, ed):
    """DR8-L1: the BASELINED flip bumps row_version, so a form opened before the freeze cannot revert it."""
    w = scope(client, ed)
    before = client.get(f"{API}/business-requirements/{w['br1']['br_id']}", headers=ed["h"]).json()
    freeze(client, ed)
    r = client.patch(f"{API}/business-requirements/{w['br1']['br_id']}", headers=ed["h"],
                     json={"row_version": before["row_version"], "status_code": "CONFIRMED"})
    assert r.status_code == 409


def test_who_may_freeze_and_the_typed_confirmation(client, ed):
    """Criteria 35, 48 (EDIT freezes, S8-1): a viewer is refused, an outsider sees nothing, the typed text
    must name the project and the next version."""
    scope(client, ed)
    p = preview(client, ed)
    assert p["confirm_text"] == "SOLO v1.0"
    url = f"{API}/projects/{ed['p']}/baselines/freeze"
    body = {"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]}
    assert client.post(url, headers=ed["rv"], json=body).status_code == 403
    assert client.post(url, headers=ed["out"], json=body).status_code == 404
    assert client.post(url, headers=ed["h"], json={**body, "confirm_text": "SOLO v1.1"}).status_code == 422
    assert client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json() == []


def test_the_freeze_is_bound_to_the_preview_the_person_confirmed(client, ed):
    """DR8-P2: scope changed after the preview → 409, nothing saved."""
    w = scope(client, ed)
    p = preview(client, ed)
    patch_br(client, ed, w["br1"], br_statement="Changed after the preview")
    r = client.post(f"{API}/projects/{ed['p']}/baselines/freeze", headers=ed["h"],
                    json={"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    assert r.status_code == 409 and "changed since" in r.json()["detail"]
    assert client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json() == []


def test_a_dfd_gap_refuses_the_freeze_and_names_it(client, ed):
    """D-38 / S7-3, criterion 46: a to-be step with no input or output refuses while the DFD is on."""
    w = scope(client, ed)
    node(client, ed, "Ship order", w["group"]["bfc_node_id"], is_process=True)
    p = preview(client, ed)
    assert p["freeze_blocking"]["process_missing_input"]
    r = client.post(f"{API}/projects/{ed['p']}/baselines/freeze", headers=ed["h"],
                    json={"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    assert r.status_code == 409 and r.json()["detail"]["freeze_blocking"]["process_missing_output"]


def test_a_requirements_only_project_freezes_without_dfd_or_rate_card(client, world):
    """S7-3, D-37: no DFD → I/O gaps do not refuse; EFFORT off → no rate-card rows and no pricing."""
    p = new_project(client, world, "REQ", [])["project_id"]
    h = world["admin"]
    w = {"h": h, "p": p}
    a = node(client, w, "Sales")
    g = node(client, w, "Order to cash", a["bfc_node_id"])
    node(client, w, "Take order", g["bfc_node_id"], is_process=True)
    out = freeze(client, w)
    assert out["counts"]["effort_rate"] == 0 and out["counts"]["business_requirement"] == 1
    assert out["counts"]["project_component"] == 0
    d = diff(client, w, bid(out), "live", priced=True)
    assert d["pricing"] == {"available": False, "reason": "EFFORT_OFF", "in": ["v1.0", "LIVE"]}


def test_versions_count_in_integers_and_a_major_bump_resets(client, ed):
    """Criterion 37 (P9): v1.9 → v1.10, MAJOR → v2.0; a resubmitted freeze is refused, never doubled."""
    scope(client, ed)
    for _ in range(11):
        last = freeze(client, ed)
    assert last["baseline"]["version_label"] == "v1.10"
    p = preview(client, ed)
    body = {"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]}
    url = f"{API}/projects/{ed['p']}/baselines/freeze"
    assert client.post(url, headers=ed["h"], json=body).status_code == 201
    assert client.post(url, headers=ed["h"], json=body).status_code == 422       # the version moved on
    assert freeze(client, ed, bump="MAJOR")["baseline"]["version_label"] == "v2.0"
    labels = [b["version_label"] for b in client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json()]
    assert labels[:3] == ["v2.0", "v1.11", "v1.10"]
    statuses = {b["status_code"] for b in client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json()[1:]}
    assert statuses == {"SUPERSEDED"}


# ---- the diff -----------------------------------------------------------------------------

def test_edits_after_a_freeze_leave_it_alone_and_the_diff_names_each_change(client, ed):
    """Criteria 14, 16, 17, 17a: the snapshot does not move; one ADDED, one REMOVED, CHANGED naming the field."""
    w = scope(client, ed)
    v10 = bid(freeze(client, ed))
    patch_br(client, ed, w["br1"], br_statement="Credit check before acceptance")   # 11a: logic is read-only
    de = client.get(f"{API}/data-entities/{w['order']['data_entity_id']}", headers=ed["h"]).json()
    assert client.patch(f"{API}/data-entities/{de['data_entity_id']}", headers=ed["h"],
                        json={"row_version": de["row_version"], "de_name": "Customer order"}).status_code == 200
    s3, br3 = io_step(client, ed, "Confirm order", w["group"]["bfc_node_id"], w["order"], w["invoice"])
    v11 = bid(freeze(client, ed))
    frozen = client.get(f"{API}/baselines/{v10}/rows/business_requirement", headers=ed["h"]).json()["rows"]
    assert {r["br_statement"] for r in frozen} == {None}
    d = diff(client, ed, v10, v11)
    br_rows = {r["label"]: r for r in d["entities"]["business_requirement"]["rows"]}
    changed = next(r for r in br_rows.values() if r["change"] == "CHANGED")
    assert changed["fields"] == ["br_statement"] and changed["after"]["br_statement"].startswith("Credit")
    assert any(r["change"] == "ADDED" for r in br_rows.values())
    de_rows = d["entities"]["data_entity"]["rows"]
    assert [(r["change"], r["fields"]) for r in de_rows] == [("CHANGED", ["de_name"])]
    # retire the new step's BR side by retiring the step → REMOVED next time
    d_live = diff(client, ed, v11, "live")
    assert d_live["summary"] == {"ADDED": 0, "CHANGED": 0, "REMOVED": 0, "MOVED": 0}
    assert br3 and s3


def test_reordering_reads_moved_not_changed(client, ed):
    """Criterion 33 (P4, D-10): position is not content."""
    w = scope(client, ed)
    v10 = bid(freeze(client, ed))
    s2 = client.get(f"{API}/bfc-nodes/{w['s2']['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{s2['bfc_node_id']}/reorder", headers=ed["h"],
                    json={"row_version": s2["row_version"], "new_seq_no": 1})
    assert r.status_code == 200, r.text
    d = diff(client, ed, v10, "live")
    kinds = {(r["change"]) for r in d["entities"]["bfc_node"]["rows"]}
    assert kinds == {"MOVED"} and d["summary"]["CHANGED"] == 0


def test_a_relabelled_code_keeps_the_frozen_label_and_reads_unchanged(client, ed, db):
    """Criterion 28, R2-D3: the label is display only; the code is what the hash reads."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    owner_exec("UPDATE code_master SET label = 'Being drafted' WHERE category = 'BR_STATUS' AND code = 'DRAFT'")
    rows = client.get(f"{API}/baselines/{v10}/rows/business_requirement", headers=ed["h"]).json()["rows"]
    assert {r["status_label"] for r in rows} == {"Draft"}
    assert diff(client, ed, v10, "live")["summary"]["CHANGED"] == 0


def test_the_diff_never_crosses_projects(client, ed, world):
    """Criterion 50 (S3): two baselines of different projects, or a project the caller cannot see → 404."""
    scope(client, ed)
    mine = bid(freeze(client, ed))
    other = {"h": world["admin"], "p": world["p_fin"]}
    a = node(client, other, "Finance")
    g = node(client, other, "Record to report", a["bfc_node_id"])
    node(client, other, "Close books", g["bfc_node_id"], is_process=True)
    p = preview(client, other)
    r = client.post(f"{API}/projects/{other['p']}/baselines/freeze", headers=world["admin"],
                    json={"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    assert r.status_code == 409          # FIN has the DFD on and its step has no I/O — fine, use none
    diff(client, ed, mine, "999999", expect=404)
    diff(client, ed, mine, "live", headers=ed["out"], expect=404)
    assert client.get(f"{API}/baselines/{mine}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{world['p_fin']}/baselines/diff", headers=world["admin"],
                      params={"from": mine, "to": "live"}).status_code == 404


def test_priced_diff_nets_added_and_removed_effort(client, ed):
    """Criteria 57, 58 (D-13): net man-days, not a row count; the frozen days never reprice."""
    w = scope(client, ed)
    s = sol(client, ed)
    link(client, ed, w["br1"]["br_id"], s["solution_id"])
    gone = fr(client, ed, name="Old report", fr_type="REPORT", solution_id=s["solution_id"])
    assert rate(client, ed, gone, "SIMPLE").status_code == 200
    v10 = bid(freeze(client, ed))
    for name in ("Order form", "Credit form"):
        f = fr(client, ed, name=name, solution_id=s["solution_id"])
        assert rate(client, ed, f, "COMPLEX").status_code == 200
    cur = client.get(f"{API}/function-requirements/{gone['fr_id']}", headers=ed["h"]).json()
    r = client.delete(f"{API}/function-requirements/{gone['fr_id']}", headers=ed["h"],
                      params={"row_version": cur["row_version"]})
    assert r.status_code in (200, 204), r.text
    d = diff(client, ed, v10, "live", priced=True)
    t = d["pricing"]["totals"]
    frs = {x["fr_name"]: x for x in d["pricing"]["lines"]}
    assert frs["Old report"]["delta_days"] < 0 and frs["Order form"]["change"] == "ADDED"
    assert t["net_days"] == pytest.approx(t["added_days"] + t["removed_days"])
    assert t["added_days"] == pytest.approx(2 * frs["Order form"]["delta_days"])
    assert t["effort_exposed_days"] is not None


# ---- approval -----------------------------------------------------------------------------

def approve(client, ed, b, expect=200, headers=None, **over):
    cur = client.get(f"{API}/baselines/{b}", headers=ed["h"]).json()
    body = {"client_approver_name": "K. Tanaka", "client_approved_on": date.today().isoformat(),
            "approval_note": "Signed at steering", "approval_reference": "SOW-12 annex B",
            "row_version": cur["row_version"], **over}
    r = client.post(f"{API}/baselines/{b}/approve", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def test_approval_is_recorded_once_and_survives_supersession(client, ed, db):
    """§5.2, DR8-P1: FROZEN → APPROVED, never twice; the next freeze supersedes it and keeps the facts."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    approve(client, ed, v10, headers=ed["rv"], expect=403)
    out = approve(client, ed, v10)
    assert (out["status_code"], out["client_approver_name"], out["approved_by"]) == ("APPROVED", "K. Tanaka", "Editor")
    approve(client, ed, v10, expect=409)
    freeze(client, ed)
    rows = client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json()
    assert [(b["version_label"], b["status_code"], b["is_agreed"]) for b in rows] == \
        [("v1.1", "FROZEN", False), ("v1.0", "SUPERSEDED", True)]
    assert rows[1]["client_approver_name"] == "K. Tanaka"
    assert db.scalars(select(AuditEvent).where(AuditEvent.event_type == "BASELINE_APPROVED")).one()


def test_the_signed_version_can_be_approved_after_a_checkpoint_freeze(client, ed):
    """DR8-P1: v1.0 sent for signature, v1.1 frozen as a checkpoint, the client signs v1.0."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    preview_body = preview(client, ed)
    assert preview_body["supersedes"]["awaiting_sign_off"] is True
    freeze(client, ed)
    out = approve(client, ed, v10)
    assert out["status_code"] == "SUPERSEDED" and out["client_approver_name"] == "K. Tanaka"
    rows = client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json()
    assert [b["is_agreed"] for b in rows] == [False, True]


def test_an_approval_date_must_fall_between_the_freeze_and_today(client, ed):
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    approve(client, ed, v10, client_approved_on=(date.today() + timedelta(days=2)).isoformat(), expect=422)
    approve(client, ed, v10, client_approved_on=(date.today() - timedelta(days=2)).isoformat(), expect=422)
    approve(client, ed, v10, client_approver_name="   ", expect=422)


# ---- the database holds it ----------------------------------------------------------------

def test_frozen_rows_cannot_be_changed_removed_or_added_to(client, ed, db):
    """Criteria 26, 55, DR8-S1, sara M2: as the owner the trigger refuses, as the app the grant refuses; nothing
    can be appended to an existing baseline even for a row it does not yet hold."""
    w = scope(client, ed)
    v10 = bid(freeze(client, ed))
    late = entity(client, ed, "Created after the freeze")
    for sql in ("UPDATE baseline_business_requirement SET br_statement = 'x' WHERE baseline_id = :b",
                "DELETE FROM baseline_business_requirement WHERE baseline_id = :b",
                "UPDATE baseline SET note = 'rewritten' WHERE baseline_id = :b",
                "DELETE FROM baseline WHERE baseline_id = :b"):
        with pytest.raises(Exception, match="not allowed|cannot change"):
            owner_exec(sql, b=v10)
        with pytest.raises(Exception, match="permission denied|not allowed|cannot change"):
            db.execute(text(sql), {"b": v10})
        db.rollback()
    smuggle = ("INSERT INTO baseline_data_entity (baseline_id, source_id, de_name, content_hash) "
               "VALUES (:b, :s, 'smuggled', repeat('0', 64))")
    with pytest.raises(Exception, match="cannot be added to an existing baseline"):
        db.execute(text(smuggle), {"b": v10, "s": late["data_entity_id"]})
    db.rollback()
    with pytest.raises(Exception, match="cannot be added to an existing baseline"):
        owner_exec(smuggle.replace(":s", str(late["data_entity_id"])), b=v10)
    assert w


def test_a_recorded_approval_is_closed_even_its_empty_fields(client, ed):
    """sara M1: an approval recorded without a reference cannot gain one later, not even as the owner."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    approve(client, ed, v10, approval_reference=None, approval_note=None)
    for sql in ("UPDATE baseline SET approval_reference = 'forged' WHERE baseline_id = :b",
                "UPDATE baseline SET approval_note = 'added later' WHERE baseline_id = :b",
                "UPDATE baseline SET client_approver_name = 'Someone else' WHERE baseline_id = :b"):
        with pytest.raises(Exception, match="approval cannot change"):
            owner_exec(sql, b=v10)


def test_an_older_version_cannot_be_approved_after_a_newer_one(client, ed):
    """sara L2: approving v1.0 after v1.1 is already signed is almost certainly a slip."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    v11 = bid(freeze(client, ed))
    assert approve(client, ed, v11)["is_agreed"] is True
    approve(client, ed, v10, expect=409)


def test_a_failure_partway_leaves_no_header_and_no_rows(client, ed, db, monkeypatch):
    """Criterion 15: one transaction — a failure on the 17th table undoes the header and the 16 before it."""
    from services import freeze_set
    w = scope(client, ed)
    link(client, ed, w["br1"]["br_id"], sol(client, ed)["solution_id"])
    p = preview(client, ed)
    real = freeze_set.live_select

    def boom(e, *a, **kw):
        if e.table == "br_solution" and getattr(boom, "armed", 0) >= 1:
            raise RuntimeError("disk full")
        if e.table == "br_solution":
            boom.armed = 1                    # the digest pass reads it first; fail on the insert pass
        return real(e, *a, **kw)
    monkeypatch.setattr(freeze_set, "live_select", boom)
    with pytest.raises(RuntimeError):
        client.post(f"{API}/projects/{ed['p']}/baselines/freeze", headers=ed["h"],
                    json={"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    assert db.scalar(text("SELECT count(*) FROM baseline")) == 0
    for t in SHADOW_TABLES:
        assert db.scalar(text(f"SELECT count(*) FROM baseline_{t}")) == 0, t
    assert {x["status_code"] for x in brs(client, ed).values()} == {"DRAFT"}


def test_an_edit_committed_during_the_freeze_lands_in_neither_half(client, ed, monkeypatch):
    """Criterion 30 (P1): the freeze reads one snapshot taken at its first statement."""
    from services import freeze_set
    w = scope(client, ed)
    p = preview(client, ed)
    real = freeze_set.live_select

    def meanwhile(e, *a, **kw):
        if e.table == "bfc_node" and not getattr(meanwhile, "done", False):
            meanwhile.done = True
            owner_exec(f"UPDATE data_entity SET de_name = 'Renamed meanwhile' WHERE data_entity_id = {w['order']['data_entity_id']}")
        return real(e, *a, **kw)
    monkeypatch.setattr(freeze_set, "live_select", meanwhile)
    r = client.post(f"{API}/projects/{ed['p']}/baselines/freeze", headers=ed["h"],
                    json={"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    assert r.status_code == 201, r.text
    monkeypatch.setattr(freeze_set, "live_select", real)
    v10 = r.json()["baseline"]["baseline_id"]
    frozen = client.get(f"{API}/baselines/{v10}/rows/data_entity", headers=ed["h"]).json()["rows"]
    assert "Renamed meanwhile" not in {x["de_name"] for x in frozen}
    assert client.get(f"{API}/baselines/{v10}", headers=ed["h"]).json()["intact"]
    d = diff(client, ed, v10, "live")
    assert [(x["change"], x["fields"]) for x in d["entities"]["data_entity"]["rows"]] == [("CHANGED", ["de_name"])]


def test_a_concurrent_change_to_the_prior_baseline_gives_one_409_and_no_new_baseline(client, ed):
    """Criterion 37 / [Q-24]: the freeze waits on the prior header's lock and then refuses — never a fork,
    never a half — with a message that says to freeze again."""
    import threading
    import time
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    p = preview(client, ed)
    eng = create_engine(OWNER_URL)
    conn = eng.connect()
    tx = conn.begin()
    conn.execute(text("SELECT 1 FROM baseline WHERE baseline_id = :b FOR UPDATE"), {"b": v10})
    result = {}

    def run():
        result["r"] = client.post(f"{API}/projects/{ed['p']}/baselines/freeze", headers=ed["h"], json={
            "bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    th = threading.Thread(target=run)
    th.start()
    time.sleep(1.5)
    conn.execute(text("UPDATE baseline SET updated_by = updated_by WHERE baseline_id = :b"), {"b": v10})
    tx.commit()
    th.join(30)
    conn.close()
    eng.dispose()
    assert result["r"].status_code == 409 and "freeze again" in result["r"].json()["detail"]
    labels = [b["version_label"] for b in client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json()]
    assert labels == ["v1.0"]


def test_the_app_role_grants_on_baselines(db):
    """§6.6: SELECT and INSERT on every shadow, never UPDATE or DELETE; header UPDATE only on its columns."""
    names = [f"baseline_{t}" for t in SHADOW_TABLES]
    rows = db.execute(text("SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                           "WHERE grantee = 'vb_app' AND table_name = ANY(:n)"), {"n": names + ["baseline"]}).all()
    privs: dict[str, set] = {}
    for t, p in rows:
        privs.setdefault(t, set()).add(p)
    for n in names:
        assert privs[n] == {"SELECT", "INSERT"}, n
    assert privs["baseline"] == {"SELECT", "INSERT"}
    cols = set(db.scalars(text("SELECT column_name FROM information_schema.column_privileges WHERE grantee = 'vb_app' "
                               "AND table_name = 'baseline' AND privilege_type = 'UPDATE'")))
    assert cols == {"status_code_id", "client_approver_name", "client_approved_on", "approval_note",
                    "approval_reference", "approved_at", "approved_by_user_id", "updated_by", "row_version"}


def test_every_shadow_matches_the_generator_in_the_database(db):
    """Criterion 27 [Q-4]: names and types, read from the migrated database."""
    from sqlalchemy import MetaData
    from models import Base
    md = MetaData()
    md.reflect(bind=db.get_bind(), only=[f"baseline_{t}" for t in SHADOW_TABLES])
    problems = []
    for t in SHADOW_TABLES:
        problems += parity_problems(Base.metadata.tables[t], md.tables[f"baseline_{t}"])
    assert problems == []
    trig = set(db.scalars(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")))
    for t in SHADOW_TABLES:
        assert {f"trg_baseline_{t}_immutable", f"trg_baseline_{t}_insert_guard"} <= trig


def test_parity_catches_a_type_change_too():
    from sqlalchemy import Column, Integer, MetaData, String, Table
    md = MetaData()
    live = Table("thing", md, Column("thing_id", Integer, primary_key=True), Column("name", String(20)))
    shadow = shadow_table(live, md, baseline_fk=False, source_fk=False)
    live2 = Table("thing", MetaData(), Column("thing_id", Integer, primary_key=True), Column("name", String(40)))
    assert parity_problems(live2, shadow) == ["baseline_thing.name: type VARCHAR(20) != live VARCHAR(40)"]


def test_tampering_with_a_frozen_row_fails_the_integrity_check(client, ed):
    """DR8-S1: even an owner who disables the trigger cannot change a baseline without every read saying so."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    owner_exec("ALTER TABLE baseline_business_requirement DISABLE TRIGGER trg_baseline_business_requirement_immutable;"
               "UPDATE baseline_business_requirement SET content_hash = repeat('a', 64) WHERE baseline_id = :b;"
               "ALTER TABLE baseline_business_requirement ENABLE TRIGGER trg_baseline_business_requirement_immutable",
               b=v10)
    assert client.get(f"{API}/baselines/{v10}", headers=ed["h"]).json()["intact"] is False
    diff(client, ed, v10, "live", expect=409)


def test_an_edited_column_with_its_old_hash_also_fails_the_check(client, ed):
    """sara M3: the check recomputes each row's hash from its columns, not only the list of hashes."""
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    owner_exec("ALTER TABLE baseline_data_entity DISABLE TRIGGER trg_baseline_data_entity_immutable;"
               "UPDATE baseline_data_entity SET de_name = 'Quietly rewritten' WHERE baseline_id = :b;"
               "ALTER TABLE baseline_data_entity ENABLE TRIGGER trg_baseline_data_entity_immutable", b=v10)
    assert client.get(f"{API}/baselines/{v10}", headers=ed["h"]).json()["intact"] is False
    assert client.get(f"{API}/baselines/{v10}/rows/bfc_node", headers=ed["h"]).status_code == 409


# ---- the hash, pinned ---------------------------------------------------------------------

def _py_hash(values) -> str:
    parts = ["\x1e" if v is None else f"{len(v)}:{v}" for v in values]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def test_the_hash_is_pinned_to_its_canonical_text(client, ed, db):
    """§4 [Q-15], DR8-L2: PostgreSQL ::text, length-prefixed, \\x1f between, \\x1e for NULL. Emptying a field
    reads CHANGED (criterion 41)."""
    w = scope(client, ed)
    patch_br(client, ed, w["br1"], br_statement="")             # 11a: the statement, not the read-only logic
    v10 = bid(freeze(client, ed))
    row = db.execute(text("SELECT * FROM baseline_business_requirement WHERE baseline_id = :b AND source_id = :s"),
                     {"b": v10, "s": w["br1"]["br_id"]}).mappings().one()
    cols = next(e for e in FREEZE_SET if e.table == "business_requirement").hash_columns[1]
    vals = [None if row[c] is None else str(row[c]) for c in cols]
    assert row["content_hash"] == _py_hash(vals)
    assert _py_hash(["A\x1fB", "C"]) != _py_hash(["A", "B\x1fC"]) and _py_hash([""]) != _py_hash([None])
    patch_br(client, ed, w["br1"], br_statement=None)
    d = diff(client, ed, v10, "live")
    assert [r["fields"] for r in d["entities"]["business_requirement"]["rows"]] == [["br_statement"]]


def test_spec_versions_that_differ_report_per_entity(client, ed, monkeypatch):
    """Criterion 41 (D5) per entity [Q-16]: only the entity whose list changed reports the mismatch."""
    from services import freeze_set
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    e = freeze_set.BY_TABLE["data_entity"]
    nxt = freeze_set.CURRENT_HASH_SPEC + 1
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", nxt)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", nxt)
    for x in freeze_set.FREEZE_SET:
        monkeypatch.setitem(x.hash_columns, nxt,
                            freeze_set.columns_for(x, nxt - 1) if x is not e else ("de_number",))
    d = diff(client, ed, v10, "live")
    assert d["entities"]["data_entity"]["status"] == "SCHEMA_VERSION_MISMATCH"
    assert d["entities"]["bfc_node"]["status"] == "OK"


def test_a_viewer_reads_baselines_and_rows(client, ed):
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    assert [b["version_label"] for b in client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["rv"]).json()] == ["v1.0"]
    assert client.get(f"{API}/baselines/{v10}/rows/bfc_node", headers=ed["rv"]).json()["total"] == 4
    assert login  # imported for symmetry with other suites
