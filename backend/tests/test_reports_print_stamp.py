"""Print to PDF, the stamp (docs/slice1f_spec.md §3.6, function 143; D-42). Grade 2: the stamp is what a printed client
report carries and the REPORT_PRINTED row is the only record that it went out; a missing row or a wrong stamp is
noticed when someone checks the audit trail. Proven: one press writes one row with what was printed, every refusal
the boundary owns (S2, N2, N4) writes nothing, and an outsider gets 404. The Excel stamp and the print stamp share
one time format (VB-005 L2).

Deliberately uncovered (spec §5): the print layout and its pagination (browser pass only); whether a PDF was saved
(A3, unknowable)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from models import AuditEvent
from services.reports import stamp_time
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def stamp(client, ed, headers=None, expect=200, **q):
    q.setdefault("report", "traceability")
    q.setdefault("generated_at", datetime.now(UTC).isoformat())
    r = client.get(f"{API}/projects/{ed['p']}/print-stamp", headers=headers or ed["rv"], params=q)
    assert r.status_code == expect, r.text
    return r.json()


def printed(db, project_id):
    db.expire_all()
    return db.scalars(select(AuditEvent).where(AuditEvent.event_type == "REPORT_PRINTED",
                                               AuditEvent.project_id == project_id)).all()


def test_one_press_writes_one_row_and_returns_the_stamp(client, ed, db):
    """A viewer may print (§11: PDF export at VIEW). The stamp carries the report's own time, not the press's (P3)."""
    at = datetime.now(UTC) - timedelta(minutes=5)
    s = stamp(client, ed, report="interfaces", filters="source SAP-ECC, target any", generated_at=at.isoformat())
    assert s["report"] == "interfaces" and s["is_live"] is True and s["generated_by"]
    assert s["project_code"] and s["project_name"] and s["filters"] == "source SAP-ECC, target any"
    assert datetime.fromisoformat(s["generated_at"]) == at and s["generated_at_text"] == stamp_time(at)
    assert s["generated_at_text"].endswith(" ICT")
    [row] = printed(db, ed["p"])
    assert row.target_table == "project" and row.target_id == ed["p"] and row.app_user_id is not None
    assert row.detail == {"report": "interfaces", "filters": "source SAP-ECC, target any",
                          "generated_at": at.isoformat()}


def test_every_refusal_writes_nothing(client, ed, db):
    now = datetime.now(UTC)
    for q in ({"report": "bfc"}, {"report": "erd"},                                      # not in PRINTABLE
              {"filters": "a\x00b"}, {"filters": "tab\there"}, {"filters": "x" * 201},  # S2
              {"generated_at": "yesterday"},
              {"generated_at": now.replace(tzinfo=None).isoformat()},               # N2: no zone
              {"generated_at": (now - timedelta(minutes=31)).isoformat()},          # N2: older than the window
              {"generated_at": (now + timedelta(minutes=2)).isoformat()}):          # N2: from the future
        stamp(client, ed, expect=422, **q)
    stamp(client, ed, expect=422, generated_at=None)                                # required
    assert printed(db, ed["p"]) == []
    stamp(client, ed, filters="x" * 200)                                            # the cap itself is allowed
    assert len(printed(db, ed["p"])) == 1


def test_an_outsider_gets_404_and_no_row(client, ed, db):
    stamp(client, ed, headers=ed["out"], expect=404)
    assert printed(db, ed["p"]) == []


def test_the_excel_stamp_uses_the_same_time_text():
    """VB-005 L2: one helper, so the Excel and the PDF never state the time two ways."""
    at = datetime(2026, 10, 29, 3, 4, tzinfo=UTC)
    assert stamp_time(at) == "2026-10-29 10:04 ICT"
