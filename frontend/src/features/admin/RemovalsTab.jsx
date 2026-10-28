// Slice 16 (spec §9, §15a, §17 R2/R3, Q-73): removal requests. One platform admin asks, a different one approves with
// the client and project codes typed again, the operator carries it out at least 24 hours later (never from here).
// What the buttons show is presentation only: the database guard decides four eyes, AR-13 and the order of steps.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Select, Stack, TextField, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { useAuth } from '../../app/AuthContext';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Status } from '../../components/kit';
import { t } from '../../i18n/t';
import { WeeklyCheckCard } from './WeeklyCheckCard';
import { useApprovers } from './useApprovers';

const TONE = { OPEN: 'caution', APPROVED: 'caution', EXECUTED: 'neutral', CANCELLED: 'neutral' };
const when = (iso) => (iso ? new Date(iso).toLocaleString() : '');

function useRemovalWrite(fn, onOk) {
  const qc = useQueryClient();
  const [error, setError] = useState('');
  const m = useMutation({ mutationFn: fn,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: keys.purgeRequests() });
      qc.invalidateQueries({ queryKey: keys.archiveOverview() });
      setError('');
      onOk?.(res);
    },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))) });
  return { m, error, setError };
}

// One dialog for request, approve and cancel: what is about to happen, and (except cancel) the typed codes (R3).
function Confirm({ action, onClose, onConfirm, busy, error }) {
  const [typed, setTyped] = useState('');
  const [reason, setReason] = useState('');
  if (!action) return null;
  const needsCodes = action.type !== 'cancel';
  const needsReason = action.type === 'request' || action.type === 'deleteArchive';
  const ready = (!needsCodes || typed.trim() === action.expected) && (!needsReason || reason.trim());
  const kind = t(`removals.kind.${action.kind}`);
  const title = { request: 'requestTitle', deleteArchive: 'requestTitle', approve: 'approveTitle',
    cancel: 'cancelTitle' }[action.type];
  const body = { request: 'requestBody', deleteArchive: 'deleteArchiveBody', approve: 'approveBody',
    cancel: 'cancelBody' }[action.type];
  return (
    <ConfirmDialog open title={t(`removals.confirm.${title}`, { kind, expected: action.expected })}
      body={t(`removals.confirm.${body}`, { who: action.row?.requested_by, when: when(action.row?.requested_at),
        reason: action.row?.reason })}
      confirmLabel={t(action.type === 'cancel' ? 'removals.cancel'
        : action.type === 'approve' ? 'removals.approve' : 'removals.new.submit')}
      busy={busy || !ready} onClose={() => { setTyped(''); setReason(''); onClose(); }}
      onConfirm={() => onConfirm({ confirm_text: typed.trim(), reason: reason.trim() })}>
      <Stack spacing={2}>
        {needsReason && (
          <TextField id="removal-reason" label={t('removals.new.reason')} value={reason} multiline minRows={2}
            onChange={(e) => setReason(e.target.value)} slotProps={{ htmlInput: { maxLength: 2000 } }} />
        )}
        {needsCodes && (
          <TextField id="removal-confirm" label={t('removals.confirm.label', { expected: action.expected })}
            value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        )}
        {error && <Alert severity="error">{error}</Alert>}
      </Stack>
    </ConfirmDialog>
  );
}

export function RemovalsTab({ notify }) {
  const { me } = useAuth() ?? {};
  const { alone } = useApprovers();                       // AR-28: the requester approves only while the setting is 1
  const myId = me?.user?.app_user_id;
  const rows = useQuery({ queryKey: keys.purgeRequests(), queryFn: api.purgeRequests });
  const overview = useQuery({ queryKey: keys.archiveOverview(), queryFn: api.archiveOverview });
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects });
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const [action, setAction] = useState(null);
  const [pick, setPick] = useState({ project_id: '', kind: 'DELETE' });

  const clientCode = (id) => (clients.data ?? []).find((c) => c.client_id === id)?.client_code ?? '';
  const project = (projects.data ?? []).find((p) => p.project_id === pick.project_id);
  const done = (key) => () => { setAction(null); notify(t(`removals.done.${key}`)); };

  const request = useRemovalWrite((v) => api.requestPurge(action.projectId,
    { kind: action.kind, reason: v.reason, confirm_text: v.confirm_text }), done('requested'));
  const deleteArchive = useRemovalWrite((v) => api.requestArchiveDeletion(action.row.project_purge_id,
    { reason: v.reason, confirm_text: v.confirm_text }), done('requested'));
  const approve = useRemovalWrite((v) => api.approvePurge(action.row.project_purge_id,
    { confirm_text: v.confirm_text, row_version: action.row.row_version }), done('approved'));
  const cancel = useRemovalWrite(() => api.cancelPurge(action.row.project_purge_id,
    { row_version: action.row.row_version }), done('cancelled'));
  const writer = { request, deleteArchive, approve, cancel }[action?.type];

  const open = (type, row, extra = {}) => {
    Object.values({ request, deleteArchive, approve, cancel }).forEach((w) => w.setError(''));
    setAction({ type, row, kind: row?.purge_kind, expected: row && `${row.client_code}/${row.project_code}`, ...extra });
  };
  const askFor = (p, kind) => open('request', null, { kind, projectId: p.project_id,
    expected: `${p.client_code ?? clientCode(p.client_id)}/${p.project_code}` });

  const admins = overview.data?.live_platform_admins;
  // ui-verifier check 8: the actions sit beside the state, and names wrap rather than truncate (who asked and who
  // approved is the point of four eyes); rows grow to fit.
  const twoLines = (v, who) => (v ? (
    <Box sx={{ py: 1, lineHeight: 1.4, whiteSpace: 'normal' }}>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>{who}</Typography>
      <Typography variant="caption">{when(v)}</Typography>
    </Box>) : null);
  const columns = [
    { field: 'purge_kind', headerName: t('removals.col.kind'), width: 120,
      valueGetter: (v) => t(`removals.kind.${v}`) },
    { field: 'project_code', headerName: t('removals.col.project'), width: 130,
      valueGetter: (v, r) => `${r.client_code}/${v}` },
    { field: 'state', headerName: t('removals.col.state'), flex: 1, minWidth: 190,
      renderCell: ({ row: r }) => (
        <Box sx={{ py: 1, whiteSpace: 'normal' }}>
          <Status size="sm" tone={TONE[r.state]} sx={{ whiteSpace: 'normal', height: 'auto', py: 0.5 }}>
            {r.waiting ? t('removals.state.WAITING', { at: when(r.runnable_from) }) : t(`removals.state.${r.state}`)}
          </Status>
          {r.approved_alone && (
            <Typography sx={{ fontSize: 12, color: 'text.secondary', mt: 0.5 }}>{t('removals.approvedAlone')}</Typography>
          )}
        </Box>) },
    { field: 'actions', headerName: '', width: 205, sortable: false,
      renderCell: ({ row: r }) => (
        <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', height: '100%', flexWrap: 'wrap', py: 1 }}>
          {r.state === 'OPEN' && (alone || r.requested_by_user_id !== myId) && (
            <Button size="small" variant="contained" onClick={() => open('approve', r)}>{t('removals.approve')}</Button>
          )}
          {(r.state === 'OPEN' || r.state === 'APPROVED') && (
            <Button size="small" color="warning" onClick={() => open('cancel', r)}>{t('removals.cancel')}</Button>
          )}
          {r.state === 'EXECUTED' && r.purge_kind === 'ARCHIVE' && (
            <Button size="small" color="warning" onClick={() => open('deleteArchive', r, { kind: 'DELETE_ARCHIVE' })}>
              {t('removals.deleteArchive')}</Button>
          )}
        </Stack>) },
    { field: 'requested_at', headerName: t('removals.col.requested'), width: 170,
      renderCell: ({ row: r }) => twoLines(r.requested_at, r.requested_by) },
    { field: 'approved_at', headerName: t('removals.col.approved'), width: 170,
      renderCell: ({ row: r }) => twoLines(r.approved_at, r.approved_by) },
    { field: 'reason', headerName: t('removals.col.reason'), flex: 1, minWidth: 110,
      renderCell: ({ value }) => <Box sx={{ py: 1, whiteSpace: 'normal' }}>{value}</Box> },
  ];

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="body2" sx={{ mb: 2, maxWidth: 900 }}>{t('removals.intro')}</Typography>
      {admins !== undefined && admins < (overview.data?.approvers_required ?? 2) && (
        <Alert severity="warning" sx={{ mb: 2 }}>{t('removals.fewAdmins', { n: admins })}</Alert>
      )}
      <WeeklyCheckCard />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <Card title={t('removals.due.title')} sx={{ flex: 1 }}>
          {(overview.data?.due_for_archiving ?? []).length === 0
            ? <Typography variant="body2">{t('removals.due.none')}</Typography>
            : overview.data.due_for_archiving.map((p) => (
              <Stack key={p.project_id} direction="row" spacing={2} sx={{ alignItems: 'center', py: 0.5 }}>
                <Typography sx={{ fontWeight: 600 }}>{`${p.client_code}/${p.project_code}`}</Typography>
                <Typography variant="body2">{t('removals.due.closed', { closed: p.closed_on, due: p.due_on })}</Typography>
                <Button size="small" onClick={() => askFor(p, 'ARCHIVE')}>{t('removals.due.ask')}</Button>
              </Stack>))}
        </Card>
        <Card title={t('removals.backlog.title')} sx={{ flex: 1 }}>
          {(overview.data?.archive_backlog ?? []).length === 0
            ? <Typography variant="body2">{t('removals.backlog.none')}</Typography>
            : overview.data.archive_backlog.map((b) => (
              <Typography key={b.project_id} variant="body2">
                {`${b.project_code ?? b.project_id}: ${t('removals.backlog.row', { n: b.owed_files })}`}
                {b.last_error ? ` — ${b.last_error}` : ''}
              </Typography>))}
        </Card>
      </Stack>
      <Card title={t('removals.new.title')} sx={{ mb: 2 }}
        bodySx={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
        <FormControl size="small" sx={{ minWidth: 260 }}>
          <InputLabel id="removal-project-label">{t('removals.new.project')}</InputLabel>
          <Select labelId="removal-project-label" id="removal-project" label={t('removals.new.project')}
            value={pick.project_id} onChange={(e) => setPick({ ...pick, project_id: e.target.value })}>
            {(projects.data ?? []).map((p) => (
              <MenuItem key={p.project_id} value={p.project_id}>{`${clientCode(p.client_id)}/${p.project_code}`}</MenuItem>))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="removal-kind-label">{t('removals.new.kind')}</InputLabel>
          <Select labelId="removal-kind-label" id="removal-kind" label={t('removals.new.kind')} value={pick.kind}
            onChange={(e) => setPick({ ...pick, kind: e.target.value })}>
            {['DELETE', 'ARCHIVE'].map((k) => <MenuItem key={k} value={k}>{t(`removals.kind.${k}`)}</MenuItem>)}
          </Select>
        </FormControl>
        <Button variant="contained" color="warning" disabled={!project} onClick={() => askFor(project, pick.kind)}>
          {t('removals.new.submit')}</Button>
      </Card>
      <Card title={t('removals.list.title')} bodySx={{ px: 0, pb: 0, pt: 0.5 }}>
        <DataGrid autoHeight getRowHeight={() => 'auto'} sx={{ '& .MuiDataGrid-cell': { display: 'flex', alignItems: 'center' } }} rows={rows.data ?? []} columns={columns} getRowId={(r) => r.project_purge_id}
          loading={rows.isLoading} disableRowSelectionOnClick hideFooter={(rows.data ?? []).length <= 25}
          localeText={{ noRowsLabel: t('removals.list.none') }} />
      </Card>
      {action && (                                        // keyed: each action starts with empty fields (sara L2)
        <Confirm key={`${action.type}-${action.row?.project_purge_id ?? action.projectId}`} action={action}
          onClose={() => setAction(null)} busy={writer?.m.isPending} error={writer?.error}
          onConfirm={(v) => writer.m.mutate(v)} />
      )}
    </Box>
  );
}
