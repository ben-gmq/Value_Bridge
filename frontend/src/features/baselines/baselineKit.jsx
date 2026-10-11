import { Box, Chip } from '@mui/material';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutlined';
import SwapVertIcon from '@mui/icons-material/SwapVert';
import VerifiedOutlinedIcon from '@mui/icons-material/VerifiedOutlined';
import { t, tOr } from '../../i18n/t';

// D-50: a change never rests on colour alone — every tag carries an icon and its word.
const CHANGE = {
  ADDED: { icon: AddCircleOutlineIcon, fg: 'ok', bg: 'okBg' },
  CHANGED: { icon: EditOutlinedIcon, fg: 'caution', bg: 'cautionBg' },
  REMOVED: { icon: RemoveCircleOutlineIcon, fg: 'escalate', bg: 'escalateBg' },
  MOVED: { icon: SwapVertIcon, fg: null, bg: null },
};
export const CHANGE_KINDS = Object.keys(CHANGE);

export function ChangeTag({ kind }) {
  const c = CHANGE[kind];
  const Icon = c.icon;
  return (
    <Box component="span" sx={(th) => ({
      display: 'inline-flex', alignItems: 'center', gap: 0.5, px: 1, py: 0.25, borderRadius: 1, fontSize: 12.5,
      fontWeight: 600, whiteSpace: 'nowrap',
      color: c.fg ? th.vars.palette.status[c.fg] : th.vars.palette.text.secondary,
      bgcolor: c.bg ? th.vars.palette.status[c.bg] : th.vars.palette.action.hover,
    })}>
      <Icon sx={{ fontSize: 15 }} aria-hidden />{t(`baselines.change.${kind}`)}
    </Box>
  );
}

// FROZEN is the working state of a version, APPROVED is signed, SUPERSEDED is history.
export function StatusChip({ code, label }) {
  const color = code === 'APPROVED' ? 'success' : code === 'FROZEN' ? 'primary' : 'default';
  return <Chip size="small" variant={code === 'SUPERSEDED' ? 'outlined' : 'filled'} color={color} label={label ?? code} />;
}

export function AgreedChip() {
  return <Chip size="small" color="success" variant="outlined" icon={<VerifiedOutlinedIcon />} label={t('baselines.agreed')}
    title={t('baselines.agreedHelp')} />;
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
