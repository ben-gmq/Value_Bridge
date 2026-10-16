"""Wave 1g — code-list maintenance (docs/slice1g_spec.md, G-1…G-5, D-71). Grade 2: a wrong rename or re-point
mislabels figures in exports and the next baseline; recoverable by retiring the override, noticed by whoever reads the
list. Proven directly through the API, with the re-point checked in the database on the rows themselves.

Left uncovered on purpose (build plan): a true concurrent save during a re-point (criterion 19) — the lock order
(guard FOR SHARE, re-point FOR UPDATE) carries it; no two-connection race test."""
import re
from pathlib import Path

from sqlalchemy import text

from seeds.ftc_rate_card import FTC_DEFAULT_RATE_CARD
from services import code_lists
from tests.conftest import login, restrict
from tests.test_baseline import bid, diff, freeze, scope
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr

API = "/api/v1"
ROOT = Path(__file__).resolve().parents[2]
import pytest  # noqa: E402


@pytest.fixture
def cl(client, world):
    """SOLO restricted: the editor is its project admin, the reviewer a reader, the owner an editor (EDIT)."""
    w = world
    restrict(client, w["admin"], w["p_solo"], {w["users"]["editor"]: "ADMIN", w["users"]["reviewer"]: "VIEW",
                                               w["users"]["owner"]: "EDIT"})
    return {**w, "p": w["p_solo"], "pa": login(client, "editor@example.test"), "h": login(client, "owner@example.test"),
            "rv": login(client, "reviewer@example.test"), "out": login(client, "outsider@example.test")}


def lists(client, cl, project=None, headers=None):
    r = client.get(f"{API}/projects/{project or cl['p']}/code-lists", headers=headers or cl["pa"])
    assert r.status_code == 200, r.text
    return {c["category"]: {i["code"]: i for i in c["codes"]} for c in r.json()}


def picker(client, cl, category, project=None, headers=None):
    r = client.get(f"{API}/projects/{project or cl['p']}/code-master/{category}", headers=headers or cl["admin"],
                   params={"for_picker": "true"})
    return {c["code"]: c["label"] for c in r.json()}


def labels(client, cl, category, project=None):
    r = client.get(f"{API}/projects/{project or cl['p']}/code-master/{category}", headers=cl["admin"])
    return {c["code"]: (c["label"], c["is_hidden"]) for c in r.json()}


def add_project(client, cl, category, code, label, headers=None, expect=201, **kw):
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/{category}", headers=headers or cl["pa"],
                    json={"code": code, "label": label, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def add_company(client, cl, category, code, label, expect=201, **kw):
    r = client.post(f"{API}/code-lists/{category}", headers=cl["admin"], json={"code": code, "label": label, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def party(client, cl, name, kind, project=None):
    r = client.post(f"{API}/projects/{project or cl['p']}/external-entities", headers=cl["admin"],
                    json={"ext_name": name, "kind_code": kind})
    assert r.status_code == 201, r.text
    return r.json()


def held(db, table, pk, row_id, col):
    return db.execute(text(f"SELECT {col} FROM {table} WHERE {pk} = :i"), {"i": row_id}).scalar_one()


def code_id(db, category, code, project_id=None):
    return db.execute(text("SELECT code_id FROM code_master WHERE category = :c AND code = :k AND "
                           "project_id IS NOT DISTINCT FROM :p"), {"c": category, "k": code, "p": project_id}).scalar_one()


def retire(client, cl, row, headers=None):
    return client.delete(f"{API}/code-master/{row['code_id']}", headers=headers or cl["pa"],
                         params={"row_version": row["row_version"]})


# ---- 1, 4, 16: company adds, hiding, and a record that holds a hidden code -------------------------------------
def test_a_company_code_reaches_every_picker_unless_a_project_hid_it(client, cl, db):
    new = add_company(client, cl, "EXTERNAL_ENTITY_KIND", "AGENCY", "Government agency")
    assert "AGENCY" in picker(client, cl, "EXTERNAL_ENTITY_KIND")
    assert "AGENCY" in picker(client, cl, "EXTERNAL_ENTITY_KIND", project=cl["p_fin"])
    bank = party(client, cl, "Our bank", "BANK")
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/hidden", headers=cl["pa"],
                    json={"code_id": code_id(db, "EXTERNAL_ENTITY_KIND", "BANK")})
    assert r.status_code == 201, r.text
    assert "BANK" not in picker(client, cl, "EXTERNAL_ENTITY_KIND")
    assert "BANK" in picker(client, cl, "EXTERNAL_ENTITY_KIND", project=cl["p_fin"])
    assert labels(client, cl, "EXTERNAL_ENTITY_KIND")["BANK"] == ("Bank", True)        # still labelled for records
    got = next(e for e in client.get(f"{API}/projects/{cl['p']}/external-entities", headers=cl["admin"]).json()
               if e["external_entity_id"] == bank["external_entity_id"])
    assert got["kind_code"] == "BANK"
    r = client.patch(f"{API}/external-entities/{bank['external_entity_id']}", headers=cl["admin"],
                     json={"ext_name": "Our main bank", "row_version": got["row_version"]})
    assert r.status_code == 200, r.text                                                  # saves unchanged (R5)
    assert lists(client, cl)["EXTERNAL_ENTITY_KIND"]["BANK"]["hidden"] is True
    assert client.delete(f"{API}/projects/{cl['p']}/code-lists/hidden", params={"code_id": code_id(db, 'EXTERNAL_ENTITY_KIND', 'BANK')},
                         headers=cl["pa"]).status_code == 204
    assert "BANK" in picker(client, cl, "EXTERNAL_ENTITY_KIND")
    assert new["project_id"] is None


# ---- 2, 3, 13, 14, 18: a project relabel moves the project's rows; retiring it moves them back -----------------------
def test_a_project_relabel_repoints_its_rows_only_and_retiring_it_points_them_back(client, cl, db):
    mine = party(client, cl, "Acme", "SUPPLIER")
    gone = party(client, cl, "Old supplier", "SUPPLIER")
    client.delete(f"{API}/external-entities/{gone['external_entity_id']}", headers=cl["admin"],
                  params={"row_version": gone["row_version"]})
    theirs = party(client, cl, "Globex", "SUPPLIER", project=cl["p_fin"])
    company = code_id(db, "EXTERNAL_ENTITY_KIND", "SUPPLIER")
    ov = add_project(client, cl, "EXTERNAL_ENTITY_KIND", "SUPPLIER", "Vendor")
    assert labels(client, cl, "EXTERNAL_ENTITY_KIND")["SUPPLIER"][0] == "Vendor"
    assert labels(client, cl, "EXTERNAL_ENTITY_KIND", project=cl["p_fin"])["SUPPLIER"][0] == "Supplier"
    col = ("external_entity", "external_entity_id")
    assert held(db, *col, mine["external_entity_id"], "kind_code_id") == ov["code_id"]
    assert held(db, *col, gone["external_entity_id"], "kind_code_id") == ov["code_id"]          # R11: retired too
    assert held(db, *col, theirs["external_entity_id"], "kind_code_id") == company               # other project
    ev = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'CODE_REPOINTED'")).scalar_one()
    assert ev["counts"] == {"external_entity.kind_code_id": 2}
    # retire the override: the company label returns, the rows follow it (criterion 3, 13)
    assert retire(client, cl, ov).status_code == 204
    assert labels(client, cl, "EXTERNAL_ENTITY_KIND")["SUPPLIER"][0] == "Supplier"
    assert held(db, *col, mine["external_entity_id"], "kind_code_id") == company
    # re-adding restores the same row (criterion 14), and the rows move again
    again = add_project(client, cl, "EXTERNAL_ENTITY_KIND", "SUPPLIER", "Vendor (approved)")
    assert again["code_id"] == ov["code_id"]
    assert held(db, *col, mine["external_entity_id"], "kind_code_id") == ov["code_id"]
    # a project-only code; its retirement leaves rows holding it (§7.6)
    own = add_project(client, cl, "EXTERNAL_ENTITY_KIND", "AUDITOR", "External auditor")
    aud = party(client, cl, "Big Four", "AUDITOR")
    assert retire(client, cl, own).status_code == 204
    assert "AUDITOR" not in picker(client, cl, "EXTERNAL_ENTITY_KIND")
    assert held(db, *col, aud["external_entity_id"], "kind_code_id") == own["code_id"]


# ---- 5, 6: pinned codes, system lists, company-only lists ------------------------------------------------------------
def test_pinned_codes_can_be_relabelled_never_retired_or_hidden(client, cl, db):
    draft = code_id(db, "BR_STATUS", "DRAFT")
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/hidden", headers=cl["pa"], json={"code_id": draft})
    assert r.status_code == 409 and "relies on" in r.json()["detail"]
    rv = db.execute(text("SELECT row_version FROM code_master WHERE code_id = :i"), {"i": draft}).scalar_one()
    full = client.patch(f"{API}/code-master/{draft}", headers=cl["admin"], json={"row_version": rv, "label": "In draft"})
    assert full.status_code == 200 and full.json()["label"] == "In draft", full.text    # relabelling a pinned code works
    assert labels(client, cl, "BR_STATUS", project=cl["p_fin"])["DRAFT"][0] == "In draft"
    r = client.delete(f"{API}/code-master/{draft}", headers=cl["admin"], params={"row_version": 99})
    assert r.status_code == 409
    rv = db.execute(text("SELECT row_version FROM code_master WHERE code_id = :i"), {"i": draft}).scalar_one()
    r = client.delete(f"{API}/code-master/{draft}", headers=cl["admin"], params={"row_version": rv})
    assert r.status_code == 409 and "never retired" in r.json()["detail"]
    # R2: a project's own wording of a pinned code is a platform admin's to give
    add_project(client, cl, "BR_STATUS", "DRAFT", "Being drafted", expect=403)
    ov = add_project(client, cl, "BR_STATUS", "DRAFT", "Being drafted", headers=cl["admin"])
    assert labels(client, cl, "BR_STATUS")["DRAFT"][0] == "Being drafted"
    assert retire(client, cl, ov, headers=cl["admin"]).status_code == 204       # withdrawing a relabel is allowed
    assert labels(client, cl, "BR_STATUS")["DRAFT"][0] == "In draft"
    # R2 as signed (history Q-38 open): the rate-card FR types are pinned, so a project admin cannot rename them yet
    add_project(client, cl, "FR_TYPE", "FORM", "Screen", expect=403)


# ---- sara 1g M3: a company code some project renamed can still be retired and restored -----------------------------
def test_a_company_code_a_project_renamed_can_be_retired_and_restored(client, cl, db):
    add_project(client, cl, "BR_PRIORITY", "MUST", "Must have")
    must = code_id(db, "BR_PRIORITY", "MUST")
    rv = db.execute(text("SELECT row_version FROM code_master WHERE code_id = :i"), {"i": must}).scalar_one()
    assert client.delete(f"{API}/code-master/{must}", headers=cl["admin"], params={"row_version": rv}).status_code == 204
    r = client.patch(f"{API}/code-master/{must}/restore", headers=cl["admin"], json={"row_version": rv + 1})
    assert r.status_code == 200, r.text


def test_system_and_company_only_lists_refuse_project_changes(client, cl, db):
    add_company(client, cl, "APP_LIFECYCLE", "RETIRING", "Being retired", expect=409)
    add_project(client, cl, "APP_LIFECYCLE", "AS_IS", "Today", expect=409)
    add_project(client, cl, "PROJECT_TEMPLATE", "X", "X", expect=409)
    add_project(client, cl, "PROJECT_STATUS", "PLANNING", "Scoping", expect=409)                  # G-2
    tmpl = db.execute(text("SELECT code_id FROM code_master WHERE category = 'PROJECT_TEMPLATE' AND project_id IS NULL "
                           "ORDER BY code_id LIMIT 1")).scalar_one()
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/hidden", headers=cl["pa"], json={"code_id": tmpl})
    assert r.status_code == 409
    sys_row = code_id(db, "APP_LIFECYCLE", "AS_IS")
    r = client.patch(f"{API}/code-master/{sys_row}", headers=cl["admin"], json={"row_version": 1, "label": "x"})
    assert r.status_code == 409


# ---- 7, 17: behaviour is fixed once used; an override keeps the company behaviour ---------------------------------------
def test_behaviour_changes_only_while_unused_and_an_override_keeps_it(client, cl):
    new = add_company(client, cl, "FR_TYPE", "PORTAL", "Portal page", behaviour_code="FORM")
    r = client.patch(f"{API}/code-master/{new['code_id']}", headers=cl["admin"],
                     json={"row_version": 1, "behaviour_code": "REPORT"})
    assert r.status_code == 409 and "in use" in r.json()["detail"]                  # its seeded rate cells use it
    lone = add_company(client, cl, "RACI_TYPE", "REVIEWS", "Reviews", behaviour_code="CONSULTED")
    r = client.patch(f"{API}/code-master/{lone['code_id']}", headers=cl["admin"],
                     json={"row_version": 1, "behaviour_code": "INFORMED"})
    assert r.status_code == 200 and r.json()["behaviour_code"] == "INFORMED"
    add_project(client, cl, "FR_TYPE", "FORM", "Screen", behaviour_code="REPORT", headers=cl["admin"], expect=409)        # R10


# ---- 8, 14, 15: FR types, rate cells and rating ------------------------------------------------------------------------
def test_an_fr_type_override_repoints_frs_and_rate_cells_and_rating_still_works(client, cl, db):
    ed = {"h": cl["h"], "p": cl["p"]}
    f = fr(client, ed, "Order entry")
    ov = add_project(client, cl, "FR_TYPE", "FORM", "Screen", headers=cl["admin"])
    assert held(db, "function_requirement", "fr_id", f["fr_id"], "fr_type_code_id") == ov["code_id"]
    cells = db.execute(text("SELECT count(*) FROM effort_rate WHERE project_id = :p AND fr_type_code_id = :c"),
                       {"p": cl["p"], "c": ov["code_id"]}).scalar_one()
    assert cells == sum(1 for t, _ in FTC_DEFAULT_RATE_CARD if t == "FORM")
    r = rate(client, ed, f, "MEDIUM")
    assert r.status_code == 200 and r.json()["effort_days"] is not None, r.text
    assert retire(client, cl, ov).status_code == 204                                 # back to the company type
    assert rate(client, ed, f, "COMPLEX").status_code == 200


def test_a_new_company_fr_type_is_rateable_in_every_project_and_other_has_no_cells(client, cl, db):
    add_company(client, cl, "FR_TYPE", "PORTAL", "Portal page", behaviour_code="FORM")
    for p in (cl["p"], cl["p_fin"], cl["p_sales"]):
        ed = {"h": cl["admin"], "p": p}
        f = fr(client, ed, "Customer portal", fr_type="PORTAL", project=p)
        assert rate(client, ed, f, "MEDIUM").status_code == 200, p
    add_company(client, cl, "FR_TYPE", "MISC", "Other work", behaviour_code="OTHER")
    ed = {"h": cl["admin"], "p": cl["p"]}
    f = fr(client, ed, "Something else", fr_type="MISC")
    assert rate(client, ed, f, "MEDIUM").status_code == 422                          # G-4: no source, no cells


# ---- 9: every write is audited, nothing is deleted ---------------------------------------------------------------------
def test_every_write_is_audited(client, cl, db):
    ov = add_project(client, cl, "BR_PRIORITY", "MUST", "Must have")
    client.patch(f"{API}/code-master/{ov['code_id']}", headers=cl["pa"], json={"row_version": ov["row_version"],
                                                                                "label": "Must-have"})
    retire(client, cl, {**ov, "row_version": ov["row_version"] + 1})
    types = db.execute(text("SELECT event_type FROM audit_event WHERE target_table = 'code_master' "
                            "ORDER BY audit_event_id")).scalars().all()
    assert types == ["CODE_OVERRIDDEN", "CODE_CHANGED", "CODE_RETIRED"]
    assert db.execute(text("SELECT count(*) FROM code_master WHERE code_id = :i"), {"i": ov["code_id"]}).scalar() == 1


# ---- 10: who may do what ------------------------------------------------------------------------------------------------
def test_readers_and_editors_are_refused_outsiders_see_nothing_company_rows_are_404(client, cl, db):
    for who in ("h", "rv"):
        add_project(client, cl, "BR_PRIORITY", "MUST", "Must have", headers=cl[who], expect=403)
        assert client.get(f"{API}/projects/{cl['p']}/code-lists", headers=cl[who]).status_code == 200
    add_project(client, cl, "BR_PRIORITY", "MUST", "Must have", headers=cl["out"], expect=404)
    company = code_id(db, "BR_PRIORITY", "MUST")
    r = client.patch(f"{API}/code-master/{company}", headers=cl["pa"], json={"row_version": 1, "label": "x"})
    assert r.status_code == 404
    assert client.get(f"{API}/code-lists", headers=cl["pa"]).status_code == 403
    assert client.post(f"{API}/code-lists/BR_PRIORITY", headers=cl["pa"],
                       json={"code": "NICE", "label": "Nice"}).status_code == 403


# ---- 11: a baseline frozen before a rename keeps its label and still reads unchanged ------------------------------------
def test_a_baseline_frozen_before_a_rename_keeps_its_label(client, cl):
    ed = {"h": cl["admin"], "p": cl["p"], "rv": cl["rv"]}
    scope(client, ed)
    v10 = bid(freeze(client, ed))
    add_project(client, cl, "BR_STATUS", "DRAFT", "Being drafted", headers=cl["admin"])
    rows = client.get(f"{API}/baselines/{v10}/rows/business_requirement", headers=cl["admin"]).json()["rows"]
    assert {r["status_label"] for r in rows} == {"Draft"}
    assert diff(client, ed, v10, "live")["summary"]["CHANGED"] == 0


# ---- R7, R8 --------------------------------------------------------------------------------------------------------------
def test_code_format_and_a_company_code_a_project_already_owns(client, cl):
    add_company(client, cl, "BR_PRIORITY", "nice to have", "Nice", expect=422)
    add_project(client, cl, "BR_PRIORITY", "WISH", "Wish list")
    r = client.post(f"{API}/code-lists/BR_PRIORITY", headers=cl["admin"], json={"code": "WISH", "label": "Wish"})
    assert r.status_code == 409 and "SOLO" in r.json()["detail"]


# ---- R12: the re-point reaches every code column, or says why not --------------------------------------------------------
def test_every_code_column_is_repointed_or_excluded(db):
    cols = code_lists.code_columns(db)
    seen = {(c["table"], c["column"]) for c in cols}
    assert set(code_lists.EXCLUDED) <= seen, set(code_lists.EXCLUDED) - seen              # no stale exclusion
    for c in cols:
        if (c["table"], c["column"]) in code_lists.EXCLUDED:
            continue
        assert c["category"], f"{c['table']}.{c['column']} has no generated category column — repoint or exclude it"
        has_project = db.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name = :t "
                                      "AND column_name = 'project_id'"), {"t": c["table"]}).scalar()
        assert has_project, f"{c['table']} has no project_id — the re-point cannot scope it"
    assert len(code_lists.repointed_columns(db)) >= 20


# ---- 12: a value lookup the application relies on is pinned ---------------------------------------------------------------
NOT_CODE_MASTER = {"R", "C", "U", "D", "TO_BE", "AS_IS", "23502", "23514"}   # CRUD letters, chart sets, SQLSTATEs


def test_every_value_lookup_is_pinned():
    pinned_codes = {code for _, code in code_lists.PINNED}
    found = set()
    for path in (ROOT / "backend" / "services").glob("*.py"):
        src = path.read_text()
        found |= {m for m in re.findall(r'(?<!behaviour_)code\s*[!=]=\s*"([A-Z][A-Z0-9_]*)"', src)}
        for group in re.findall(r'code\s+(?:not\s+)?in\s+\(([^)]*)\)', src):
            found |= set(re.findall(r'"([A-Z][A-Z0-9_]*)"', group))
        found |= {code for _, code in re.findall(
            r'validate_required_code\(db,\s*[^,]+,\s*"([A-Z_]+)",\s*"([A-Z][A-Z0-9_]*)"', src)}
        found |= {code for _, code in re.findall(r'_code_id\(\w+,\s*[^,]+,\s*"([A-Z_]+)",\s*"([A-Z][A-Z0-9_]*)"', src)}
    for path in (ROOT / "frontend" / "src").rglob("*.js*"):
        found |= set(re.findall(r"[cC]ode\)?\s*!?===\s*'([A-Z][A-Z0-9_]*)'", path.read_text()))
    from services import business_requirement, scope_summary
    found |= set(business_requirement.SYSTEM_SET_STATUSES) | set(scope_summary.AGREED)
    system_codes = {"FROZEN", "SUPERSEDED", "APPROVED", "AS_IS", "TO_BE"}        # BASELINE_STATUS, APP_LIFECYCLE
    missing = found - pinned_codes - NOT_CODE_MASTER - system_codes
    assert missing == set(), f"looked up by value but not in code_lists.PINNED: {sorted(missing)}"
