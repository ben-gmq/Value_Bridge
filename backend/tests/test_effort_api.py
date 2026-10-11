"""Rate card and FR effort days (docs/slice6c_spec.md §8). Grade 1: effort days price the vendor scope —
a silent wrong number moves money. The riskiest concern — days that do not come from the card (typed,
stale, or silently repriced) — is proven directly, including at the database.

Deliberately uncovered (spec §8): two editors changing the same cell at the same instant (row_version
decides). A mutation harness for this slice is proposed separately (spec §8)."""
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text

from models import AuditEvent
from seeds.ftc_rate_card import FTC_DEFAULT_RATE_CARD
from services import effort
from tests.conftest import OWNER_URL
from tests.test_function_requirement_api import fr, patch as fr_patch
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def card(client, ed, headers=None):
    return client.get(f"{API}/projects/{ed['p']}/rate-card", headers=headers or ed["rv"]).json()


def cell(c, fr_type, cx):
    return next(x for x in c["cells"] if (x["fr_type_code"], x["complexity_code"]) == (fr_type, cx))


def put_card(client, ed, cells, rationale="Client agreed", headers=None, **kw):
    return client.put(f"{API}/projects/{ed['p']}/rate-card", headers=headers or ed["h"],
                      json={"change_rationale": rationale, "cells": cells, **kw})


def change(client, ed, fr_type, cx, days, **kw):
    c = cell(card(client, ed), fr_type, cx)
    return put_card(client, ed, [{"fr_type_code": fr_type, "complexity_code": cx, "standard_days": str(days),
                                  "row_version": c["row_version"]}], **kw)


def rate(client, ed, f, cx, headers=None):
    cur = client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"]).json()
    return client.patch(f"{API}/function-requirements/{f['fr_id']}/complexity", headers=headers or ed["h"],
                        json={"row_version": cur["row_version"], "complexity_code": cx})


# ---- seeding ------------------------------------------------------------------------------

def test_a_new_project_gets_the_full_default_card(client, ed, db):
    """S6c-1, DR6c-D5: all 16 cells, every one marked as an unconfirmed default."""
    c = card(client, ed)
    seeded = [x for x in c["cells"] if x["standard_days"] is not None]
    assert len(seeded) == 16 == len(FTC_DEFAULT_RATE_CARD)
    assert Decimal(cell(c, "INTERFACE", "COMPLEX")["standard_days"]) == Decimal("12")
    assert all(x["unconfirmed_default"] for x in seeded)
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_CREATED",
                                             AuditEvent.project_id == ed["p"])).one()
    assert (ev.detail["rate_cells_seeded"], ev.detail["rate_cells_unresolved"]) == (16, [])


def test_backfill_fills_gaps_only_is_idempotent_and_needs_a_platform_admin(client, ed, db):
    """A project from before 6c (simulated by removing one cell as the owner — the app role cannot DELETE)."""
    owner = create_engine(OWNER_URL)
    with owner.begin() as c:
        c.execute(text("DELETE FROM effort_rate WHERE project_id = :p AND standard_days = 20"), {"p": ed["p"]})
    owner.dispose()
    assert cell(card(client, ed), "INTERFACE", "VERY_COMPLEX")["standard_days"] is None
    with pytest.raises(SystemExit):
        effort.backfill(db, "editor@example.test")                            # not a platform admin (DR6c-S1)
    first = {r["project_id"]: r["rate_cells_seeded"] for r in effort.backfill(db, "admin@example.test")}
    assert first[ed["p"]] == 1 and sum(first.values()) == 1
    assert Decimal(cell(card(client, ed), "INTERFACE", "VERY_COMPLEX")["standard_days"]) == 20
    again = effort.backfill(db, "admin@example.test")
    assert sum(r["rate_cells_seeded"] for r in again) == 0
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RATE_CARD_SEEDED")).one()
    assert ev.project_id == ed["p"] and ev.detail["os_user"] and ev.detail["host"]


# ---- rating -------------------------------------------------------------------------------

def test_rating_sets_days_from_the_card_and_clearing_clears_both(client, ed):
    """Criterion 56 and apple Q-10."""
    f = fr(client, ed, "Order form", "FORM")
    r = rate(client, ed, f, "COMPLEX")
    assert r.status_code == 200, r.text
    assert (r.json()["complexity_code"], Decimal(r.json()["effort_days"])) == ("COMPLEX", Decimal("8"))
    c = rate(client, ed, f, None).json()
    assert (c["complexity_code"], c["effort_days"]) == (None, None)


def test_effort_days_in_any_body_is_ignored(client, ed):
    f = fr(client, ed, "Order form", "FORM", effort_days=99, complexity_code="COMPLEX")
    assert (f["effort_days"], f["complexity_code"]) == (None, None)
    rated = rate(client, ed, f, "SIMPLE").json()
    r = fr_patch(client, ed, rated, effort_days=500, description="d")
    assert Decimal(r.json()["effort_days"]) == Decimal("2")


def test_a_missing_cell_is_422_naming_it(client, ed, db):
    """Criterion 104: a new type with no card entry saves, and rating it names the cell."""
    db.execute(text("INSERT INTO code_master (project_id, category, code, label, behaviour_code, sort_order, is_system) "
                    "VALUES (:p, 'FR_TYPE', 'WORKFLOW', 'Workflow', 'OTHER', 99, false)"), {"p": ed["p"]})
    db.commit()
    f = fr(client, ed, "Approval flow", "WORKFLOW")
    r = rate(client, ed, f, "MEDIUM")
    assert r.status_code == 422 and "Workflow × Medium" in r.json()["detail"]


def test_the_database_refuses_a_half_written_rating(client, ed, db):
    """D-13: complexity and days together, or neither — even by direct SQL."""
    f = fr(client, ed)
    for sql in ("UPDATE function_requirement SET effort_days = 5 WHERE fr_id = :i",
                "UPDATE function_requirement SET complexity_code_id = (SELECT code_id FROM code_master "
                "WHERE category='FR_COMPLEXITY' AND code='SIMPLE' AND project_id IS NULL) WHERE fr_id = :i"):
        with pytest.raises(Exception, match="ck_fr_effort_with_complexity"):
            db.execute(text(sql), {"i": f["fr_id"]})
            db.commit()
        db.rollback()


def test_rating_checks_the_version_after_the_lock(client, ed):
    """DR6c-D2: a stale request is refused, not priced at whatever the row became."""
    f = fr(client, ed)
    stale = f["row_version"]
    fr_patch(client, ed, f, fr_type_code="REPORT")
    r = client.patch(f"{API}/function-requirements/{f['fr_id']}/complexity", headers=ed["h"],
                     json={"row_version": stale, "complexity_code": "COMPLEX"})
    assert r.status_code == 409


def test_rating_is_audited_with_the_cell(client, ed, db):
    f = fr(client, ed)
    rate(client, ed, f, "MEDIUM")
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "function_requirement")).one()
    assert ev.detail["previous_complexity_code"] is None and ev.detail["effort_rate_id"]


# ---- changing the card --------------------------------------------------------------------

def test_a_rate_change_never_reprices_and_says_how_many_are_off_rate(client, ed, db):
    """A-38, S6c-2, S6c-5, DR6c-P1: the standing per-cell count, on the card, the summary and the audit."""
    f1, f2 = fr(client, ed, "A"), fr(client, ed, "B")
    rate(client, ed, f1, "COMPLEX")
    rate(client, ed, f2, "COMPLEX")
    r = change(client, ed, "FORM", "COMPLEX", 10, rationale="Client complexity")
    assert r.status_code == 200, r.text
    assert r.json()["changes"][0]["not_at_current_rate"] == 2
    assert Decimal(client.get(f"{API}/function-requirements/{f1['fr_id']}", headers=ed["h"]).json()["effort_days"]) == 8
    c = cell(card(client, ed), "FORM", "COMPLEX")
    assert (c["not_at_current_rate"], Decimal(c["not_at_current_rate_days"]), c["unconfirmed_default"]) == (2, 16, False)
    assert Decimal(rate(client, ed, f1, "COMPLEX").json()["effort_days"]) == 10       # explicit re-rate takes today's rate
    assert cell(card(client, ed), "FORM", "COMPLEX")["not_at_current_rate"] == 1
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RATE_CARD_CHANGED")).one()
    line = ev.detail["changes"][0]
    assert (line["from"], line["to"], ev.detail["change_rationale"]) == ("8.00", "10", "Client complexity")


def test_move_rerate_and_move_back_is_still_visible(client, ed):
    """DR6c-P1's scenario: the card reads as seeded, but the FRs priced off it are counted."""
    f = fr(client, ed)
    rate(client, ed, f, "COMPLEX")
    change(client, ed, "FORM", "COMPLEX", 40, rationale="client complexity")
    rate(client, ed, f, "COMPLEX")
    change(client, ed, "FORM", "COMPLEX", 8, rationale="reverted")
    c = cell(card(client, ed), "FORM", "COMPLEX")
    assert (Decimal(c["standard_days"]), c["not_at_current_rate"], Decimal(c["not_at_current_rate_days"])) == (8, 1, 40)
    s = client.get(f"{API}/projects/{ed['p']}/effort-summary", headers=ed["rv"]).json()
    assert (s["not_at_current_rate"]["count"], Decimal(s["not_at_current_rate"]["days"])) == (1, 40)


def test_rationale_required_and_values_checked(client, ed):
    """Criterion 125, DR6c-D3/D4, apple Q-5/Q-6."""
    base = {"fr_type_code": "FORM", "complexity_code": "SIMPLE"}
    rv = cell(card(client, ed), "FORM", "SIMPLE")["row_version"]
    assert put_card(client, ed, [{**base, "standard_days": "3", "row_version": rv}], rationale="  ").status_code == 422
    for bad in ("0", "-1", "3.125", "100000", "NaN", "Infinity"):
        r = put_card(client, ed, [{**base, "standard_days": bad, "row_version": rv}])
        assert r.status_code == 422, (bad, r.text)
    assert put_card(client, ed, [{"fr_type_code": "NOPE", "complexity_code": "SIMPLE", "standard_days": "3",
                                  "row_version": rv}]).status_code == 400
    assert put_card(client, ed, [{**base, "standard_days": "3", "row_version": rv}] * 2).status_code == 422


def test_a_high_rate_needs_confirming_and_is_flagged(client, ed):
    """S6c-7."""
    assert change(client, ed, "BATCH", "VERY_COMPLEX", 75).status_code == 422
    assert change(client, ed, "BATCH", "VERY_COMPLEX", 75, confirm_high=True).status_code == 200
    assert cell(card(client, ed), "BATCH", "VERY_COMPLEX")["high"] is True


def test_a_stale_cell_rolls_back_the_whole_request(client, ed):
    a = cell(card(client, ed), "FORM", "SIMPLE")
    b = cell(card(client, ed), "REPORT", "SIMPLE")
    r = put_card(client, ed, [{"fr_type_code": "FORM", "complexity_code": "SIMPLE", "standard_days": "3",
                               "row_version": a["row_version"]},
                              {"fr_type_code": "REPORT", "complexity_code": "SIMPLE", "standard_days": "3",
                               "row_version": b["row_version"] + 5}])
    assert r.status_code == 409
    assert Decimal(cell(card(client, ed), "FORM", "SIMPLE")["standard_days"]) == 2


def test_unchanged_cells_write_nothing(client, ed, db):
    c = cell(card(client, ed), "FORM", "SIMPLE")
    r = put_card(client, ed, [{"fr_type_code": "FORM", "complexity_code": "SIMPLE", "standard_days": "2.00",
                               "row_version": c["row_version"]}])
    assert r.status_code == 200 and r.json()["changes"] == []
    assert db.scalar(text("SELECT count(*) FROM audit_event WHERE event_type = 'RATE_CARD_CHANGED'")) == 0
    assert cell(card(client, ed), "FORM", "SIMPLE")["row_version"] == c["row_version"]


def test_the_database_refuses_a_silent_rate_change(client, ed, db):
    """DR6c-D1: no write path — ORM or not — moves a rate without a version bump and a reason."""
    with pytest.raises(Exception, match="new row_version and a reason"):
        db.execute(text("UPDATE effort_rate SET standard_days = 50 WHERE project_id = :p"), {"p": ed["p"]})
        db.commit()
    db.rollback()
    with pytest.raises(Exception, match="new row_version and a reason"):
        db.execute(text("UPDATE effort_rate SET standard_days = 50, row_version = row_version + 1 "
                        "WHERE project_id = :p"), {"p": ed["p"]})
        db.commit()
    db.rollback()


def test_editors_change_the_card_and_reviewers_cannot(client, ed):
    """S6c-3, DR6c-P4: the writer role is pinned."""
    assert change(client, ed, "FORM", "MEDIUM", 5).status_code == 200                  # ed["h"] is an EDITOR
    rv = cell(card(client, ed), "FORM", "MEDIUM")["row_version"]
    assert put_card(client, ed, [{"fr_type_code": "FORM", "complexity_code": "MEDIUM", "standard_days": "6",
                                  "row_version": rv}], headers=ed["rv"]).status_code == 403
    assert client.get(f"{API}/projects/{ed['p']}/rate-card", headers=ed["out"]).status_code == 404
    f = fr(client, ed)
    assert rate(client, ed, f, "SIMPLE", headers=ed["rv"]).status_code == 403


# ---- type change --------------------------------------------------------------------------

def test_a_type_change_rederives_and_says_so(client, ed, db):
    """§7.5 change_fr_type, DR6c-P2."""
    f = fr(client, ed)
    rated = rate(client, ed, f, "COMPLEX").json()                                   # FORM × COMPLEX = 8
    r = fr_patch(client, ed, rated, fr_type_code="INTERFACE")                        # INTERFACE × COMPLEX = 12
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["effort_days"]) == 12 and "effort_changed" in r.json()["warnings"]
    assert {k: Decimal(v) for k, v in r.json()["effort_change"].items()} == {"previous_days": 8, "new_days": 12}
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "function_requirement")
                    .order_by(AuditEvent.audit_event_id.desc())).first()
    assert ev.detail["previous_effort_days"] == "8.00"


def test_a_type_change_with_no_cell_is_refused_whole(client, ed, db):
    db.execute(text("INSERT INTO code_master (project_id, category, code, label, behaviour_code, sort_order, is_system) "
                    "VALUES (:p, 'FR_TYPE', 'WORKFLOW', 'Workflow', 'OTHER', 99, false)"), {"p": ed["p"]})
    db.commit()
    rated = rate(client, ed, fr(client, ed), "COMPLEX").json()
    r = fr_patch(client, ed, rated, fr_type_code="WORKFLOW", description="changed too")
    assert r.status_code == 422 and "Workflow × Complex" in r.json()["detail"]
    after = client.get(f"{API}/function-requirements/{rated['fr_id']}", headers=ed["h"]).json()
    assert (after["fr_type_code"], after["description"]) == ("FORM", None)


# ---- the summary --------------------------------------------------------------------------

def test_summary_totals_unassigned_unrated_rejected_and_unconfirmed(client, ed):
    """S6c-4, S6c-8, DR6c-P3."""
    portal = sol(client, ed, "Portal", "TECHNOLOGY")
    dead = sol(client, ed, "Dropped idea", "TECHNOLOGY")
    client.patch(f"{API}/solutions/{dead['solution_id']}", headers=ed["h"],
                 json={"row_version": dead["row_version"], "status_code": "REJECTED"})
    rate(client, ed, fr(client, ed, "A", "FORM", portal["solution_id"]), "COMPLEX")      # 8
    rate(client, ed, fr(client, ed, "B", "INTERFACE", portal["solution_id"]), "SIMPLE")  # 3
    rate(client, ed, fr(client, ed, "C", "REPORT"), "MEDIUM")                            # 4, unassigned
    rate(client, ed, fr(client, ed, "D", "FORM", dead["solution_id"]), "SIMPLE")         # 2, rejected
    fr(client, ed, "E", "BATCH")                                                         # unrated
    s = client.get(f"{API}/projects/{ed['p']}/effort-summary", headers=ed["rv"]).json()
    assert (Decimal(s["total_days"]), s["rated_count"], s["unrated_count"]) == (15, 3, 1)
    assert (s["rejected"]["count"], Decimal(s["rejected"]["days"])) == (1, 2)
    assert {t["fr_type_code"]: Decimal(t["days"]) for t in s["by_type"]} == {"FORM": 8, "INTERFACE": 3, "REPORT": 4}
    by_sol = {x["solution_number"]: Decimal(x["days"]) for x in s["by_solution"]}
    assert by_sol == {"SOL-0001": 11, None: 4}
    assert s["on_unconfirmed_default"] == 3
