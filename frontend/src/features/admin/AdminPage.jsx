import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Select, Snackbar, Stack, Tab, Tabs,
  TextField } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';

function useSave(fn, keys, onOk) {
  const qc = useQueryClient();
  const [error, setError] = useState('');
  const m = useMutation({ mutationFn: fn,
    onSuccess: () => { keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] })); setError(''); onOk?.(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))) });
  return { m, error, setError };
}

const grid = { autoHeight: true, disableRowSelectionOnClick: true, sx: { bgcolor: 'background.paper', borderRadius: 3 } };

function ClientSelect({ id, value, onChange, clients }) {
  return (
    <FormControl size="small" sx={{ minWidth: 200 }}>
      <InputLabel id={`${id}-label`}>{t('admin.client')}</InputLabel>
      <Select labelId={`${id}-label`} id={id} label={t('admin.client')}
        value={clients.some((c) => c.client_id === value) ? value : ''} onChange={(e) => onChange(e.target.value)}>
        {clients.map((c) => <MenuItem key={c.client_id} value={c.client_id}>{c.client_name}</MenuItem>)}
      </Select>
    </FormControl>
  );
}

function Users({ notify }) {
  const users = useQuery({ queryKey: ['users'], queryFn: api.users });
  const empty = { email: '', display_name: '', initial_password: '' };
  const [f, setF] = useState(empty);
  const [deact, setDeact] = useState(null);
  const [adminChange, setAdminChange] = useState(null);
  const [reason, setReason] = useState('');
  const create = useSave(() => api.createUser(f), ['users'], () => { setF(empty); notify(t('admin.userCreated')); });
  const deactivate = useSave((id) => api.deactivateUser(id), ['users'], () => { setDeact(null); notify(t('admin.deactivated')); });
  const setAdmin = useSave((u) => api.setPlatformAdmin(u.app_user_id, {
    is_platform_admin: !u.is_platform_admin, rationale: reason, row_version: u.row_version }),
  ['users'], () => { setAdminChange(null); setReason(''); notify(t('admin.adminChanged')); });
  const error = create.error || deactivate.error || setAdmin.error;
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <WrapperBox>
        <TextField id="u-name" label={t('admin.name')} value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} />
        <TextField id="u-email" label={t('admin.email')} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <TextField id="u-pw" label={t('admin.initialPassword')} type="password" value={f.initial_password}
          onChange={(e) => setF({ ...f, initial_password: e.target.value })} />
        <Button variant="contained" disabled={create.m.isPending} onClick={() => create.m.mutate()}>{t('admin.createUser')}</Button>
      </WrapperBox>
      <DataGrid {...grid} rows={users.data ?? []} getRowId={(r) => r.app_user_id}
        columns={[
          { field: 'app_user_id', headerName: t('admin.id'), width: 70 },
          { field: 'display_name', headerName: t('admin.name'), flex: 1 },
          { field: 'email', headerName: t('admin.email'), flex: 1 },
          { field: 'is_platform_admin', headerName: t('admin.isAdmin'), width: 90, type: 'boolean' },
          { field: 'is_active', headerName: t('admin.active'), width: 90, type: 'boolean' },
          { field: 'x', headerName: '', width: 240, sortable: false, renderCell: ({ row }) => row.is_active && (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
              <Button size="small" onClick={() => { setAdmin.setError(''); setAdminChange(row); }}>
                {row.is_platform_admin ? t('admin.removeAdmin') : t('admin.makeAdmin')}</Button>
              <Button size="small" color="warning" onClick={() => setDeact(row)}>{t('admin.deactivate')}</Button>
            </Stack>) },
        ]} />
      <ConfirmDialog open={Boolean(deact)} title={t('admin.deactivateTitle')}
        body={t('admin.deactivateBody', { name: deact?.display_name })} confirmLabel={t('admin.deactivate')}
        busy={deactivate.m.isPending} onClose={() => setDeact(null)} onConfirm={() => deactivate.m.mutate(deact.app_user_id)} />
      <ConfirmDialog open={Boolean(adminChange)} title={t('admin.adminTitle')}
        body={t(adminChange?.is_platform_admin ? 'admin.adminBodyRemove' : 'admin.adminBodyGrant', { name: adminChange?.display_name })}
        confirmLabel={adminChange?.is_platform_admin ? t('admin.removeAdmin') : t('admin.makeAdmin')}
        busy={setAdmin.m.isPending || !reason.trim()} onClose={() => { setAdminChange(null); setReason(''); }}
        onConfirm={() => setAdmin.m.mutate(adminChange)}>
        <TextField id="admin-reason" label={t('admin.reason')} value={reason} onChange={(e) => setReason(e.target.value)}
          fullWidth multiline minRows={2} />
      </ConfirmDialog>
    </>
  );
}

function Clients({ notify }) {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const empty = { client_code: '', client_name: '', industry: '' };
  const [f, setF] = useState(empty);
  const { m, error } = useSave(() => api.createClient(f), ['clients'], () => { setF(empty); notify(t('admin.clientCreated')); });
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <WrapperBox>
        <TextField id="c-code" label={t('admin.clientCode')} value={f.client_code} onChange={(e) => setF({ ...f, client_code: e.target.value })} />
        <TextField id="c-name" label={t('admin.clientName')} value={f.client_name} onChange={(e) => setF({ ...f, client_name: e.target.value })} />
        <TextField id="c-ind" label={t('admin.industry')} value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} />
        <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('admin.createClient')}</Button>
      </WrapperBox>
      <DataGrid {...grid} rows={clients.data ?? []} getRowId={(r) => r.client_id}
        columns={[{ field: 'client_code', headerName: t('admin.code'), width: 140 },
                  { field: 'client_name', headerName: t('admin.name'), flex: 1 },
                  { field: 'industry', headerName: t('admin.industry'), flex: 1 }]} />
    </>
  );
}

function Programs({ notify }) {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const empty = { client_id: '', program_code: '', program_name: '' };
  const [f, setF] = useState(empty);
  const { m, error } = useSave(() => api.createProgram(f), ['programs'], () => { setF(empty); notify(t('admin.programCreated')); });
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <WrapperBox>
        <ClientSelect id="g-client" value={f.client_id} onChange={(v) => setF({ ...f, client_id: v })} clients={clients.data ?? []} />
        <TextField id="g-code" label={t('admin.programCode')} value={f.program_code} onChange={(e) => setF({ ...f, program_code: e.target.value })} />
        <TextField id="g-name" label={t('admin.programName')} value={f.program_name} onChange={(e) => setF({ ...f, program_name: e.target.value })} />
        <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('admin.createProgram')}</Button>
      </WrapperBox>
      <DataGrid {...grid} rows={programs.data ?? []} getRowId={(r) => r.program_id}
        columns={[{ field: 'program_code', headerName: t('admin.code'), width: 140 },
                  { field: 'program_name', headerName: t('admin.name'), flex: 1 }]} />
    </>
  );
}

function Projects({ notify }) {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects });
  const empty = { client_id: '', project_code: '', project_name: '', program_id: '' };
  const [f, setF] = useState(empty);
  const { m, error } = useSave(() => api.createProject({ ...f, program_id: f.program_id || null }), ['projects'],
    () => { setF(empty); notify(t('admin.projectCreated')); });
  const progs = (programs.data ?? []).filter((g) => g.client_id === f.client_id);
  const programCode = (id) => (programs.data ?? []).find((g) => g.program_id === id)?.program_code ?? '';
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <WrapperBox>
        <ClientSelect id="p-client" value={f.client_id} onChange={(v) => setF({ ...f, client_id: v, program_id: '' })} clients={clients.data ?? []} />
        <TextField id="p-code" label={t('admin.projectCode')} value={f.project_code} onChange={(e) => setF({ ...f, project_code: e.target.value })} />
        <TextField id="p-name" label={t('admin.projectName')} value={f.project_name} onChange={(e) => setF({ ...f, project_name: e.target.value })} />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="p-prog-label">{t('admin.programOptional')}</InputLabel>
          <Select labelId="p-prog-label" id="p-prog" label={t('admin.programOptional')}
            value={progs.some((g) => g.program_id === f.program_id) ? f.program_id : ''}
            onChange={(e) => setF({ ...f, program_id: e.target.value })}>
            <MenuItem value="">{t('common.none')}</MenuItem>
            {progs.map((g) => <MenuItem key={g.program_id} value={g.program_id}>{g.program_name}</MenuItem>)}
          </Select>
        </FormControl>
        <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('admin.createProject')}</Button>
      </WrapperBox>
      <DataGrid {...grid} rows={projects.data ?? []} getRowId={(r) => r.project_id}
        columns={[{ field: 'project_code', headerName: t('admin.code'), width: 140 },
                  { field: 'project_name', headerName: t('admin.name'), flex: 1 },
                  { field: 'program_id', headerName: t('admin.program'), width: 140, valueGetter: (v) => programCode(v) }]} />
    </>
  );
}

const TABS = [['admin.users', Users], ['admin.clients', Clients], ['admin.programs', Programs], ['admin.projects', Projects]];

export default function AdminPage() {
  const [tab, setTab] = useState(0);
  const [notice, setNotice] = useState('');
  const Body = TABS[tab][1];
  return (
    <Page title={t('admin.title')} subtitle={t('admin.subtitle')}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 1 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label={t('admin.tabs')}>
          {TABS.map(([key]) => <Tab key={key} label={t(key)} />)}
        </Tabs>
      </Box>
      <Body notify={setNotice} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
