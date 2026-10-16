import { useMemo, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar,
  Stack, TextField, Tooltip, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { frApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { Card, Code, PurpleTile, Segmented, Tag, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { FrWarnings, GRID_SX, TileRow, Toolbar, solutionOptions } from './frKit';

const EMPTY = { fr_name: '', fr_type_code: '', solution_id: '', description: '' };
const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };
const firstLine = (v) => (v ?? '').split('\n')[0];

function AddFrDialog({ projectId, solutions, onClose, onDone }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const { options: typeOptions } = useCodes(projectId, 'FR_TYPE');
  const m = useMutation({
    // The number, status and the type's behaviour are set by the server (VB law 6).
    mutationFn: () => frApi.create(projectId, { fr_name: f.fr_name.trim(), fr_type_code: f.fr_type_code,
      solution_id: f.solution_id === '' ? null : f.solution_id, description: f.description.trim() || null }),
    onSuccess: (fr) => { onDone(fr); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('frs.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="fr-new-name" label={t('frs.name')} required autoFocus value={f.fr_name}
            onChange={(e) => setF({ ...f, fr_name: e.target.value })} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <SimpleSelect id="fr-new-type" label={t('frs.type')} value={f.fr_type_code}
            onChange={(v) => setF({ ...f, fr_type_code: v })} options={typeOptions().map((c) => ({ value: c.code, label: c.label }))} />
          <SimpleSelect id="fr-new-solution" label={t('frs.solution')} value={f.solution_id} allowEmpty
            emptyLabel={t('frs.noSolution')} onChange={(v) => setF({ ...f, solution_id: v })} options={solutionOptions(solutions)} />
          <TextField id="fr-new-desc" label={t('frs.description')} multiline minRows={2} value={f.description}
            onChange={(e) => setF({ ...f, description: e.target.value })} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('frs.numberMinted')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        {/* DR6a-P2: disabled while in flight, so a double click cannot create two */}
        <Button variant="contained" disabled={m.isPending || !f.fr_name.trim() || !f.fr_type_code}
          onClick={() => { setError(''); m.mutate(); }}>{t('common.create')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// The register's views (D-52): untraced = no live BR link (the D-28 warning, re-based); no solution = no tag,
// which is information only now that the solution is optional (slice10b_schema §6.10).
const FILTERS = ['all', 'untraced', 'unassigned'];

// The FR register (§4.4, D-28), the second tab of the BR–FR map (S6a-4).
export default function FrsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const [showRetired, setShowRetired] = useState(false);
  const [filter, setFilter] = useState('all');
  const q = useQuery({ queryKey: keys.frList(projectId, filter, showRetired),
    queryFn: () => frApi.list(projectId, { includeRetired: showRetired, unlinked: filter === 'untraced',
      unassigned: filter === 'unassigned' }), placeholderData: (prev) => prev });
  const solsQ = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId) });
  const solById = useMemo(() => new Map((solsQ.data ?? []).map((s) => [s.solution_id, s])), [solsQ.data]);
  const { getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const { getLabel: statusLabel } = useCodes(projectId, 'FR_FULFILMENT_STATUS');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const [warnings, setWarnings] = useState([]);
  const rows = q.data ?? [];
  const activeCount = rows.filter((r) => r.is_active).length;
  const untracedCount = rows.filter((r) => r.is_active && r.br_count === 0).length;
  const unassignedCount = rows.filter((r) => r.is_active && !r.solution_id).length;
  const unratedCount = rows.filter((r) => r.is_active && r.effort_days == null).length;

  const columns = [
    { field: 'fr_number', headerName: t('frs.number'), width: 120,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.fr(projectId, row.fr_id)} tabIndex={tabIndex} underline="hover"
          onClick={(e) => e.stopPropagation()}>
          <Code tone={row.is_active ? 'navy' : 'muted'}>{value}</Code></Link>) },
    { field: 'fr_name', headerName: t('frs.name'), flex: 1, minWidth: 220,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%', minWidth: 0 }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary',
            overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</Box>
          {!row.is_active && <Tag tone="neutral">{t('frs.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'fr_type_code', headerName: t('frs.type'), width: 140,
      renderCell: ({ value }) => <Tag tone="navy">{typeLabel(value)}</Tag> },
    { field: 'br_count', headerName: t('frs.brs'), width: 110, type: 'number',
      renderCell: ({ row, value }) => (value == null ? null : value > 0
        ? <Box component="span" sx={{ fontFamily: MONO }}>{value}</Box>
        : row.is_active && (
          <Tooltip title={t('frs.untracedTip')}>
            <Box component="span"><Tag tone="caution">{t('frs.untracedChip')}</Tag></Box>
          </Tooltip>)) },
    { field: 'solution_id', headerName: t('frs.solution'), flex: 1, minWidth: 200,
      valueGetter: (v) => (v ? `${solById.get(v)?.solution_number ?? ''} ${solById.get(v)?.solution_name ?? ''}` : ''),
      renderCell: ({ row }) => (row.solution_id ? (
        <Link component={RouterLink} to={links.solution(projectId, row.solution_id)} underline="hover"
          onClick={(e) => e.stopPropagation()} color="inherit" sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'baseline', minWidth: 0 }}>
          <Code>{solById.get(row.solution_id)?.solution_number ?? ''}</Code>
          <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{solById.get(row.solution_id)?.solution_name ?? ''}</Box></Link>
      ) : <Tag tone="neutral">{t('frs.noSolution')}</Tag>) },
    { field: 'fulfilment_status_code', headerName: t('frs.status'), width: 170,
      renderCell: ({ value }) => <Tag tone="neutral">{statusLabel(value)}</Tag> },
    { field: 'effort_days', headerName: t('frs.trace.effort'), width: 100, type: 'number',
      valueGetter: (v) => (v == null ? null : Number(v)),
      renderCell: ({ value }) => (value == null ? <Box component="span" sx={{ color: 'text.disabled' }}>—</Box>
        : <Box component="span" sx={{ fontFamily: MONO }}>{t('frs.trace.days', { d: value })}</Box>) },
    { field: 'description', headerName: t('frs.description'), flex: 1, minWidth: 180, valueGetter: (v) => firstLine(v) },
  ];

  return (
    <Page title={t('frs.title')} subtitle={t('frs.subtitle')} error={q.error && errorText(q.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('frs.add')}</Button>)}>
      <FrWarnings warnings={warnings} onClose={() => setWarnings([])} />
      {!q.error && q.data && (
        <TileRow>
          <PurpleTile label={t('frs.tiles.shown')} value={activeCount} />
          <Tile label={t('frs.tiles.untraced')} value={untracedCount} tone={untracedCount ? 'caution' : undefined} note={t('frs.tiles.untracedNote')} />
          <Tile label={t('frs.tiles.unassigned')} value={unassignedCount} note={t('frs.tiles.unassignedNote')} />
          <Tile label={t('frs.tiles.unrated')} value={unratedCount} tone={unratedCount ? 'caution' : undefined} note={t('frs.tiles.unratedNote')} />
        </TileRow>)}
      <Card>
        <Toolbar>
          {!q.error && (
            <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('frs.count', { n: activeCount })}</Typography>)}
          <Box sx={{ flex: 1 }} />
          <Segmented size="sm" label={t('frs.filter.label')} value={filter} onChange={setFilter}
            options={FILTERS.map((f) => ({ value: f, label: t(`frs.filter.${f}`) }))} />
          <ShowRetired id="fr-show-retired" checked={showRetired} onChange={setShowRetired} />
        </Toolbar>
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.fr_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.fr(projectId, row.fr_id))}
            localeText={{ noRowsLabel: t('frs.empty') }}
            initialState={{ sorting: { sortModel: [{ field: 'fr_number', sort: 'asc' }] } }}
            sx={GRID_SX} />)}
      </Card>
      {adding && <AddFrDialog projectId={projectId} solutions={solsQ.data} onClose={() => setAdding(false)}
        onDone={(fr) => { qc.invalidateQueries({ queryKey: keys.frs(projectId) });
          qc.invalidateQueries({ queryKey: keys.frTrace() });
          setWarnings(fr.warnings ?? []); setNotice(t('frs.created', { number: fr.fr_number })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
