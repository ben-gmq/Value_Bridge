"""Seed the FTC-wide code_master library (§8). Run from backend/:  python -m seeds.seed_code_master
Idempotent: inserts missing rows, updates labels/sort/behaviour of existing global rows.
Seeds go here via CLI — never in Alembic (§13)."""
from sqlalchemy import select

from database import SessionLocal
from models import CodeMaster

# (category, is_system, [(code, label) or (code, label, behaviour)])
LIBRARY: list[tuple[str, bool, list[tuple]]] = [
    ("PROJECT_ROLE", True, [("OWNER", "Owner"), ("EDITOR", "Editor"), ("REVIEWER", "Reviewer")]),
    ("PROJECT_STATUS", False, [("PLANNING", "Planning"), ("ACTIVE", "Active"),
                               ("ON_HOLD", "On hold"), ("CLOSED", "Closed")]),
    ("RACI_TYPE", False, [("R", "Responsible", "RESPONSIBLE"), ("A", "Accountable", "ACCOUNTABLE"),
                          ("C", "Consulted", "CONSULTED"), ("I", "Informed", "INFORMED")]),
    ("FR_TYPE", False, [("FORM", "Form", "FORM"), ("INTERFACE", "Interface", "INTERFACE"),
                        ("REPORT", "Report", "REPORT"), ("BATCH", "Batch", "BATCH")]),
    ("FR_COMPLEXITY", False, [("SIMPLE", "Simple"), ("MEDIUM", "Medium"), ("COMPLEX", "Complex"),
                              ("VERY_COMPLEX", "Very complex")]),
    ("SOLUTION_CATEGORY", False, [("ORG_AND_RULES", "Organization & rules"), ("PEOPLE", "People"),
                                  ("PROCESS", "Process"), ("DATA", "Data"),
                                  ("TECHNOLOGY", "Technology")]),
    ("SOLUTION_STATUS", False, [("PROPOSED", "Proposed"), ("AGREED", "Agreed"),
                                ("IN_DELIVERY", "In delivery"), ("DELIVERED", "Delivered"),
                                ("REJECTED", "Rejected")]),
    ("APP_LIFECYCLE", True, [("AS_IS", "As-is"), ("TO_BE", "To-be"), ("BOTH", "Both")]),
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
    ("FLOW_TYPE", True, [("SEQUENCE", "Sequence"), ("CONDITIONAL", "Conditional"),
                         ("PARALLEL", "Parallel"), ("HANDOFF", "Hand-off")]),
    ("BASELINE_STATUS", True, [("DRAFT", "Draft"), ("FROZEN", "Frozen"), ("APPROVED", "Approved"),
                               ("SUPERSEDED", "Superseded")]),
    ("BR_STATUS", False, [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"),
                          ("BASELINED", "Baselined"), ("SUPERSEDED", "Superseded")]),
    ("FR_FULFILMENT_STATUS", False, [("SPECIFIED", "Specified"),
                                     ("ACCEPTED_BY_VENDOR", "Accepted by vendor"),
                                     ("BUILT", "Built"), ("TESTED", "Tested"),
                                     ("DEFERRED", "Deferred")]),
    ("ISSUE_SEVERITY", False, [("CRITICAL", "Critical"), ("HIGH", "High"), ("MEDIUM", "Medium"),
                               ("LOW", "Low")]),
    ("ISSUE_TYPE", False, [("PROCESS", "Process"), ("DATA", "Data"), ("SYSTEM", "System"),
                           ("ORGANIZATION", "Organization"), ("POLICY", "Policy"),
                           ("OTHER", "Other")]),
    ("ISSUE_STATUS", False, [("OPEN", "Open"), ("IN_PROGRESS", "In progress"),
                             ("RESOLVED", "Resolved"), ("DEFERRED", "Deferred"),
                             ("CLOSED", "Closed")]),
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
    db.commit()
    return added, updated


if __name__ == "__main__":
    with SessionLocal() as session:
        a, u = seed(session)
        print(f"code_master: {a} added, {u} updated")
