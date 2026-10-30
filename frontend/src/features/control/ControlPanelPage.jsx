import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Link, MenuItem,
  Snackbar, Stack, Switch, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { controlApi, orgApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { Card, KV, Status, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';
import { fmtDate } from '../baselines/baselineKit';

// Control-A (docs/slice_control_a_spec.md §5; D-19, CT-1…CT-4): one row per agreed rule — today's figure against the
// threshold, the verdict, the owning role and the agreed response. The server measures and decides the verdict; the
// screen only lays it out. Free text renders as text (VB law 9).
const TONE = { GREEN: 'ok', FLAG: 'caution', ESCALATE: 'escalate', NOT_MEASURED: 'neutral' };
const REPORT = {
  priced_diff: (p) => links.baselines(p), coverage: (p) => links.reports(p, 'coverage'),
  solution_matrix: (p) => links.reports(p, 'solution_matrix'), interface_load: (p) => links.interfaces(p),
};

const num = (v, unit) => (v === null || v === undefined ? '–' : `${Number(v)}${unit === 'PCT' ? ' %' : ''}`);

function Figures({ r }) {
  const f = r.figures ?? {};
  if (r.reason) {
    return <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t(`control.reason.${r.reason}`, { label: f.baseline_label })}</Typography>;
  }
  return (
    <Stack sx={{ gap: 0.5 }}>
      {r.analysis_code === 'priced_diff' && f.base_days !== undefined && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
          {t('control.growth', { added: f.added_days, removed: Math.abs(f.removed_days), base: f.base_days, label: f.baseline_label })}
        </Typography>)}
      {f.unrated_count > 0 && (
        <Typography sx={{ fontSize: 13, color: 'status.caution' }}>{t('control.unrated', { n: f.unrated_count })}</Typography>)}
      {r.analysis_code === 'interface_load' && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('control.iface', { i: f.interface_count, n: f.fr_count })}</Typography>)}
    </Stack>
  );
}

function RuleRow({ projectId, r, canEdit, onEdit }) {
  const lt = r.comparison === 'LT';
  const changed = r.last_changed_at
    ? t('control.lastChanged', { date: fmtDate(r.last_changed_at), name: r.last_changed_by ?? '' })
    : t('control.houseDefault', { date: fmtDate(r.agreed_at) });
  return (
    <Card title={t(`control.analysis.${r.analysis_code}`)}
      action={(
        <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
          {r.is_enabled ? <Status tone={TONE[r.verdict]}>{t(`control.verdict.${r.verdict}`)}</Status>
            : <Tag tone="neutral">{t('control.verdict.off')}</Tag>}
          {canEdit && <Button size="small" variant="outlined" onClick={() => onEdit(r)}>{t('control.edit')}</Button>}
        </Stack>)}
      sx={r.is_enabled ? undefined : { opacity: 0.7 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} sx={{ gap: 3 }}>
        <Stack sx={{ minWidth: 220, gap: 1 }}>
          <Typography sx={{ fontFamily: MONO, fontSize: 26, fontWeight: 600 }}>{num(r.measured, r.unit)}</Typography>
          <Figures r={r} />
          <KV k={t(lt ? 'control.thresholdLt' : 'control.threshold')} v={num(r.threshold_value, r.unit)} mono />
          <KV k={t(lt ? 'control.escalateLt' : 'control.escalate')}
            v={r.escalate_value === null ? t('control.never') : num(r.escalate_value, r.unit)} mono />
        </Stack>
        <Stack sx={{ flex: 1, gap: 1 }}>
          <KV k={t('control.owner')} v={r.owner ? `${r.owner.org_role_code} · ${r.owner.org_role_name}`
            : <Tag tone="caution">{t('control.ownerNone')}</Tag>} />
          <KV k={t('control.action')} v={r.prescribed_action ?? '–'} />
          <KV k={t('control.path')} v={r.escalation_path ?? '–'} />
          <Stack direction="row" sx={{ gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{changed}</Typography>
            {REPORT[r.analysis_code] && (
              <Link component={RouterLink} to={REPORT[r.analysis_code](projectId)} sx={{ fontSize: 13 }}>{t('control.open')}</Link>)}
          </Stack>
        </Stack>
      </Stack>
    </Card>
  );
}

function EditDialog({ projectId, rule, onClose, onSaved, onStale }) {
  const qc = useQueryClient();
  const roles = useQuery({ queryKey: keys.roles(projectId), queryFn: () => orgApi.roles(projectId) });
  const lt = rule.comparison === 'LT';
  const [form, setForm] = useState({
    threshold_value: String(Number(rule.threshold_value)),
    escalate_value: rule.escalate_value === null ? '' : String(Number(rule.escalate_value)),
    owner_org_role_id: rule.owner_org_role_id ?? '', prescribed_action: rule.prescribed_action ?? '',
    escalation_path: rule.escalation_path ?? '', is_enabled: rule.is_enabled,
  });
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = useMutation({
    mutationFn: () => controlApi.update(projectId, rule.analysis_code, {
      threshold_value: form.threshold_value, escalate_value: form.escalate_value === '' ? null : form.escalate_value,
      owner_org_role_id: form.owner_org_role_id === '' ? null : Number(form.owner_org_role_id),
      prescribed_action: form.prescribed_action, escalation_path: form.escalation_path, is_enabled: form.is_enabled,
      change_rationale: reason, row_version: rule.row_version,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['control', String(projectId)] }); onSaved(); },
    onError: (err) => {
      // sara M1: the dialog holds the row version it opened with, so a stale save closes it; reopening reads the new row
      if (isStale(err)) { qc.invalidateQueries({ queryKey: ['control', String(projectId)] }); onStale(); }
      else setError(errorText(err));
    },
  });
  const live = (roles.data ?? []).filter((o) => o.is_active !== false);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="control-edit-title">
      <DialogTitle id="control-edit-title">{t('control.dialog.title', { name: t(`control.analysis.${rule.analysis_code}`) })}</DialogTitle>
      <DialogContent>
        <Stack sx={{ gap: 2, pt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
          {roles.error && <Alert severity="error">{errorText(roles.error)}</Alert>}
          <Stack direction="row" sx={{ gap: 2 }}>
            <TextField label={t(lt ? 'control.dialog.thresholdLt' : 'control.dialog.threshold')} type="number" required
              value={form.threshold_value} onChange={set('threshold_value')} slotProps={{ htmlInput: { min: 0, step: '0.01' } }} />
            <TextField label={t(lt ? 'control.dialog.escalateLt' : 'control.dialog.escalate')} type="number"
              value={form.escalate_value} onChange={set('escalate_value')} slotProps={{ htmlInput: { min: 0, step: '0.01' } }} />
          </Stack>
          <TextField select label={t('control.dialog.owner')} value={form.owner_org_role_id} onChange={set('owner_org_role_id')}>
            <MenuItem value="">{t('control.dialog.noOwner')}</MenuItem>
            {live.map((o) => <MenuItem key={o.org_role_id} value={o.org_role_id}>{o.org_role_code} · {o.org_role_name}</MenuItem>)}
          </TextField>
          <TextField label={t('control.action')} multiline minRows={2} value={form.prescribed_action}
            onChange={set('prescribed_action')} slotProps={{ htmlInput: { maxLength: 2000 } }} />
          <TextField label={t('control.path')} multiline minRows={2} value={form.escalation_path}
            onChange={set('escalation_path')} slotProps={{ htmlInput: { maxLength: 2000 } }} />
          <FormControlLabel label={t('control.dialog.enabled')}
            control={<Switch checked={form.is_enabled} onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })} />} />
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

export default function ControlPanelPage() {
  const { projectId } = useParams();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.controlPanel(projectId), queryFn: () => controlApi.panel(projectId) });
  const [editing, setEditing] = useState(null);
  const [notice, setNotice] = useState('');
  const d = q.data;
  return (
    <Page title={t('control.title')} subtitle={t('control.subtitle')} error={q.error && errorText(q.error)}>
      {d && (
        <Stack sx={{ gap: 2 }}>
          {d.rows.map((r) => <RuleRow key={r.analysis_code} projectId={projectId} r={r} canEdit={canEdit} onEdit={setEditing} />)}
          {d.coming.length > 0 && (
            <Card title={t('control.coming')}>
              <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                {d.coming.map((c) => (
                  <Typography component="li" key={c.analysis_code} sx={{ fontSize: 13.5, color: 'text.secondary' }}>
                    {t(`control.analysis.${c.analysis_code}`)} — {t(`control.comingBy.${c.brought_by}`)}
                  </Typography>))}
              </Box>
            </Card>)}
        </Stack>)}
      {editing && (
        <EditDialog projectId={projectId} rule={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); setNotice(t('control.saved')); }}
          onStale={() => { setEditing(null); setNotice(t('control.stale')); }} />)}
      <Snackbar open={Boolean(notice)} autoHideDuration={5000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
