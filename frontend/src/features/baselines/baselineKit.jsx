import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutlined';
import SwapVertIcon from '@mui/icons-material/SwapVert';
import VerifiedOutlinedIcon from '@mui/icons-material/VerifiedOutlined';
import { Tag } from '../../components/kit';
import { t, tOr } from '../../i18n/t';

// D-50: a change never rests on colour alone — every tag carries an icon and its word. Tones follow mockup 09.
const CHANGE = {
  ADDED: { icon: AddCircleOutlineIcon, tone: 'purple' },
  CHANGED: { icon: EditOutlinedIcon, tone: 'navy' },
  REMOVED: { icon: RemoveCircleOutlineIcon, tone: 'teal' },
  MOVED: { icon: SwapVertIcon, tone: 'neutral' },
};
export const CHANGE_KINDS = Object.keys(CHANGE);

export function ChangeTag({ kind }) {
  const c = CHANGE[kind];
  const Icon = c.icon;
  return <Tag tone={c.tone} icon={<Icon sx={{ fontSize: 14 }} aria-hidden />}>{t(`baselines.change.${kind}`)}</Tag>;
}

// FROZEN is the working state of a version, APPROVED is signed, SUPERSEDED is history.
export function StatusChip({ code, label }) {
  const tone = code === 'APPROVED' ? 'ok' : code === 'FROZEN' ? 'navy' : 'neutral';
  return <Tag tone={tone}>{label ?? code}</Tag>;
}

export function AgreedChip() {
  return (
    <Tag tone="ok" icon={<VerifiedOutlinedIcon sx={{ fontSize: 14 }} aria-hidden />}>
      <span title={t('baselines.agreedHelp')}>{t('baselines.agreed')}</span>
    </Tag>
  );
}

// A row label that starts with its code ("FR-0031 Credit hold", "01.02.02.03 Pack order") splits into the
// code (shown coloured) and the name; a link ("BR-0042 ↔ SOL-0003") and any other label is all name.
export function splitLabel(label = '') {
  const m = /^([A-Z]{2,4}-\d+|\d{2}(?:\.\d{2})*)\s+(?:·\s+)?(?![↔·])(.+)$/s.exec(label);
  return m ? { code: m[1], name: m[2] } : { code: '', name: label };
}

const DATE = { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Bangkok' };
export const fmtDate = (v) => (v ? new Date(v.length === 10 ? `${v}T00:00:00+07:00` : v).toLocaleDateString('en-GB', DATE) : '');
export const fmtDateTime = (v) => (v ? new Date(v).toLocaleString('en-GB', { ...DATE, hour: '2-digit', minute: '2-digit' }) : '');

// A column name the strings file does not name reads as words: "performer_label" → "Performer label".
const words = (c) => c.replace(/_/g, ' ').replace(/^./, (x) => x.toUpperCase());
export const fieldLabel = (c) => tOr(`baselines.field.${c}`, {}, words(c));
export const entityLabel = (e) => tOr(`baselines.entity.${e}`, {}, words(e));
export const areaLabel = (a) => t(`baselines.area.${a}`);

// Frozen values are untrusted text: React renders them as text (law 9).
export function fmtValue(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? t('baselines.yes') : t('baselines.no');
  return String(v);
}

export const fmtDays = (n) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : '0');

export const lineLabel = (k) => tOr(`baselines.line.${k}`, {}, words(k));
