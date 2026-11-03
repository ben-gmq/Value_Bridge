"""Slice Decisions — the decision log through the API and at the database (docs/slice_decisions_spec.md §9; design
criterion 78, A-41). Riskiest concern Grade 1: a decision that can be changed or deleted loses the reasoning for good,
so immutability is proven at the database for both roles, not only through the routes. The rest is Grade 2.

Deliberately uncovered: more than 1,000 decisions per project (no paging); the ICT/UTC midnight edge beyond the +1 day
the CHECK allows (the service refuses tomorrow in ICT)."""
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from models import AuditEvent
from services.baseline import local_today
from tests.test_migration_0053 import owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def dec(client, ed, title="Use the vendor's standard pricing engine", expect=201, headers=None, project=None, **kw):
    body = {"title": title, "decision_text": "Adopt the standard engine for wave 1.",
            "alternative_rejected": "Custom pricing build (+40 days)", "dimension_code": "SCOPE", **kw}
    r = client.post(f"{API}/projects/{project or ed['p']}/decisions", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def log(client, ed, **params):
    r = client.get(f"{API}/projects/{ed['p']}/decisions", headers=ed["h"], params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---- 1. numbers and derived values ------------------------------------------------------------------------------------
def test_numbers_are_minted_and_derived_values_never_come_from_the_body(client, ed, db):
    a = dec(client, ed, created_by=1, decided_by_user_id=1, decision_number="DEC-9999", created_at="2001-01-01T00:00:00Z")
    b = dec(client, ed, "Second")
    assert (a["decision_number"], b["decision_number"]) == ("DEC-0001", "DEC-0002")
    assert a["decided_on"] == local_today().isoformat() and a["created_at"][:4] != "2001"
    me = db.execute(text("SELECT created_by, decided_by_user_id FROM decision WHERE decision_id = :d"),
                    {"d": a["decision_id"]}).one()
    assert me[0] == me[1] == a["decided_by_user_id"] != 1 and a["decided_by_name"]
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "DECISION_RECORDED")
                    .order_by(AuditEvent.audit_event_id)).all()
    assert len(ev) == 2 and ev[0].detail["decision_number"] == "DEC-0001" and ev[0].detail["dimension"] == "SCOPE"
    assert "Adopt" not in str(ev[0].detail)                                     # numbers and codes only (R7)


# ---- 2. criterion 78: immutable at the database -----------------------------------------------------------------------
def test_the_app_role_cannot_update_delete_or_truncate_a_decision(client, ed, db):
    d = dec(client, ed)
    for sql in ("UPDATE decision SET title = 'x' WHERE decision_id = :d", "DELETE FROM decision WHERE decision_id = :d",
                "TRUNCATE decision"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            db.execute(text(sql), {"d": d["decision_id"]})
        db.rollback()
    assert dec(client, ed, "after")["decision_number"] == "DEC-0002"


def test_even_the_owner_cannot_update_or_delete_a_decision(client, ed, owner):
    d = dec(client, ed)
    for sql in ("UPDATE decision SET title = 'rewritten' WHERE decision_id = :d",
                "DELETE FROM decision WHERE decision_id = :d"):
        with pytest.raises(DBAPIError, match="a decision is never changed"):
            x(owner, sql, d=d["decision_id"])
    assert q(owner, "SELECT title FROM decision WHERE decision_id = :d", d=d["decision_id"])[0][0] == d["title"]


def test_created_at_is_the_databases_clock_and_a_future_date_is_refused_by_the_check(client, ed, db, owner):
    d = dec(client, ed)
    x(owner, "INSERT INTO decision (project_id, decision_number, title, decision_text, alternative_rejected, "
             "dimension_code_id, decided_on, decided_by_user_id, created_by, created_at) "
             "SELECT project_id, 'DEC-0900', 't', 't', 't', dimension_code_id, decided_on, created_by, created_by, "
             "'2001-01-01' FROM decision WHERE decision_id = :d", d=d["decision_id"])
    assert q(owner, "SELECT created_at > now() - interval '1 hour' FROM decision WHERE decision_number = 'DEC-0900'")[0][0]
    with pytest.raises(DBAPIError, match="ck_decision_not_future"):
        x(owner, "INSERT INTO decision (project_id, decision_number, title, decision_text, alternative_rejected, "
                 "dimension_code_id, decided_on, decided_by_user_id, created_by) "
                 "SELECT project_id, 'DEC-0901', 't', 't', 't', dimension_code_id, current_date + 5, created_by, "
                 "created_by FROM decision WHERE decision_id = :d", d=d["decision_id"])


# ---- 3–5. corrections (DC-2) ------------------------------------------------------------------------------------------
def test_a_correction_is_a_new_row_and_both_stay_readable(client, ed):
    a = dec(client, ed)
    b = dec(client, ed, "Use the vendor engine, wave 2", supersedes_decision_id=a["decision_id"])
    assert b["supersedes_number"] == "DEC-0001" and b["superseded_by_number"] is None
    old = client.get(f"{API}/decisions/{a['decision_id']}", headers=ed["h"]).json()
    assert (old["title"], old["superseded_by_number"], old["superseded_by_id"]) == (a["title"], "DEC-0002",
                                                                                   b["decision_id"])
    assert [r["decision_number"] for r in log(client, ed)] == ["DEC-0002", "DEC-0001"]
    assert [r["decision_number"] for r in log(client, ed, include_superseded=False)] == ["DEC-0002"]


def test_only_the_latest_in_a_chain_can_be_corrected(client, ed):
    a = dec(client, ed)
    dec(client, ed, "b", supersedes_decision_id=a["decision_id"])
    r = dec(client, ed, "c", supersedes_decision_id=a["decision_id"], expect=409)
    assert "DEC-0001 was already corrected by DEC-0002" in r["detail"]
    assert len(log(client, ed)) == 2


def test_a_racing_second_correction_loses_on_the_index_with_the_same_409(client, ed, monkeypatch):
    from services import decision as svc
    a = dec(client, ed)
    first = dec(client, ed, "b", supersedes_decision_id=a["decision_id"])
    real = svc._target
    calls = []

    def blind(db, project_id, decision_id):                     # the read that ran before the other insert committed
        calls.append(decision_id)
        from models import Decision
        return db.get(Decision, decision_id)
    monkeypatch.setattr(svc, "_target", blind)
    r = dec(client, ed, "c", supersedes_decision_id=a["decision_id"], expect=409)
    assert calls and f"corrected by {first['decision_number']}" in r["detail"]
    monkeypatch.setattr(svc, "_target", real)
    assert dec(client, ed, "d")["decision_number"] == "DEC-0003"           # the loser's number went with its rollback


def test_a_correction_of_another_projects_decision_is_a_404(client, ed, world):
    other = dec(client, ed, project=world["p_sales"], headers=world["admin"])
    dec(client, ed, "x", supersedes_decision_id=other["decision_id"], expect=404)
    dec(client, ed, "x", supersedes_decision_id=999999, expect=404)


# ---- 6, 7. validation -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["title", "decision_text", "alternative_rejected"])
def test_blank_text_is_refused(client, ed, field):
    dec(client, ed, **{field: "   "}, expect=422)


def test_the_date_is_the_meeting_date_and_never_in_the_future(client, ed):
    past = (local_today() - timedelta(days=3)).isoformat()
    assert dec(client, ed, decided_on=past)["decided_on"] == past
    dec(client, ed, decided_on=(local_today() + timedelta(days=1)).isoformat(), expect=422)


def test_dimension_and_analysis_are_checked(client, ed, world):
    dec(client, ed, dimension_code="HIGH", expect=400)                  # not a PM_DIMENSION code
    dec(client, ed, dimension_code="", expect=422)
    assert dec(client, ed, analysis_code="priced_diff")["analysis_code"] == "priced_diff"
    dec(client, ed, analysis_code="not_a_rule", expect=422)
    rules = client.get(f"{API}/projects/{ed['p']}/control-rules", headers=ed["h"]).json()
    assert rules and all(r["analysis_code"] != "value_ranking" for r in rules)   # registry code, no rule (CC-5)
    dec(client, ed, analysis_code="value_ranking", expect=422)


def test_pm_dimension_is_company_only(client, ed, world):
    from services import code_lists
    assert "PM_DIMENSION" in code_lists.COMPANY_ONLY
    assert ("decision", "dimension_code_id") in code_lists.EXCLUDED


# ---- 8. access --------------------------------------------------------------------------------------------------------
def test_readers_and_outsiders(client, ed):
    d = dec(client, ed)
    dec(client, ed, headers=ed["rv"], expect=403)
    assert client.get(f"{API}/projects/{ed['p']}/decisions", headers=ed["rv"]).status_code == 200
    assert client.get(f"{API}/decisions/{d['decision_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/decisions", headers=ed["out"]).status_code == 404
    dec(client, ed, headers=ed["out"], expect=404)


def test_no_route_changes_a_decision(client, ed):
    d = dec(client, ed)
    for method in ("patch", "put", "delete"):
        r = getattr(client, method)(f"{API}/decisions/{d['decision_id']}", headers=ed["h"])
        assert r.status_code in (404, 405), (method, r.status_code)


# ---- 9. the log -------------------------------------------------------------------------------------------------------
def test_log_is_newest_first_and_filters_by_dimension(client, ed):
    today = local_today()
    dec(client, ed, "old", decided_on=(today - timedelta(days=10)).isoformat())
    dec(client, ed, "cost", dimension_code="COST")
    dec(client, ed, "mid", decided_on=(today - timedelta(days=2)).isoformat())
    assert [r["title"] for r in log(client, ed)] == ["cost", "mid", "old"]
    assert [r["title"] for r in log(client, ed, dimension="COST")] == ["cost"]
