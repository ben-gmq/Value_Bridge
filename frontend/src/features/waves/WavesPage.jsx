import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Snackbar, Stack, TextField,
  Tooltip, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import EditOutlined from '@mui/icons-material/EditOutlined';
import { errorText, isStale } from '../../api/client';
import { phaseApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Code, ListRow, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { fmtDate } from '../baselines/baselineKit';
import { WavePlan } from './WavePlan';
import { WaveStatus } from './waveKit';

const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };

// Add or edit a wave. The code is typed (no number series); the order is the list's, never the dates (schema §3.1).
function WaveDialog({ projectId, wave, onClose, onDone }) {
  const [f, setF] = useState({ phase_code: wave?.phase_code ?? '', phase_name: wave?.phase_name ?? '',
    start_date: wave?.start_date ?? '', end_date: wave?.end_date ?? '', status_code: wave?.status_code ?? '' });
  const [error, setError] = useState('');
  const { options: statusOptions } = useCodes(projectId, 'PHASE_STATUS');
  const opts = statusOptions(wave?.status_code).map((c) => ({ value: c.code, label: c.label }));
  const status = f.status_code || opts[0]?.value || '';
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const m = useMutation({
    mutationFn: () => {
      const body = { phase_code: f.phase_code.trim(), phase_name: f.phase_name.trim(), start_date: f.start_date || null,
        end_date: f.end_date || null, status_code: status };
      return wave ? phaseApi.update(wave.phase_id, { row_version: wave.row_version, ...body })
        : phaseApi.create(projectId, body);
    },
    onSuccess: (row) => { onDone(row); onClose(); },
    onError: (err) => setError(isStale(err) ? t('waves.stale') : errorText(err, t('common.saveFailed'))),
  });
  const ok = f.phase_code.trim() && f.phase_name.trim() && status;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{wave ? t('waves.editTitle', { code: wave.phase_code }) : t('waves.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={2}>
            <TextField id="wave-code" label={t('waves.field.code')} required value={f.phase_code} onChange={set('phase_code')}
              helperText={t('waves.codeHelp')} slotProps={{ htmlInput: { maxLength: 20 } }} sx={{ width: 200 }} />
            <TextField id="wave-name" label={t('waves.field.name')} required fullWidth value={f.phase_name}
              onChange={set('phase_name')} helperText={t('waves.nameHelp')} slotProps={{ htmlInput: { maxLength: 200 } }} />
          </Stack>
          <Stack direction="row" spacing={2}>
            <TextField id="wave-start" type="date" label={t('waves.field.start')} value={f.start_date ?? ''}
              onChange={set('start_date')} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
            <TextField id="wave-end" type="date" label={t('waves.field.end')} value={f.end_date ?? ''}
              onChange={set('end_date')} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
          </Stack>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: -1 }}>{t('waves.datesHelp')}</Typography>
          <SimpleSelect id="wave-status" label={t('waves.field.status')} value={status}
            onChange={(v) => setF({ ...f, status_code: v })} options={opts} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!ok || m.isPending} onClick={() => { setError(''); m.mutate(); }}>
          {wave ? t('common.save') : t('waves.add')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function WaveList({ projectId, canEdit, notify }) {
  const qc = useQueryClient();
  const [showRetired, setShowRetired] = useState(false);
  const [editing, setEditing] = useState(null);           // null | 'new' | a wave
  const [retiring, setRetiring] = useState(null);
  const [error, setError] = useState('');
  const q = useQuery({ queryKey: [...keys.phases(projectId), { retired: showRetired }],
    queryFn: () => phaseApi.list(projectId, showRetired) });
  const { getLabel } = useCodes(projectId, 'PHASE_STATUS');
  const rows = q.data ?? [];
  const live = rows.filter((w) => w.is_active);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.phases(projectId) });
  const fail = (err) => { refresh(); setError(isStale(err) ? t('waves.stale') : errorText(err, t('common.saveFailed'))); };
  const move = useMutation({
    mutationFn: ({ from, to }) => {
      const order = [...live];
      const [w] = order.splice(from, 1);
      order.splice(to, 0, w);
      return phaseApi.reorder(projectId, order.map((x) => ({ id: x.phase_id, row_version: x.row_version })));
    },
    onSuccess: () => { setError(''); refresh(); notify(t('waves.reordered')); },
    onError: fail,
  });
  const retire = useMutation({
    mutationFn: (w) => phaseApi.retire(w.phase_id, w.row_version),
    onSuccess: () => { setRetiring(null); setError(''); refresh(); notify(t('waves.retiredNotice')); },
    onError: (err) => { setRetiring(null); fail(err); },
  });
  const restore = useMutation({
    mutationFn: (w) => phaseApi.restore(w.phase_id),
    onSuccess: (row) => { setError(''); refresh(); notify(t('waves.restored', { code: row.phase_code })); },
    onError: fail,
  });
  const busy = move.isPending || retire.isPending || restore.isPending;
  const current = live.find((w) => w.status_code === 'IN_DELIVERY');   // Q-57: the lowest live wave in delivery

  return (
    <>
      {(error || q.error) && <Alert severity="error" sx={ERR_SX} onClose={() => setError('')}>{error || errorText(q.error)}</Alert>}
      <Card title={t('waves.count', { n: live.length })}
        action={<Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <ShowRetired id="wave-show-retired" checked={showRetired} onChange={setShowRetired} />
          {canEdit && <Button variant="contained" startIcon={<AddRounded />} onClick={() => setEditing('new')}>
            {t('waves.add')}</Button>}
        </Stack>} bodySx={{ gap: 1 }}>
        {!q.isLoading && rows.length === 0 && (
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('waves.empty')}</Typography>)}
        {rows.map((w) => {
          const pos = live.indexOf(w);
          return (
            <ListRow key={w.phase_id}>
              <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', minWidth: 0, flex: 1 }}>
                <Code tone={w.is_active ? 'navy' : 'muted'}>{w.phase_code}</Code>
                <Box sx={{ minWidth: 0 }}>
                  <Typography noWrap sx={{ fontSize: 14, fontWeight: 600,
                    color: w.is_active ? 'text.primary' : 'text.secondary' }}>{w.phase_name}</Typography>
                  <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                    {w.start_date || w.end_date ? `${fmtDate(w.start_date) || '…'} – ${fmtDate(w.end_date) || '…'}`
                      : t('waves.noDates')}</Typography>
                </Box>
              </Box>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexShrink: 0 }}>
                {current?.phase_id === w.phase_id && <Tag tone="purple">{t('waves.current')}</Tag>}
                {w.is_active ? <WaveStatus code={w.status_code} label={getLabel(w.status_code)} />
                  : <Tag tone="neutral">{t('waves.retired')}</Tag>}
                {canEdit && w.is_active && (
                  <>
                    <Tooltip title={t('waves.moveUp')}><span>
                      <IconButton size="small" aria-label={t('waves.moveUp')} disabled={pos <= 0 || busy}
                        onClick={() => move.mutate({ from: pos, to: pos - 1 })}><ArrowUpwardIcon fontSize="small" /></IconButton>
                    </span></Tooltip>
                    <Tooltip title={t('waves.moveDown')}><span>
                      <IconButton size="small" aria-label={t('waves.moveDown')} disabled={pos >= live.length - 1 || busy}
                        onClick={() => move.mutate({ from: pos, to: pos + 1 })}><ArrowDownwardIcon fontSize="small" /></IconButton>
                    </span></Tooltip>
                    <Tooltip title={t('waves.edit')}>
                      <IconButton size="small" aria-label={t('waves.edit')} disabled={busy}
                        onClick={() => setEditing(w)}><EditOutlined fontSize="small" /></IconButton>
                    </Tooltip>
                    <Button size="small" color="warning" disabled={busy} onClick={() => setRetiring(w)}>{t('waves.retire')}</Button>
                  </>)}
                {canEdit && !w.is_active && (
                  <Button size="small" variant="outlined" disabled={busy} onClick={() => restore.mutate(w)}>{t('waves.restore')}</Button>)}
              </Stack>
            </ListRow>
          );
        })}
      </Card>
      {editing && <WaveDialog projectId={projectId} wave={editing === 'new' ? null : editing} onClose={() => setEditing(null)}
        onDone={(row) => { refresh(); notify(editing === 'new' ? t('waves.added', { code: row.phase_code }) : t('waves.saved')); }} />}
      <ConfirmDialog open={Boolean(retiring)} title={t('waves.retireTitle', { code: retiring?.phase_code ?? '' })}
        body={t('waves.retireBody')} confirmLabel={t('waves.retire')} busy={retire.isPending}
        onClose={() => setRetiring(null)} onConfirm={() => retire.mutate(retiring)} />
    </>
  );
}

export default function WavesPage() {
  const { projectId } = useParams();
  const canEdit = useCanEdit();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'plan' ? 'plan' : 'list';
  const [notice, setNotice] = useState('');
  return (
    <Page title={t('waves.title')} subtitle={t('waves.subtitle')}>
      <Segmented label={t('waves.title')} value={tab} sx={{ mb: 2 }}
        onChange={(v) => setParams(v === 'plan' ? { tab: 'plan' } : {}, { replace: true })}
        options={[{ value: 'list', label: t('waves.tab.list') }, { value: 'plan', label: t('waves.tab.plan') }]} />
      {tab === 'list' && <WaveList projectId={projectId} canEdit={canEdit} notify={setNotice} />}
      {tab === 'plan' && <WavePlan projectId={projectId} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}

