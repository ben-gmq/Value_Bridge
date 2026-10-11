import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl,
  InputLabel, MenuItem, Select, Snackbar, Stack, TextField, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { useAuth } from '../../app/AuthContext';
import { keys } from '../../app/links';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';

const LEVELS = ['EDIT', 'VIEW'];

function LevelSelect({ id, value, onChange }) {
  return (
    <FormControl size="small" sx={{ minWidth: 160 }}>
      <InputLabel id={`${id}-label`}>{t('access.level')}</InputLabel>
      <Select labelId={`${id}-label`} id={id} label={t('access.level')} value={value} onChange={(e) => onChange(e.target.value)}>
        {LEVELS.map((l) => <MenuItem key={l} value={l}>{t(`access.level.${l}`)}</MenuItem>)}
      </Select>
    </FormControl>
  );
}

function AddMember({ projectId, members, onDone }) {
  const users = useQuery({ queryKey: ['users'], queryFn: api.users });
  const [user, setUser] = useState(null);
  const [level, setLevel] = useState('EDIT');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const taken = new Set(members.map((m) => m.user_id));
  const m = useMutation({
    mutationFn: () => api.addMember(projectId, { user_id: user.app_user_id, access_level: level, member_note: note || null }),
    onSuccess: (res) => { setUser(null); setNote(''); setError(''); onDone(res.warnings?.includes('VIEWER_CAPPED')
      ? t('access.viewerCapped') : t('access.added')); },
    onError: (err) => setError(errorText(err, t('access.failed'))),
  });
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <WrapperBox>
        <Autocomplete id="member-user" sx={{ minWidth: 300 }} value={user} onChange={(_, v) => setUser(v)}
          options={(users.data ?? []).filter((u) => u.is_active && !u.is_platform_admin && !taken.has(u.app_user_id))}
          getOptionLabel={(u) => `${u.display_name} — ${t(`access.kind.${u.user_kind}`)}`}
          renderInput={(params) => <TextField {...params} size="small" label={t('access.person')} />} />
        <LevelSelect id="member-level" value={level} onChange={setLevel} />
        <TextField id="member-note" size="small" label={t('access.note')} value={note} onChange={(e) => setNote(e.target.value)} />
        <Button variant="contained" disabled={!user || m.isPending} onClick={() => m.mutate()}>{t('access.addMember')}</Button>
      </WrapperBox>
    </>
  );
}

// Who can open the project (D-40, OR-6). Admin only: members, the restriction switch with a
// preview of who loses, gains and keeps access (DR7-D2), and the effective list.
export default function AccessPage() {
  const { projectId } = useParams();
  const { isAdmin } = useAuth();
  const qc = useQueryClient();
  const acc = useQuery({ queryKey: keys.projectAccess(projectId), queryFn: () => api.access(projectId), enabled: isAdmin });
  const [preview, setPreview] = useState(null);
  const [confirmRemove, setConfirmRemove] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const refresh = () => { qc.invalidateQueries({ queryKey: keys.projectAccess(projectId) });
    qc.invalidateQueries({ queryKey: keys.project(projectId) }); };
  const fail = (err) => setError(errorText(err, t('access.failed')));

  const restrict = useMutation({
    mutationFn: ({ value, hash }) => api.setRestriction(projectId, { is_restricted: value, confirm_hash: hash ?? null }),
    onSuccess: (res) => { setError('');
      if (res.applied) { setPreview(null); setNotice(t('access.applied')); refresh(); } else setPreview(res); },
    onError: (err) => { setPreview(null); fail(err); },
  });
  const change = useMutation({
    mutationFn: ({ row, level }) => api.changeMember(row.project_member_id, { access_level: level, row_version: row.row_version }),
    onSuccess: () => { setNotice(t('access.changed')); refresh(); }, onError: fail,
  });
  const remove = useMutation({
    mutationFn: (row) => api.removeMember(row.project_member_id, row.row_version),
    onSuccess: () => { setConfirmRemove(null); setNotice(t('access.removed')); refresh(); },
    onError: (err) => { setConfirmRemove(null); fail(err); },
  });

  if (!isAdmin) {
    return <Page title={t('access.title')}><Alert severity="info">{t('access.adminOnly')}</Alert></Page>;
  }
  const data = acc.data;
  const names = (list) => list.map((p) => p.display_name).join(', ');
  return (
    <Page title={t('access.title')} subtitle={t('access.subtitle')} error={error || (acc.error && errorText(acc.error))}
      actions={data && (
        <Button variant="contained" color="warning" disabled={restrict.isPending}
          onClick={() => restrict.mutate({ value: !data.is_restricted })}>
          {data.is_restricted ? t('access.unrestrict') : t('access.restrict')}</Button>)}>
      {data && (
        <Alert severity={data.is_restricted ? 'warning' : 'info'} sx={{ mb: 2 }}>
          {data.is_restricted ? t('access.restricted')
            : t('access.unrestricted', { users: data.staff?.USER ?? 0, viewers: data.staff?.VIEWER ?? 0 })}
        </Alert>
      )}
      <Typography variant="h6" component="h2" sx={{ mt: 2 }}>{t('access.members')}</Typography>
      <Typography sx={{ color: 'text.secondary' }}>{t('access.membersNote')}</Typography>
      <AddMember projectId={projectId} members={data?.members ?? []} onDone={(msg) => { setNotice(msg); refresh(); }} />
      <DataGrid autoHeight disableRowSelectionOnClick rows={data?.members ?? []} getRowId={(r) => r.project_member_id}
        localeText={{ noRowsLabel: t('access.noMembers') }} sx={{ bgcolor: 'background.paper', borderRadius: 3 }}
        columns={[
          { field: 'display_name', headerName: t('access.person'), flex: 1 },
          { field: 'user_kind', headerName: t('access.kind'), width: 110, valueFormatter: (v) => t(`access.kind.${v}`) },
          { field: 'access_level', headerName: t('access.level'), width: 190, sortable: false, renderCell: ({ row }) => (
            <Box sx={{ display: 'flex', alignItems: 'center', height: '100%' }}>
              <LevelSelect id={`lvl-${row.project_member_id}`} value={row.access_level}
                onChange={(level) => change.mutate({ row, level })} />
            </Box>) },
          { field: 'effective_level', headerName: t('access.effective'), width: 130, valueFormatter: (v) => t(`access.level.${v}`) },
          { field: 'member_note', headerName: t('access.note'), flex: 1 },
          { field: 'x', headerName: '', width: 110, sortable: false, renderCell: ({ row }) => (
            <Button size="small" color="warning" onClick={() => setConfirmRemove(row)}>{t('access.remove')}</Button>) },
        ]} />
      <Typography variant="h6" component="h2" sx={{ mt: 3, mb: 1 }}>{t('access.admins')}</Typography>
      <Typography sx={{ color: 'text.secondary' }}>{names(data?.admins ?? [])}</Typography>

      <Dialog open={Boolean(preview)} onClose={() => setPreview(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{preview?.restricted ? t('access.restrictTitle') : t('access.unrestrictTitle')}</DialogTitle>
        <DialogContent>
          {preview && (
            <Stack spacing={1}>
              {preview.loses.length > 0 && <Alert severity="warning">{t('access.loses', { list: names(preview.loses) })}</Alert>}
              {preview.gains.length > 0 && <Typography>{t('access.gains', { list: names(preview.gains) })}</Typography>}
              {preview.restricted && (
                <>
                  <Typography sx={{ fontWeight: 600 }}>{t('access.keeps')}</Typography>
                  {preview.keeps.length === 0 && <Typography sx={{ color: 'text.secondary' }}>{t('access.noMembers')}</Typography>}
                  {preview.keeps.map((k) => (
                    <Typography key={k.project_member_id} variant="body2">
                      {k.display_name} — {t(`access.level.${k.effective_level}`)}{k.member_note ? ` · ${k.member_note}` : ''}
                    </Typography>))}
                </>
              )}
              {!preview.changed && <Typography>{t('access.nobody')}</Typography>}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreview(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" color="warning" disabled={restrict.isPending || !preview?.changed}
            onClick={() => restrict.mutate({ value: preview.restricted, hash: preview.confirm_hash })}>{t('access.apply')}</Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog open={Boolean(confirmRemove)} title={t('access.removeTitle')}
        body={t(data?.is_restricted ? 'access.removeBody' : 'access.removeBodyOpen', { name: confirmRemove?.display_name })}
        confirmLabel={t('access.remove')}
        busy={remove.isPending} onClose={() => setConfirmRemove(null)} onConfirm={() => remove.mutate(confirmRemove)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
