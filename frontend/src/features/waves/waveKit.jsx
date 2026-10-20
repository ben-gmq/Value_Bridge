import { Status } from '../../components/kit';

// A wave's status as a semantic pill. Only the two pinned codes the plan reads (R8) change the tone; every other status
// — and any relabel an FTC admin gives them — shows neutral with its label.
const TONE = { IN_DELIVERY: 'ok', CANCELLED: 'caution' };

export function WaveStatus({ code, label, size = 'sm' }) {
  return <Status tone={TONE[code] ?? 'neutral'} size={size}>{label}</Status>;
}

/** Days as the plan shows them: two decimals, the server's own rounding (R6). */
export const fmtDays = (v) => Number(v ?? 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** A percent without trailing zeros: 40, 33.33. */
export const fmtPct = (v) => String(Number(v));
