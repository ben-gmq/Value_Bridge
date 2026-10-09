import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack,
  TextField, Tooltip, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';
import { Mono, ShowRetired, SimpleSelect } from '../processes/chartKit';

const EMPTY = { solution_name: '', category_code: '', description: '' };
const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };
const firstLine = (v) => (v ?? '').split('\n')[0];

function AddSolutionDialog({ projectId, onClose, onDone }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const { codes: categories } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const m = useMutation({
    // The number and the PROPOSED status are set by the server (VB law 6); only what was typed is sent.
    mutationFn: () => solutionApi.create(projectId, { solution_name: f.solution_name.trim(),
      category_code: f.category_code, description: f.description.trim() || null }),
    onSuccess: (s) => { onDone(s); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('solutions.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="sol-new-name" label={t('solutions.name')} required autoFocus value={f.solution_name}
            onChange={set('solution_name')} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <SimpleSelect id="sol-new-category" label={t('solutions.category')} value={f.category_code}
            onChange={(v) => setF({ ...f, category_code: v })}
            options={categories.map((c) => ({ value: c.code, label: c.label }))} />
          <TextField id="sol-new-desc" label={t('solutions.description')} multiline minRows={2} value={f.description}
            onChange={set('description')} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('solutions.numberMinted')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        {/* DR1-P2: disabled while in flight, so a double click cannot create two */}
        <Button variant="contained" disabled={m.isPending || !f.solution_name.trim() || !f.category_code}
          onClick={() => { setError(''); m.mutate(); }}>{t('common.create')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// The solution register (§4.4, D-7). Opened by the BR–FR map item until FRs arrive.
export default function SolutionsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const [showRetired, setShowRetired] = useState(false);
  // Retired rows are a separate query under the same prefix, so invalidating keys.solutions refreshes both.
  const q = useQuery({ queryKey: showRetired ? [...keys.solutions(projectId), 'with-retired'] : keys.solutions(projectId),
    queryFn: () => solutionApi.list(projectId, showRetired), placeholderData: (prev) => prev });
  const { getLabel: categoryLabel } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const { getLabel: statusLabel } = useCodes(projectId, 'SOLUTION_STATUS');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const rows = q.data ?? [];
  const activeCount = rows.filter((r) => r.is_active).length;

  const columns = [
    { field: 'solution_number', headerName: t('solutions.number'), width: 130,
      renderCell: ({ row, value, tabIndex }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Link component={RouterLink} to={links.solution(projectId, row.solution_id)} tabIndex={tabIndex} underline="hover"
            onClick={(e) => e.stopPropagation()} sx={{ color: row.is_active ? 'brand.link' : 'text.disabled' }}>
            <Mono>{value}</Mono></Link>
        </Stack>) },
    { field: 'solution_name', headerName: t('solutions.name'), flex: 1, minWidth: 220,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%', minWidth: 0 }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary',
            overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</Box>
          {!row.is_active && <Chip size="small" variant="outlined" label={t('solutions.retiredChip')} />}
        </Stack>) },
    { field: 'category_code', headerName: t('solutions.category'), width: 190,
      renderCell: ({ value }) => <Chip size="small" variant="outlined" label={categoryLabel(value)} /> },
    { field: 'status_code', headerName: t('solutions.status'), width: 140,
      renderCell: ({ value }) => <Chip size="small" label={statusLabel(value)} /> },
    { field: 'live_br_count', headerName: t('solutions.brCount'), width: 190, type: 'number',
      renderCell: ({ row, value }) => (row.is_active && value === 0 ? (
        <Tooltip title={t('solutions.noBrTip')}>
          <Chip size="small" variant="outlined" label={t('solutions.noBrChip')}
            sx={{ color: 'status.caution', borderColor: 'status.caution' }} />
        </Tooltip>) : value) },
    { field: 'description', headerName: t('solutions.description'), flex: 1, minWidth: 200,
      valueGetter: (v) => firstLine(v) },
  ];

  return (
    <Page title={t('solutions.title')} subtitle={t('solutions.subtitle')}
      error={q.error && errorText(q.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('solutions.add')}</Button>)}>
      <WrapperBox>
        {!q.error && (
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('solutions.count', { n: activeCount })}</Typography>)}
        <Box sx={{ flex: 1 }} />
        <ShowRetired id="sol-show-retired" checked={showRetired} onChange={setShowRetired} />
      </WrapperBox>
      {!q.error && (
        <DataGrid autoHeight rows={rows} getRowId={(r) => r.solution_id} columns={columns} loading={q.isLoading}
          disableRowSelectionOnClick hideFooterSelectedRowCount
          onRowClick={({ row }) => navigate(links.solution(projectId, row.solution_id))}
          localeText={{ noRowsLabel: t('solutions.empty') }}
          initialState={{ sorting: { sortModel: [{ field: 'solution_number', sort: 'asc' }] } }}
          sx={{ bgcolor: 'background.paper', borderRadius: 3, '& .MuiDataGrid-row': { cursor: 'pointer' } }} />)}
      {adding && <AddSolutionDialog projectId={projectId} onClose={() => setAdding(false)}
        onDone={(s) => { qc.invalidateQueries({ queryKey: keys.solutions(projectId) });
          setNotice(t('solutions.created', { number: s.solution_number })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
