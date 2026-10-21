"""Slice 16: removal requests through the API (spec §9, §10 criteria 5, 13, 24, 28, 30; §17 R2, R3, R17; Q-73).
Grade 1 for the pending-purge refusal — while a request is open every write to the project is refused, so the file
and the purge see a project that no longer changes; the sweep calls every write route against a real row of the
pending project rather than trusting a hand list."""
import re
from datetime import date

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select

import models
from routers.guards import GUARD_KEY
from tests.conftest import OWNER_URL, login
from tests.test_access import _seed_restricted
from tests.test_project_purge_record import promote, run

API = "/api/v1"


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def two(client, world, owner):
    """The setup admin requests; the owner user, made a platform admin 31 days ago, approves."""
    promote(owner, world["users"]["owner"])
    return {**world, "a2": login(client, "owner@example.test")}


def ask(client, h, pid, kind="DELETE", reason="Contract clause 9.2, signed 2026-10-01", confirm="ACME/SOLO"):
    return client.post(f"{API}/projects/{pid}/purge-requests", headers=h,
                       json={"kind": kind, "reason": reason, "confirm_text": confirm})


def a_write(client, h, pid):
    return client.post(f"{API}/projects/{pid}/data-entities", headers=h, json={"de_name": "Invoice"})


def test_who_may_request_and_what_the_request_must_say(client, two):
    """Criterion 5: non-admin 403; no reason 422; wrong typed codes 422; a second request 409."""
    pid = two["p_solo"]
    assert ask(client, login(client, "editor@example.test"), pid).status_code == 403
    assert ask(client, two["admin"], pid, reason="  ").status_code == 422
    assert ask(client, two["admin"], pid, confirm="BETA/SOLO").status_code == 422           # R3: the client too
    r = ask(client, two["admin"], pid)
    assert r.status_code == 201 and r.json()["state"] == "OPEN" and r.json()["client_code"] == "ACME"
    again = ask(client, two["a2"], pid)
    assert again.status_code == 409 and again.headers["X-VB-Error"] == "PURGE_PENDING"


def test_an_open_request_freezes_the_project_and_cancelling_frees_it(client, two):
    """Criteria 5 and 13: writes 409 PURGE_PENDING while open, reads still work; cancel restores writes."""
    pid = two["p_solo"]
    r = ask(client, two["admin"], pid).json()
    blocked = a_write(client, two["admin"], pid)
    assert blocked.status_code == 409 and blocked.headers["X-VB-Error"] == "PURGE_PENDING"
    assert client.get(f"{API}/projects/{pid}", headers=two["admin"]).status_code == 200
    assert a_write(client, two["admin"], two["p_fin"]).status_code == 201                  # another project: free
    c = client.post(f"{API}/purge-requests/{r['project_purge_id']}/cancel", headers=two["a2"],
                    json={"row_version": r["row_version"]})
    assert c.status_code == 200 and c.json()["state"] == "CANCELLED"
    assert a_write(client, two["admin"], pid).status_code == 201


def test_platform_writes_that_reach_the_project_are_refused_too(client, two):
    """R17 (sara H1, M2): the writes the project guard does not see — moving the project between programs, and a new
    company FR type, which adds rate cells to every project — wait while a request is open."""
    pid, prog = two["p_sales"], two["program_id"]
    assert ask(client, two["admin"], pid, confirm="ACME/SALES").status_code == 201
    out = client.delete(f"{API}/programs/{prog}/projects/{pid}", headers=two["admin"])
    into = client.post(f"{API}/programs/{prog}/projects", headers=two["admin"], json={"project_id": pid})
    fr = client.post(f"{API}/code-lists/FR_TYPE", headers=two["admin"],
                     json={"code": "WORKFLOW", "label": "Workflow", "behaviour_code": "OTHER"})
    for r in (out, into, fr):
        assert r.status_code == 409 and r.headers["X-VB-Error"] == "PURGE_PENDING", r.text
    assert "SALES" in fr.json()["detail"]
    assert client.post(f"{API}/code-lists/SOLUTION_STATUS", headers=two["admin"],
                       json={"code": "PAUSED", "label": "Paused"}).status_code == 201     # writes to no project


def test_an_archive_deletion_is_requested_only_from_its_archive(client, two):
    """AR-9: the project-scoped route refuses DELETE_ARCHIVE; the archive route needs an executed ARCHIVE."""
    r = ask(client, two["admin"], two["p_solo"], kind="DELETE_ARCHIVE")
    assert r.status_code == 422 and "from its executed ARCHIVE" in r.json()["detail"]
    open_ = ask(client, two["admin"], two["p_solo"]).json()
    assert client.post(f"{API}/purge-requests/{open_['project_purge_id']}/delete-archive", headers=two["admin"],
                       json={"reason": "Clause 4", "confirm_text": "ACME/SOLO"}).status_code == 404


def _fill(path: str, pid: int, oid: int) -> str:
    out = path.replace("{project_id}", str(pid))
    return re.sub(r"\{(\w+)\}", lambda m: str(oid) if m.group(1).endswith("id") else "X", out)


def test_every_write_route_refuses_a_project_with_an_open_request(client, two, db):
    """Criterion 13 (R17): every non-GET route that reaches a project — by its id or by one of its rows — answers
    409 PURGE_PENDING, called on a real row of the pending project. Positive control: the sweep must reach every
    project write route and dozens of row routes, so it cannot pass by calling nothing."""
    from main import app
    pid, _marks, _ids = _seed_restricted(client, two)
    assert ask(client, two["admin"], pid, confirm="ACME/ZQXCODE").status_code == 201
    project_routes = row_routes = 0
    bad = []
    for r in app.routes:
        if not isinstance(r, APIRoute) or r.methods <= {"GET", "HEAD"}:
            continue
        g = r.openapi_extra[GUARD_KEY]
        if g["kind"] == "PROJECT_CTX":
            oid, project_routes = 1, project_routes + 1
        elif g["kind"] == "OBJECT_GUARD":
            model = getattr(models, g["model"])
            row = next((o for o in db.scalars(select(model)) if o.owning_project_id() == pid), None)
            if row is None:
                continue                                      # nothing of this kind in the project
            oid, row_routes = row.__mapper__.primary_key_from_instance(row)[0], row_routes + 1
        else:
            continue
        for m in r.methods - {"HEAD"}:
            resp = client.request(m, _fill(r.path, pid, oid), headers=two["admin"], json={})
            if resp.status_code != 409 or resp.headers.get("X-VB-Error") != "PURGE_PENDING":
                bad.append((m, r.path, resp.status_code))
    assert bad == []
    # a floor, not a target: 32 and 93 were measured on 2026-10-21; it stops a sweep that silently calls nothing
    assert project_routes >= 30 and row_routes >= 80, (project_routes, row_routes)


def test_approval_needs_the_typed_codes_a_second_independent_admin_and_shows_the_wait(client, two, owner):
    """R2, R3, criterion 28 (AR-13 through the API): self-approval and an approver granted by the requester are
    refused with plain messages; a proper approval starts the 24 hours."""
    r = ask(client, two["admin"], two["p_solo"]).json()
    pp, url = r["project_purge_id"], f"{API}/purge-requests/{r['project_purge_id']}/approve"
    body = {"confirm_text": "ACME/SOLO", "row_version": r["row_version"]}
    assert client.post(url, headers=two["admin"], json=body).json()["detail"].startswith("four eyes")
    assert client.post(url, headers=two["a2"], json={**body, "confirm_text": "ACME/SOLX"}).status_code == 422
    run(owner, "UPDATE app_user SET is_platform_admin = false WHERE app_user_id = :u", u=two["users"]["editor"])
    promote(owner, two["users"]["editor"], by=None, days=5)                                # too recent
    young = client.post(url, headers=login(client, "editor@example.test"), json=body)
    assert young.status_code == 409 and "AR-13" in young.json()["detail"]
    ok = client.post(url, headers=two["a2"], json=body)
    assert ok.status_code == 200 and ok.json()["state"] == "APPROVED" and ok.json()["waiting"]
    rows = client.get(f"{API}/purge-requests", headers=two["admin"]).json()
    assert [x["project_purge_id"] for x in rows] == [pp] and rows[0]["approved_by"] == "Owner"
    assert client.get(f"{API}/purge-requests", headers=login(client, "editor@example.test")).status_code == 200
    assert client.get(f"{API}/purge-requests", headers=login(client, "reviewer@example.test")).status_code == 403


def test_with_one_platform_admin_every_request_refuses_and_the_overview_warns(client, world):
    """Criterion 24 (AR-5)."""
    r = ask(client, world["admin"], world["p_solo"])
    assert r.status_code == 409 and "two live platform admins" in r.json()["detail"]
    assert client.get(f"{API}/admin/archive-overview", headers=world["admin"]).json()["live_platform_admins"] == 1


def test_an_archive_is_requested_only_when_due(client, two, owner):
    """Criterion 30 (AR-11) and the due list (criterion 20, AR-1): closed under two years ago → 409 naming the due
    date; closed over two years ago → listed as due, and the request is accepted."""
    pid = two["p_solo"]
    closed = "SELECT code_id FROM code_master WHERE category = 'PROJECT_STATUS' AND code = 'CLOSED' AND project_id IS NULL"
    for days, ok in ((300, False), (800, True)):
        run(owner, f"UPDATE project SET status_code_id = ({closed}), status_behaviour = 'CLOSED', "
                   f"closed_on = current_date - {days} WHERE project_id = :p", p=pid)
        due = [d["project_id"] for d in
               client.get(f"{API}/admin/archive-overview", headers=two["admin"]).json()["due_for_archiving"]]
        r = ask(client, two["admin"], pid, kind="ARCHIVE")
        if ok:
            assert r.status_code == 201 and pid in due
            listed = client.get(f"{API}/admin/archive-overview", headers=two["admin"]).json()["due_for_archiving"]
            assert pid not in [d["project_id"] for d in listed]               # requested: no longer offered (L8)
        else:
            assert r.status_code == 409 and "not due" in r.json()["detail"] and pid not in due
    assert ask(client, two["admin"], two["p_fin"], kind="ARCHIVE", confirm="ACME/FIN").json()["detail"] == \
        "This project is not due for archiving yet: it is not closed"


def test_a_baseline_shows_its_archive_files_to_its_readers_only(client, two):
    """Spec §9: status, size, written time — never the file; 404 to someone who cannot see the project."""
    from tests.test_baseline import bid, freeze, scope
    ed = {"p": two["p_solo"], "h": two["admin"]}
    scope(client, ed)
    b = bid(freeze(client, ed))
    got = client.get(f"{API}/baselines/{b}/archive", headers=two["admin"]).json()
    assert got == [{"archive_part": "SCOPE", "file_seq": 1, "status": "OWED", "written_at": None, "byte_size": None,
                    "last_error": None}]
    from tests.conftest import restrict
    restrict(client, two["admin"], two["p_solo"])
    assert client.get(f"{API}/baselines/{b}/archive", headers=login(client, "outsider@example.test")).status_code == 404


def test_due_on_handles_a_leap_day():
    from services.purge import due_on
    assert due_on(date(2024, 2, 29)) == date(2026, 3, 1) and due_on(date(2024, 3, 1)) == date(2026, 3, 1)
    assert due_on(None) is None and due_on(date(2026, 1, 1)) == date(2028, 1, 1)
