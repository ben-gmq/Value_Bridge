"""This database's archive identity (slice16 schema §3.4, §12.7; spec §17 R8, §18 S6, S9). The table is the source
of truth — a config value describes the host, not the data — so the server refuses to start when VB_INSTANCE_ID is
missing, the database is not stamped, or the two differ: a prod backup restored into UAT stops at start-up until
someone deliberately re-stamps it, and never writes under prod's names."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import VbInstance


class NotStamped(RuntimeError):
    pass


def current(db: Session) -> VbInstance:
    row = db.scalar(select(VbInstance))
    if row is None:
        raise NotStamped("This database has no archive identity: run scripts.stamp_instance as the owner")
    return row


def ids(db: Session) -> list[str]:
    """The current id first, then every id the data was stamped under before (their tombstones still count)."""
    row = current(db)
    return [row.instance_id, *row.prior_instance_ids]


def check_startup(db: Session, configured: str | None) -> str:
    if not configured:
        raise NotStamped("VB_INSTANCE_ID is not set")
    stamped = current(db).instance_id
    if stamped != configured:
        raise NotStamped(f"VB_INSTANCE_ID is {configured!r} but this database is stamped {stamped!r}: "
                         "re-stamp it deliberately (scripts.stamp_instance) or fix the setting")
    return stamped
