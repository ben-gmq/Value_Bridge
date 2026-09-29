import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { dataApi } from '../../api/scope';
import { errorText } from '../../api/client';
import { keys, links } from '../../app/links';
import { Page, WrapperBox } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { firstLine } from './fieldRules';

const EMPTY = { de_name: '', description: '', business_owner_note: '' };

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
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
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
  const q = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const rows = q.data ?? [];

  const columns = [
    { field: 'de_number', headerName: t('data.number'), width: 120,
      renderCell: ({ value }) => <Typography component="span" sx={{ fontFamily: MONO, fontSize: 13 }}>{value}</Typography> },
    { field: 'de_name', headerName: t('data.name'), flex: 1, minWidth: 180 },
    { field: 'description', headerName: t('data.description'), flex: 2, minWidth: 240,
      valueGetter: (v) => firstLine(v) },
  ];

  return (
    <Page title={t('data.title')} subtitle={t('data.subtitle')} error={q.error && errorText(q.error)}
      actions={<Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>
        {t('data.add')}</Button>}>
      <WrapperBox>
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('data.count', { n: rows.length })}</Typography>
      </WrapperBox>
      <DataGrid autoHeight rows={rows} getRowId={(r) => r.data_entity_id} columns={columns} loading={q.isLoading}
        disableRowSelectionOnClick hideFooterSelectedRowCount
        onRowClick={({ row }) => navigate(links.entity(projectId, row.data_entity_id))}
        localeText={{ noRowsLabel: t('data.empty') }}
        sx={{ bgcolor: 'background.paper', borderRadius: 3, '& .MuiDataGrid-row': { cursor: 'pointer' } }} />
      {adding && <AddEntityDialog projectId={projectId} onClose={() => setAdding(false)}
        onDone={(de) => { qc.invalidateQueries({ queryKey: keys.entities(projectId) });
          setNotice(t('data.created', { number: de.de_number })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
