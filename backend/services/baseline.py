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
from models import AppUser, Baseline, BaselineArchive, BusinessRequirement, Project, Stakeholder
from services import access, audit, components, dfd_rule, freeze_set
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


def counts(db: Session, baseline_id: int, version: int | None = None) -> dict[str, int | None]:
    """Rows per entity. None (not 0) for an entity not in the set at the baseline's hash spec: it was not
    frozen at that spec, which is different from frozen with no rows (slice10b §5.3)."""
    return {e.table: (None if version is not None and freeze_set.columns_for(e, version) is None else
                      db.scalar(select(func.count()).select_from(freeze_set.shadow(e.table))
                                .where(freeze_set.shadow(e.table).c.baseline_id == baseline_id)))
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


gate_report = _gate_report                    # public name: the Scope dashboard counts the same gate (slice 12, S10)


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
    rule = dfd_rule.rules(tx, project_id)          # D-70: the rule the gate above just applied, same snapshot
    b = Baseline(content_digest=content_digest, project_id=project_id, major_no=major, minor_no=minor, note=note,
                 status_code_id=_code_id(tx, project_id, "BASELINE_STATUS", "FROZEN"),
                 hash_spec_version=CURRENT_HASH_SPEC, data_model_depth=project.data_model_depth,
                 # D-67 (C6): the FTE basis at the freeze, so the baseline's FTE re-derives as frozen
                 fte_working_days=project.working_days_per_year, fte_hours_per_day=project.hours_per_working_day,
                 dfd_rule_to_be=list(rule["TO_BE"]), dfd_rule_as_is=list(rule["AS_IS"]),
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
    owe_archive(tx, b, "SCOPE", user.app_user_id)      # slice 16: the file is owed in the freeze transaction
    audit.record(tx, "BASELINE_FROZEN", actor_id=user.app_user_id, project_id=project_id,
                 target_table="baseline", target_id=b.baseline_id,
                 detail={"version_label": label, "hash_spec_version": CURRENT_HASH_SPEC, "components": sorted(on),
                         "dfd_rule": {k: list(v) for k, v in rule.items()},
                         "content_digest": content_digest,                  # sara M3: a second, append-only record
                         "counts": n, "superseded": prior.version_label if prior else None,
                         "superseded_awaiting_sign_off": bool(prior and prior.client_approver_name is None),
                         "warnings": sorted(warnings), "warning_detail": warning_detail(warnings)})
    tx.flush()
    tx.refresh(b)
    return {"baseline": header(tx, b), "counts": n, "warnings": warnings}


def owe_archive(tx: Session, b: Baseline, part: str, actor_id: int) -> None:
    """Slice 16 (schema §12.3): record the archive file this baseline now owes — SCOPE at the freeze, SIGNOFF at
    the client approval — in the caller's transaction, so a baseline can never exist without its owed row. The
    writer (scripts.write_archives) fills it in later; its failure never touches the freeze."""
    tx.add(BaselineArchive(baseline_id=b.baseline_id, archive_part=part, file_seq=1, project_id=b.project_id,
                           format_version=BaselineArchive.FORMAT_VERSION, created_by=actor_id))
    tx.flush()


# S10b-3 step 1, DR10b-S4: WHICH rows each open warning was about, kept on the append-only freeze record. Business
# numbers only — never names, which a purge could not clean out of audit_event — and at most this many per line.
WARNING_DETAIL_CAP = 100
_NUMBER_KEYS = ("fr_number", "br_number", "de_number", "solution_number", "application_code", "hier_code")


def _number_of(item) -> str | None:
    """A business number from a report row, or None — never free text into the append-only audit."""
    if isinstance(item, dict):
        return next((str(item[k]) for k in _NUMBER_KEYS if item.get(k) is not None), None)
    return None


def warning_detail(warnings: dict[str, list]) -> dict[str, dict]:
    """{line: {"count": n, "numbers": [first WARNING_DETAIL_CAP business numbers]}} for every open warning."""
    out = {}
    for key in sorted(warnings):
        numbers = [n for n in (_number_of(x) for x in warnings[key]) if n is not None]
        out[key] = {"count": len(warnings[key]), "numbers": numbers[:WARNING_DETAIL_CAP]}
    return out


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
    db.flush()                                          # the guard reads the recorded approval
    owe_archive(db, b, "SIGNOFF", user.app_user_id)     # Q-79: the sign-off file, owed with the approval
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
    if freeze_set.digest(db, b.project_id, frozenset(), b.baseline_id, b.hash_spec_version) != b.content_digest:
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
            # D-70 [Q-19]: null on both = frozen before 13b, under the D-38 rule
            "dfd_rule_to_be": b.dfd_rule_to_be, "dfd_rule_as_is": b.dfd_rule_as_is,
            # D-67 [Q-25]: null on both = frozen before 13c (no FTE shown)
            "fte_working_days": b.fte_working_days, "fte_hours_per_day": b.fte_hours_per_day,
            "prior_baseline_id": b.prior_baseline_id, "frozen_at": b.frozen_at,
            "frozen_by": names.get(b.frozen_by_user_id), "client_approver_name": b.client_approver_name,
            "client_approved_on": b.client_approved_on, "approval_note": b.approval_note,
            "approval_reference": b.approval_reference,
            "approved_at": b.approved_at, "approved_by": names.get(b.approved_by_user_id),
            "row_version": b.row_version}


def detail(db: Session, b: Baseline) -> dict:
    return {**header(db, b), "intact": verify(db, b), "components": components_of(db, b.baseline_id), "counts": counts(db, b.baseline_id, b.hash_spec_version)}


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
    if freeze_set.columns_for(BY_TABLE[table], b.hash_spec_version) is None:     # not frozen at this spec
        return {"entity": table, "area": BY_TABLE[table].area, "total": None, "frozen": False,
                "columns": [], "rows": []}
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


BRFR = "br_function_requirement"
BRL = "br_requirement_line"


def _derive_links(lab: "_Labeller") -> dict:
    """slice10b §5.3, DR10b-P1/D1: a side frozen before direct links existed has its links DERIVED from its own
    frozen rows — the 0051 backfill rule applied to the snapshot: BR_SOLUTION ⋈ SOLUTION ⋈ FR tagged with it.
    Keyed by (br_id, fr_id); no source_id, no hash, and a NULL note (DR10b-D2)."""
    sols = lab.rows("solution")
    by_sol: dict = {}
    for fid, fr in lab.rows("function_requirement").items():
        if fr.get("solution_id") is not None:
            by_sol.setdefault(fr["solution_id"], []).append(fid)
    out = {}
    for bs in lab.rows("br_solution").values():
        if bs["solution_id"] not in sols:
            continue
        for fid in by_sol.get(bs["solution_id"], ()):
            out[(bs["br_id"], fid)] = {"source_id": None, "br_id": bs["br_id"], "fr_id": fid, "coverage_note": None,
                                       "content_hash": None, "derived": True}
    return out


def _link_changes(e, A: dict, B: dict, la, lb) -> tuple[list, dict]:
    """The link entity is always matched on its grain (br_id, fr_id), so a derived side and a stored side compare
    pair for pair; an unlink + relink keeps one row and one pair anyway (S1-7)."""
    pa = {(r["br_id"], r["fr_id"]): r for r in A.values()}
    pb = {(r["br_id"], r["fr_id"]): r for r in B.values()}
    changes, counted = [], {c: 0 for c in CHANGES}
    for pair in sorted(pa.keys() | pb.keys()):
        ra, rb = pa.get(pair), pb.get(pair)
        if ra is None:
            kind, fields = "ADDED", []
        elif rb is None:
            kind, fields = "REMOVED", []
        elif ra.get("derived") or rb.get("derived"):
            if ra.get("coverage_note") == rb.get("coverage_note"):
                continue
            kind, fields = "CHANGED", ["coverage_note"]
        elif ra["content_hash"] != rb["content_hash"]:
            kind, fields = "CHANGED", [c for c in ("br_id", "fr_id", "coverage_note") if ra.get(c) != rb.get(c)]
        else:
            continue
        row = rb or ra
        changes.append({"source_id": row["source_id"] if row["source_id"] is not None else (ra or {}).get("source_id"),
                        "pair": list(pair),        # the row's key on screen: a derived row has no source_id
                        "change": kind, "fields": fields, "moved": False,
                        "label": (lb if rb else la).label(e.table, row),
                        "before": {c: _shown(ra, c) for c in fields} if ra and fields else {},
                        "after": {c: _shown(rb, c) for c in fields} if rb and fields else {}})
        counted[kind] += 1
    return changes, counted


def diff(db: Session, project_id: int, a, b) -> dict:
    """ADDED / CHANGED / REMOVED / MOVED per entity (§7.7, [Q-14], [Q-16])."""
    on_a = frozenset(components.enabled(db, project_id) if a == LIVE else components_of(db, a.baseline_id))
    on_b = frozenset(components.enabled(db, project_id) if b == LIVE else components_of(db, b.baseline_id))
    cache_a, cache_b = {}, {}
    la = _Labeller(db, project_id, a, cache_a, on_a)
    lb = _Labeller(db, project_id, b, cache_b, on_b)
    # DR10b-P1/D1: each side frozen before the link entity derives its links once, into its own cache, so the
    # diff, the labels, the priced lines and effort exposed all read the same rows.
    derived = []
    for name, side, lab, cache in (("a", a, la, cache_a), ("b", b, lb, cache_b)):
        if freeze_set.columns_for(BY_TABLE[BRFR], _spec(side)) is None:
            cache[BRFR] = _derive_links(lab)
            derived.append(name)
    out, summary = {}, {c: 0 for c in CHANGES}
    # I-14 (Q-52): issues are counted apart from scope — resolving thirty issues is not thirty scope changes.
    issue_summary = {c: 0 for c in CHANGES}
    raiser = _raiser_names(db, project_id)                    # I-15: today's name, never frozen
    for e in FREEZE_SET:
        cols_a, cols_b = freeze_set.columns_for(e, _spec(a)), freeze_set.columns_for(e, _spec(b))
        entry = {"area": e.area, "component_on": {"a": e.gate.open(on_a), "b": e.gate.open(on_b)}}
        if e.table == BRFR:
            rows_, counted = _link_changes(e, la.rows(e.table), lb.rows(e.table), la, lb)
            for k, v in counted.items():
                summary[k] += v
            out[e.table] = {**entry, "status": "OK", "rows": rows_, "derived_sides": derived}
            continue
        # slice11_schema §5.1: an entity one side's spec predates. Its rows still list as ADDED / REMOVED, but the
        # entry says which side never froze it and they are kept out of the summary: new structure, not new scope.
        unfrozen = {}
        if cols_a is None or cols_b is None:
            side = "both" if cols_a is None and cols_b is None else "a" if cols_a is None else "b"   # sara L3
            unfrozen = {"not_frozen_in": side, "joined_at_spec": min(e.hash_columns)}
            cols_a = cols_b = cols_a or cols_b
        # slice13_schema §3.7 (F3, Q-22): the entity gained fields between the two sides' specs. The stored hashes
        # cover different lists, so the two sides are compared field by field on the older (shorter) list, and the
        # entry names the fields one side never froze ("Volume is not in v1.2"). freeze_set asserts every later
        # list extends the earlier one; anything else is still a mismatch.
        by_fields, extra = False, {}
        if cols_a != cols_b:
            # older = the list of the side frozen at the older spec (never "the shorter one": a list that shrank
            # between specs is not an extension and stays a mismatch)
            older, newer = (cols_a, cols_b) if _spec(a) <= _spec(b) else (cols_b, cols_a)
            if len(newer) <= len(older) or newer[:len(older)] != older:
                out[e.table] = {**entry, "status": "SCHEMA_VERSION_MISMATCH", "rows": []}
                continue
            cols_a, by_fields = older, True
            extra = {"compared_on_spec": min(_spec(a), _spec(b)), "not_compared": list(newer[len(older):])}
        A, B = la.rows(e.table), lb.rows(e.table)
        changes = []
        for sid in sorted(A.keys() | B.keys()):
            ra, rb = A.get(sid), B.get(sid)
            moved = bool(ra and rb and any(ra.get(c) != rb.get(c) for c in e.position_columns))
            if ra is None:
                kind, fields = "ADDED", []
            elif rb is None:
                kind, fields = "REMOVED", []
            elif (any(ra.get(c) != rb.get(c) for c in cols_a) if by_fields
                  else ra["content_hash"] != rb["content_hash"]):
                kind, fields = "CHANGED", [c for c in cols_a if ra.get(c) != rb.get(c)]
            elif moved:
                kind, fields = "MOVED", [c for c in e.position_columns if ra.get(c) != rb.get(c)]
            else:
                continue
            row = rb or ra
            shown = (lambda r, c: raiser.get(r.get(c), r.get(c)) if c == "raised_by_stakeholder_id"
                     else _shown(r, c))
            changes.append({"source_id": sid, "change": kind, "fields": fields, "moved": moved,
                            "label": (lb if rb else la).label(e.table, row),
                            "before": {c: shown(ra, c) for c in fields} if ra and fields else {},
                            "after": {c: shown(rb, c) for c in fields} if rb and fields else {}})
            if not unfrozen:
                (issue_summary if e.area == ISSUE_AREA else summary)[kind] += 1
        out[e.table] = {**entry, "status": "OK", "rows": changes, **extra, **unfrozen}
    return {"from": _label_of(a), "to": _label_of(b), "summary": summary, "issue_summary": issue_summary,
            "entities": out, "_rows": (cache_a, cache_b)}


ISSUE_AREA = "ISSUE"


def _raiser_names(db: Session, project_id: int) -> dict[int, str]:
    """I-15 (Q-53): a baseline freezes the raiser's id only; a comparison shows today's name for it."""
    return dict(db.execute(select(Stakeholder.stakeholder_id, Stakeholder.stakeholder_name)
                           .where(Stakeholder.project_id == project_id)).all())


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
    traced_a = {r["fr_id"] for r in cache_a.get(BRFR, {}).values()}
    traced_b = {r["fr_id"] for r in cache_b.get(BRFR, {}).values()}
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
        traced = traced_b if fid in B else traced_a          # the side the line is read from (slice10b §6.5)
        lines.append({"source_id": fid, "fr_number": row["fr_number"], "fr_name": row["fr_name"], "change": cls,
                      "delta_days": float(delta), "untraced": fid not in traced,
                      "unassigned": row["solution_id"] is None,
                      "unrated": (eb if fid in B else ea) is None})

    def total(pred):
        return float(sum(Decimal(str(x["delta_days"])) for x in lines if pred(x)))
    totals = {"added_days": total(lambda x: x["change"] == "ADDED"),
              "removed_days": total(lambda x: x["change"] == "REMOVED"),
              "changed_days": total(lambda x: x["change"] == "CHANGED"),
              "net_days": total(lambda x: True), "untraced_days": total(lambda x: x["untraced"]),
              "unassigned_days": total(lambda x: x["unassigned"]),
              "unlinked_days": total(lambda x: x["untraced"]),      # pre-10b name of untraced_days, kept for the UI
              "unrated_fr_count": sum(1 for x in lines if x["unrated"]),
              "base_days": float(sum((r["effort_days"] or 0) for r in A.values())),
              "effort_exposed_days": _exposed(d, cache_a, cache_b, on_a, on_b)}
    return {"available": True, "lines": lines, "totals": totals}


def _exposed(d, cache_a, cache_b, on_a, on_b) -> float | None:
    """Σ effort of the FRs reachable BR → BR ↔ FR link → FR from a changed BR, in b (in a for a REMOVED BR);
    slice10b §6.5: needs only FUNCTION_REQUIREMENT, and a pre-v2 side's links are the derived ones in its cache.
    Lines de-duplicated by FR. Informational, never added to net (Q3).
    sara H2 (slice 11a): what a BR says now lives in its requirement lines, so a BR also counts as changed when one
    of its lines was added, removed or changed (a reorder is not a change). Lines one side never froze
    (`not_frozen_in`) are new structure, not a change, and are skipped."""
    changed = [(r["change"], r["source_id"]) for r in d["entities"]["business_requirement"]["rows"]]
    lines = d["entities"].get(BRL, {})
    if not lines.get("not_frozen_in"):
        for r in lines.get("rows", []):
            if r["change"] == "MOVED":
                continue
            side = cache_a if r["change"] == "REMOVED" else cache_b
            row = side.get(BRL, {}).get(r["source_id"])
            if row is not None:
                changed.append((r["change"], row["br_id"]))
    if not changed:
        return 0.0
    if "FUNCTION_REQUIREMENT" not in on_a | on_b:
        return None
    seen: dict[int, Decimal] = {}
    for change, br_id in changed:
        side_rows, on = (cache_a, on_a) if change == "REMOVED" else (cache_b, on_b)
        if "FUNCTION_REQUIREMENT" not in on:
            continue
        frs = side_rows.get("function_requirement", {})
        for link in side_rows.get(BRFR, {}).values():
            if link["br_id"] == br_id and link["fr_id"] in frs and link["fr_id"] not in seen:
                seen[link["fr_id"]] = frs[link["fr_id"]]["effort_days"] or Decimal(0)
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
