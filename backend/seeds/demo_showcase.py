"""A fuller demo project for screenshots and UAT: a realistic core-systems renewal with four business areas,
about two dozen processes, filled-in requirements, CRUD, RACI, solutions, rated FRs, systems and two frozen
baselines with changes after them. Built only through the services, so every row obeys the app's rules.
Called by seeds.seed_demo after the acceptance-case project; it keeps the same database guard.
All names, figures and organisations are illustrative."""
from datetime import date

from sqlalchemy import select

from models import AppUser, BfcNode, BrOrgRole, BusinessRequirement
from services import (application, baseline, bfc, business_requirement, client_org, components, data_entity, effort,
                      external_entity, freeze_set, function_requirement, raci, solution, trigger)
from services.project import create_client, create_project
from services.user_admin import create_user

from seeds._guard import assert_throwaway_db

# Org: unit code → (name, [(role code, role name)]).
ORG = {
    "SALES": ("Sales Operations", [("ORDER_CLERK", "Order clerk"), ("SALES_MGR", "Sales manager")]),
    "CREDIT": ("Credit Control", [("CREDIT_OFF", "Credit officer"), ("CREDIT_MGR", "Credit manager")]),
    "PROC": ("Procurement", [("BUYER", "Buyer"), ("PROC_MGR", "Procurement manager")]),
    "WH": ("Warehouse", [("WH_CLERK", "Warehouse clerk"), ("WH_SUP", "Warehouse supervisor")]),
    "FIN": ("Finance", [("AR_CLERK", "Receivables clerk"), ("AP_CLERK", "Payables clerk"),
                        ("CONTROLLER", "Financial controller")]),
}

# Entities: name → fields (first is the key).
ENTITIES = {
    "Customer": ["customer_id", "customer_name", "segment", "payment_terms"],
    "Credit limit": ["customer_id", "limit_amount", "currency", "review_date"],
    "Sales order": ["order_id", "customer_id", "order_date", "status", "total_amount"],
    "Order line": ["order_id", "line_no", "product_id", "quantity", "unit_price"],
    "Price list": ["price_list_id", "product_id", "valid_from", "list_price"],
    "Discount approval": ["approval_id", "order_id", "discount_pct", "approved_by"],
    "Product": ["product_id", "product_name", "uom", "category"],
    "Supplier": ["supplier_id", "supplier_name", "country", "rating"],
    "Purchase request": ["request_id", "product_id", "quantity", "needed_by"],
    "Purchase order": ["po_id", "supplier_id", "po_date", "total_amount"],
    "Goods receipt": ["receipt_id", "po_id", "received_on", "quantity"],
    "Stock": ["product_id", "location", "on_hand", "reserved"],
    "Shipment": ["shipment_id", "order_id", "shipped_on", "carrier"],
    "Invoice": ["invoice_id", "order_id", "invoice_date", "amount", "due_date"],
    "Payment": ["payment_id", "invoice_id", "paid_on", "amount"],
    "Supplier invoice": ["sup_invoice_id", "po_id", "amount", "due_date"],
    "GL journal": ["journal_id", "period", "account", "amount"],
}

# Chart: L1 → L2 → processes. Each process: (name, performer role, accountable role, CRUD list,
# statement, logic, output, confirmed?). CRUD: (entity, letter). R = input, C/U = output.
CHART = [
    ("Sales", [
        ("Order management", [
            ("Receive order", "ORDER_CLERK", "SALES_MGR",
             [("Customer", "R"), ("Product", "R"), ("Price list", "R"), ("Sales order", "C"), ("Order line", "C")],
             "Register every customer order the day it arrives, whatever the channel",
             "Orders arrive by EDI, e-mail or phone. The clerk checks the customer is active and every product "
             "is orderable; an unknown product is held and returned to Sales within one working day.",
             "A registered sales order with its lines, status Received", True),
            ("Check credit", "CREDIT_OFF", "CREDIT_MGR",
             [("Credit limit", "R"), ("Sales order", "R"), ("Sales order", "U")],
             "Decide acceptance against the customer's remaining credit limit",
             "Remaining limit = credit limit − open receivables − open orders. If the order amount exceeds the "
             "remaining limit, set the credit result to HOLD and return the order to Sales with the shortfall.",
             "The order carries a credit result: Released or Hold", True),
            ("Confirm order", "ORDER_CLERK", "SALES_MGR",
             [("Sales order", "R"), ("Stock", "R"), ("Sales order", "U")],
             "Confirm a delivery date to the customer within four working hours",
             "Promise from available stock first, then from open purchase orders. A date later than the "
             "customer's requested date needs the sales manager's agreement.",
             "An order confirmation sent with a promised date", True),
            ("Amend order", "ORDER_CLERK", "SALES_MGR",
             [("Sales order", "R"), ("Order line", "U")],
             "Change quantities or dates on an open order without re-keying it",
             "Only orders not yet picked may change. A quantity increase re-runs the credit check.",
             "The amended order and a revised confirmation", False),
        ]),
        ("Pricing", [
            ("Maintain price list", "SALES_MGR", "SALES_MGR",
             [("Product", "R"), ("Price list", "C")],
             "Publish one price list per quarter, valid from a fixed date",
             "Prices are set in the list currency; a change inside the quarter needs a dated new version.",
             "A dated, approved price list", True),
            ("Approve discount", "SALES_MGR", "SALES_MGR",
             [("Sales order", "R"), ("Discount approval", "C")],
             "Approve any discount above the clerk's 5% authority before the order is confirmed",
             "5–15% by the sales manager, above 15% by the sales director. Rejections return to the clerk.",
             "A recorded approval or rejection on the order", False),
        ]),
    ]),
    ("Procurement", [
        ("Purchasing", [
            ("Raise purchase request", "WH_SUP", "PROC_MGR",
             [("Stock", "R"), ("Product", "R"), ("Purchase request", "C")],
             "Request replenishment when stock falls below its reorder point",
             "The reorder point is set per product and location. Requests are grouped by supplier weekly.",
             "An open purchase request", True),
            ("Approve purchase request", "PROC_MGR", "PROC_MGR",
             [("Purchase request", "R"), ("Purchase request", "U")],
             "Approve requests within budget before any order is placed",
             "Up to 1M yen by the procurement manager, above that by the controller.",
             "An approved or rejected request", False),
            ("Issue purchase order", "BUYER", "PROC_MGR",
             [("Purchase request", "R"), ("Supplier", "R"), ("Purchase order", "C")],
             "Place a purchase order with an approved supplier",
             "Only suppliers rated B or better may receive orders. One order per supplier per week.",
             "A purchase order sent to the supplier", True),
        ]),
        ("Supplier management", [
            ("Onboard supplier", "BUYER", "PROC_MGR",
             [("Product", "R"), ("Supplier", "C")],
             "Register a new supplier only after the due-diligence checks pass",
             "Bank details are confirmed by a call-back to a known number before first payment.",
             "An active supplier record", False),
            ("Evaluate supplier", "PROC_MGR", "PROC_MGR",
             [("Goods receipt", "R"), ("Supplier", "U")],
             "Rate every active supplier twice a year on delivery and quality",
             "On-time delivery below 90% drops the rating by one grade.",
             "An updated supplier rating", True),
        ]),
    ]),
    ("Logistics", [
        ("Warehouse", [
            ("Receive goods", "WH_CLERK", "WH_SUP",
             [("Purchase order", "R"), ("Goods receipt", "C")],
             "Book every delivery against its purchase order on the day it arrives",
             "Over-deliveries above 5% are refused at the dock.",
             "A goods receipt matched to its purchase order", True),
            ("Put away stock", "WH_CLERK", "WH_SUP",
             [("Goods receipt", "R"), ("Stock", "U")],
             "Put received goods into a storage location within four hours",
             "Fast movers go to the pick face; the rest to reserve.",
             "Stock on hand updated by location", True),
            ("Pick goods", "WH_CLERK", "WH_SUP",
             [("Sales order", "R"), ("Stock", "U")],
             "Pick released orders in promised-date order",
             "Only credit-released, confirmed orders are picked. Short picks are reported the same day.",
             "Goods picked and stock reserved", True),
            ("Ship goods", "WH_CLERK", "WH_SUP",
             [("Sales order", "R"), ("Shipment", "C")],
             "Ship picked orders on the promised date with a delivery note",
             "Carrier by region; a missed cut-off moves the shipment to the next day and informs Sales.",
             "A shipment with carrier and tracking number", True),
        ]),
        ("Inventory", [
            ("Count stock", "WH_SUP", "WH_SUP",
             [("Stock", "R"), ("Stock", "U")],
             "Count every location at least once a quarter",
             "A-class items monthly. Differences above 2% are recounted before posting.",
             "Counted quantities posted", False),
            ("Adjust stock", "WH_SUP", "CONTROLLER",
             [("Stock", "R"), ("Stock", "U"), ("GL journal", "C")],
             "Post stock adjustments with a reason and a finance approval",
             "Write-offs above 100k yen need the controller's approval.",
             "An adjustment and its journal", False),
        ]),
    ]),
    ("Finance", [
        ("Receivables", [
            ("Raise invoice", "AR_CLERK", "CONTROLLER",
             [("Shipment", "R"), ("Sales order", "R"), ("Invoice", "C")],
             "Invoice every shipment within one working day",
             "One invoice per shipment; prices from the order, not the current list.",
             "An invoice sent to the customer", True),
            ("Post payment", "AR_CLERK", "CONTROLLER",
             [("Invoice", "R"), ("Payment", "C")],
             "Apply customer payments to open invoices daily",
             "Unmatched receipts sit on account for at most five days before Sales is asked.",
             "Invoices marked paid; open receivables updated", True),
            ("Chase overdue", "AR_CLERK", "CREDIT_MGR",
             [("Invoice", "R"), ("Credit limit", "U")],
             "Chase every invoice overdue by more than seven days",
             "Reminder at 7 days, call at 21, credit hold at 45.",
             "A dunning record and, past 45 days, a reduced limit", False),
        ]),
        ("Payables", [
            ("Match supplier invoice", "AP_CLERK", "CONTROLLER",
             [("Supplier invoice", "C"), ("Goods receipt", "R")],
             "Pay only what was ordered and received (three-way match)",
             "Price or quantity differences above 2% go back to the buyer.",
             "A matched invoice ready to pay", True),
            ("Pay supplier", "AP_CLERK", "CONTROLLER",
             [("Supplier invoice", "R"), ("GL journal", "C")],
             "Pay matched invoices on their due date in two weekly runs",
             "The payment run is released by two people.",
             "A payment run and its journal", True),
        ]),
        ("Close", [
            ("Close the month", "CONTROLLER", "CONTROLLER",
             [("GL journal", "R"), ("GL journal", "U")],
             "Close the books by the fifth working day",
             "Accruals, stock valuation and receivables ageing are reviewed before the period locks.",
             "A closed period and the management pack", False),
        ]),
    ]),
]

APPS = [("SALESPRO", "SalesPro v8", "AS_IS", "CUSTOM"), ("S4", "SAP S/4HANA", "TO_BE", "PACKAGE"),
        ("WMS", "Warehouse management system", "BOTH", "PACKAGE"), ("EDI", "EDI hub", "TO_BE", "INTEGRATION")]

# Solutions: name, category, delivering app, BRs (process names) it covers, FRs [(name, type, complexity)].
SOLUTIONS = [
    ("Order-to-cash on S/4HANA", "TECHNOLOGY", "S4",
     ["Receive order", "Confirm order", "Amend order", "Raise invoice", "Post payment"],
     [("Sales order entry screen", "FORM", "MEDIUM"), ("Order confirmation output", "REPORT", "SIMPLE"),
      ("Order amendment workflow", "FORM", "COMPLEX"), ("Invoice output", "REPORT", "SIMPLE"),
      ("Bank statement import", "INTERFACE", "MEDIUM"), ("Cash application batch", "BATCH", "COMPLEX")]),
    ("Credit automation", "TECHNOLOGY", "S4", ["Check credit", "Chase overdue"],
     [("Credit inquiry screen", "FORM", "MEDIUM"), ("Credit decision batch", "BATCH", "COMPLEX"),
      ("Dunning letters", "REPORT", "SIMPLE")]),
    ("EDI order intake", "TECHNOLOGY", "EDI", ["Receive order"],
     [("Inbound EDI order interface", "INTERFACE", "COMPLEX")]),
    ("Pricing and discount rules", "ORG_AND_RULES", None, ["Maintain price list", "Approve discount"],
     [("Price list upload", "INTERFACE", "SIMPLE"), ("Discount approval screen", "FORM", "MEDIUM")]),
    ("Procure-to-pay on S/4HANA", "TECHNOLOGY", "S4",
     ["Raise purchase request", "Approve purchase request", "Issue purchase order", "Match supplier invoice",
      "Pay supplier"],
     [("Reorder proposal batch", "BATCH", "MEDIUM"), ("Purchase approval workflow", "FORM", "COMPLEX"),
      ("Purchase order output", "REPORT", "SIMPLE"), ("Three-way match exceptions", "REPORT", "MEDIUM"),
      ("Payment file to bank", "INTERFACE", "MEDIUM")]),
    ("Supplier master governance", "DATA", None, ["Onboard supplier", "Evaluate supplier"],
     [("Supplier scorecard", "REPORT", "MEDIUM")]),
    ("Warehouse on WMS", "TECHNOLOGY", "WMS",
     ["Receive goods", "Put away stock", "Pick goods", "Ship goods", "Count stock"],
     [("Goods receipt to S/4HANA", "INTERFACE", "MEDIUM"), ("Pick list", "REPORT", "SIMPLE"),
      ("Shipment confirmation interface", "INTERFACE", "MEDIUM"), ("Cycle count app", "FORM", "MEDIUM")]),
    ("Month-end close playbook", "PROCESS", None, ["Close the month", "Adjust stock"], []),
]


def _node(db, nid):
    return db.get(BfcNode, nid)


def build_showcase(db, admin: AppUser, domain: str, pw: str) -> int:
    assert_throwaway_db(db, ("uat", "demo", "test"))
    yamada = create_user(db, admin, f"k.yamada@{domain}", "K. Yamada", pw, "USER")
    db.commit()
    y = yamada.app_user_id
    client = create_client(db, admin, "KAITO", "Kaito Manufacturing", "Manufacturing")
    proj = create_project(db, admin, client.client_id, "CSR27", "2027 Core Systems Renewal", None,
                          date(2026, 4, 1), date(2027, 3, 31), component_codes=list(components.ALL),
                          is_restricted=False)
    pid = proj.project_id
    db.commit()

    roles = {}
    for ucode, (uname, rlist) in ORG.items():
        unit = client_org.create_unit(db, y, pid, None, ucode, uname, "DEPARTMENT", None)
        for rcode, rname in rlist:
            roles[rcode] = client_org.create_role(db, y, pid, unit.org_unit_id, rcode, rname, None, None)

    ents = {}
    for ename, fields in ENTITIES.items():
        de = data_entity.create_entity(db, y, pid, ename, None, None)
        for i, f in enumerate(fields):
            spec = {"is_primary_key": True, "pk_ordinal": 1, "is_mandatory": True} if i == 0 else {}
            data_entity.create_field(db, y, de, f, spec)
        ents[ename] = de

    step, brs = {}, {}
    for l1name, l2s in CHART:
        l1 = bfc.create_node(db, y, pid, None, l1name)
        for l2name, procs in l2s:
            l2 = bfc.create_node(db, y, pid, l1.bfc_node_id, l2name)
            for pname, perf, acc, crud, stmt, logic, out, confirmed in procs:
                node = bfc.create_node(db, y, pid, l2.bfc_node_id, pname, is_process=True)
                br = db.scalars(select(BusinessRequirement).where(
                    BusinessRequirement.bfc_node_id == node.bfc_node_id, BusinessRequirement.is_active)).one()
                br = business_requirement.update_br(db, y, br, br.row_version, {
                    "br_statement": stmt, "business_logic": logic, "output_expectation": out},
                    "CONFIRMED" if confirmed else None)
                for ename, letter in crud:
                    business_requirement.link_data_entity(db, y, br, ents[ename].data_entity_id, letter, None)
                raci.link(db, y, BrOrgRole, br, roles[perf].org_role_id, "R")
                if acc != perf:
                    raci.link(db, y, BrOrgRole, br, roles[acc].org_role_id, "A")
                n = _node(db, node.bfc_node_id)
                bfc.set_performer(db, y, n, n.row_version, "ORG_ROLE", perf, None)
                step[pname], brs[pname] = node.bfc_node_id, br.br_id

    # What starts the processes that no other process feeds.
    cust = external_entity.create_party(db, y, pid, "Customer", "CUSTOMER", None)
    bank = external_entity.create_party(db, y, pid, "Bank", "BANK", None)
    supplier = external_entity.create_party(db, y, pid, "Supplier", "SUPPLIER", None)
    bfc.link_external_flow(db, y, _node(db, step["Receive order"]), cust.external_entity_id, "I",
                           ents["Sales order"].data_entity_id, "purchase order (EDI / e-mail)", None)
    bfc.link_external_flow(db, y, _node(db, step["Ship goods"]), cust.external_entity_id, "O", None, "delivery note", None)
    bfc.link_external_flow(db, y, _node(db, step["Post payment"]), bank.external_entity_id, "I",
                           ents["Payment"].data_entity_id, "bank statement", None)
    bfc.link_external_flow(db, y, _node(db, step["Receive goods"]), supplier.external_entity_id, "I", None,
                           "delivery", None)
    bfc.link_external_flow(db, y, _node(db, step["Onboard supplier"]), supplier.external_entity_id, "I", None,
                           "application form", None)
    for tname, kind, sched, procs in [
        ("Quarter start", "TIME", "first working day of the quarter", ["Maintain price list"]),
        ("Weekly replenishment run", "TIME", "Monday 07:00", ["Raise purchase request"]),
        ("Twice-yearly review", "TIME", "April and October", ["Evaluate supplier"]),
        ("Quarterly count plan", "TIME", "per the count calendar", ["Count stock"]),
        ("Month end", "TIME", "last working day, 18:00", ["Close the month"]),
        ("Customer asks for a change", "EVENT", None, ["Amend order"]),
        ("Daily overdue report", "TIME", "08:00", ["Chase overdue"]),
        ("Supplier invoice arrives", "EVENT", None, ["Match supplier invoice"]),
    ]:
        trg = trigger.create_trigger(db, y, pid, tname, kind, sched, None)
        for p in procs:
            trigger.link(db, y, _node(db, step[p]), trg.process_trigger_id, None)

    apps = {}
    for code, aname, life, kind in APPS:
        apps[code] = application.create_application(db, y, pid, code, aname, life, kind, {})

    for sname, cat, app, covers, frs in SOLUTIONS:
        sol = solution.create_solution(db, y, pid, sname, cat, {})
        if app:
            application.link_solution(db, y, sol, apps[app].application_id, None)
        for p in covers:
            solution.link(db, y, db.get(BusinessRequirement, brs[p]), sol.solution_id, None)
        for i, (fname, ftype, cx) in enumerate(frs):
            br_id = brs[covers[min(i, len(covers) - 1)]]
            fr, _ = function_requirement.create_fr(db, y, pid, fname, ftype, sol.solution_id, {}, br_id=br_id)
            effort.rate_fr(db, y, fr, fr.row_version, cx)
    db.commit()

    # v1.0 frozen and approved, then v1.1 frozen, then work after it so "changed since" has something to show.
    on = components.enabled(db, pid)
    for bump, note in [("MAJOR", "Scope agreed at the steering committee"), ("MINOR", "After the procurement workshop")]:
        db.commit()
        prior = baseline.latest(db, pid)
        label = "v1.0" if prior is None else f"v{prior.major_no}.{prior.minor_no + 1}"
        out = baseline.freeze(yamada, pid, note, bump, f"CSR27 {label}", freeze_set.digest(db, pid, on))
        db.expire_all()
        if prior is None:
            b = baseline.latest(db, pid)
            baseline.approve(db, admin, b, "T. Kato (Kaito CIO)", baseline.local_today(), None, "SC-2026-10", b.row_version)
        if label == "v1.0":
            # Between the two freezes: a new process and a reworded requirement.
            node = bfc.create_node(db, y, pid, db.get(BfcNode, step["Receive order"]).parent_bfc_node_id,
                                   "Cancel order", is_process=True)
            br = db.scalars(select(BusinessRequirement).where(
                BusinessRequirement.bfc_node_id == node.bfc_node_id, BusinessRequirement.is_active)).one()
            br = business_requirement.update_br(db, y, br, br.row_version, {
                "br_statement": "Cancel an open order and release its stock and credit",
                "business_logic": "Picked orders cannot be cancelled, only returned.",
                "output_expectation": "A cancelled order; stock and credit released"}, "CONFIRMED")
            business_requirement.link_data_entity(db, y, br, ents["Sales order"].data_entity_id, "R", None)
            business_requirement.link_data_entity(db, y, br, ents["Sales order"].data_entity_id, "U", None)
            raci.link(db, y, BrOrgRole, br, roles["ORDER_CLERK"].org_role_id, "R")
            raci.link(db, y, BrOrgRole, br, roles["SALES_MGR"].org_role_id, "A")
            n = _node(db, node.bfc_node_id)
            bfc.set_performer(db, y, n, n.row_version, "ORG_ROLE", "ORDER_CLERK", None)
            trg = trigger.create_trigger(db, y, pid, "Customer cancels", "EVENT", None, None)
            trigger.link(db, y, _node(db, node.bfc_node_id), trg.process_trigger_id, None)
            step["Cancel order"], brs["Cancel order"] = node.bfc_node_id, br.br_id

    # Work in progress after v1.1: draft edits and one new draft process with no data yet.
    br = db.get(BusinessRequirement, brs["Check credit"])
    business_requirement.update_br(db, y, br, br.row_version, {
        "business_logic": "Remaining limit = credit limit − open receivables − open orders. If the order amount "
                          "exceeds the remaining limit, set the credit result to HOLD and return the order to "
                          "Sales with the shortfall. Key accounts may exceed by 10% with the credit manager's "
                          "approval."}, None)
    bfc.create_node(db, y, pid, db.get(BfcNode, step["Raise invoice"]).parent_bfc_node_id, "Issue credit note",
                    is_process=True)
    db.commit()
    return pid
