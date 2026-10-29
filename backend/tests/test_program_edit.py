"""Program edit (docs/slice1f_spec.md §3.7, function 134; §4.7 update_program). Grade 2: a wrong header misnames a
program on every screen and roll-up, and is corrected by editing it again; a client change under live projects would
break the "a program's projects belong to its client" rule, which the database also refuses. Proven: the audit
carries before → after for changed fields only, an edit changing nothing writes nothing, a stale row_version and a
retired program are 409, a client change is refused while any project (retired included) is in the program and
allowed when none is, an inactive client is 422, a taken code or live name is 409, and only a platform admin may edit.

Deliberately uncovered: two admins racing the same edit on two connections (the row lock and row_version carry it)."""
from sqlalchemy import select, text

from models import AuditEvent
from tests.conftest import login
from tests.test_program_members import padd

API = "/api/v1"


def edit(client, h, program_id, expect=200, **body):
    r = client.patch(f"{API}/programs/{program_id}", headers=h, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def program(client, w, pid=None):
    return client.get(f"{API}/programs/{pid or w['program_id']}", headers=w["admin"]).json()


def updates(db, program_id):
    db.expire_all()
    return db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROGRAM_UPDATED",
                                               AuditEvent.target_id == program_id)).all()


def empty_program(client, w, code="EMPTY1", name="Empty program"):
    r = client.post(f"{API}/programs", headers=w["admin"],
                    json={"client_id": w["client_id"], "program_code": code, "program_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_an_edit_audits_changed_fields_only_and_no_change_writes_nothing(client, world, db):
    w = world
    p = program(client, w)
    out = edit(client, w["admin"], p["program_id"], row_version=p["row_version"], program_code=" csr28 ",
               program_name="Core renewal", description="Phase two")
    assert out["program_code"] == "CSR28" and out["description"] == "Phase two"
    assert out["row_version"] == p["row_version"] + 1
    [row] = updates(db, p["program_id"])
    assert row.detail == {"program_code": ["CSR27", "CSR28"], "description": [None, "Phase two"]}  # name unchanged
    same = edit(client, w["admin"], p["program_id"], row_version=out["row_version"], program_code="CSR28",
                program_name="Core renewal")
    assert same["row_version"] == out["row_version"] and len(updates(db, p["program_id"])) == 1
    cleared = edit(client, w["admin"], p["program_id"], row_version=out["row_version"], description=None)
    assert cleared["description"] is None


def test_stale_retired_blank_and_taken_are_refused(client, world, db):
    w = world
    p = program(client, w)
    edit(client, w["admin"], p["program_id"], expect=409, row_version=p["row_version"] - 1, program_name="X")
    edit(client, w["admin"], p["program_id"], expect=422, row_version=p["row_version"], program_name="   ")
    edit(client, w["admin"], p["program_id"], expect=422, row_version=p["row_version"], program_code=None)
    other = empty_program(client, w)
    edit(client, w["admin"], other["program_id"], expect=409, row_version=other["row_version"], program_code="csr27")
    edit(client, w["admin"], other["program_id"], expect=409, row_version=other["row_version"],
         program_name="CORE RENEWAL")                                                    # live names, any case
    db.execute(text("UPDATE program SET is_active = false WHERE program_id = :p"), {"p": other["program_id"]})
    db.commit()
    gone = program(client, w, other["program_id"])
    edit(client, w["admin"], other["program_id"], expect=409, row_version=gone["row_version"], program_name="Back")
    assert updates(db, p["program_id"]) == [] and updates(db, other["program_id"]) == []


def test_client_change_refused_while_any_project_is_in_the_program(client, world, db):
    """Round 1 D7: a retired project still binds the client; the 409 names every project, retired ones included."""
    w = world
    p = program(client, w)
    r = edit(client, w["admin"], p["program_id"], expect=409, row_version=p["row_version"],
             client_id=w["other_client_id"])
    assert "FIN" in r["detail"] and "SALES" in r["detail"]
    db.execute(text("UPDATE project SET is_active = false WHERE project_id = :p"), {"p": w["p_fin"]})
    db.commit()
    r = edit(client, w["admin"], p["program_id"], expect=409, row_version=p["row_version"],
             client_id=w["other_client_id"])
    assert "FIN" in r["detail"]
    empty = empty_program(client, w)
    moved = edit(client, w["admin"], empty["program_id"], row_version=empty["row_version"],
                 client_id=w["other_client_id"])
    assert moved["client_id"] == w["other_client_id"]
    [row] = updates(db, empty["program_id"])
    assert row.detail == {"client_id": [w["client_id"], w["other_client_id"]]}


def test_an_inactive_client_is_422_and_only_a_platform_admin_may_edit(client, world, db):
    w = world
    empty = empty_program(client, w)
    db.execute(text("UPDATE client SET is_active = false WHERE client_id = :c"), {"c": w["other_client_id"]})
    db.commit()
    edit(client, w["admin"], empty["program_id"], expect=422, row_version=empty["row_version"],
         client_id=w["other_client_id"])
    edit(client, w["admin"], empty["program_id"], expect=422, row_version=empty["row_version"], client_id=999999)
    padd(client, w["admin"], empty["program_id"], w["users"]["owner"], "ADMIN")    # sara L4: a program admin too
    for who in ("owner", "reviewer", "outsider"):
        r = client.patch(f"{API}/programs/{empty['program_id']}", headers=login(client, f"{who}@example.test"),
                         json={"row_version": empty["row_version"], "program_name": "Mine"})
        assert r.status_code == 403, (who, r.status_code)
    assert updates(db, empty["program_id"]) == []
