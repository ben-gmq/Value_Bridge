"""Control rules and the control panel (docs/slice_control_a_spec.md §4; design §7.13, D-19, SC-7). Control is not a
project component — it is always on — so the write names none; its path matches no ROUTE_COMPONENTS fragment."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser
from routers.guards import GuardedRouter, platform_admin, project_ctx
from schemas.control import (ChangeIntensityOut, ControlPanelOut, ControlRuleIn, ControlRuleOut, DataMigrationOut,
                             EngagementOut, HouseRuleIn, HouseRuleOut, MasterDataOut, OrgImpactOut, ResetIn,
                             ResetOut, ResetPreviewOut, VolatilityOut)
from services import control, control_reports

router = GuardedRouter(tags=["control"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT")
_ftc = platform_admin()


@router.get("/projects/{project_id}/control-panel", response_model=ControlPanelOut, **_read.route)
def control_panel(project_id: int):
    return control.panel(project_id)


@router.get("/projects/{project_id}/control-rules", response_model=list[ControlRuleOut], **_read.route)
def list_control_rules(project_id: int, db: Session = Depends(get_db)):
    return control.list_rules(db, project_id)


@router.patch("/projects/{project_id}/control-rules/{analysis_code}", response_model=ControlRuleOut, **_edit.route)
def maintain_control_rule(project_id: int, analysis_code: str, body: ControlRuleIn,
                          user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    values = body.model_dump(exclude={"change_rationale", "row_version"})
    return control.update_rule(db, user, project_id, analysis_code, values, body.change_rationale, body.row_version)


# ---- Control-B report tabs (docs/slice_control_b_spec.md §4): read-only, VIEW, no component ------------------------
@router.get("/projects/{project_id}/requirement-volatility", response_model=VolatilityOut, **_read.route)
def requirement_volatility(project_id: int, db: Session = Depends(get_db)):
    return control_reports.requirement_volatility(db, project_id)


@router.get("/projects/{project_id}/org-impact", response_model=OrgImpactOut, **_read.route)
def org_impact(project_id: int, db: Session = Depends(get_db)):
    return control_reports.org_impact_heatmap(db, project_id)


@router.get("/projects/{project_id}/stakeholder-engagement", response_model=EngagementOut, **_read.route)
def stakeholder_engagement(project_id: int, db: Session = Depends(get_db)):
    return control_reports.stakeholder_engagement(db, project_id)


@router.get("/projects/{project_id}/data-migration", response_model=DataMigrationOut, **_read.route)
def data_migration(project_id: int, db: Session = Depends(get_db)):
    return control_reports.data_migration_map(db, project_id)


# ---- Control-C report tabs (docs/slice_control_c_spec.md §5) -------------------------------------------------------
@router.get("/projects/{project_id}/change-intensity", response_model=ChangeIntensityOut, **_read.route)
def change_intensity(project_id: int, db: Session = Depends(get_db)):
    return control_reports.process_change_intensity(db, project_id)


@router.get("/projects/{project_id}/master-data", response_model=MasterDataOut, **_read.route)
def master_data(project_id: int, db: Session = Depends(get_db)):
    return control_reports.master_data_candidates(db, project_id)


# ---- Control-C: FTC company defaults (platform admins) and reset (EDIT) — spec §3–§5 -------------------------------
@router.get("/control-rules/defaults", response_model=list[HouseRuleOut], **_ftc.route)
def list_house_defaults(db: Session = Depends(get_db)):
    return control.list_house(db)


@router.patch("/control-rules/defaults/{analysis_code}", response_model=HouseRuleOut, **_ftc.route)
def maintain_house_default(analysis_code: str, body: HouseRuleIn, user: AppUser = Depends(current_user),
                           db: Session = Depends(get_db)):
    values = body.model_dump(exclude={"change_rationale", "row_version"})
    return control.update_house(db, user, analysis_code, values, body.change_rationale, body.row_version)


@router.get("/projects/{project_id}/control-rules/reset-preview", response_model=ResetPreviewOut, **_edit.route)
def reset_preview(project_id: int, db: Session = Depends(get_db)):
    return control.reset_preview(db, project_id)


@router.post("/projects/{project_id}/control-rules/reset", response_model=ResetOut, **_edit.route)
def reset_to_house_defaults(project_id: int, body: ResetIn, user: AppUser = Depends(current_user),
                            db: Session = Depends(get_db)):
    return control.reset(db, user, project_id, body.change_rationale, body.stamp.model_dump())
