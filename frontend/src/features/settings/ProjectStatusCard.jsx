// Slice 16 (AR-8, U2): the project's status and its two-year archive clock. An editor changes the status; entering a
// closed status starts the clock (closed_on, shown here). Leaving a closed status is a platform admin's "Reopen" — the
// reminder's only off-switch — so an editor sees the closed status read-only. Labels come from the company code list
// (PROJECT_STATUS); the open / closed meaning is the server's (status_behaviour), never read from a code here.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { useAuth } from '../../app/AuthContext';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Status } from '../../components/kit';
import { t } from '../../i18n/t';

export function ProjectStatusCard({ projectId, notify }) {
  const qc = useQueryClient();
  const { isAdmin } = useAuth();
  const canEdit = useCanEdit();
  const p = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const { codes, options, getLabel } = useCodes(projectId, 'PROJECT_STATUS');
  const [pick, setPick] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState('');
  const current = codes.find((c) => c.code_id === p.data?.status_code_id);
  const closed = p.data?.status_behaviour === 'CLOSED';
  const m = useMutation({
    mutationFn: (code) => (closed ? api.reopenProject(projectId, { status_code: code, row_version: p.data.row_version })
      : api.setProjectStatus(projectId, { status_code: code, row_version: p.data.row_version })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.project(projectId) });
      setPick(''); setConfirm(false); setError('');
      notify(t(closed ? 'settings.status.reopened' : 'settings.status.saved'));
    },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  if (!p.data) return null;
  // Closed: only a platform admin may move it, and only to an open status (U2). The server decides either way.
  const choices = options(current?.code).filter((c) => c.code_id !== p.data.status_code_id
    && (!closed || c.behaviour_code !== 'CLOSED'));
  const mayChange = closed ? isAdmin : canEdit;
  const goingClosed = codes.find((c) => c.code === pick)?.behaviour_code === 'CLOSED';
  return (
    <Card title={t('settings.status.title')} sx={{ mb: 2 }}>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 1 }}>
        <Status tone={closed ? 'neutral' : 'ok'}>{current ? getLabel(current.code) : '—'}</Status>
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
          {closed ? t('settings.status.closedOn', { date: p.data.closed_on }) : t('settings.status.open')}
        </Typography>
        {mayChange && (
          <>
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel id="project-status-label">{t(closed ? 'settings.status.reopenTo' : 'settings.status.change')}</InputLabel>
              <Select labelId="project-status-label" id="project-status" value={pick}
                label={t(closed ? 'settings.status.reopenTo' : 'settings.status.change')}
                onChange={(e) => setPick(e.target.value)}>
                {choices.map((c) => <MenuItem key={c.code} value={c.code}>{c.label}</MenuItem>)}
              </Select>
            </FormControl>
            <Button variant="contained" disabled={!pick || m.isPending}
              onClick={() => (closed || goingClosed ? setConfirm(true) : m.mutate(pick))}>
              {t(closed ? 'settings.status.reopen' : 'settings.status.save')}</Button>
          </>
        )}
      </Stack>
      {closed && !isAdmin && (
        <Typography sx={{ mt: 1, fontSize: 12.5, color: 'text.secondary' }}>{t('settings.status.adminReopens')}</Typography>)}
      <ConfirmDialog open={confirm}
        title={t(closed ? 'settings.status.reopenTitle' : 'settings.status.closeTitle')}
        body={t(closed ? 'settings.status.reopenBody' : 'settings.status.closeBody', { date: p.data.closed_on })}
        confirmLabel={t(closed ? 'settings.status.reopen' : 'settings.status.save')} busy={m.isPending}
        onClose={() => setConfirm(false)} onConfirm={() => m.mutate(pick)} />
    </Card>
  );
}
