"""The one writer of AUDIT_EVENT. Append-only: the app role cannot UPDATE or DELETE it (§6.6)."""
import ipaddress

from sqlalchemy.orm import Session

from models import AuditEvent


def record(db: Session, event_type: str, *, actor_id: int | None = None,
           project_id: int | None = None, target_table: str | None = None,
           target_id: int | None = None, detail: dict | None = None,
           source_ip: str | None = None) -> None:
    db.add(AuditEvent(event_type=event_type, app_user_id=actor_id, project_id=project_id,
                      target_table=target_table, target_id=target_id, detail=detail,
                      source_ip=_ip(source_ip)))


def _ip(value: str | None) -> str | None:
    """Only a real address reaches the inet column; a proxy or test host name does not."""
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None
