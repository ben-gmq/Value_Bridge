import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Alert, Box, Button, CircularProgress, GlobalStyles, Stack, Typography } from '@mui/material';
import { PrintRounded } from '@mui/icons-material';
import { errorText } from '../../api/client';
import { reportApi } from '../../api/scope';
import { useCodes } from '../../app/useCodes';
import { t } from '../../i18n/t';

// The time a report was worked out, always in ICT (spec §3.1), whatever the browser's own zone.
export function Generated({ at }) {
  const when = new Date(at).toLocaleString('en-GB', { timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short',
    year: 'numeric', hour: '2-digit', minute: '2-digit' });
  return <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1.5 }}>{t('reports.generated', { at: when })}</Typography>;
}

// A report part whose component is off is null from the server (A1); the screen says so rather than "none". The
// component's name is its code_master label, the one the Components settings screen shows.
export function Off({ projectId, component }) {
  const { getLabel } = useCodes(projectId, 'PROJECT_COMPONENT');
  return <Alert severity="info">{t('reports.off', { component: getLabel(component) })}</Alert>;
}

export function Loading() {
  return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={28} /></Box>;
}

// ---- Print to PDF (spec §3.6, function 143; D-42) ----------------------------------------------------------------
// One stylesheet for every printable screen: no buttons or filter controls, light colours on paper, table heads on
// every page, no row split across pages. The left rail and the header hide themselves (AppShell, displayPrint).
// Paper is the card colour: with backgrounds printed (sara M1) the page tint would otherwise print as a grey wash.
const PRINT_CSS = (th) => ({
  '@media print': {
    '*': { printColorAdjust: 'exact', WebkitPrintColorAdjust: 'exact' },          // sara M1: tiles keep their fill
    'html, body, #root, #root > div': { backgroundColor: `${th.vars.palette.background.paper} !important` },
    // a Segmented (the tab and level switchers) is a pill around buttons: hidden whole, never an empty ring
    'button, .MuiButtonBase-root, .MuiToggleButtonGroup-root, .vb-print-hide': { display: 'none !important' },
    '.MuiTypography-noWrap': { whiteSpace: 'normal', overflow: 'visible', textOverflow: 'clip' },   // sara M2
    thead: { display: 'table-header-group' },
    'tr:not(.vb-print-frame), .vb-print-row': { breakInside: 'avoid' },
  },
  '@page': { margin: '14mm 12mm' },
});

// Press → refetch the report → fetch the stamp (one REPORT_PRINTED row) → hold it → the browser's print dialog.
// The stamp is held only for the data and filters it was fetched for, and dropped after printing (round 2 N1), so
// Ctrl+P on its own prints the one-line notice, never an unrecorded report (P2). Paper prints in the light scheme.
function usePrint({ projectId, report, refetch, data, filters }) {
  const [held, setHeld] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const scheme = useRef(null);
  useEffect(() => {
    const root = document.documentElement;
    const before = () => { scheme.current = root.getAttribute('data-vb-theme'); root.setAttribute('data-vb-theme', 'light'); };
    const after = () => {
      if (scheme.current) root.setAttribute('data-vb-theme', scheme.current);
      else root.removeAttribute('data-vb-theme');
      setHeld(null);
    };
    window.addEventListener('beforeprint', before);
    window.addEventListener('afterprint', after);
    return () => { window.removeEventListener('beforeprint', before); window.removeEventListener('afterprint', after); };
  }, []);
  const print = async () => {
    setError(null);
    setBusy(true);
    try {
      const fresh = await refetch({ throwOnError: true });                           // P3: the time printed is the data's
      const stamp = await reportApi.printStamp(projectId, { report, generated_at: fresh.data.generated_at,
        ...(filters ? { filters } : {}) });
      flushSync(() => setHeld({ stamp, data: fresh.data, filters }));
      window.print();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const stamp = held && held.data === data && held.filters === filters ? held.stamp : null;
  return { print, busy, error, stamp };
}

// What every printed page carries (D-42). On paper it is the head of a one-cell frame table, so it repeats on every
// page and takes its own room there, never covering a row (sara M3); on screen the frame is plain blocks.
function StampHeader({ stamp }) {
  return (
    <Box sx={{ fontSize: 11, borderBottom: 1, borderColor: 'divider', pb: 0.5, mb: 1.5 }}>
      {stamp.is_live && <Typography component="div" sx={{ fontSize: 12, fontWeight: 700 }}>{t('reports.print.live')}</Typography>}
      <Typography component="div" sx={{ fontSize: 11 }}>
        {t('reports.print.stamp', { project: `${stamp.project_code} ${stamp.project_name}`, at: stamp.generated_at_text,
          by: stamp.generated_by })}
      </Typography>
      {stamp.filters && <Typography component="div" sx={{ fontSize: 11 }}>{t('reports.print.filters', { filters: stamp.filters })}</Typography>}
    </Box>
  );
}

const FRAME_SX = {
  display: 'block', width: '100%', borderCollapse: 'collapse',
  '& > thead': { display: 'none' }, '& > tbody, & > tbody > tr, & > tbody > tr > td': { display: 'block', p: 0 },
  '@media print': { display: 'table', '& > thead': { display: 'table-header-group' },
    '& > tbody': { display: 'table-row-group' }, '& > tbody > tr': { display: 'table-row' },
    '& > tbody > tr > td': { display: 'table-cell' } },
};

// A printable report: the Generated line and the Print / PDF button above the body; on paper, the stamp on every page
// and the body only under a stamp fetched for this print. `query` is the report's useQuery result; `data` its data.
export function Printable({ projectId, report, query, data, filters = null, children }) {
  const p = usePrint({ projectId, report, refetch: query.refetch, data, filters });
  return (
    <>
      <GlobalStyles styles={PRINT_CSS} />
      <Stack direction="row" useFlexGap className="vb-print-hide"
        sx={{ gap: 1.5, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {data.generated_at && <Generated at={data.generated_at} />}
        <Button variant="outlined" size="small" startIcon={<PrintRounded />} disabled={p.busy} onClick={p.print}
          sx={{ mb: 1.5, ml: 'auto' }}>{t('reports.print.button')}</Button>
      </Stack>
      {p.error && <Alert severity="error" sx={{ mb: 2 }} className="vb-print-hide">{errorText(p.error, t('reports.print.failed'))}</Alert>}
      <Box component="table" sx={{ ...FRAME_SX, ...(p.stamp ? {} : { '@media print': { display: 'none' } }) }}>
        {p.stamp && <thead><tr className="vb-print-frame"><td><StampHeader stamp={p.stamp} /></td></tr></thead>}
        <tbody><tr className="vb-print-frame"><td>{children}</td></tr></tbody>
      </Box>
      {!p.stamp && (
        <Typography sx={{ display: 'none', '@media print': { display: 'block' } }}>{t('reports.print.useButton')}</Typography>)}
    </>
  );
}
