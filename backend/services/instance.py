"""This database's archive identity (slice16 schema §3.4, §12.7; spec §17 R8, §18 S6, S9). The table is the source
of truth — a config value describes the host, not the data — so the server refuses to start when VB_INSTANCE_ID is
missing, the database is not stamped, or the two differ: a prod backup restored into UAT stops at start-up until
someone deliberately re-stamps it, and never writes under prod's names."""
from urllib.parse import urlsplit

from sqlalchemy import select, text
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


SINGLE_OWNER = "LOCAL_SINGLE_OWNER"


def approvers_required(db: Session) -> int:
    """How many admins a removal or an admin grant needs (0079, docs/approvers_setting_spec.md): the database's
    fn_approvers_required() — 1 only on a declared single-owner installation set to 1, otherwise 2. Never re-coded."""
    return int(db.scalar(text("SELECT public.fn_approvers_required()")))


def check_startup(db: Session, configured: str | None, configured_kind: str | None = None) -> str:
    if not configured:
        raise NotStamped("VB_INSTANCE_ID is not set")
    row = current(db)
    stamped = row.instance_id
    if stamped != configured:
        raise NotStamped(f"VB_INSTANCE_ID is {configured!r} but this database is stamped {stamped!r}: "
                         "re-stamp it deliberately (scripts.stamp_instance) or fix the setting")
    why = kind_mismatch(row.installation_kind, configured_kind)
    if why:
        raise NotStamped(why)
    return stamped


def kind_mismatch(db_kind: str | None, configured_kind: str | None) -> str | None:
    """A-Q3 (Ben 2026-10-24), the one rule for the server, the archive writer, the weekly check and the removal run: a
    single-owner database needs the host to say so too — a copy restored elsewhere stops. None when they agree."""
    if db_kind == SINGLE_OWNER and configured_kind != SINGLE_OWNER:
        return ("This database is declared a local single-owner installation, but VB_INSTALLATION_KIND is "
                f"{configured_kind!r}: set VB_INSTALLATION_KIND={SINGLE_OWNER} on this host, or have the owner "
                "declare the database SHARED (scripts.instance_settings)")
    if SINGLE_OWNER in (db_kind, configured_kind):
        return not_this_computer()
    return None


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def not_this_computer() -> str | None:
    """Ben 2026-10-28 (sara M3, AR-28): one approver only where the app is served to this computer alone — FRONTEND_URL's
    host must be localhost / 127.0.0.1 / ::1. A server with a real address can never run single-owner, even if its
    database or its .env were declared so by mistake. None when the address is local."""
    from config import get_settings
    s = get_settings()
    if "frontend_url" not in s.model_fields_set:        # sara M: the built-in default is not a host's declaration
        return ("Single-owner needs FRONTEND_URL set in this host's .env to a localhost address; it is not set — a "
                "server always needs two approvers")
    host = urlsplit(s.frontend_url or "").hostname
    if host in LOCAL_HOSTS:
        return None
    return (f"Single-owner is allowed only on this computer, but FRONTEND_URL points at {host!r}: a server always "
            "needs two approvers — have the owner declare the database SHARED (scripts.instance_settings)")
