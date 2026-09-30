import { createTheme } from '@mui/material/styles';
import { BRAND, STATUS_COLOR_MAP, TOKENS } from './brand';

const scheme = (mode) => {
  const t = TOKENS[mode];
  return {
    palette: {
      mode,
      primary: { main: t.action, dark: t.actionHover, contrastText: '#FFFFFF' },
      secondary: { main: t.data },
      success: { main: STATUS_COLOR_MAP[mode].ok },
      warning: { main: STATUS_COLOR_MAP[mode].caution },   // regret-able actions only (§6)
      error: { main: STATUS_COLOR_MAP[mode].escalate },
      background: { default: t.page, paper: t.card, subtle: t.raised },
      text: { primary: t.text, secondary: t.text2, disabled: t.muted },
      divider: t.line,
      brand: { ...BRAND, title: t.title, link: t.link, teal: t.teal, tealText: t.tealText, onTeal: t.onTeal,
               selected: t.selected, lineStrong: t.lineStrong, field: t.field, muted: t.muted },
      status: STATUS_COLOR_MAP[mode],
    },
  };
};

export const theme = createTheme({
  cssVariables: { colorSchemeSelector: 'data-vb-theme' },
  colorSchemes: { light: scheme('light'), dark: scheme('dark') },
  defaultColorScheme: 'light',
  shape: { borderRadius: 14 },           // fields 14 (tokens board)
  typography: {
    fontFamily: "'IBM Plex Sans', 'Noto Sans JP', system-ui, sans-serif",
    fontSize: 13.5,
    h5: { fontWeight: 700, fontSize: '1.375rem' },          // page title 22/700
    h6: { fontWeight: 700, fontSize: '0.9375rem' },         // section heading 15/700
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiButton: { styleOverrides: { root: { borderRadius: 999 } }, defaultProps: { disableElevation: true } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiCard: { styleOverrides: { root: ({ theme }) => ({ borderRadius: 24, border: `1px solid ${theme.vars.palette.divider}`, boxShadow: 'none' }) } },
    MuiTextField: { defaultProps: { size: 'small' } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
  },
});

export const MONO = "'IBM Plex Mono', ui-monospace, monospace";
