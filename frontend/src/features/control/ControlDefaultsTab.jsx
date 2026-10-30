import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, KV } from '../../components/kit';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';
import { fmtDate } from '../baselines/baselineKit';

// Control-C (docs/slice_control_c_spec.md §3; CC-6): the FTC company defaults every new project starts from. Platform
// admins only (the Admin page and the server both refuse anyone else). An edit needs a reason, reaches future projects
// only, and its history is read from the audit trail (R1-P4). Free text renders as text (VB law 9).
const num = (v, unit) => (v === null || v === undefined ? '–' : `${Number(v)}${unit === 'PCT' ? ' %' : ''}`);

function History({ rows, unit }) {
  if (!rows.length) return <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('control.house.never')}</Typography>;
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
      {rows.map((h, i) => (
        <Typography component="li" key={`${h.at}-${i}`} sx={{ fontSize: 12.5, color: 'text.secondary' }}>
          {t('control.house.historyRow', { date: fmtDate(h.at), name: h.by ?? '' })}
          {Object.keys(h.to).map((f) => ` · ${t(`control.house.field.${f}`)} ${num(h.from[f], unit)} → ${num(h.to[f], unit)}`).join('')}
          {h.text_changed.map((f) => ` · ${t(`control.house.textChanged.${f}`)}`).join('')}
          {h.change_rationale ? ` — ${h.change_rationale}` : ''}
        </Typography>))}
    </Box>
  );
}

function EditDefault({ rule, onClose, onSaved, onStale }) {
  const qc = useQueryClient();
  const lt = rule.comparison === 'LT';
  const [form, setForm] = useState({
    threshold_value: String(Number(rule.threshold_value)),
    escalate_value: rule.escalate_value === null ? '' : String(Number(rule.escalate_value)),
    prescribed_action: rule.prescribed_action ?? '', escalation_path: rule.escalation_path ?? '',
  });
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = useMutation({
    mutationFn: () => controlApi.updateHouseDefault(rule.analysis_code, {
      threshold_value: form.threshold_value, escalate_value: form.escalate_value === '' ? null : form.escalate_value,
      prescribed_action: form.prescribed_action, escalation_path: form.escalation_path,
      change_rationale: reason, row_version: rule.row_version,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: keys.houseDefaults() }); onSaved(); },
    onError: (err) => {
      if (isStale(err)) { qc.invalidateQueries({ queryKey: keys.houseDefaults() }); onStale(); }
      else setError(errorText(err));
    },
  });
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="house-edit-title">
      <DialogTitle id="house-edit-title">{t('control.house.dialogTitle', { name: t(`control.analysis.${rule.analysis_code}`) })}</DialogTitle>
      <DialogContent>
        <Stack sx={{ gap: 2, pt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
          <Alert severity="info">{t('control.house.futureOnly')}</Alert>
          <Stack direction="row" sx={{ gap: 2 }}>
            <TextField label={t(lt ? 'control.dialog.thresholdLt' : 'control.dialog.threshold')} type="number" required
              value={form.threshold_value} onChange={set('threshold_value')} slotProps={{ htmlInput: { min: 0, step: '0.01' } }} />
            <TextField label={t(lt ? 'control.dialog.escalateLt' : 'control.dialog.escalate')} type="number"
              value={form.escalate_value} onChange={set('escalate_value')} slotProps={{ htmlInput: { min: 0, step: '0.01' } }} />
          </Stack>
          <TextField label={t('control.action')} multiline minRows={2} value={form.prescribed_action}
            onChange={set('prescribed_action')} helperText={t('control.house.textWarning')}
            slotProps={{ htmlInput: { maxLength: 2000 } }} />
          <TextField label={t('control.path')} multiline minRows={2} value={form.escalation_path}
            onChange={set('escalation_path')} helperText={t('control.house.textWarning')}
            slotProps={{ htmlInput: { maxLength: 2000 } }} />
          <TextField label={t('control.dialog.reason')} helperText={t('control.dialog.reasonHelp')} required multiline minRows={2}
            value={reason} onChange={(e) => setReason(e.target.value)} slotProps={{ htmlInput: { maxLength: 2000 } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('control.dialog.cancel')}</Button>
        <Button variant="contained" disabled={save.isPending || !reason.trim() || form.threshold_value === ''}
          onClick={() => { setError(''); save.mutate(); }}>{t('control.dialog.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export function ControlDefaultsTab({ notify }) {
  const q = useQuery({ queryKey: keys.houseDefaults(), queryFn: controlApi.houseDefaults });
  const [editing, setEditing] = useState(null);
  if (q.error) return <Alert severity="error" sx={{ mt: 2 }}>{errorText(q.error)}</Alert>;
  return (
    <Stack sx={{ gap: 2, mt: 2 }}>
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('control.house.intro')}</Typography>
      {(q.data ?? []).map((r) => {
        const lt = r.comparison === 'LT';
        return (
          <Card key={r.analysis_code} title={t(`control.analysis.${r.analysis_code}`)}
            action={<Button size="small" variant="outlined" onClick={() => setEditing(r)}>{t('control.edit')}</Button>}>
            <Stack direction={{ xs: 'column', md: 'row' }} sx={{ gap: 3 }}>
              <Stack sx={{ minWidth: 220, gap: 1 }}>
                <KV k={t(lt ? 'control.thresholdLt' : 'control.threshold')} v={<Box component="span" sx={{ fontFamily: MONO }}>{num(r.threshold_value, r.unit)}</Box>} />
                <KV k={t(lt ? 'control.escalateLt' : 'control.escalate')}
                  v={<Box component="span" sx={{ fontFamily: MONO }}>{r.escalate_value === null ? t('control.never') : num(r.escalate_value, r.unit)}</Box>} />
              </Stack>
              <Stack sx={{ flex: 1, gap: 1 }}>
                <KV k={t('control.action')} v={r.prescribed_action ?? '–'} />
                <KV k={t('control.path')} v={r.escalation_path ?? '–'} />
                <History rows={r.history} unit={r.unit} />
              </Stack>
            </Stack>
          </Card>);
      })}
      {editing && (
        <EditDefault rule={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); notify(t('control.house.saved')); }}
          onStale={() => { setEditing(null); notify(t('control.house.stale')); }} />)}
    </Stack>
  );
}
