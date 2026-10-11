// Small presentation helpers for the requirement screens (D-51, mockup 03). No logic lives here.
import { Tag } from '../../components/kit';

// BR status → tag tone. Presentation only: what a person may set is still SETTABLE_STATUSES on the
// page and business_requirement.SYSTEM_SET_STATUSES on the server.
const STATUS_TONE = { DRAFT: 'neutral', CONFIRMED: 'ok', BASELINED: 'purple', SUPERSEDED: 'neutral' };

export function BrStatusTag({ code, label, sx }) {
  return <Tag tone={STATUS_TONE[code] ?? 'neutral'} sx={sx}>{label}</Tag>;
}

// The pill box shared by the RACI toggle and the solution tags: field fill, hairline, fully round.
export const pillBox = (th) => ({
  display: 'inline-flex', alignItems: 'center', borderRadius: 999, bgcolor: th.vars.palette.background.field,
  border: `1px solid ${th.vars.palette.divider}`,
});
