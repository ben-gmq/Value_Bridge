"""Which FRs are traced to a requirement — the one definition (VB-005, Control-C3 L1).

An FR is traced when it has a live link to a live BR. The FR register's "untraced" view, the control panel's
`fr_unlinked` rule, the effort summary's "untraced" line and the scope summary's traced / without-BR totals all
read it from here, so they cannot drift apart. Its own module because `function_requirement` imports `effort`."""
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from models import BrFunctionRequirement, BusinessRequirement


def traced_fr_query(project_id: int | None) -> Select:
    """The FR ids with a live link to a live BR — usable as a subquery. `None` = every project (for a caller that
    already narrows by FR id)."""
    q = (select(BrFunctionRequirement.fr_id)
         .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
         .where(BrFunctionRequirement.is_active, BusinessRequirement.is_active))
    return q if project_id is None else q.where(BrFunctionRequirement.project_id == project_id)


def traced_fr_ids(db: Session, project_id: int) -> set[int]:
    return set(db.scalars(traced_fr_query(project_id)))
