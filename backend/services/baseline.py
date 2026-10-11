"""The scope-control core (§7.7, §7.13; slice8_schema §5): freeze, approve, read and diff baselines.

A freeze is ONE transaction, opened at REPEATABLE READ before its first statement on a session of its own
(the request session already ran the guard at READ COMMITTED, R2-P6): the consistency check and the 24
INSERT … SELECTs see the same data, an edit committed meanwhile lands in neither half, and a failure leaves
no header and no rows (criteria 15, 30). Concurrent freezes resolve to one baseline and one 409 through the
header's constraints and the lock on the prior header (criterion 37). Nothing here ever updates or deletes a
shadow row; the database refuses it anyway (criteria 26, 55).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AppUser, Baseline, BusinessRequirement, Project
from services import access, audit, components, freeze_set
from services.code_master import resolve
from services.consistency import FREEZE_BLOCKING_WARNINGS, INFORMATIONAL, WARNINGS, consistency_check
from services.freeze_set import BY_TABLE, CURRENT_HASH_SPEC, FREEZE_SET

ICT = ZoneInfo("Asia/Bangkok")           # dates are the engagement's local dates (criterion 45)
LIVE = "live"
CHANGES = ("ADDED", "CHANGED", "REMOVED", "MOVED")
RETRY = "Something changed while freezing. Nothing was saved; freeze again."


# ---- reading ---------------------------------------------------------------------------------------------

def _code_id(db: Session, project_id: int, category: str, code: str) -> int:
    row = next((c for c in resolve(db, project_id, category) if c.code == code), None)
    if row is None:
        raise HTTPException(500, "Something went wrong.")
    return row.code_id


def list_baselines(db: Session, project_id: int) -> list[Baseline]:
    return list(db.scalars(select(Baseline).where(Baseline.project_id == project_id)
                           .order_by(Baseline.major_no.desc(), Baseline.minor_no.desc())))


def latest(db: Session, project_id: int, lock: bool = False) -> Baseline | None:
    q = (select(Baseline).where(Baseline.project_id == project_id)
         .order_by(Baseline.major_no.desc(), Baseline.minor_no.desc()).limit(1))
    if lock:
        q = q.with_for_update(of=Baseline)
    return db.scalars(q).first()


def _next(prior: Baseline | None, bump: str) -> tuple[int, int]:
    if prior is None:
        return 1, 0
    return (prior.major_no + 1, 0) if bump == "MAJOR" else (prior.major_no, prior.minor_no + 1)


def counts(db: Session, baseline_id: int) -> dict[str, int]:
    return {e.table: db.scalar(select(func.count()).select_from(freeze_set.shadow(e.table))
                               .where(freeze_set.shadow(e.table).c.baseline_id == baseline_id))
            for e in FREEZE_SET}


def components_of(db: Session, baseline_id: int) -> list[str]:
    t = freeze_set.shadow("project_component")
    return sorted(db.scalars(select(t.c.component_code).where(t.c.baseline_id == baseline_id)))


def _gate_report(report: dict) -> tuple[dict, dict, dict]:
    """(errors, blocking, warnings): the must-be-empty lines that are not empty, the freeze-blocking warnings
    (S7-3: I/O gaps are already scoped to charts whose DFD is on), and the warnings that never refuse."""
    errors = {k: v for k, v in report.items() if v and k not in INFORMATIONAL | WARNINGS | FREEZE_BLOCKING_WARNINGS}
    blocking = {k: v for k, v in report.items() if v and k in FREEZE_BLOCKING_WARNINGS}
    warnings = {k: v for k, v in report.items() if v and k in WARNINGS}
    return errors, blocking, warnings


def _live_counts(db: Session, project_id: int, on: frozenset[str]) -> dict[str, int]:
    out = {}
    for e in FREEZE_SET:
        q = freeze_set.live_select(e, project_id, on)
        out[e.table] = 0 if q is None else db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    return out


def preview(db: Session, project: Project, bump: str) -> dict:
    """What a freeze now would do (the dialog, §5.1 `next`). Writes nothing."""
    prior = latest(db, project.project_id)
    major, minor = _next(prior, bump)
    label = f"v{major}.{minor}"
    errors, blocking, warnings = _gate_report(consistency_check(project.project_id, db))
    on = components.enabled(db, project.project_id)
    supersedes = None
    if prior is not None:
        supersedes = {"version_label": prior.version_label, "status_code": prior.status_code,
                      "client_approver_name": prior.client_approver_name,
                      "awaiting_sign_off": prior.client_approver_name is None}
    return {"next_label": label, "confirm_text": f"{project.project_code} {label}",
            "preview_digest": freeze_set.digest(db, project.project_id, on),     # DR8-P2
            "supersedes": supersedes, "prior_label": prior.version_label if prior else None, "errors": errors,
            "freeze_blocking": blocking, "warnings": warnings, "components": sorted(on),
            "counts_by_entity": _live_counts(db, project.project_id, on)}


# ---- freeze ----------------------------------------------------------------------------------------------

def freeze(user: AppUser, project_id: int, note: str | None, bump: str, confirm_text: str,
           preview_digest: str) -> dict:
    note = note.strip() if note and note.strip() else None
    with SessionLocal() as tx:
        tx.connection(execution_options={"isolation_level": "REPEATABLE READ"})   # before ANY statement
        try:
            out = _freeze(tx, user, project_id, note, bump, confirm_text, preview_digest)
            tx.commit()
            return out
        except (IntegrityError, OperationalError) as exc:
            tx.rollback()
            # sara L1: only a concurrent freeze (unique) or a concurrent edit (serialization, deadlock) is "again"
            if getattr(exc.orig, "sqlstate", None) in ("23505", "40001", "40P01"):
                raise HTTPException(409, RETRY) from exc
            raise


def _freeze(tx: Session, user: AppUser, project_id: int, note, bump: str, confirm_text: str,
            preview_digest: str) -> dict:
    access.require_project(tx, tx.get(AppUser, user.app_user_id), project_id, "EDIT")  # inside the snapshot
    project = tx.get(Project, project_id)
    prior = latest(tx, project_id, lock=True)
    major, minor = _next(prior, bump)
    label = f"v{major}.{minor}"
    if (confirm_text or "").strip() != f"{project.project_code} {label}":
        raise HTTPException(422, f"Type the project code and version to confirm: {project.project_code} {label}")
    errors, blocking, warnings = _gate_report(consistency_check(project_id, tx))
    if errors or blocking:
        raise HTTPException(409, {"message": "The project is not ready to freeze. Resolve these first.",
                                  "errors": errors, "freeze_blocking": blocking})
    on = components.enabled(tx, project_id)
    # DR8-P2: the person confirmed one preview; freeze exactly that or nothing.
    content_digest = freeze_set.digest(tx, project_id, on)
    if content_digest != preview_digest:
        raise HTTPException(409, "The scope changed since you opened this freeze. Review it again; nothing was saved.")
    b = Baseline(content_digest=content_digest, project_id=project_id, major_no=major, minor_no=minor, note=note,
                 status_code_id=_code_id(tx, project_id, "BASELINE_STATUS", "FROZEN"),
                 hash_spec_version=CURRENT_HASH_SPEC, data_model_depth=project.data_model_depth,
                 prior_baseline_id=prior.baseline_id if prior else None, frozen_by_user_id=user.app_user_id)
    tx.add(b)
    tx.flush()
    n = {}
    for e in FREEZE_SET:
        q = freeze_set.live_select(e, project_id, on)
        if q is None:
            n[e.table] = 0
            continue
        cols = ["source_id", *freeze_set.shadow_columns(e.table), "content_hash"]
        sub = q.subquery()
        t = freeze_set.shadow(e.table)
        tx.execute(insert(t).from_select(["baseline_id", *cols], select(literal(b.baseline_id), *[sub.c[c] for c in cols])))
        n[e.table] = tx.scalar(select(func.count()).select_from(t).where(t.c.baseline_id == b.baseline_id))
    # [Q-17] after the snapshot, so the frozen BR keeps the consultant's DRAFT / CONFIRMED (status is not hashed)
    baselined = _code_id(tx, project_id, "BR_STATUS", "BASELINED")
    tx.execute(update(BusinessRequirement)
               .where(BusinessRequirement.project_id == project_id, BusinessRequirement.is_active,
                      BusinessRequirement.status_code_id != baselined)
               .values(status_code_id=baselined, updated_by=user.app_user_id,
                       row_version=BusinessRequirement.row_version + 1)
               .execution_options(synchronize_session=False))
    if prior is not None:
        prior.status_code_id = _code_id(tx, project_id, "BASELINE_STATUS", "SUPERSEDED")
        prior.updated_by = user.app_user_id
    audit.record(tx, "BASELINE_FROZEN", actor_id=user.app_user_id, project_id=project_id,
                 target_table="baseline", target_id=b.baseline_id,
                 detail={"version_label": label, "hash_spec_version": CURRENT_HASH_SPEC, "components": sorted(on),
                         "content_digest": content_digest,                  # sara M3: a second, append-only record
                         "counts": n, "superseded": prior.version_label if prior else None,
                         "superseded_awaiting_sign_off": bool(prior and prior.client_approver_name is None),
                         "warnings": sorted(warnings)})
    tx.flush()
    tx.refresh(b)
    return {"baseline": header(tx, b), "counts": n, "warnings": warnings}


# ---- approve ---------------------------------------------------------------------------------------------

def approve(db: Session, user: AppUser, b: Baseline, approver: str, approved_on: date, note: str | None,
            reference: str | None, row_version: int) -> dict:
    """§5.2 [Q-9], DR8-P1: record the client's sign-off on the version they actually signed — FROZEN, or
    SUPERSEDED when a later checkpoint was frozen while sign-off was pending. FROZEN becomes APPROVED; a
    SUPERSEDED baseline keeps its status and gains the approval facts. Never undone, never changed."""
    db.refresh(b, with_for_update={"of": Baseline})
    if b.row_version != row_version:
        raise HTTPException(409, "This baseline was changed by someone else. Reload it.")
    if b.client_approver_name is not None:
        raise HTTPException(409, f"{b.version_label} already records the client's approval.")
    require_intact(db, b)                                                     # sara L2
    newer = db.scalar(select(Baseline.version_label).where(
        Baseline.project_id == b.project_id, Baseline.client_approver_name.is_not(None),
        (Baseline.major_no > b.major_no) | ((Baseline.major_no == b.major_no) & (Baseline.minor_no > b.minor_no)))
        .limit(1))
    if newer:
        raise HTTPException(409, f"The client has already approved the later version {newer}.")
    if b.status_code not in ("FROZEN", "SUPERSEDED"):
        raise HTTPException(409, f"{b.version_label} cannot be approved.")
    approver = (approver or "").strip()
    if not approver:
        raise HTTPException(422, "Name the person who approved it for the client")
    if approved_on > local_today():
        raise HTTPException(422, "The approval date cannot be in the future")
    if approved_on < b.frozen_at.astimezone(ICT).date():
        raise HTTPException(422, f"The approval date cannot be before {b.version_label} was frozen")
    b.client_approver_name, b.client_approved_on = approver, approved_on
    b.approval_note = note.strip() if note and note.strip() else None
    b.approval_reference = reference.strip() if reference and reference.strip() else None
    b.approved_at, b.approved_by_user_id = datetime.now(timezone.utc), user.app_user_id
    if b.status_code == "FROZEN":
        b.status_code_id = _code_id(db, b.project_id, "BASELINE_STATUS", "APPROVED")
    b.updated_by = user.app_user_id
    audit.record(db, "BASELINE_APPROVED", actor_id=user.app_user_id, project_id=b.project_id,
                 target_table="baseline", target_id=b.baseline_id,
                 detail={"version_label": b.version_label, "client_approver_name": approver,
                         "client_approved_on": approved_on.isoformat(), "reference": b.approval_reference})
    db.commit()
    db.refresh(b)
    return header(db, b)


def local_today() -> date:
    return datetime.now(ICT).date()


def agreed_id(baselines: list[Baseline]) -> int | None:
    """DR8-P1: the agreed (contractual) baseline is the newest one with a recorded client approval — not a
    status. A wave-2 change request is raised against it."""
    return next((b.baseline_id for b in baselines if b.client_approver_name is not None), None)


def verify(db: Session, b: Baseline) -> bool:
    """DR8-S1, sara M3: the shadows still hold exactly what was frozen — no row added, removed or re-hashed
    (the digest), and no row whose columns no longer match its own hash."""
    if freeze_set.digest(db, b.project_id, frozenset(), b.baseline_id) != b.content_digest:
        return False
    return all(freeze_set.rehash_mismatches(db, e, b.baseline_id, b.hash_spec_version) == 0 for e in FREEZE_SET)


def require_intact(db: Session, b: Baseline) -> None:
    if not verify(db, b):
        raise HTTPException(409, f"{b.version_label} failed its integrity check. Report this to an administrator.")


def header(db: Session, b: Baseline) -> dict:
    names = {u.app_user_id: u.display_name for u in db.scalars(
        select(AppUser).where(AppUser.app_user_id.in_([x for x in (b.frozen_by_user_id, b.approved_by_user_id)
                                                        if x])))}
    return {"baseline_id": b.baseline_id, "project_id": b.project_id, "version_label": b.version_label,
            "major_no": b.major_no, "minor_no": b.minor_no, "status_code": b.status_code,
            "status_label": b.status_code_row.label if b.status_code_row else None,
            "hash_spec_version": b.hash_spec_version, "data_model_depth": b.data_model_depth, "note": b.note,
            "prior_baseline_id": b.prior_baseline_id, "frozen_at": b.frozen_at,
            "frozen_by": names.get(b.frozen_by_user_id), "client_approver_name": b.client_approver_name,
            "client_approved_on": b.client_approved_on, "approval_note": b.approval_note,
            "approval_reference": b.approval_reference,
            "approved_at": b.approved_at, "approved_by": names.get(b.approved_by_user_id),
            "row_version": b.row_version}


def detail(db: Session, b: Baseline) -> dict:
    return {**header(db, b), "intact": verify(db, b), "components": components_of(db, b.baseline_id), "counts": counts(db, b.baseline_id)}


# ---- rows of one side ------------------------------------------------------------------------------------

def _side_rows(db: Session, project_id: int, side, table: str, on: frozenset[str] | None = None) -> dict[int, dict]:
    """{source_id: row} of one entity on one side: a Baseline, or LIVE (the freeze's own SELECT)."""
    e = BY_TABLE[table]
    if side == LIVE:
        q = freeze_set.live_select(e, project_id, on if on is not None else components.enabled(db, project_id))
        if q is None:
            return {}
        rows = db.execute(q).mappings()
    else:
        t = freeze_set.shadow(table)
        rows = db.execute(select(t).where(t.c.baseline_id == side.baseline_id).order_by(t.c.source_id)).mappings()
    return {r["source_id"]: dict(r) for r in rows}


def _own_label(e, row: dict) -> str:
    return " ".join(str(row[c]) for c in e.label_columns if row.get(c) not in (None, ""))


class _Labeller:
    """Labels rows from the rows of the same side, so a removed link to a removed BR still reads
    'BR-0042 ↔ SOL-0003' (§5.3)."""

    def __init__(self, db: Session, project_id: int, side, cache: dict, on=None):
        self.db, self.project_id, self.side, self.cache, self.on = db, project_id, side, cache, on

    def rows(self, table: str) -> dict[int, dict]:
        if table not in self.cache:
            self.cache[table] = _side_rows(self.db, self.project_id, self.side, table, self.on)
        return self.cache[table]

    def label(self, table: str, row: dict) -> str:
        e = BY_TABLE[table]
        ends = []
        for col, target in e.refs:
            ref = self.rows(target).get(row.get(col))
            if ref is not None:
                ends.append(self.label(target, ref) if BY_TABLE[target].refs else _own_label(BY_TABLE[target], ref))
            elif row.get(col) is not None:
                ends.append(f"#{row.get(col)}")
        own = _own_label(e, row)
        parts = (" ↔ ".join(ends), own) if len(e.refs) > 1 else (own, " ↔ ".join(ends))   # a link reads by its ends
        return " · ".join(x for x in parts if x)


def rows(db: Session, b: Baseline, table: str, offset: int, limit: int) -> dict:
    """§5.4: the snapshot rows of one frozen entity, paged in SQL (sara L7) — labels shown, never code ids."""
    if table not in BY_TABLE:
        raise HTTPException(400, "Not a frozen entity")
    t = freeze_set.shadow(table)
    total = db.scalar(select(func.count()).select_from(t).where(t.c.baseline_id == b.baseline_id))
    page = [dict(r) for r in db.execute(select(t).where(t.c.baseline_id == b.baseline_id)
                                        .order_by(t.c.source_id).offset(offset).limit(limit)).mappings()]
    lab = _Labeller(db, b.project_id, b, {})
    hidden = {"project_id", "baseline_id", "content_hash", f"baseline_{table}_id"} | {
        c for c in freeze_set.shadow_columns(table) if c.endswith("_code_id")}
    return {"entity": table, "area": BY_TABLE[table].area, "total": total,
            "columns": [c for c in freeze_set.shadow_columns(table) if c not in hidden],
            "rows": [{"source_id": r["source_id"], "label": lab.label(table, r),
                      **{k: v for k, v in r.items() if k not in hidden and k != "source_id"}} for r in page]}


# ---- diff ------------------------------------------------------------------------------------------------

def resolve_side(db: Session, project_id: int, ref: str):
    """A diff side: 'live', or the id of a baseline of THIS project — anything else is 404 (S3, criterion 50)."""
    if ref == LIVE:
        return LIVE
    b = db.get(Baseline, int(ref)) if str(ref).isdigit() else None
    if b is None or b.project_id != project_id:
        raise HTTPException(404, access.NOT_FOUND)
    return b


def _spec(side) -> int:
    return CURRENT_HASH_SPEC if side == LIVE else side.hash_spec_version


def _label_of(side) -> str:
    return "LIVE" if side == LIVE else side.version_label


def diff(db: Session, project_id: int, a, b) -> dict:
    """ADDED / CHANGED / REMOVED / MOVED per entity (§7.7, [Q-14], [Q-16])."""
    on_a = frozenset(components.enabled(db, project_id) if a == LIVE else components_of(db, a.baseline_id))
    on_b = frozenset(components.enabled(db, project_id) if b == LIVE else components_of(db, b.baseline_id))
    cache_a, cache_b = {}, {}
    la = _Labeller(db, project_id, a, cache_a, on_a)
    lb = _Labeller(db, project_id, b, cache_b, on_b)
    out, summary = {}, {c: 0 for c in CHANGES}
    for e in FREEZE_SET:
        cols_a, cols_b = freeze_set.columns_for(e, _spec(a)), freeze_set.columns_for(e, _spec(b))
        entry = {"area": e.area, "component_on": {"a": e.gate.open(on_a), "b": e.gate.open(on_b)}}
        if cols_a is None or cols_b is None:      # joined the set later: its rows are ADDED / REMOVED below
            cols_a = cols_b = cols_a or cols_b
        if cols_a != cols_b:
            out[e.table] = {**entry, "status": "SCHEMA_VERSION_MISMATCH", "rows": []}
            continue
        A, B = la.rows(e.table), lb.rows(e.table)
        changes = []
        for sid in sorted(A.keys() | B.keys()):
            ra, rb = A.get(sid), B.get(sid)
            moved = bool(ra and rb and any(ra.get(c) != rb.get(c) for c in e.position_columns))
            if ra is None:
                kind, fields = "ADDED", []
            elif rb is None:
                kind, fields = "REMOVED", []
            elif ra["content_hash"] != rb["content_hash"]:
                kind, fields = "CHANGED", [c for c in cols_a if ra.get(c) != rb.get(c)]
            elif moved:
                kind, fields = "MOVED", [c for c in e.position_columns if ra.get(c) != rb.get(c)]
            else:
                continue
            row = rb or ra
            changes.append({"source_id": sid, "change": kind, "fields": fields, "moved": moved,
                            "label": (lb if rb else la).label(e.table, row),
                            "before": {c: _shown(ra, c) for c in fields} if ra and fields else {},
                            "after": {c: _shown(rb, c) for c in fields} if rb and fields else {}})
            summary[kind] += 1
        out[e.table] = {**entry, "status": "OK", "rows": changes}
    return {"from": _label_of(a), "to": _label_of(b), "summary": summary, "entities": out,
            "_rows": (cache_a, cache_b)}


def _shown(row: dict, col: str):
    """A changed code reads as its label (the code is what was compared; the label is what people read)."""
    if col.endswith("_code") and f"{col[:-5]}_label" in row:
        return row[f"{col[:-5]}_label"] or row[col]
    return _plain(row.get(col))


def _plain(v):
    return float(v) if isinstance(v, Decimal) else v


def priced(d: dict, a, b, on_a: frozenset, on_b: frozenset) -> dict:
    """§7.13 priced_diff over the FR rows the diff already read. Only when EFFORT is on in both sides
    [Q-20]; effort exposed needs SOLUTION on in the side it reads, else it is None, not 0."""
    off = [lbl for lbl, on in ((_label_of(a), on_a), (_label_of(b), on_b)) if "EFFORT" not in on]
    if off:
        return {"available": False, "reason": "EFFORT_OFF", "in": off}
    cache_a, cache_b = d["_rows"]
    A, B = cache_a.get("function_requirement", {}), cache_b.get("function_requirement", {})
    lines = []
    for fid in sorted(A.keys() | B.keys()):
        ea = A[fid]["effort_days"] if fid in A else None
        eb = B[fid]["effort_days"] if fid in B else None
        if fid not in A:
            cls, delta = "ADDED", +(eb or 0)
        elif fid not in B:
            cls, delta = "REMOVED", -(ea or 0)
        elif (eb or 0) != (ea or 0):
            cls, delta = "CHANGED", (eb or 0) - (ea or 0)
        else:
            continue
        row = B.get(fid) or A[fid]
        lines.append({"source_id": fid, "fr_number": row["fr_number"], "fr_name": row["fr_name"], "change": cls,
                      "delta_days": float(delta), "unlinked": row["solution_id"] is None,
                      "unrated": (eb if fid in B else ea) is None})

    def total(pred):
        return float(sum(Decimal(str(x["delta_days"])) for x in lines if pred(x)))
    totals = {"added_days": total(lambda x: x["change"] == "ADDED"),
              "removed_days": total(lambda x: x["change"] == "REMOVED"),
              "changed_days": total(lambda x: x["change"] == "CHANGED"),
              "net_days": total(lambda x: True), "unlinked_days": total(lambda x: x["unlinked"]),
              "unrated_fr_count": sum(1 for x in lines if x["unrated"]),
              "base_days": float(sum((r["effort_days"] or 0) for r in A.values())),
              "effort_exposed_days": _exposed(d, cache_a, cache_b, on_a, on_b)}
    return {"available": True, "lines": lines, "totals": totals}


def _exposed(d, cache_a, cache_b, on_a, on_b) -> float | None:
    """Σ effort of the FRs reachable BR → BR_SOLUTION → SOLUTION → FR from a changed BR, in b (in a for a
    REMOVED BR). Informational, never added to net (Q3)."""
    changed = d["entities"]["business_requirement"]["rows"]
    if not changed:
        return 0.0
    if "SOLUTION" not in on_a | on_b:
        return None
    seen: dict[int, Decimal] = {}
    for r in changed:
        side_rows, on = (cache_a, on_a) if r["change"] == "REMOVED" else (cache_b, on_b)
        if "SOLUTION" not in on:
            continue
        sols = {x["solution_id"] for x in side_rows.get("br_solution", {}).values() if x["br_id"] == r["source_id"]}
        for fid, fr in side_rows.get("function_requirement", {}).items():
            if fr["solution_id"] in sols and fid not in seen:
                seen[fid] = fr["effort_days"] or Decimal(0)
    return float(sum(seen.values()))


def diff_for_api(project_id: int, a_ref: str, b_ref: str, with_price: bool) -> dict:
    """One read-only REPEATABLE READ snapshot (DR8-L3), so a live side never mixes two states of the data.
    Each baseline side must pass its integrity check (DR8-S1)."""
    with SessionLocal() as db:
        db.connection(execution_options={"isolation_level": "REPEATABLE READ", "postgresql_readonly": True})
        a, b = resolve_side(db, project_id, a_ref), resolve_side(db, project_id, b_ref)
        if a == LIVE:
            raise HTTPException(422, "Compare from a baseline: 'from' must be a baseline of this project")
        for side in (a, b):
            if side != LIVE:
                require_intact(db, side)
        d = diff(db, project_id, a, b)
        if with_price:
            on_a = frozenset(components_of(db, a.baseline_id))
            on_b = frozenset(components.enabled(db, project_id) if b == LIVE else components_of(db, b.baseline_id))
            d["pricing"] = priced(d, a, b, on_a, on_b)
        d.pop("_rows")
        db.rollback()
        return d
