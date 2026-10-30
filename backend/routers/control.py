"""Control rules and the control panel (docs/slice_control_a_spec.md §4; design §7.13, D-19, SC-7). Control is not a
project component — it is always on — so the write names none; its path matches no ROUTE_COMPONENTS fragment."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser
from routers.guards import GuardedRouter, project_ctx
from schemas.control import ControlPanelOut, ControlRuleIn, ControlRuleOut
from services import control

router = GuardedRouter(tags=["control"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT")


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
