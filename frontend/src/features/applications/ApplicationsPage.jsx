import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { appApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { Card, Code, PurpleTile, Tag, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { GRID_SX, TileRow, Toolbar } from '../frs/frKit';

const EMPTY = { application_code: '', application_name: '', lifecycle_code: '', kind_code: '', vendor: '' };
const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };

function AddAppDialog({ projectId, onClose, onDone }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const { options: lifecycleOptions } = useCodes(projectId, 'APP_LIFECYCLE');
  const { options: kindOptions } = useCodes(projectId, 'APP_KIND');
  const m = useMutation({
    mutationFn: () => appApi.create(projectId, { application_code: f.application_code.trim(),
      application_name: f.application_name.trim(), lifecycle_code: f.lifecycle_code,
      kind_code: f.kind_code || null, vendor: f.vendor.trim() || null }),
    onSuccess: (a) => { onDone(a); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('applications.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="app-new-code" label={t('applications.code')} required autoFocus value={f.application_code}
            onChange={(e) => setF({ ...f, application_code: e.target.value.toUpperCase() })}
            helperText={t('applications.codeHelp')} slotProps={{ htmlInput: { maxLength: 30 } }} />
          <TextField id="app-new-name" label={t('applications.name')} required value={f.application_name}
            onChange={set('application_name')} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <SimpleSelect id="app-new-lifecycle" label={t('applications.lifecycle')} value={f.lifecycle_code}
            onChange={(v) => setF({ ...f, lifecycle_code: v })} options={lifecycleOptions().map((c) => ({ value: c.code, label: c.label }))} />
          <SimpleSelect id="app-new-kind" label={t('applications.kind')} value={f.kind_code} allowEmpty
            emptyLabel={t('applications.noKind')} onChange={(v) => setF({ ...f, kind_code: v })}
            options={kindOptions().map((c) => ({ value: c.code, label: c.label }))} />
          <TextField id="app-new-vendor" label={t('applications.vendor')} value={f.vendor} onChange={set('vendor')}
            slotProps={{ htmlInput: { maxLength: 200 } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !f.application_code.trim() || !f.application_name.trim() || !f.lifecycle_code}
          onClick={() => { setError(''); m.mutate(); }}>{t('common.create')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// The application landscape (§4.4, D-8), under Settings with the other project reference data.
export default function ApplicationsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const [showRetired, setShowRetired] = useState(false);
  const q = useQuery({ queryKey: [...keys.applications(projectId), { retired: showRetired }],
    queryFn: () => appApi.list(projectId, showRetired), placeholderData: (prev) => prev });
  const { getLabel: lifecycleLabel } = useCodes(projectId, 'APP_LIFECYCLE');
  const { getLabel: kindLabel } = useCodes(projectId, 'APP_KIND');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const rows = q.data ?? [];
  const live = rows.filter((r) => r.is_active);

  const columns = [
    { field: 'application_code', headerName: t('applications.code'), width: 150,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.application(projectId, row.application_id)} tabIndex={tabIndex}
          underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code tone={row.is_active ? 'navy' : 'muted'}>{value}</Code></Link>) },
    { field: 'application_name', headerName: t('applications.name'), flex: 1, minWidth: 200,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary' }}>{value}</Box>
          {!row.is_active && <Tag tone="neutral">{t('applications.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'lifecycle_code', headerName: t('applications.lifecycle'), width: 130,
      renderCell: ({ value }) => <Tag tone="teal">{lifecycleLabel(value)}</Tag> },
    { field: 'app_kind_code', headerName: t('applications.kind'), width: 130, valueGetter: (v) => (v ? kindLabel(v) : '') },
    { field: 'vendor', headerName: t('applications.vendor'), width: 160 },
    { field: 'live_solution_count', headerName: t('applications.solutions'), width: 110, type: 'number' },
    { field: 'live_step_count', headerName: t('applications.steps'), width: 140, type: 'number' },
  ];

  return (
    <Page title={t('applications.title')} subtitle={t('applications.subtitle')} error={q.error && errorText(q.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('applications.add')}</Button>)}>
      {!q.error && q.data && (
        <TileRow>
          <PurpleTile label={t('applications.tiles.live')} value={live.length} />
          <Tile label={t('applications.tiles.delivering')} value={live.filter((r) => r.live_solution_count > 0).length}
            note={t('applications.tiles.deliveringNote')} />
          <Tile label={t('applications.tiles.supporting')} value={live.filter((r) => r.live_step_count > 0).length}
            note={t('applications.tiles.supportingNote')} />
        </TileRow>)}
      <Card>
        <Toolbar>
          {!q.error && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('applications.count', { n: live.length })}</Typography>}
          <Box sx={{ flex: 1 }} />
          <ShowRetired id="app-show-retired" checked={showRetired} onChange={setShowRetired} />
        </Toolbar>
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.application_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.application(projectId, row.application_id))}
            localeText={{ noRowsLabel: t('applications.empty') }}
            initialState={{ sorting: { sortModel: [{ field: 'application_code', sort: 'asc' }] } }}
            sx={GRID_SX} />)}
      </Card>
      {adding && <AddAppDialog projectId={projectId} onClose={() => setAdding(false)}
        onDone={(a) => { qc.invalidateQueries({ queryKey: keys.applications(projectId) });
          setNotice(t('applications.created', { code: a.application_code })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
