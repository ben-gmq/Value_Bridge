// Slice 17 (spec §9, §10 criterion 13; schema rev 3 §3; AR-13, AR-18, AR-24): requests for platform-admin rights. One
// admin asks with a reason; a different, independent admin approves (the user becomes an admin at once), rejects with
// a reason, or any admin cancels. The card shows what the approver needs to judge it (P5, S1): the email, who created
// the account and when, whether its owner has signed in, and the request's age. Hiding Approve from the requester and
// the user is presentation only: the database guards decide.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { useAuth } from '../../app/AuthContext';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card } from '../../components/kit';
import { t } from '../../i18n/t';
import { useApprovers } from './useApprovers';

const when = (iso) => (iso ? new Date(iso).toLocaleString() : '');

export function useGrantWrite(fn, onOk) {
  const qc = useQueryClient();
  const [error, setError] = useState('');
  const m = useMutation({ mutationFn: fn,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: keys.grantRequests() });
      qc.invalidateQueries({ queryKey: ['users'] });
      setError('');
      onOk?.(res);
    },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))) });
  return { m, error, setError };
}

// Request: from the user list's "Request admin rights" button.
export function RequestGrantDialog({ user, onClose, notify }) {
  const [reason, setReason] = useState('');
  const w = useGrantWrite(() => api.requestGrant(user.app_user_id, { reason: reason.trim() }),
    () => { setReason(''); onClose(); notify(t('grants.requested')); });
  if (!user) return null;
  return (
    <ConfirmDialog open title={t('grants.requestTitle', { name: user.display_name })}
      body={t('grants.requestBody', { name: user.display_name })} confirmLabel={t('grants.request')}
      busy={w.m.isPending || !reason.trim()} onClose={() => { setReason(''); w.setError(''); onClose(); }}
      onConfirm={() => w.m.mutate()}>
      {w.error && <Alert severity="error" sx={{ mb: 2 }}>{w.error}</Alert>}
      <TextField id="grant-reason" label={t('grants.reason')} value={reason} fullWidth multiline minRows={2}
        onChange={(e) => setReason(e.target.value)} slotProps={{ htmlInput: { maxLength: 2000 } }} />
    </ConfirmDialog>
  );
}

function Decide({ action, onClose, notify }) {
  const [reason, setReason] = useState('');
  const r = action?.row;
  const fn = (body) => (action.type === 'approve' ? api.approveGrant(r.grant_id, body)
    : action.type === 'reject' ? api.rejectGrant(r.grant_id, body) : api.cancelGrant(r.grant_id, body));
  const w = useGrantWrite((body) => fn(body), () => {
    setReason('');
    onClose();
    notify(t(`grants.done.${{ approve: 'approved', reject: 'rejected', cancel: 'cancelled' }[action.type]}`,
      { name: r.target_name }));
  });
  if (!action) return null;
  const vars = { name: r.target_name, email: r.target_email, who: r.requested_by, days: r.age_days, reason: r.reason };
  const needsReason = action.type === 'reject';
  return (
    <ConfirmDialog open title={t(`grants.${action.type}Title`, vars)} body={t(`grants.${action.type}Body`, vars)}
      confirmLabel={t(`grants.${action.type}`)} busy={w.m.isPending || (needsReason && !reason.trim())}
      onClose={() => { setReason(''); w.setError(''); onClose(); }}
      onConfirm={() => w.m.mutate({ row_version: r.row_version, ...(needsReason ? { reason: reason.trim() } : {}) })}>
      {w.error && <Alert severity="error" sx={{ mb: 2 }}>{w.error}</Alert>}
      {needsReason && (
        <TextField id="grant-reject-reason" label={t('grants.reason')} value={reason} fullWidth multiline minRows={2}
          onChange={(e) => setReason(e.target.value)} slotProps={{ htmlInput: { maxLength: 2000 } }} />)}
    </ConfirmDialog>
  );
}

// The card above the user list: open requests only (decided ones stay in the record, GET /admin/grant-requests).
export function PendingGrants({ notify }) {
  const { me } = useAuth();
  const myId = me?.user?.app_user_id;
  const q = useQuery({ queryKey: keys.grantRequests(), queryFn: api.grantRequests });
  const [action, setAction] = useState(null);
  const { alone } = useApprovers();
  const open = (q.data ?? []).filter((r) => r.state === 'OPEN');
  // AR-28: the user themselves never approves; the requester may only while the single-owner setting is on
  const mine = (r) => r.target_user_id === myId || (!alone && r.requested_by_user_id === myId);
  return (
    <Card title={t('grants.pending.title')} sx={{ mb: 2 }} bodySx={{ px: 0, pb: 0, pt: 0.5 }}>
      {q.error && <Alert severity="error" sx={{ m: 2 }}>{errorText(q.error, t('grants.loadFailed'))}</Alert>}
      {open.length === 0 ? (
        <Typography sx={{ px: 2, pb: 2, fontSize: 13.5, color: 'text.secondary' }}>{t('grants.pending.none')}</Typography>
      ) : (
        <DataGrid autoHeight disableRowSelectionOnClick getRowHeight={() => 'auto'} rows={open}
          getRowId={(r) => r.grant_id} sx={{ bgcolor: 'background.paper', border: 0, borderRadius: 0,
            '& .MuiDataGrid-cell': { py: 1, alignItems: 'flex-start', whiteSpace: 'normal' } }}
          columns={[
            { field: 'target_name', headerName: t('grants.col.user'), flex: 1, minWidth: 180,
              renderCell: ({ row }) => (
                <Stack><Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{row.target_name}</Typography>
                  <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{row.target_email}</Typography></Stack>) },
            { field: 'account', headerName: t('grants.col.account'), flex: 1, minWidth: 200, sortable: false,
              valueGetter: (v, row) => t(row.target_created_by ? 'grants.account' : 'grants.account.noCreator', {
                who: row.target_created_by, when: when(row.target_created_at),
                signedIn: t(row.target_has_signed_in ? 'grants.signedIn' : 'grants.notSignedIn') }) },
            { field: 'requested_at', headerName: t('grants.col.requested'), flex: 1, minWidth: 190,
              valueGetter: (v, row) => t('grants.age', { when: when(row.requested_at), who: row.requested_by,
                days: row.age_days }) },
            { field: 'reason', headerName: t('grants.col.reason'), flex: 1.4, minWidth: 200 },
            { field: 'x', headerName: '', width: 260, sortable: false, renderCell: ({ row }) => (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                {!mine(row) && (
                  <Button size="small" variant="contained" onClick={() => setAction({ type: 'approve', row })}>
                    {t('grants.approve')}</Button>)}
                {row.requested_by_user_id !== myId && (
                  <Button size="small" onClick={() => setAction({ type: 'reject', row })}>{t('grants.reject')}</Button>)}
                <Button size="small" color="warning" onClick={() => setAction({ type: 'cancel', row })}>
                  {t('grants.cancel')}</Button>
              </Stack>) },
          ]} />
      )}
      {open.some(mine) && (
        <Typography sx={{ px: 2, py: 1, fontSize: 12.5, color: 'text.secondary' }}>{t('grants.notYours')}</Typography>)}
      <Decide key={action ? `${action.type}-${action.row.grant_id}` : 'none'} action={action}
        onClose={() => setAction(null)} notify={notify} />
    </Card>
  );
}
