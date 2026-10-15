"""Who last saved a row, and when — the "Saved · v7 · K. Yamada 10-15" stamp on a detail panel (mockups 01, 03).
Read-only: from the audit columns every business table carries (models/base.py::AuditMixin)."""
from datetime import datetime

from sqlalchemy.orm import Session

from models import AppUser


def of(db: Session, row) -> dict[str, datetime | str | None]:
    """The row's last save: `updated_at` and the saver's display name (the creator's, before any update)."""
    who = db.get(AppUser, row.updated_by or row.created_by)
    return {"updated_at": row.updated_at, "updated_by_name": who.display_name if who else None}
