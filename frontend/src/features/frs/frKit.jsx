import { Alert, Box, Stack } from '@mui/material';
import { Code, Status } from '../../components/kit';
import { t, tOr } from '../../i18n/t';

// Shared pieces of the FR screens (Slice 6a), and the layout pieces the solution, FR, effort,
// application and interface screens share (Slice 9, D-51). Built only from the kit and theme tokens.

// The live solutions an FR may sit under, as select options; '' means none (D-28).
export const solutionOptions = (solutions) => (solutions ?? []).filter((s) => s.is_active)
  .map((s) => ({ value: s.solution_id, label: `${s.solution_number} ${s.solution_name}` }));

/** The server's warnings as one shape: [{code, frs}] (D-52 drift, naming FR numbers) or plain codes. */
export const warningList = (ws) => (Array.isArray(ws) ? ws : [])
  .map((w) => (typeof w === 'string' ? { code: w, frs: [] } : { code: w?.code, frs: w?.frs ?? [] }))
  .filter((w) => w.code);

// What the server said about the save — never errors (D-28, DR6a-P2, S6a-5).
export function FrWarnings({ warnings, onClose }) {
  const list = warningList(warnings);
  if (!list.length) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {list.map((w) => (
        <Alert key={w.code} severity="warning" onClose={onClose}>
          {tOr(`frs.warn.${w.code}`, { frs: w.frs.join(', ') }, w.code)}</Alert>
      ))}
    </Stack>
  );
}

/** A detail page title as the mockups draw it: the coloured code, then the name. */
export function CodeTitle({ code, name, tone = 'navy' }) {
  return <><Code tone={tone} sx={{ fontSize: 22, mr: 1.5, fontWeight: 500 }}>{code}</Code>{name}</>;
}

/** The form card's save state, from the record's own row_version (nothing invented). */
export function SaveState({ version, dirty, retired }) {
  if (retired) return <Status tone="neutral" size="sm">{t('frs.kit.retired')}</Status>;
  if (dirty) return <Status tone="caution" size="sm">{t('frs.kit.unsaved')}</Status>;
  return <Status tone="ok" size="sm">{t('frs.kit.saved', { v: version })}</Status>;
}

/** Main column plus a side column (the mockups' 360–380px panel); stacks below 1200px. */
export function TwoCol({ main, side, sideWidth = 360 }) {
  return (
    <Box sx={{ display: 'grid', gap: 2, alignItems: 'start',
      gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: `minmax(0,1fr) ${sideWidth}px` } }}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>{main}</Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>{side}</Box>
    </Box>
  );
}

/** A row of figure tiles (PurpleTile first for the key figure). */
export function TileRow({ children, min = 200 }) {
  return (
    <Box sx={{ display: 'grid', gap: 2, mb: 2, gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${min}px), 1fr))` }}>
      {children}
    </Box>
  );
}

/** A register toolbar inside a card: count on the left, filters on the right; wraps when narrow. */
export function Toolbar({ children }) {
  return (
    <Stack direction="row" useFlexGap sx={{ alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>{children}</Stack>
  );
}

/** DataGrid styling for a grid that sits inside a kit Card: no second frame, quiet head, pointer rows. */
export const GRID_SX = (th) => ({
  border: 0, bgcolor: 'transparent', '--DataGrid-containerBackground': th.vars.palette.background.subtle,
  '& .MuiDataGrid-columnHeaders': { borderRadius: '14px' },
  '& .MuiDataGrid-columnHeaderTitle': { fontWeight: 600, fontSize: 12.5, color: th.vars.palette.brand.muted },
  '& .MuiDataGrid-row': { cursor: 'pointer' },
});

/** A bordered box that lets a wide table scroll inside its card instead of pushing the page. */
export function TableFrame({ children }) {
  return (
    <Box sx={(th) => ({ border: `1px solid ${th.vars.palette.divider}`, borderRadius: '16px', overflowX: 'auto', minWidth: 0,
      '& thead tr': { bgcolor: th.vars.palette.background.subtle } })}>
      {children}
    </Box>
  );
}
