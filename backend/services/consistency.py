"""consistency_check (design §7.12, D11): read-only proofs that a rule the database cannot hold
as a CHECK still holds. Each key is one line of the report; an empty list means it holds.

Lines land with the slice that owns their rule. Slice 4a-3 adds `purge_overdue` (A-4a-5): import
batches past their 90-day window that still hold rows, shown until a purge run removes them, so
a forgotten or failing purge is visible while it runs as a CLI with no schedule."""
from sqlalchemy.orm import Session

from services import import_purge


def consistency_check(db: Session, project_id: int | None = None) -> dict[str, list]:
    """The report for one project, or across every project when project_id is None (operators).
    The caller owns access: a route checks require_project(…, REVIEWER) first (§7.12)."""
    return {
        "purge_overdue": import_purge.overdue(db, project_id),
    }
