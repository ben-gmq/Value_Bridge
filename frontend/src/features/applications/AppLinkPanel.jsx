import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Link, Stack,
  TextField, Tooltip, Typography } from '@mui/material';
import EditRounded from '@mui/icons-material/EditRounded';
import LinkOffRounded from '@mui/icons-material/LinkOffRounded';
import { errorText, isStale } from '../../api/client';
import { appApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { t } from '../../i18n/t';
import { Mono, PickDialog, SectionTitle } from '../processes/chartKit';

const ERR_SX = { mb: 1, whiteSpace: 'pre-wrap' };

function NoteDialog({ row, save, onClose, onDone, onStale }) {
  const [note, setNote] = useState(row.note ?? '');
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => save(row, note.trim() || null),
    onSuccess: () => { onDone(); onClose(); },
    onError: (err) => { if (isStale(err)) { onStale(); onClose(); } else setError(errorText(err, t('common.saveFailed'))); },
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('applications.links.editTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <TextField id="applink-note" sx={{ mt: 1 }} label={t('applications.links.note')} multiline minRows={2} fullWidth
          autoFocus value={note} onChange={(e) => setNote(e.target.value)} slotProps={{ htmlInput: { maxLength: 4000 } }} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending} onClick={() => { setError(''); m.mutate(); }}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/**
 * Applications linked to one owner — a Solution (to-be allocation) or a process step (as-is
 * support). `api` = { list, link(applicationId, note), edit(row, note), unlink(row) } over the
 * owner's routes; `rowId` names the link id field; `allow(app)` filters the picker; `ruleHint`
 * explains what the filter leaves out.
 */
export function AppLinkPanel({ projectId, title, empty, ownerKey, api, rowId, allow = () => true, ruleHint,
  disabled }) {
  const qc = useQueryClient();
  const canEdit = useCanEdit() && !disabled;
  const { getLabel: lifecycleLabel } = useCodes(projectId, 'APP_LIFECYCLE');
  const listKey = keys.appLinksOf(...ownerKey);
  const q = useQuery({ queryKey: listKey, queryFn: api.list });
  const rows = q.data ?? [];
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [error, setError] = useState('');
  const [warning, setWarning] = useState(null);
  const appsQ = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId), enabled: adding });
  const linked = new Set(rows.map((r) => r.application_id));
  const options = (appsQ.data ?? []).filter((a) => a.is_active && !linked.has(a.application_id) && allow(a));
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.appLinks() });
    qc.invalidateQueries({ queryKey: keys.applications(projectId) });     // the register's counts
  };
  const stale = () => { refresh(); setError(t('applications.links.stale')); };
  const unlink = useMutation({
    mutationFn: (row) => api.unlink(row),
    onSuccess: () => { setRemoving(null); setError(''); refresh(); },
    onError: (err) => { setRemoving(null); refresh(); setError(isStale(err) ? t('applications.links.stale') : errorText(err, t('common.saveFailed'))); },
  });

  return (
    <Box>
      <SectionTitle action={canEdit && (
        <Button size="small" onClick={() => { setError(''); setNote(''); setAdding(true); }}>{t('applications.links.add')}</Button>)}>
        {title}
      </SectionTitle>
      {error && <Alert severity="error" sx={ERR_SX} onClose={() => setError('')}>{error}</Alert>}
      {warning && <Alert severity="warning" sx={ERR_SX} onClose={() => setWarning(null)}>
        {t(`applications.warn.${warning.code}`, { items: warning.items.join(', ') })}</Alert>}
      {q.error && <Alert severity="error" sx={ERR_SX}>{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{empty}</Typography>)}
      <Stack spacing={1.5}>
        {rows.map((row) => (
          <Stack key={row[rowId]} direction="row" sx={{ alignItems: 'flex-start', gap: 1 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Link component={RouterLink} to={links.application(projectId, row.application_id)} underline="hover"
                  sx={{ fontWeight: 600 }}><Mono>{row.application_code}</Mono> {row.application_name}</Link>
                <Chip size="small" variant="outlined" label={lifecycleLabel(row.lifecycle_code)} />
              </Stack>
              {row.note && <Typography sx={{ fontSize: 13, color: 'text.secondary', mt: 0.5, whiteSpace: 'pre-wrap' }}>{row.note}</Typography>}
            </Box>
            {canEdit && (
              <>
                <Tooltip title={t('applications.links.edit')}>
                  <IconButton size="small" aria-label={t('applications.links.edit')} onClick={() => { setError(''); setEditing(row); }}>
                    <EditRounded fontSize="small" /></IconButton>
                </Tooltip>
                <Tooltip title={t('applications.links.remove')}>
                  <IconButton size="small" aria-label={t('applications.links.remove')} onClick={() => { setError(''); setRemoving(row); }}>
                    <LinkOffRounded fontSize="small" /></IconButton>
                </Tooltip>
              </>)}
          </Stack>
        ))}
      </Stack>

      {adding && (
        <PickDialog open title={t('applications.links.addTitle')} optionLabel={t('applications.links.pick')}
          options={options} getOptionLabel={(a) => `${a.application_code} ${a.application_name}`}
          submitLabel={t('applications.links.add')}
          emptyHint={(
            <Alert severity="info">
              {t('applications.links.noApps')}{' '}
              <Link component={RouterLink} to={links.applications(projectId)}>{t('applications.links.goApps')}</Link>
            </Alert>)}
          extra={(
            <Stack spacing={1}>
              {ruleHint && <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{ruleHint}</Typography>}
              <TextField id="applink-new-note" label={t('applications.links.note')} multiline minRows={2} fullWidth
                value={note} onChange={(e) => setNote(e.target.value)} slotProps={{ htmlInput: { maxLength: 4000 } }} />
            </Stack>)}
          onSubmit={(a) => api.link(a.application_id, note.trim() || null)}
          onDone={(r) => { refresh(); setWarning(r?.warnings?.[0] ?? null); }} onClose={() => setAdding(false)} />)}
      {editing && <NoteDialog row={editing} save={api.edit} onClose={() => setEditing(null)} onDone={refresh} onStale={stale} />}
      <ConfirmDialog open={Boolean(removing)} title={t('applications.links.removeTitle')}
        body={removing ? t('applications.links.removeBody', { app: `${removing.application_code} ${removing.application_name}` }) : ''}
        confirmLabel={t('applications.links.remove')} busy={unlink.isPending}
        onClose={() => setRemoving(null)} onConfirm={() => unlink.mutate(removing)} />
    </Box>
  );
}
