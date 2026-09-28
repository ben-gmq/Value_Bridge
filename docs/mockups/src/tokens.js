// ---------------------------------------------------------------------------
// BRAND — the only source of truth for colour (FTC playbook §6).
// Navy = actions and data. FTC Dark Purple (#2B245C, "Dark 2" in the Fortience
// deck theme) = brand surface, selection and hierarchy. Neutrals carry a faint
// purple tint so dark mode is not flat black and white.
// ---------------------------------------------------------------------------
export const BRAND = {
  primary: '#4A73A8', primaryLight: '#8FB0E0', primaryDark: '#1F3A5F',
  purple: '#2B245C', purpleMid: '#7848DC', purpleLight: '#B9A6F2', purpleTint: 'rgba(120,72,220,0.16)',
  teal: '#2A9BB0', tealText: '#7CCBD8', tealTint: 'rgba(2,120,142,0.16)',
  amber: '#FBAE40',
};

export const SURFACE = {
  page: '#13121A', rail: BRAND.purple, card: '#1A1922', raised: '#221F2D', field: '#16151D',
  border: '#2C2A38', borderStrong: '#3B3848',
  text: '#EEEDF3', textSecondary: '#B7B4C4', textMuted: '#8E8A9E',
};

// Status is semantic and never overridden by BRAND (playbook §6).
export const STATUS_COLOR_MAP = {
  ok: { fg: '#6FCBA6', bg: 'rgba(79,176,141,0.14)', dot: '#4FB08D' },
  caution: { fg: '#FBC46E', bg: 'rgba(251,174,64,0.14)', dot: BRAND.amber },
  escalate: { fg: '#F08A7D', bg: 'rgba(224,105,90,0.16)', dot: '#E0695A' },
  neutral: { fg: SURFACE.textSecondary, bg: 'rgba(183,180,196,0.10)', dot: SURFACE.textMuted },
};

export const RADIUS = { card: 24, diagram: 18, field: 14, pill: 999 };
export const MONO = "'IBM Plex Mono', ui-monospace, monospace";

