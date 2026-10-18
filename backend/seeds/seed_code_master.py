"""Seed the FTC-wide code_master library (§8). Run from backend/:  python -m seeds.seed_code_master
Idempotent: inserts missing rows, updates labels/sort/behaviour of existing global rows.
Seeds go here via CLI — never in Alembic (§13)."""
from sqlalchemy import func, select

from database import SessionLocal
from models import CodeMaster

# Categories that left the library. Their global rows are retired, never deleted: FLOW_TYPE
# became a CHECK-listed column on bfc_node_flow (S2-1); PROJECT_ROLE went with the grants (D-40,
# slice7_schema §8.5 step 3 — old grants still reference its codes).
RETIRED_CATEGORIES = ("FLOW_TYPE", "PROJECT_ROLE")

# (category, is_system, [(code, label) or (code, label, behaviour)])
LIBRARY: list[tuple[str, bool, list[tuple]]] = [
    ("PROJECT_STATUS", False, [("PLANNING", "Planning"), ("ACTIVE", "Active"),
                               ("ON_HOLD", "On hold"), ("CLOSED", "Closed")]),
    ("RACI_TYPE", False, [("R", "Responsible", "RESPONSIBLE"), ("A", "Accountable", "ACCOUNTABLE"),
                          ("C", "Consulted", "CONSULTED"), ("I", "Informed", "INFORMED")]),
    ("FR_TYPE", False, [("FORM", "Form", "FORM"), ("INTERFACE", "Interface", "INTERFACE"),
                        ("REPORT", "Report", "REPORT"), ("BATCH", "Batch", "BATCH"),
                        # S11-5: a one-off data migration covers a BR flow exactly as an interface does
                        ("MIGRATION", "Data migration", "INTERFACE")]),
    ("FR_COMPLEXITY", False, [("SIMPLE", "Simple"), ("MEDIUM", "Medium"), ("COMPLEX", "Complex"),
                              ("VERY_COMPLEX", "Very complex")]),
    ("SOLUTION_CATEGORY", True, [("ORG_AND_RULES", "Organization & rules"), ("PEOPLE", "People"),
                                  ("PROCESS", "Process"), ("DATA", "Data"),
                                  ("TECHNOLOGY", "Technology")]),
    ("SOLUTION_STATUS", False, [("PROPOSED", "Proposed"), ("AGREED", "Agreed"),
                                ("IN_DELIVERY", "In delivery"), ("DELIVERED", "Delivered"),
                                ("REJECTED", "Rejected")]),
    ("APP_LIFECYCLE", True, [("AS_IS", "As-is"), ("TO_BE", "To-be"), ("BOTH", "Both")]),
    # D-67 (slice 13c): what one transaction of a process is. Client vocabulary, never branched on (§3.4).
    ("TRANSACTION_UNIT", False, [("INVOICE", "Invoice"), ("ORDER", "Order"), ("CASE", "Case"), ("DOCUMENT", "Document"),
                                 ("RECORD", "Record"), ("CALL", "Call"), ("PAYMENT", "Payment"),
                                 ("EMPLOYEE", "Employee"), ("OTHER", "Other")]),
    ("APP_KIND", False, [("PACKAGE", "Package"), ("CUSTOM", "Custom"), ("SAAS", "SaaS"),
                         ("PLATFORM", "Platform"), ("RPA", "RPA"), ("INTEGRATION", "Integration"),
                         ("REPORTING", "Reporting")]),
    ("INTERFACE_PATTERN", False, [("PUSH", "Push"), ("PULL", "Pull"),
                                  ("BIDIRECTIONAL", "Bidirectional")]),
    ("INTERFACE_METHOD", False, [("API", "API"), ("FILE", "File"), ("DB", "Database"),
                                 ("MESSAGE", "Message"), ("MANUAL", "Manual")]),
    ("INTERFACE_FREQUENCY", False, [("REALTIME", "Real time"), ("NEAR_REALTIME", "Near real time"),
                                    ("HOURLY", "Hourly"), ("DAILY", "Daily"), ("WEEKLY", "Weekly"),
                                    ("MONTHLY", "Monthly"), ("ON_DEMAND", "On demand")]),
    ("EXTERNAL_ENTITY_KIND", False, [("CUSTOMER", "Customer"), ("SUPPLIER", "Supplier"),
                                     ("BANK", "Bank"), ("REGULATOR", "Regulator"),
                                     ("PARTNER", "Partner"), ("OTHER", "Other")]),
    ("IMPORT_STATUS", True, [("VALIDATING", "Validating"), ("VALIDATED", "Validated"),
                             ("REJECTED", "Rejected"), ("COMMITTED", "Committed")]),
    ("BASELINE_STATUS", True, [("DRAFT", "Draft"), ("FROZEN", "Frozen"), ("APPROVED", "Approved"),
                               ("SUPERSEDED", "Superseded")]),
    ("BR_STATUS", False, [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"),
                          ("BASELINED", "Baselined"), ("SUPERSEDED", "Superseded")]),
    # D-59 (slice11_schema §1.3): no behaviour codes — nothing branches on a kind; "highest priority" is sort_order.
    ("BR_LINE_KIND", False, [("RULE", "Rule"), ("CALCULATION", "Calculation"), ("VALIDATION", "Validation"),
                             ("OUTPUT", "Output"), ("CONTROL", "Control")]),
    ("BR_PRIORITY", False, [("MUST", "Must"), ("SHOULD", "Should"), ("COULD", "Could"), ("WONT", "Won't")]),
    ("FR_FULFILMENT_STATUS", False, [("SPECIFIED", "Specified"),
                                     ("ACCEPTED_BY_VENDOR", "Accepted by vendor"),
                                     ("BUILT", "Built"), ("TESTED", "Tested"),
                                     ("DEFERRED", "Deferred")]),
    ("ISSUE_SEVERITY", False, [("CRITICAL", "Critical"), ("HIGH", "High"), ("MEDIUM", "Medium"),
                               ("LOW", "Low")]),
    ("ISSUE_TYPE", False, [("PROCESS", "Process"), ("DATA", "Data"), ("SYSTEM", "System"),
                           ("ORGANIZATION", "Organization"), ("POLICY", "Policy"),
                           ("OTHER", "Other")]),
    # I-1, slice14 §15 N1–N2: company-only, each status open or closed (migration 0061 set these on existing rows).
    ("ISSUE_STATUS", False, [("OPEN", "Open", "OPEN"), ("IN_PROGRESS", "In progress", "OPEN"),
                             ("RESOLVED", "Resolved", "CLOSED"), ("DEFERRED", "Deferred", "OPEN"),
                             ("CLOSED", "Closed", "CLOSED")]),
    ("ORG_UNIT_LEVEL", False, [("DEPARTMENT", "Department"), ("DIVISION", "Division"),
                               ("SECTION", "Section")]),
    ("FIELD_DATA_TYPE", False, [("STRING", "String"), ("INTEGER", "Integer"),
                                ("DECIMAL", "Decimal"), ("DATE", "Date"),
                                ("DATETIME", "Date and time"), ("BOOLEAN", "Boolean"),
                                ("TEXT", "Text"), ("UUID", "UUID")]),
    ("BENEFIT_TYPE", False, [("COST_REDUCTION", "Cost reduction"), ("REVENUE", "Revenue"),
                             ("PRODUCTIVITY", "Productivity"), ("RISK_REDUCTION", "Risk reduction"),
                             ("COMPLIANCE", "Compliance"), ("CUSTOMER", "Customer")]),
    ("BENEFIT_STATUS", False, [("FORECAST", "Forecast"), ("COMMITTED", "Committed"),
                               ("IN_REALISATION", "In realisation"), ("REALISED", "Realised"),
                               ("ABANDONED", "Abandoned")]),
    ("RISK_PROBABILITY", False, [("RARE", "Rare"), ("UNLIKELY", "Unlikely"),
                                 ("POSSIBLE", "Possible"), ("LIKELY", "Likely"),
                                 ("ALMOST_CERTAIN", "Almost certain")]),
    ("RISK_IMPACT", False, [("NEGLIGIBLE", "Negligible"), ("MINOR", "Minor"),
                            ("MODERATE", "Moderate"), ("MAJOR", "Major"), ("SEVERE", "Severe")]),
    ("RISK_STATUS", False, [("OPEN", "Open"), ("MITIGATING", "Mitigating"), ("CLOSED", "Closed"),
                            ("MATERIALISED", "Materialised")]),
    ("CR_STATUS", False, [("DRAFT", "Draft"), ("ANALYSED", "Analysed"), ("PRICED", "Priced"),
                          ("APPROVED", "Approved"), ("REJECTED", "Rejected"),
                          ("DEFERRED", "Deferred")]),
    ("CR_ORIGIN", False, [("CLIENT", "Client"), ("VENDOR", "Vendor"),
                          ("REGULATORY", "Regulatory"), ("FTC", "FTC"), ("DEFECT", "Defect")]),
    ("PM_DIMENSION", False, [("SCOPE", "Scope"), ("SCHEDULE", "Schedule"), ("COST", "Cost"),
                             ("BENEFIT", "Benefit"), ("RISK", "Risk"), ("QUALITY", "Quality"),
                             ("ORG_CHANGE", "Organizational change"), ("DATA", "Data"),
                             ("VENDOR", "Vendor")]),
    # D-37: the components a project may use. System category: the code branches on it (S5-4).
    ("PROJECT_COMPONENT", True, [("SOLUTION", "Solutions"),
                                 ("FUNCTION_REQUIREMENT", "Function requirements"),
                                 ("APPLICATION", "Applications & interfaces"),
                                 ("EFFORT", "Effort & rate card"), ("ISSUE", "Issues"),
                                 ("TO_BE_DFD", "To-be DFD"), ("AS_IS", "As-is BFC + DFD"),
                                 ("WBS", "WBS"), ("BENEFIT", "Benefits"), ("RISK", "Risks"),
                                 ("CHANGE_REQUEST", "Change requests")]),
    # OR-3: starting points for a new project's component set (contents: seed_project_templates).
    ("PROJECT_TEMPLATE", False, [("REQUIREMENTS_ONLY", "Requirements only"),
                                 ("DATA_AND_PROCESS", "Data & process"),
                                 ("FULL_DELIVERY", "Full delivery")]),
    ("PHASE_STATUS", False, [("PLANNED", "Planned"), ("IN_DELIVERY", "In delivery"),
                             ("COMPLETE", "Complete"), ("CANCELLED", "Cancelled")]),
]


def seed(db) -> tuple[int, int]:
    added = updated = 0
    for category, is_system, rows in LIBRARY:
        for order, row in enumerate(rows, start=1):
            code, label = row[0], row[1]
            behaviour = row[2] if len(row) > 2 else None
            existing = db.scalars(select(CodeMaster).where(
                CodeMaster.project_id.is_(None), CodeMaster.category == category,
                CodeMaster.code == code)).one_or_none()
            if existing is None:
                db.add(CodeMaster(category=category, code=code, label=label,
                                  behaviour_code=behaviour, sort_order=order * 10,
                                  is_system=is_system))
                added += 1
            elif (existing.label, existing.sort_order, existing.is_system) != (label, order * 10, is_system):
                existing.label, existing.sort_order, existing.is_system = label, order * 10, is_system
                updated += 1
            # behaviour_code is never changed here: once referenced it is immutable (Q6).
    for row in db.scalars(select(CodeMaster).where(
            CodeMaster.project_id.is_(None), CodeMaster.category.in_(RETIRED_CATEGORIES),
            CodeMaster.is_active)):
        row.is_active, row.deleted_at = False, func.now()
        updated += 1
    db.commit()
    return added, updated


if __name__ == "__main__":
    with SessionLocal() as session:
        a, u = seed(session)
        print(f"code_master: {a} added, {u} updated")
