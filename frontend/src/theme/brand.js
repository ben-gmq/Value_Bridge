// THE brand source of truth (playbook §6). Components read these through the MUI theme
// (useTheme / sx tokens) — never a hard-coded hex anywhere else.
// FTC chrome = the Fortience deck palette (§14.2): indigo header/footer, cyan accent.
export const BRAND = {
  ftc: '#2B245C',          // deck Dark 2 — header, footer, light page titles
  ftcCyan: '#04AED6',      // deck accent 3 — header rule, status dot
  ftcViolet: '#7848DC',    // deck accent 4 — avatar
  onFtc: '#FFFFFF',
  onFtc2: '#D9D5F3',       // nav text on indigo (~11:1)
  onFtc3: '#B9B2E6',       // small labels on indigo (~7.5:1)
  onFtcPill: '#FFFFFF',    // active nav pill and logo disc on indigo
  onFtcFill: 'rgba(255,255,255,0.06)',   // quiet controls on indigo
  onFtcHover: 'rgba(255,255,255,0.08)',
  onFtcLine: 'rgba(255,255,255,0.22)',   // control outlines on indigo
};

// Semantic status colours — separate from BRAND, never overridden by it (§6).
export const STATUS_COLOR_MAP = {
  light: { ok: '#1E7A5A', okBg: '#EDF6F1', caution: '#A15C00', cautionBg: '#FBF5EA',
           escalate: '#B3261E', escalateBg: '#FBEDEC' },
  dark:  { ok: '#4FB08D', okBg: '#17261F', caution: '#D9A04E', cautionBg: '#2A2217',
           escalate: '#E0695A', escalateBg: '#2B1A18' },
};

// Neutral + action tokens from the v9 canvas "Colour and type" board.
export const TOKENS = {
  light: {
    page: '#F7F7F8', card: '#FFFFFF', raised: '#F9F9FA', selected: '#EDF1F6',
    line: '#E6E6E9', lineStrong: '#D4D5D9', field: '#CACCD2',
    text: '#111318', text2: '#50545C', muted: '#686C74',
    action: '#1F3A5F', actionHover: '#172D4A', link: '#2B4F7E', data: '#3E6A9E',
    teal: '#7FA6A3', tealText: '#2F5F5D', title: BRAND.ftc,
  },
  dark: {
    page: '#111214', card: '#18191C', raised: '#1F2024', selected: '#1E2733',
    line: '#2A2B30', lineStrong: '#3A3B41', field: '#3A3B41',
    text: '#EDEDEF', text2: '#B4B6BC', muted: '#8B8E96',
    action: '#4A73A8', actionHover: '#5A83B8', link: '#7DA2D6', data: '#6F97CC',
    teal: '#5E8C88', tealText: '#8FC1BD', title: '#EDEDEF',
  },
};
