"""The one place any VB identifier is minted (§7.1, §9.10). Called at commit, never on load."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ProjectSequence

SERIES = {  # sequence_code → display prefix (§5.3); all ten seeded by create_project (R2-D14)
    "DE": "DE", "BR": "BR", "FR": "FR", "ISSUE": "ISS", "SOL": "SOL",
    "BEN": "BEN", "RSK": "RSK", "CR": "CR", "DEC": "DEC", "EXT": "EXT",
}


class MissingSequence(RuntimeError):
    """A project without all ten series is a consistency failure, not something to repair
    lazily — a lazy insert races on the first number (§5.3 PROJECT_SEQUENCE)."""


def seed_all(db: Session, project_id: int) -> None:
    for code, prefix in SERIES.items():
        db.add(ProjectSequence(project_id=project_id, sequence_code=code, prefix=prefix,
                               pad_width=4, last_value=0))


def next_number(db: Session, project_id: int, sequence_code: str) -> str:
    row = db.scalars(
        select(ProjectSequence)
        .where(ProjectSequence.project_id == project_id,
               ProjectSequence.sequence_code == sequence_code)
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise MissingSequence(f"project {project_id} has no {sequence_code} series")
    row.last_value += 1
    db.flush()
    # Gap-tolerant by design: a rolled-back transaction burns a number (§7.1).
    return f"{row.prefix}-{row.last_value:0{row.pad_width}d}"
