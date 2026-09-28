import React from 'react';
import { ThemeProvider, createTheme, CssBaseline, Box } from '@mui/material';
import BfcHierarchy from './screens/01_BfcHierarchy.jsx';
import DfdEditor from './screens/02_DfdEditor.jsx';
import BusinessRequirement from './screens/03_BusinessRequirement.jsx';
import DataEntity from './screens/04_DataEntity.jsx';
import Solution from './screens/05_Solution.jsx';
import FunctionalRequirement from './screens/06_FunctionalRequirement.jsx';
import Issue from './screens/07_Issue.jsx';
import ImportPreview from './screens/08_ImportPreview.jsx';
import Baseline from './screens/09_Baseline.jsx';
import ProjectAccess from './screens/10_ProjectAccess.jsx';

import { BRAND, SURFACE, RADIUS } from './tokens.js';

// BRAND and the other tokens live in tokens.js so screens can import them
// without a circular import through App.jsx.
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: BRAND.primary, light: BRAND.primaryLight, dark: BRAND.primaryDark, contrastText: '#FFFFFF' },
    secondary: { main: BRAND.purpleMid, light: BRAND.purpleLight, dark: BRAND.purple, contrastText: '#FFFFFF' },
    warning: { main: BRAND.amber },
    background: { default: SURFACE.page, paper: SURFACE.card },
    text: { primary: SURFACE.text, secondary: SURFACE.textSecondary, disabled: SURFACE.textMuted },
    divider: SURFACE.border,
    brand: BRAND,
  },
  shape: { borderRadius: RADIUS.field },
  typography: {
    fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
    fontSize: 14,
    h1: { fontSize: 24, fontWeight: 700, letterSpacing: '-0.01em' },
    h2: { fontSize: 16, fontWeight: 700 },
    h3: { fontSize: 14, fontWeight: 700 },
    body1: { fontSize: 14 },
    body2: { fontSize: 13.5 },
    caption: { fontSize: 12.5 },
    button: { textTransform: 'none', fontWeight: 600, fontSize: 14 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: RADIUS.pill, height: 38, paddingInline: 18, whiteSpace: 'nowrap', flexShrink: 0 },
        sizeSmall: { height: 32, paddingInline: 14, fontSize: 13 },
        outlined: { borderColor: SURFACE.borderStrong, color: SURFACE.text },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: RADIUS.field, background: SURFACE.field,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: SURFACE.borderStrong },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: BRAND.purpleMid },
        },
        input: { fontSize: 14 },
      },
    },
    MuiInputLabel: { styleOverrides: { root: { fontSize: 14, '&.Mui-focused': { color: BRAND.purpleLight } } } },
    MuiChip: { styleOverrides: { root: { borderRadius: RADIUS.pill, fontWeight: 600 } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiTableCell: { styleOverrides: { root: { borderColor: SURFACE.border, fontSize: 13.5, paddingBlock: 10 }, head: { color: SURFACE.textMuted, fontWeight: 600, fontSize: 12.5 } } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600, minHeight: 44 } } },
    MuiCheckbox: { defaultProps: { size: 'small' } },
  },
});

const SCREENS = {
  1: BfcHierarchy, 2: DfdEditor, 3: BusinessRequirement, 4: DataEntity, 5: Solution,
  6: FunctionalRequirement, 7: Issue, 8: ImportPreview, 9: Baseline, 10: ProjectAccess,
};

const TITLES = ['Business function chart', 'Data flow diagram', 'Business requirement', 'Data entity', 'Solution',
  'Functional requirement', 'Issue', 'Bulk import preview', 'Baseline', 'Project & access'];
const SHOTS = ['01_bfc-hierarchy', '02_dfd-editor', '03_business-requirement', '04_data-entity', '05_solution',
  '06_functional-requirement', '07_issue', '08_import-preview', '09_baseline', '10_project-access'];

// Index of all screens, shown when no ?screen= is given.
function Gallery() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: SURFACE.page, color: SURFACE.text, p: 5 }}>
      <Box component="h1" sx={{ m: 0, fontSize: 26, fontWeight: 700 }}>Value Bridge — mockups</Box>
      <Box component="p" sx={{ mt: 1, mb: 4, color: SURFACE.textSecondary, fontSize: 14 }}>Dark theme · open a screen, then use ← → to move between screens</Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 3 }}>
        {TITLES.map((t, i) => (
          <Box key={t} component="a" href={`?screen=${i + 1}`} sx={{ textDecoration: 'none', color: 'inherit', borderRadius: `${RADIUS.card}px`, overflow: 'hidden', bgcolor: SURFACE.card, border: `1px solid ${SURFACE.border}`, '&:hover': { borderColor: BRAND.purpleMid } }}>
            <Box component="img" src={`/screenshots/${SHOTS[i]}.png`} alt="" sx={{ display: 'block', width: '100%', aspectRatio: '1440 / 900', objectFit: 'cover' }} />
            <Box sx={{ px: 2.5, py: 1.75, fontSize: 15, fontWeight: 600 }}><Box component="span" sx={{ color: BRAND.purpleLight, fontFamily: 'IBM Plex Mono, monospace', mr: 1 }}>{String(i + 1).padStart(2, '0')}</Box>{t}</Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

export default function App() {
  const param = new URLSearchParams(window.location.search).get('screen');
  const n = Number(param || 0);
  React.useEffect(() => {
    if (!n) return undefined;
    const onKey = (e) => {
      if (e.target.closest('input, textarea, [contenteditable]')) return;
      const next = e.key === 'ArrowRight' ? n % 10 + 1 : e.key === 'ArrowLeft' ? (n + 8) % 10 + 1 : e.key === 'Escape' ? 0 : null;
      if (next === null) return;
      window.location.search = next ? `?screen=${next}` : '';
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [n]);
  if (!SCREENS[n]) return <ThemeProvider theme={theme}><CssBaseline /><Gallery /></ThemeProvider>;
  const Screen = SCREENS[n];
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ width: 1440, height: 900, overflow: 'hidden' }}>
        <Screen />
      </Box>
    </ThemeProvider>
  );
}
