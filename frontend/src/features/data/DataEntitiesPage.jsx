import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Link,
  Snackbar, Stack, Switch, TextField, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import UploadFileRounded from '@mui/icons-material/UploadFileRounded';
import SchemaRounded from '@mui/icons-material/SchemaRounded';
import { DataGrid } from '@mui/x-data-grid';
import { dataApi, importApi } from '../../api/scope';
import { errorText } from '../../api/client';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { ImportWizard } from '../../components/ImportWizard';
import { Page, WrapperBox } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { entityLabel, firstLine } from './fieldRules';

const EMPTY = { de_name: '', description: '', business_owner_note: '' };
const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };

function AddEntityDialog({ projectId, onClose, onDone }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const m = useMutation({
    // The number is minted by the server at save (VB law 6); only what was typed is sent.
    mutationFn: () => dataApi.create(projectId, { de_name: f.de_name.trim(),
      description: f.description.trim() || null, business_owner_note: f.business_owner_note.trim() || null }),
    onSuccess: (de) => { onDone(de); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('data.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="de-new-name" label={t('data.name')} required autoFocus value={f.de_name}
            onChange={set('de_name')} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <TextField id="de-new-desc" label={t('data.description')} multiline minRows={2} value={f.description}
            onChange={set('description')} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          <TextField id="de-new-owner" label={t('data.ownerNote')} multiline minRows={2} value={f.business_owner_note}
            onChange={set('business_owner_note')} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.numberMinted')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !f.de_name.trim()}
          onClick={() => { setError(''); m.mutate(); }}>{t('common.create')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function DataEntitiesPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showRetired, setShowRetired] = useState(false);
  // Retired rows are a separate query under the same prefix, so every invalidation of
  // keys.entities refreshes both, and the active list other screens read stays active-only.
  const q = useQuery({ queryKey: showRetired ? [...keys.entities(projectId), 'with-retired'] : keys.entities(projectId),
    queryFn: () => dataApi.list(projectId, showRetired), placeholderData: (prev) => prev });
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const canEdit = useCanEdit();
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const rows = q.data ?? [];
  const activeCount = rows.filter((r) => r.is_active !== false).length;

  const restore = useMutation({
    mutationFn: (de) => dataApi.restore(de.data_entity_id),
    onSuccess: (de) => { qc.invalidateQueries({ queryKey: keys.entities(projectId) });
      qc.invalidateQueries({ queryKey: keys.entity(de.data_entity_id) });
      setNotice(t('data.restored', { label: entityLabel(de) })); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });

  // Export is a read (REVIEWER may); template, validate and commit are edits, so Import hides.
  const exportList = useMutation({
    mutationFn: () => importApi.export(projectId, 'data-entities'),
    onSuccess: (name) => setNotice(t('data.import.exported', { name })),
    onError: (err) => setError(errorText(err, t('data.import.downloadFailed'))),
  });

  const columns = [
    { field: 'de_number', headerName: t('data.number'), width: 120,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.entity(projectId, row.data_entity_id)} tabIndex={tabIndex}
          onClick={(e) => e.stopPropagation()}
          sx={{ fontFamily: MONO, fontSize: 13, color: 'brand.link' }}>{value}</Link>) },
    { field: 'de_name', headerName: t('data.name'), flex: 1, minWidth: 180,
      renderCell: ({ row, value }) => (
        <Box component="span" sx={{ color: row.is_active === false ? 'text.secondary' : 'inherit' }}>{value}</Box>) },
    { field: 'description', headerName: t('data.description'), flex: 2, minWidth: 240,
      valueGetter: (v) => firstLine(v) },
    ...(showRetired ? [{ field: 'is_active', headerName: '', width: 190, sortable: false,
      renderCell: ({ row, tabIndex }) => row.is_active === false && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Chip size="small" variant="outlined" label={t('data.retiredChip')} />
          <Button size="small" tabIndex={tabIndex} disabled={restore.isPending}
            onClick={(e) => { e.stopPropagation(); setError(''); restore.mutate(row); }}>{t('data.restore')}</Button>
        </Stack>) }] : []),
  ];

  const loadError = q.error && errorText(q.error, t('data.loadFailed'));
  return (
    <Page title={t('data.title')} subtitle={t('data.subtitle')}
      actions={(<>
        <Button component={RouterLink} to={links.erd(projectId)} startIcon={<SchemaRounded />}>{t('data.diagram')}</Button>
        <Button startIcon={<DownloadRounded />} disabled={exportList.isPending}
          onClick={() => { setError(''); exportList.mutate(); }}>{t('data.import.exportList')}</Button>
        {canEdit && (
          <Button variant="outlined" startIcon={<UploadFileRounded />} onClick={() => setImporting(true)}>{t('data.import.open')}</Button>)}
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('data.add')}</Button>
      </>)}>
      {(error || loadError) && <Alert severity="error" sx={ERR_SX}>{error || loadError}</Alert>}
      <WrapperBox>
        {!q.error && (
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('data.count', { n: activeCount })}</Typography>)}
        <FormControlLabel sx={{ ml: 'auto' }} label={t('data.showRetired')}
          control={<Switch id="de-show-retired" size="small" checked={showRetired}
            onChange={(e) => setShowRetired(e.target.checked)} />} />
      </WrapperBox>
      {!q.error && (
        <DataGrid autoHeight rows={rows} getRowId={(r) => r.data_entity_id} columns={columns} loading={q.isLoading}
          disableRowSelectionOnClick hideFooterSelectedRowCount
          onRowClick={({ row }) => navigate(links.entity(projectId, row.data_entity_id))}
          localeText={{ noRowsLabel: t('data.empty') }}
          sx={{ bgcolor: 'background.paper', borderRadius: 3, '& .MuiDataGrid-row': { cursor: 'pointer' } }} />
      )}
      {adding && <AddEntityDialog projectId={projectId} onClose={() => setAdding(false)}
        onDone={(de) => { qc.invalidateQueries({ queryKey: keys.entities(projectId) });
          setNotice(t('data.created', { number: de.de_number })); }} />}
      {importing && <ImportWizard projectId={projectId} onClose={() => setImporting(false)} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
