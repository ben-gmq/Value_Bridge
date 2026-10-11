// THE brand source of truth (playbook §6). Components read these through the MUI theme
// (theme.vars.palette.*) — never a hard-coded hex anywhere else.
// D-51: the screen mockups (docs/mockups/src/tokens.js) are the reference. FTC Dark Purple carries the
// rail and the one highlight tile per screen; navy is actions and data; teal is data entities and stores.
export const BRAND = {
  ftc: '#2B245C',          // FTC Dark Purple (deck "Dark 2") — the rail, highlight tiles
  ftcCyan: '#04AED6',      // deck accent 3 — focus accents
  ftcViolet: '#7848DC',    // deck accent 4 — selection, focus, level 5, active nav icon
  purpleLight: '#B9A6F2',  // codes and labels on dark purple tints
  onFtc: '#FFFFFF',
  onFtc2: '#DCD7F2',       // rail text (~11:1 on the rail)
  onFtc3: '#A79FD4',       // rail group labels and icons (~6:1)
  onFtcPill: '#FFFFFF',    // the active rail item and logo tile
  onFtcFill: 'rgba(255,255,255,0.08)',   // quiet controls on the rail
  onFtcHover: 'rgba(255,255,255,0.10)',
  onFtcLine: 'rgba(255,255,255,0.10)',   // dividers on the rail
  onFtcTile: '#CFC6F5',    // labels inside a purple highlight tile
  amber: '#FBAE40',        // deck highlight — reserved for regret-able actions (§6)
};

// Levels 1–5 of the business function chart, stepped in the FTC purple scale (mockup kit LEVEL_COLORS).
export const LEVEL_COLORS = ['#E3DCFA', '#C9B9F5', '#B09AEE', '#9679E5', '#7848DC'];
// On white the outline levels (1–3) need depth to read; 4–5 stay filled light steps with purple text.
export const LEVEL_COLORS_LIGHT = ['#5B3FB8', '#6A50C2', '#7A62CC', '#B09AEE', '#9679E5'];

// Semantic status colours — separate from BRAND, never overridden by it (§6).
export const STATUS_COLOR_MAP = {
  light: { ok: '#1E7A5A', okBg: '#EAF5EF', caution: '#A15C00', cautionBg: '#FBF3E6',
           escalate: '#B3261E', escalateBg: '#FBECEA', neutral: '#5B5869', neutralBg: '#EFEDF4' },
  dark:  { ok: '#6FCBA6', okBg: 'rgba(79,176,141,0.14)', caution: '#FBC46E', cautionBg: 'rgba(251,174,64,0.14)',
           escalate: '#F08A7D', escalateBg: 'rgba(224,105,90,0.16)', neutral: '#B7B4C4', neutralBg: 'rgba(183,180,196,0.10)' },
};

// Neutral + action tokens. Dark = the mockups' purple-tinted SURFACE set (D-51); light is the same system
// on white, kept as the alternate.
export const TOKENS = {
  light: {
    page: '#F6F5F9', card: '#FFFFFF', raised: '#F8F7FB', selected: '#EEEAF8', field: '#FFFFFF',
    line: '#E4E2EC', lineStrong: '#CFCCDA',
    text: '#14121C', text2: '#4E4A5E', muted: '#6B6780',
    action: '#1F3A5F', actionHover: '#172D4A', actionLight: '#2B4F7E', link: '#2B4F7E', data: '#3E6A9E',
    purpleText: '#5B32B8', purpleTint: 'rgba(120,72,220,0.10)', navyTint: 'rgba(31,58,95,0.08)',
    teal: '#2A9BB0', tealText: '#1F6E7C', tealTint: 'rgba(2,120,142,0.10)', onTeal: '#0E1F1E', title: '#14121C',
  },
  dark: {
    page: '#13121A', card: '#1A1922', raised: '#221F2D', selected: '#2A2440', field: '#16151D',
    line: '#2C2A38', lineStrong: '#3B3848',
    text: '#EEEDF3', text2: '#B7B4C4', muted: '#8E8A9E',
    action: '#4A73A8', actionHover: '#5A83B8', actionLight: '#8FB0E0', link: '#8FB0E0', data: '#8FB0E0',
    purpleText: '#B9A6F2', purpleTint: 'rgba(120,72,220,0.16)', navyTint: 'rgba(74,115,168,0.18)',
    teal: '#2A9BB0', tealText: '#7CCBD8', tealTint: 'rgba(2,120,142,0.16)', onTeal: '#0E1F1E', title: '#EEEDF3',
  },
};

export const RADIUS = { card: 24, diagram: 18, field: 14, pill: 999 };
