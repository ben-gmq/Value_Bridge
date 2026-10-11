import { createTheme } from '@mui/material/styles';
import { BRAND, LEVEL_COLORS, RADIUS, STATUS_COLOR_MAP, TOKENS } from './brand';

const scheme = (mode) => {
  const t = TOKENS[mode];
  return {
    palette: {
      mode,
      primary: { main: t.action, dark: t.actionHover, light: t.actionLight, contrastText: '#FFFFFF' },
      secondary: { main: BRAND.ftcViolet, light: t.purpleText, dark: BRAND.ftc, contrastText: '#FFFFFF' },
      success: { main: STATUS_COLOR_MAP[mode].ok },
      warning: { main: mode === 'dark' ? BRAND.amber : STATUS_COLOR_MAP.light.caution },   // regret-able actions only (§6)
      error: { main: STATUS_COLOR_MAP[mode].escalate },
      background: { default: t.page, paper: t.card, subtle: t.raised, field: t.field },
      text: { primary: t.text, secondary: t.text2, disabled: t.muted },
      divider: t.line,
      brand: { ...BRAND, title: t.title, link: t.link, data: t.data, teal: t.teal, tealText: t.tealText, tealTint: t.tealTint,
               onTeal: t.onTeal, selected: t.selected, lineStrong: t.lineStrong, field: t.field, muted: t.muted,
               purpleText: t.purpleText, purpleTint: t.purpleTint, navyTint: t.navyTint, raised: t.raised,
               level1: LEVEL_COLORS[0], level2: LEVEL_COLORS[1], level3: LEVEL_COLORS[2], level4: LEVEL_COLORS[3],
               level5: LEVEL_COLORS[4] },
      status: STATUS_COLOR_MAP[mode],
    },
  };
};

// D-51: dark is the default and light the alternate; component shapes follow the mockups' theme
// (docs/mockups/src/App.jsx): pill buttons 38 high, 14px fields on a field fill, quiet table heads.
export const theme = createTheme({
  cssVariables: { colorSchemeSelector: 'data-vb-theme' },
  colorSchemes: { dark: scheme('dark'), light: scheme('light') },
  defaultColorScheme: 'dark',
  shape: { borderRadius: RADIUS.field },
  typography: {
    fontFamily: "'IBM Plex Sans', 'Noto Sans JP', 'Noto Sans Thai', system-ui, sans-serif",
    fontSize: 14,
    h1: { fontSize: 24, fontWeight: 700, letterSpacing: '-0.01em' },
    h2: { fontSize: 16, fontWeight: 700 },
    h3: { fontSize: 14, fontWeight: 700 },
    h5: { fontWeight: 700, fontSize: 24, letterSpacing: '-0.01em' },        // page title (mockup h1)
    h6: { fontWeight: 700, fontSize: 15 },                                   // card title
    body1: { fontSize: 14 },
    body2: { fontSize: 13.5 },
    caption: { fontSize: 12.5 },
    button: { textTransform: 'none', fontWeight: 600, fontSize: 14 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: RADIUS.pill, minHeight: 38, paddingInline: 18, whiteSpace: 'nowrap', flexShrink: 0 },
        sizeSmall: { minHeight: 32, paddingInline: 14, fontSize: 13 },
        text: { paddingInline: 12 },
        outlined: ({ theme }) => ({ borderColor: theme.vars.palette.brand.lineStrong, color: theme.vars.palette.text.primary }),
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: RADIUS.field, background: theme.vars.palette.background.field,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: theme.vars.palette.brand.lineStrong },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: BRAND.ftcViolet },
        }),
        input: { fontSize: 14 },
      },
    },
    MuiInputLabel: { styleOverrides: { root: ({ theme }) => ({ fontSize: 14, '&.Mui-focused': { color: theme.vars.palette.brand.purpleText } }) } },
    MuiTextField: { defaultProps: { size: 'small' } },
    MuiChip: { styleOverrides: { root: { borderRadius: RADIUS.pill, fontWeight: 600 } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiCard: {
      styleOverrides: {
        root: ({ theme }) => ({ borderRadius: RADIUS.card, border: `1px solid ${theme.vars.palette.divider}`, boxShadow: 'none',
                                backgroundColor: theme.vars.palette.background.paper }),
      },
    },
    MuiCardContent: { styleOverrides: { root: { padding: 20, '&:last-child': { paddingBottom: 20 } } } },
    MuiDialog: { styleOverrides: { paper: ({ theme }) => ({ borderRadius: RADIUS.card, border: `1px solid ${theme.vars.palette.divider}` }) } },
    MuiMenu: { styleOverrides: { paper: { borderRadius: RADIUS.field } } },
    MuiAlert: { styleOverrides: { root: { borderRadius: RADIUS.field } } },
    MuiTableCell: {
      styleOverrides: {
        root: ({ theme }) => ({ borderColor: theme.vars.palette.divider, fontSize: 13.5, paddingBlock: 10 }),
        head: ({ theme }) => ({ color: theme.vars.palette.brand.muted, fontWeight: 600, fontSize: 12.5 }),
      },
    },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600, minHeight: 44 } } },
    MuiToggleButton: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } } },
    MuiCheckbox: { defaultProps: { size: 'small' } },
    MuiTooltip: { styleOverrides: { tooltip: { fontSize: 12.5 } } },
    // Lists (MUI X): a card with quiet heads, as the mockups' tables (D-51).
    MuiDataGrid: {
      styleOverrides: {
        root: ({ theme }) => ({ borderRadius: RADIUS.card, borderColor: theme.vars.palette.divider,
          backgroundColor: theme.vars.palette.background.paper, '--DataGrid-containerBackground': theme.vars.palette.background.paper,
          '& .MuiDataGrid-columnSeparator': { display: 'none' } }),
        columnHeaderTitle: ({ theme }) => ({ color: theme.vars.palette.brand.muted, fontWeight: 600, fontSize: 12.5 }),
        cell: ({ theme }) => ({ borderColor: theme.vars.palette.divider, fontSize: 13.5 }),
        row: ({ theme }) => ({ '&:hover': { backgroundColor: theme.vars.palette.brand.selected } }),
      },
    },
  },
});

export const MONO = "'IBM Plex Mono', ui-monospace, monospace";
