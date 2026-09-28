import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControl, InputLabel, MenuItem, Select, Snackbar, Stack, TextField, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { useAuth } from '../../app/AuthContext';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';

function GrantDialog({ projectId, open, onClose, onDone, existing }) {
  const { isAdmin } = useAuth();
  const users = useQuery({ queryKey: ['users'], queryFn: api.users, enabled: open && isAdmin });
  const { codes: roles } = useCodes(projectId, 'PROJECT_ROLE');
  const [user, setUser] = useState(null);
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState('EDITOR');
  const [error, setError] = useState('');
  const targetId = Number(user?.app_user_id ?? userId);
  // A person already on this project is a role change: send that grant's row_version (D-6).
  const current = existing.find((r) => r.source === 'PROJECT' && r.user_id === targetId);
  const m = useMutation({
    mutationFn: () => api.grant(projectId, { user_id: targetId, project_role_code: role,
      row_version: current?.row_version ?? null }),
    onSuccess: () => { onDone(); onClose(); },
    onError: (err) => setError(errorText(err, t('access.grantFailed'))),
  });
  const roleValue = roles.some((r) => r.code === role) ? role : '';   // no out-of-range Select value
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('access.giveTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          {isAdmin ? (
            <Autocomplete id="grant-user" options={(users.data ?? []).filter((u) => u.is_active && !u.is_platform_admin)}
              getOptionLabel={(u) => `${u.display_name} — ${u.email}`} value={user} onChange={(_, v) => setUser(v)}
              renderInput={(params) => <TextField {...params} label={t('access.person')} />} />
          ) : (
            <TextField id="grant-user-id" label={t('access.userId')} value={userId}
              onChange={(e) => setUserId(e.target.value)} helperText={t('access.userIdHelp')} />
          )}
          <FormControl size="small">
            <InputLabel id="grant-role-label">{t('access.role')}</InputLabel>
            <Select labelId="grant-role-label" id="grant-role" label={t('access.role')} value={roleValue}
              onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => <MenuItem key={r.code} value={r.code}>{r.label}</MenuItem>)}
            </Select>
          </FormControl>
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('access.oneScope')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !targetId || !roleValue}
          onClick={() => { setError(''); m.mutate(); }}>{t('access.grant')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function AccessPage() {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['access', projectId], queryFn: () => api.access(projectId) });
  const { getLabel } = useCodes(projectId, 'PROJECT_ROLE');
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const refresh = () => qc.invalidateQueries({ queryKey: ['access', projectId] });
  const revoke = useMutation({
    mutationFn: (grantId) => api.revoke(grantId),
    onSuccess: () => { refresh(); setConfirm(null); setNotice(t('access.revoked')); },
    onError: (err) => { setConfirm(null); setError(errorText(err, t('access.revokeFailed'))); },
  });
  const rows = q.data ?? [];

  const columns = [
    { field: 'display_name', headerName: t('access.person'), flex: 1, minWidth: 160 },
    { field: 'email', headerName: t('access.email'), flex: 1, minWidth: 200 },
    { field: 'project_role_code', headerName: t('access.role'), width: 130,
      valueGetter: (v) => (v === 'ALL' ? t('access.source.PLATFORM_ADMIN') : getLabel(v)) },
    { field: 'source', headerName: t('access.how'), flex: 1, minWidth: 220,
      renderCell: ({ row }) => (
        <Chip size="small" variant={row.source === 'PROJECT' ? 'filled' : 'outlined'}
          label={t(`access.source.${row.source}`, { program: row.program })} />) },
    { field: 'actions', headerName: '', width: 110, sortable: false,
      renderCell: ({ row }) => row.source === 'PROJECT' && (
        <Button size="small" color="warning" onClick={() => setConfirm(row)}>{t('access.revoke')}</Button>) },
  ];

  return (
    <Page title={t('access.title')} error={error || (q.error && errorText(q.error))} subtitle={t('access.subtitle')}
      actions={<Button variant="contained" onClick={() => setOpen(true)}>{t('access.give')}</Button>}>
      <WrapperBox>
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('access.count', { n: rows.length })}</Typography>
      </WrapperBox>
      <DataGrid autoHeight rows={rows.map((r, i) => ({ id: r.grant_id ?? `x${i}`, ...r }))}
        columns={columns} loading={q.isLoading} disableRowSelectionOnClick hideFooterSelectedRowCount
        sx={{ bgcolor: 'background.paper', borderRadius: 3 }} />
      {open && <GrantDialog projectId={projectId} open existing={rows} onClose={() => setOpen(false)}
        onDone={() => { refresh(); setNotice(t('access.granted')); }} />}
      <ConfirmDialog open={Boolean(confirm)} title={t('access.revokeTitle')}
        body={t('access.revokeBody', { name: confirm?.display_name })} confirmLabel={t('access.revoke')}
        busy={revoke.isPending} onClose={() => setConfirm(null)} onConfirm={() => revoke.mutate(confirm.grant_id)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
