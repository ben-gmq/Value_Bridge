"""A demo project for UAT and screenshots — never for a real database. Run from backend/:
    DATABASE_URL=<a throwaway db> python -m seeds.seed_demo --secrets-out <file>
It refuses unless VB_ALLOW_DEMO_SEED=1 is set AND the database it is actually connected to
(`current_database()`, not the URL — a URL query can redirect the connection, sara H1) has
'uat' or 'demo' in its name. It creates an admin, an EDITOR and a REVIEWER with one random
password, written only to --secrets-out (mode 600, outside the repo) and never printed. It is
not re-runnable: drop and recreate the database to seed again. Everything goes through the services, so the rows obey the same rules as the app.

The data covers the Slice 3 acceptance cases: two L1 areas sharing a store (cross-area), an
external flow that covers a step input and carries both a DE and a label (5a), a start and an
end event (21), a composite FK, two FK groups to one parent, an identifying FK, a no-key entity,
a 12-attribute entity (collapse) and a Japanese field name (20a).
"""
import argparse
import os
import secrets
from pathlib import Path

from sqlalchemy import select, text

from auth.security import hash_password
from database import SessionLocal
from models import AppUser, BrOrgRole, BusinessRequirement
from services import audit, bfc, bfc_set, client_org, data_entity, external_entity, raci, step_io, trigger
from services import components
from services.project import create_client, create_project
from services.user_admin import check_ftc_address, create_user

SAFE_MARKERS = ("uat", "demo")
REPO = Path(__file__).resolve().parents[2]


def _entity(db, actor, pid, name, fields):
    de = data_entity.create_entity(db, actor, pid, name, None, None)
    made = {}
    for fname, spec in fields:
        made[fname] = data_entity.create_field(db, actor, de, fname, spec)
    return de, made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secrets-out", required=True)
    ap.add_argument("--domain", default="fortience.com")
    args = ap.parse_args()
    if os.environ.get("VB_ALLOW_DEMO_SEED") != "1":
        raise SystemExit("Refusing: set VB_ALLOW_DEMO_SEED=1 to seed a demo database")
    out = Path(args.secrets_out).resolve()
    if out.is_relative_to(REPO):
        raise SystemExit("Refusing: --secrets-out must be outside the repository (sara L3)")
    check_ftc_address(f"uat.admin@{args.domain}")          # D-11, before any write (sara M1)
    pw = secrets.token_urlsafe(18)
    # Opened before the first write so a bad path cannot strand an admin (sara L1). O_EXCL
    # refuses an existing file or symlink, so the mode is always 600 (sara M2).
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    with SessionLocal() as db, os.fdopen(fd, "w") as fh:
        name = db.scalar(text("select current_database()"))
        if not any(m in name.lower() for m in SAFE_MARKERS):
            raise SystemExit(f"Refusing: connected database '{name}' is not a uat/demo database")
        admin = AppUser(email=f"uat.admin@{args.domain}", display_name="UAT Admin",
                        password_hash=hash_password(pw), is_platform_admin=True)
        db.add(admin)
        db.flush()
        audit.record(db, "ADMIN_CREATED_BY_DEMO_SEED", actor_id=admin.app_user_id,
                     target_table="app_user", target_id=admin.app_user_id)
        db.commit()
        pid = build_project(db, admin, args.domain, pw)

        fh.write(f"project_id={pid}\npassword={pw}\n")
        for who in ("admin", "editor", "reviewer"):
            fh.write(f"{who}=uat.{who}@{args.domain}\n")
    print(f"Demo project {pid} seeded in '{name}'. Sign-in details written to {out}")


def build_project(db, admin: AppUser, domain: str, pw: str) -> int:
    """The demo project itself, through the services. Split from main() so the DFD invariant
    test (slice 3 criterion 5a) runs over exactly this data. It keeps a guard of its own, so an
    importer cannot use it to seed a real database around main()'s checks (sara L2)."""
    name = db.scalar(text("select current_database()"))
    if not any(m in name.lower() for m in (*SAFE_MARKERS, "test")):
        raise SystemExit(f"Refusing: connected database '{name}' is not a uat/demo/test database")
    a = admin.app_user_id
    client = create_client(db, admin, "DEMO", "Demo Trading Co", "Distribution")
    proj = create_project(db, admin, client.client_id, "DEMO", "Order to cash demo", None, None, None,
                          component_codes=list(components.ALL), is_restricted=False)
    pid = proj.project_id
    for name, kind in (("editor", "USER"), ("reviewer", "VIEWER")):      # D-40: kinds, not grants
        create_user(db, admin, f"uat.{name}@{domain}", f"UAT {name.title()}", pw, kind)

    # Client organisation → the lanes.
    sales = client_org.create_unit(db, a, pid, None, "SALES", "Sales Operations", "DEPARTMENT", None)
    wh = client_org.create_unit(db, a, pid, None, "WH", "Warehouse", "DEPARTMENT", None)
    fin = client_org.create_unit(db, a, pid, None, "FIN", "Finance", "DEPARTMENT", None)
    r_sales = client_org.create_role(db, a, pid, sales.org_unit_id, "SALES_ADMIN", "Sales administrator", None, None)
    r_credit = client_org.create_role(db, a, pid, sales.org_unit_id, "CREDIT", "Credit controller", None, None)
    r_wh = client_org.create_role(db, a, pid, wh.org_unit_id, "WH_CLERK", "Warehouse clerk", None, None)
    r_ar = client_org.create_role(db, a, pid, fin.org_unit_id, "AR_CLERK", "Receivables clerk", None, None)

    # Chart: two L1 areas, steps at level 3.
    o2c = bfc.create_node(db, a, pid, None, "Order to cash")
    capture = bfc.create_node(db, a, pid, o2c.bfc_node_id, "Order capture")
    fulfil = bfc.create_node(db, a, pid, o2c.bfc_node_id, "Fulfilment")
    finance = bfc.create_node(db, a, pid, None, "Finance")
    billing = bfc.create_node(db, a, pid, finance.bfc_node_id, "Billing")
    step = {}
    for parent, sname, role in [
        (capture, "Receive order", r_sales), (capture, "Check credit", r_credit),
        (capture, "Confirm order", r_sales), (fulfil, "Pick goods", r_wh),
        (fulfil, "Ship goods", r_wh), (billing, "Raise invoice", r_ar), (billing, "Post payment", r_ar),
    ]:
        node = bfc.create_node(db, a, pid, parent.bfc_node_id, sname, is_process=True)
        br = db.scalars(select(BusinessRequirement).where(BusinessRequirement.bfc_node_id == node.bfc_node_id,
                                                          BusinessRequirement.is_active)).one()
        raci.link(db, a, BrOrgRole, br, role.org_role_id, "R")          # D-64: a to-be process's RACI is its BR's
        step[sname] = node

    # Data entities, shaped for the ERD cases.
    mand = {"is_mandatory": True}
    customer, cf = _entity(db, a, pid, "Customer", [
        ("customer_id", {"is_primary_key": True, "pk_ordinal": 1, "data_type_code": "INTEGER", **mand}),
        ("customer_name", {"data_type_code": "STRING", **mand})])
    address, af = _entity(db, a, pid, "Address", [
        ("address_id", {"is_primary_key": True, "pk_ordinal": 1, **mand}), ("postcode", {})])
    order, of = _entity(db, a, pid, "Sales order", [
        ("order_id", {"is_primary_key": True, "pk_ordinal": 1, "data_type_code": "INTEGER", **mand}),
        ("customer_id", {"ref_data_entity_id": customer.data_entity_id,
                         "ref_data_field_id": cf["customer_id"].data_field_id, **mand}),
        ("ship_to_address_id", {"ref_data_entity_id": address.data_entity_id, "is_mandatory": False}),
        ("bill_to_address_id", {"ref_data_entity_id": address.data_entity_id, "fk_group": "new"}),
        ("order_date", {"data_type_code": "DATE"})])
    line, lf = _entity(db, a, pid, "Order line", [
        ("order_id", {"is_primary_key": True, "pk_ordinal": 1, "ref_data_entity_id": order.data_entity_id,
                      "ref_data_field_id": of["order_id"].data_field_id, **mand}),
        ("line_no", {"is_primary_key": True, "pk_ordinal": 2, "data_type_code": "INTEGER", **mand}),
        ("quantity", {"data_type_code": "DECIMAL"})])
    shipment, _ = _entity(db, a, pid, "Shipment line", [
        ("shipment_id", {"is_primary_key": True, "pk_ordinal": 1, **mand}),
        ("order_id", {"ref_data_entity_id": line.data_entity_id,
                      "ref_data_field_id": lf["order_id"].data_field_id, **mand}),
        ("line_no", {"ref_data_entity_id": line.data_entity_id, "ref_data_field_id": lf["line_no"].data_field_id,
                     "fk_group": 1, **mand})])
    invoice, _ = _entity(db, a, pid, "Invoice", [
        ("invoice_id", {"is_primary_key": True, "pk_ordinal": 1, **mand}),
        ("order_id", {"ref_data_entity_id": order.data_entity_id, "is_mandatory": False}),
        ("注文番号", {"data_type_code": "STRING"})])
    payment, _ = _entity(db, a, pid, "Payment", [("amount", {"data_type_code": "DECIMAL"})])   # NO_KEY
    product, _ = _entity(db, a, pid, "Product", [("product_id", {"is_primary_key": True, "pk_ordinal": 1, **mand})]
                         + [(f"attribute_{i:02d}", {}) for i in range(1, 13)])

    # Step I/O. Sales order is written under 01 and read under 02 → cross-area.
    for sname, de, d in [
        ("Receive order", customer, "I"), ("Receive order", order, "O"),
        ("Check credit", customer, "I"), ("Check credit", order, "I"),
        ("Confirm order", order, "O"), ("Confirm order", line, "O"),
        ("Pick goods", line, "I"), ("Pick goods", product, "I"),
        ("Ship goods", shipment, "O"), ("Ship goods", address, "I"),
        ("Raise invoice", order, "I"), ("Raise invoice", invoice, "O"),
        ("Post payment", invoice, "I"), ("Post payment", payment, "O"),
    ]:
        step_io.link(db, a, step[sname], de.data_entity_id, d)

    # External parties. Customer → Receive order covers an existing input (with a label too).
    cust = external_entity.create_party(db, a, pid, "Customer", "CUSTOMER", None)
    bank = external_entity.create_party(db, a, pid, "Bank", "BANK", None)
    bfc.link_external_flow(db, a, step["Receive order"], cust.external_entity_id, "I",
                           order.data_entity_id, "emailed PO", None)
    bfc.link_external_flow(db, a, step["Ship goods"], cust.external_entity_id, "O", None, "delivery note", None)
    bfc.link_external_flow(db, a, step["Post payment"], bank.external_entity_id, "I",
                           payment.data_entity_id, None, None)

    # D-46 performers (the lanes), D-49 triggers; order is derived from the step I/O above (D-38).
    db.expire_all()
    for sname, kind, code, label in [
        ("Receive order", "ORG_ROLE", "SALES_ADMIN", None), ("Check credit", "AI", None, "Credit scoring agent"),
        ("Confirm order", "ORG_ROLE", "SALES_ADMIN", None), ("Pick goods", "ORG_UNIT", "WH", None),
        ("Ship goods", "ORG_UNIT", "WH", None), ("Raise invoice", "ORG_ROLE", "AR_CLERK", None),
        ("Post payment", "ORG_ROLE", "AR_CLERK", None),
    ]:
        node = db.get(type(step[sname]), step[sname].bfc_node_id)
        bfc.set_performer(db, a, node, node.row_version, kind, code, label)
    month_end = trigger.create_trigger(db, a, pid, "Month-end close", "TIME", "last working day, 18:00", None)
    calls = trigger.create_trigger(db, a, pid, "Customer calls", "EVENT", None, None)
    trigger.link(db, a, db.get(type(step["Raise invoice"]), step["Raise invoice"].bfc_node_id),
                 month_end.process_trigger_id, None)
    trigger.link(db, a, db.get(type(step["Receive order"]), step["Receive order"].bfc_node_id),
                 calls.process_trigger_id, None)

    # D-47: start the as-is chart from the to-be one (preview, then confirm).
    prev = bfc_set.copy_set(db, a, pid, "AS_IS", "TO_BE", None)
    bfc_set.copy_set(db, a, pid, "AS_IS", "TO_BE", prev["confirm_hash"])
    return pid


if __name__ == "__main__":
    main()
