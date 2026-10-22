"""Platform-admin grant requests (slice17 spec §7, §9; schema rev 3 §3, §6, §7; AR-13, AR-16…AR-25). One admin asks
for someone's admin rights with a reason; a different, independent admin approves (the user becomes an admin in the
same transaction), rejects with a reason, or any admin cancels.

The database is the control: the grant guard (0076) decides four eyes, the creator rule (AR-24) and independence
(fn_admin_grant_independent — never re-coded here, §16 P3), and the app_user guard (0078) refuses the flag without
this transaction's approval. This service asks the same questions first only to answer in plain words, and turns the
guards' refusals into 409s. Audit rows are for people to read; no rule reads them."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from models import AppUser, AuditEvent, PlatformAdminGrant
from services import audit

STALE_AFTER = timedelta(days=7)                          # §7 / P2: the weekly check names older open requests


def _guarded(db: Session, step) -> None:
    try:
        step()
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23001":                   # a guard's refusal, fixed text
            raise HTTPException(409, exc.orig.diag.message_primary) from exc
        if "uq_pag_open" in str(exc.orig):
            raise HTTPException(409, "Admin rights for this user have already been requested") from exc
        raise


def independent(db: Session, approver_id: int, requester_id: int) -> bool:
    """AR-18 / AR-24, answered by the database function alone."""
    return bool(db.scalar(text("SELECT fn_admin_grant_independent(:a, :r)"), {"a": approver_id, "r": requester_id}))


def request(db: Session, actor: AppUser, user_id: int, reason: str | None) -> PlatformAdminGrant:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Give the reason: who asked for it, and for which engagement")
    target = db.get(AppUser, user_id)
    if target is None:
        raise HTTPException(404, "Not found")
    if not target.is_active or target.is_platform_admin:
        raise HTTPException(409, f"{target.display_name} is not an active user without admin rights")
    if target.created_by == actor.app_user_id:
        raise HTTPException(409, "You created this account, so a request for its admin rights must come from "
                                 "another admin (AR-24)")
    g = PlatformAdminGrant(grant_origin="REQUEST", target_user_id=user_id, reason=reason,
                           requested_by_user_id=actor.app_user_id)
    _guarded(db, lambda: db.add(g))
    audit.record(db, "PLATFORM_ADMIN_GRANT_REQUESTED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=user_id, detail={"grant_id": g.platform_admin_grant_id, "rationale": reason})
    db.commit()
    db.refresh(g)
    return g


def _open(db: Session, grant_id: int, row_version: int) -> PlatformAdminGrant:
    g = db.scalar(select(PlatformAdminGrant).where(PlatformAdminGrant.platform_admin_grant_id == grant_id)
                  .with_for_update())
    if g is None or g.grant_origin != "REQUEST":
        raise HTTPException(404, "Not found")
    if g.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if g.approved_at or g.rejected_at or g.cancelled_at:
        raise HTTPException(409, "This request has already been decided")
    return g


def approve(db: Session, actor: AppUser, grant_id: int, row_version: int) -> PlatformAdminGrant:
    g = _open(db, grant_id, row_version)
    target = db.get(AppUser, g.target_user_id)
    if actor.app_user_id in (g.requested_by_user_id, g.target_user_id):
        raise HTTPException(409, "four eyes: a different admin approves, never the requester or the user themselves")
    if target.created_by == actor.app_user_id:
        raise HTTPException(409, "You created this account, so you cannot approve its admin rights (AR-24)")
    if not independent(db, actor.app_user_id, g.requested_by_user_id):
        raise HTTPException(409, "You and the requester are not independent: one of you made the other an admin or "
                                 "created their account (AR-18, AR-24)")

    def decide():
        g.approved_by_user_id = actor.app_user_id                            # the guard sets the time and xact
        g.updated_by, g.row_version = actor.app_user_id, g.row_version + 1
    _guarded(db, decide)                                                     # the approval first, then the flag
    _guarded(db, lambda: setattr(target, "is_platform_admin", True))
    target.updated_by = actor.app_user_id
    audit.record(db, "PLATFORM_ADMIN_GRANTED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=target.app_user_id,
                 detail={"origin": "REQUEST", "grant_id": g.platform_admin_grant_id,
                         "requested_by": g.requested_by_user_id, "rationale": g.reason})
    _guarded(db, db.commit)
    db.refresh(g)
    return g


def reject(db: Session, actor: AppUser, grant_id: int, reason: str | None, row_version: int) -> PlatformAdminGrant:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Give the reason for rejecting it")
    g = _open(db, grant_id, row_version)
    if actor.app_user_id == g.requested_by_user_id:
        raise HTTPException(409, "The requester cancels their own request; another admin rejects it")

    def decide():
        g.rejected_by_user_id, g.rejection_reason = actor.app_user_id, reason
        g.updated_by, g.row_version = actor.app_user_id, g.row_version + 1
    _guarded(db, decide)
    audit.record(db, "PLATFORM_ADMIN_GRANT_REJECTED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=g.target_user_id, detail={"grant_id": g.platform_admin_grant_id, "rationale": reason})
    db.commit()
    db.refresh(g)
    return g


def cancel(db: Session, actor: AppUser, grant_id: int, row_version: int) -> PlatformAdminGrant:
    g = _open(db, grant_id, row_version)

    def decide():
        g.cancelled_by_user_id = actor.app_user_id
        g.updated_by, g.row_version = actor.app_user_id, g.row_version + 1
    _guarded(db, decide)
    audit.record(db, "PLATFORM_ADMIN_GRANT_CANCELLED", actor_id=actor.app_user_id, target_table="app_user",
                 target_id=g.target_user_id, detail={"grant_id": g.platform_admin_grant_id})
    db.commit()
    db.refresh(g)
    return g


def state(g: PlatformAdminGrant) -> str:
    """Derived from the dates, never stored (Q-67)."""
    return ("APPROVED" if g.approved_at else "REJECTED" if g.rejected_at else "CANCELLED" if g.cancelled_at
            else "OPEN")


def rows(db: Session, grants: list[PlatformAdminGrant]) -> list[dict]:
    """What the pending card shows (P5, S1): the target's email, who created the account and when, whether they have
    signed in, and the request's age."""
    ids = {i for g in grants for i in (g.target_user_id, g.requested_by_user_id, g.approved_by_user_id,
                                       g.rejected_by_user_id, g.cancelled_by_user_id) if i}
    users = {u.app_user_id: u for u in db.scalars(select(AppUser).where(AppUser.app_user_id.in_(ids)))}
    creators = {u.app_user_id: u.display_name for u in db.scalars(select(AppUser).where(
        AppUser.app_user_id.in_({users[g.target_user_id].created_by for g in grants} - {None})))}
    now = db.scalar(select(func.now()))

    def name(i):
        return users[i].display_name if i in users else None
    out = []
    for g in grants:
        t = users[g.target_user_id]
        out.append({"grant_id": g.platform_admin_grant_id, "state": state(g), "reason": g.reason,
                    "target_user_id": t.app_user_id, "target_name": t.display_name, "target_email": t.email,
                    "target_created_by": creators.get(t.created_by), "target_created_at": t.created_at,
                    "target_has_signed_in": t.last_login_at is not None,
                    "requested_at": g.requested_at, "requested_by": name(g.requested_by_user_id),
                    "requested_by_user_id": g.requested_by_user_id, "age_days": (now - g.requested_at).days,
                    "approved_at": g.approved_at, "approved_by": name(g.approved_by_user_id),
                    "rejected_at": g.rejected_at, "rejected_by": name(g.rejected_by_user_id),
                    "rejection_reason": g.rejection_reason,
                    "cancelled_at": g.cancelled_at, "cancelled_by": name(g.cancelled_by_user_id),
                    "row_version": g.row_version})
    return out


def list_requests(db: Session) -> list[dict]:
    """Every request, open first (oldest first), then decided (newest first)."""
    grants = list(db.scalars(select(PlatformAdminGrant).where(PlatformAdminGrant.grant_origin == "REQUEST")))
    grants.sort(key=lambda g: (state(g) != "OPEN",
                               g.requested_at.timestamp() if state(g) == "OPEN" else -g.requested_at.timestamp()))
    return rows(db, grants)


def weekly_admin_lines(db: Session) -> dict:
    """Criterion 12 (§7, P2, N3, N4, N5): the facts the weekly check reports, read from database-set columns only.
    Shown on the Removals tab once slice 16's weekly check exists (AR-23)."""
    now = db.scalar(select(func.now()))
    week = now - timedelta(days=7)
    grants = list(db.scalars(select(PlatformAdminGrant)))
    granted = {g.target_user_id for g in grants if g.approved_at}
    admins = list(db.scalars(select(AppUser).where(AppUser.is_active, AppUser.is_platform_admin)))
    removed = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PLATFORM_ADMIN_REMOVED",
                                                  AuditEvent.occurred_at >= week)).all()
    return {
        "open_over_7_days": [g.platform_admin_grant_id for g in grants
                             if state(g) == "OPEN" and g.grant_origin == "REQUEST" and now - g.requested_at > STALE_AFTER],
        "approved_last_7_days": [g.platform_admin_grant_id for g in grants
                                 if g.grant_origin == "REQUEST" and g.approved_at and g.approved_at >= week],
        "live_admins_below_two": len(admins) < 2,
        "admins_without_a_grant": sorted(a.app_user_id for a in admins if a.app_user_id not in granted),
        "owner_grants_last_7_days": [{"grant_id": g.platform_admin_grant_id, "origin": g.grant_origin,
                                      "backdated": g.approved_at < g.recorded_at}
                                     for g in grants if g.grant_origin != "REQUEST" and g.source_audit_event_id is None
                                     and g.recorded_at >= week],
        "legacy_without_asker": [g.platform_admin_grant_id for g in grants
                                 if g.grant_origin == "LEGACY" and g.requested_by_user_id is None],
        "admins_removed_last_7_days": sorted({e.target_id for e in removed}),
        "admins_deactivated_last_7_days": sorted(u.app_user_id for u in db.scalars(select(AppUser).where(
            AppUser.is_platform_admin, AppUser.deleted_at.is_not(None), AppUser.deleted_at >= week))),
    }
