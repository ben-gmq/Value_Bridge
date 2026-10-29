import { useMemo, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Link, Snackbar, Tooltip, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { appApi, ifaceApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code, PurpleTile, Status, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';
import { GRID_SX, TileRow, Toolbar } from '../frs/frKit';
import { Loading, Printable } from '../reports/reportKit';

// Slice 1f §3.6: on paper the grid gives way to a plain table (a data grid prints only the rows and columns in view),
// with the Excel file's columns except effort (a vendor scope print, not an estimate). Text renders through React.
const PRINT_COLS = ['number', 'name', 'type', 'route', 'pattern', 'method', 'frequency', 'carried', 'solution', 'brs',
  'status', 'completeHead'];

function PrintTable({ rows, missingText }) {
  const cell = { border: 1, borderColor: 'divider', p: 0.5, fontSize: 10, textAlign: 'left', verticalAlign: 'top' };
  return (
    <Box component="table" sx={{ display: 'none', '@media print': { display: 'table' }, width: '100%', borderCollapse: 'collapse' }}>
      <thead><tr>{PRINT_COLS.map((c) => (
        <Box component="th" key={c} scope="col" sx={{ ...cell, fontWeight: 700 }}>{t(`interfaces.${c}`)}</Box>))}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.fr_id}>{[r.interface_number, r.interface_name, r.fr_type_label,
          r.is_described ? `${r.source_application_code} → ${r.target_application_code}` : '',
          r.pattern_label, r.method_label, r.frequency_label,
          (r.carried ?? []).map((c) => `${c.de_number} ${c.de_name}${c.note ? ` (${c.note})` : ''}`).join(', '),
          r.solution_number, (r.br_numbers ?? []).join(', '), r.fulfilment_status_label,
          r.is_complete ? t('interfaces.completeChip') : t('interfaces.missingTip', { items: missingText(r.missing) }),
        ].map((v, i) => <Box component="td" key={PRINT_COLS[i]} sx={cell}>{v ?? ''}</Box>)}</tr>))}
      </tbody>
    </Box>
  );
}

// The generated interface list (D-27): one row per interface-behaviour FR, never typed. Incomplete
// interfaces are marked with what they lack (criterion 103, S6b2-1); a pair filter says how many
// interfaces it cannot match because they have no endpoints yet (S6b2-2).
export default function InterfacesPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [status, setStatus] = useState('');
  const params = Object.fromEntries(Object.entries({ source, target, status }).filter(([, v]) => v !== ''));
  const q = useQuery({ queryKey: [...keys.interfaces(projectId), params], queryFn: () => ifaceApi.list(projectId, params),
    placeholderData: (prev) => prev });
  const appsQ = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId) });
  const { codes: statuses } = useCodes(projectId, 'FR_FULFILMENT_STATUS');
  const apps = useMemo(() => (appsQ.data ?? []).map((a) => ({ value: a.application_id, label: `${a.application_code} ${a.application_name}` })),
    [appsQ.data]);
  const rows = q.data?.rows ?? [];
  const hidden = q.data?.unfilterable_incomplete ?? 0;
  const incomplete = rows.filter((r) => !r.is_complete).length;
  const missingText = (m) => m.map((x) => t(`interfaces.missing.${x}`)).join(', ');
  // Slice 1f §3.5: the same filters, as .xlsx. Success is a toast, a failure an alert (playbook §7).
  const [done, setDone] = useState(null);
  const xlsx = useMutation({ mutationFn: () => ifaceApi.export(projectId, params), onSuccess: () => setDone(t('interfaces.exported')) });
  // §3.6: the print states its filters as the Excel does; the not-described count prints in the warning above the list.
  const appCode = (id) => (appsQ.data ?? []).find((a) => String(a.application_id) === String(id))?.application_code ?? `#${id}`;
  const statusLabel = statuses.find((c) => c.code === status)?.label ?? status;
  const filters = source || target || status ? t('interfaces.printFilters', {
    source: source ? appCode(source) : t('interfaces.filterAny'), target: target ? appCode(target) : t('interfaces.filterAny'),
    status: status ? statusLabel : t('interfaces.filterAny') }) : null;

  const columns = [
    { field: 'interface_number', headerName: t('interfaces.number'), width: 110,
      renderCell: ({ row, value }) => (
        <Link component={RouterLink} to={links.fr(projectId, row.fr_id)} underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code>{value}</Code></Link>) },
    { field: 'interface_name', headerName: t('interfaces.name'), flex: 1, minWidth: 200 },
    { field: 'fr_type_label', headerName: t('interfaces.type'), width: 130 },          // S11-7: Data migration told apart
    { field: 'is_complete', headerName: '', width: 120, sortable: false,
      renderCell: ({ row }) => (row.is_complete ? <Status tone="ok" size="sm">{t('interfaces.completeChip')}</Status> : (
        <Tooltip title={t('interfaces.missingTip', { items: missingText(row.missing) })}>
          <Box component="span"><Status tone="caution" size="sm">{t('interfaces.incompleteChip')}</Status></Box>
        </Tooltip>)) },
    { field: 'route', headerName: t('interfaces.route'), width: 220,
      valueGetter: (_, row) => (row.is_described ? `${row.source_application_code} → ${row.target_application_code}` : ''),
      renderCell: ({ row }) => (row.is_described ? (
        <Box component="span" sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'baseline' }}>
          <Code>{row.source_application_code}</Code>→<Code>{row.target_application_code}</Code></Box>) : null) },
    { field: 'pattern_label', headerName: t('interfaces.pattern'), width: 120 },
    { field: 'method_label', headerName: t('interfaces.method'), width: 110 },
    { field: 'frequency_label', headerName: t('interfaces.frequency'), width: 130 },
    { field: 'carried', headerName: t('interfaces.carried'), flex: 1, minWidth: 220, sortable: false,
      valueGetter: (v) => (v ?? []).map((c) => (c.note ? `${c.de_number} (${c.note})` : c.de_number)).join(', ') },
    { field: 'solution_number', headerName: t('interfaces.solution'), width: 110,
      renderCell: ({ value }) => (value ? <Code>{value}</Code> : null) },
    { field: 'br_numbers', headerName: t('interfaces.brs'), width: 160, valueGetter: (v) => (v ?? []).join(', '),
      renderCell: ({ row }) => (
        <Box component="span" sx={{ display: 'inline-flex', gap: 1, overflow: 'hidden' }}>
          {(row.br_numbers ?? []).map((b) => <Code key={b} tone="purple">{b}</Code>)}</Box>) },
    { field: 'fulfilment_status_label', headerName: t('interfaces.status'), width: 140 },
  ];

  return (
    <Page title={t('interfaces.title')} subtitle={t('interfaces.subtitle')} error={q.error && errorText(q.error)}>
      {!q.data && !q.error && <Loading />}
      {q.data && (
        <Printable projectId={projectId} report="interfaces" query={q} data={q.data} filters={filters}>
          <TileRow>
            <PurpleTile label={t('interfaces.tiles.shown')} value={rows.length} />
            <Tile label={t('interfaces.tiles.incomplete')} value={incomplete} tone={incomplete ? 'caution' : undefined}
              note={t('interfaces.tiles.incompleteNote')} />
          </TileRow>
          {hidden > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }} action={(
              <Button size="small" onClick={() => { setSource(''); setTarget(''); }}>{t('interfaces.showUnfilterable')}</Button>)}>
              {t('interfaces.unfilterable', { n: hidden })}</Alert>)}
          {xlsx.error && <Alert severity="error" sx={{ mb: 2 }} className="vb-print-hide">{errorText(xlsx.error, t('interfaces.exportFailed'))}</Alert>}
          <PrintTable rows={rows} missingText={missingText} />
          <Card sx={{ displayPrint: 'none' }}>
            <Toolbar>
              <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('interfaces.count', { n: rows.length })}</Typography>
              <Box sx={{ flex: 1 }} />
              <Box sx={{ width: 220, maxWidth: '100%' }}><SimpleSelect id="if-source" label={t('interfaces.filterSource')} value={source} allowEmpty
                emptyLabel={t('interfaces.filterAny')} onChange={setSource} options={apps} /></Box>
              <Box sx={{ width: 220, maxWidth: '100%' }}><SimpleSelect id="if-target" label={t('interfaces.filterTarget')} value={target} allowEmpty
                emptyLabel={t('interfaces.filterAny')} onChange={setTarget} options={apps} /></Box>
              <Box sx={{ width: 180, maxWidth: '100%' }}><SimpleSelect id="if-status" label={t('interfaces.filterStatus')} value={status} allowEmpty
                emptyLabel={t('interfaces.filterAny')} onChange={setStatus} options={statuses.map((c) => ({ value: c.code, label: c.label }))} /></Box>
              <Button variant="outlined" size="small" disabled={xlsx.isPending} onClick={() => xlsx.mutate()}>
                {t('interfaces.export')}</Button>
            </Toolbar>
            {!q.error && (
              <DataGrid autoHeight rows={rows} getRowId={(r) => r.fr_id} columns={columns} loading={q.isLoading}
                disableRowSelectionOnClick hideFooterSelectedRowCount onRowClick={({ row }) => navigate(links.fr(projectId, row.fr_id))}
                localeText={{ noRowsLabel: t('interfaces.empty') }}
                sx={GRID_SX} />)}
          </Card>
        </Printable>)}
      <Snackbar open={Boolean(done)} autoHideDuration={4000} onClose={() => setDone(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {done ? <Alert severity="success" variant="filled" onClose={() => setDone(null)}>{done}</Alert> : undefined}
      </Snackbar>
    </Page>
  );
}
