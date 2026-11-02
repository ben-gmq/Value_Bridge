import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { riskApi, stakeholderApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, Code } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CodeTitle, SaveState, TwoCol } from '../frs/frKit';
import { ExposureTag, RiskFields, useRiskRefs } from './riskKit';

const FIELDS = ['title', 'description', 'probability_code', 'impact_code', 'owner_org_role_id', 'raised_date',
  'target_date', 'phase_id', 'solution_id', 'bfc_node_id', 'mitigation', 'status_code'];
const pick = (r) => Object.fromEntries(FIELDS.map((k) => [k, r[k] ?? '']));

// Promote to an issue (§4.10 promote_risk_to_issue): the raiser is a stakeholder chosen here (RK-4); the issue takes
// the risk's title and description and its own optional target date (R1-1). The risk stays as the record.
function PromoteDialog({ projectId, risk, onClose, onDone, onStale }) {
  const stk = useQuery({ queryKey: keys.stakeholders(projectId), queryFn: () => stakeholderApi.list(projectId, true) });
  const sev = useCodes(projectId, 'ISSUE_SEVERITY');
  const typ = useCodes(projectId, 'ISSUE_TYPE');
  const [f, setF] = useState({ raised_by_stakeholder_id: '', severity_code: '', issue_type_code: '', target_date: '' });
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => riskApi.materialise(risk.risk_id, { row_version: risk.row_version, ...f,
      target_date: f.target_date || null }),
    onSuccess: (out) => { onDone(out); onClose(); },
    onError: (err) => (isStale(err) ? onStale() : setError(errorText(err, t('common.saveFailed')))),
  });
  const people = (stk.data ?? []).filter((s) => s.is_active);
  const ready = f.raised_by_stakeholder_id && f.severity_code && f.issue_type_code;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('risks.promoteTitle', { number: risk.risk_number })}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mb: 1 }}>{t('risks.promoteBody')}</Typography>
        {people.length === 0 && <Alert severity="info" sx={{ mb: 2 }}>{t('issues.needStakeholder')}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <SimpleSelect id="rsk-promote-raiser" label={t('issues.field.raiser')} value={f.raised_by_stakeholder_id}
            onChange={(v) => setF({ ...f, raised_by_stakeholder_id: v })}
            options={people.map((s) => ({ value: s.stakeholder_id, label: s.stakeholder_name }))} />
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
            <SimpleSelect id="rsk-promote-severity" label={t('issues.field.severity')} value={f.severity_code}
              onChange={(v) => setF({ ...f, severity_code: v })}
              options={sev.options().map((c) => ({ value: c.code, label: c.label }))} />
            <SimpleSelect id="rsk-promote-type" label={t('issues.field.type')} value={f.issue_type_code}
              onChange={(v) => setF({ ...f, issue_type_code: v })}
              options={typ.options().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <TextField id="rsk-promote-target" type="date" size="small" label={t('risks.issueTarget')} value={f.target_date}
            onChange={(e) => setF({ ...f, target_date: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !ready}
          onClick={() => { setError(''); m.mutate(); }}>{t('risks.promote')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function RiskPage() {
  const { projectId, riskId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('RISK');
  const refs = useRiskRefs(projectId);
  const q = useQuery({ queryKey: keys.risk(riskId), queryFn: () => riskApi.get(riskId) });
  const risk = q.data;
  const sts = useCodes(projectId, 'RISK_STATUS');
  const form = useEditForm(risk, pick);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [promoting, setPromoting] = useState(false);
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.risk(riskId) });
    qc.invalidateQueries({ queryKey: keys.risks(projectId) });
    qc.invalidateQueries({ queryKey: ['control', String(projectId)] });
  };
  const landed = (row, msg) => { form.saved(row); qc.setQueryData(keys.risk(riskId), row); refreshAll(); setNotice(msg); };
  const save = useFormSave({
    save: () => {
      const body = { row_version: form.version };
      for (const k of form.changed) body[k] = k === 'title' ? form.values.title.trim() : blankToNull(form.values[k]);
      return riskApi.update(risk.risk_id, body);
    },
    onSaved: (row) => landed(row, t('risks.saved')),
  });
  const reload = async () => {
    try {
      form.rebase(await qc.fetchQuery({ queryKey: keys.risk(riskId), queryFn: () => riskApi.get(riskId) }));
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => { refreshAll(); setActionError(isStale(err) ? t('risks.stale') : errorText(err, t('common.saveFailed'))); };
  const retire = useMutation({
    mutationFn: () => riskApi.retire(risk.risk_id, risk.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('risks.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => riskApi.restore(risk.risk_id),
    onSuccess: (row) => { setActionError(''); landed(row, t('risks.restored')); },
    onError: actionFail,
  });

  if (q.error) return <Page title={t('risks.title')} error={errorText(q.error)} />;
  if (!risk || !form.values) return <Page title={t('risks.loading')} />;

  const v = form.values;
  const live = risk.is_active;
  const materialised = risk.status_behaviour === 'MATERIALISED';
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const unsaved = Object.fromEntries(form.changed.map((k) => [t(`risks.field.${k}`), v[k]]));
  // A PATCH moves among open and closed statuses only; MATERIALISED comes only from promote.
  const statusOptions = materialised
    ? sts.options(risk.status_code).filter((c) => c.code === risk.status_code)
    : sts.options(risk.status_code).filter((c) => c.behaviour_code !== 'MATERIALISED');

  const actions = canEdit && (
    <>
      {live && !materialised && refs.issueOn && (
        <Button variant="outlined" disabled={busy || form.dirty} onClick={() => { setActionError(''); setPromoting(true); }}>
          {t('risks.promote')}</Button>)}
      {live && !materialised && (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>
          {t('risks.retire')}</Button>)}
      {!live && (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('risks.restore')}</Button>)}
      {editable && (
        <>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('risks.discard')}</Button>
          <Button variant="contained" disabled={!form.dirty || busy || !String(v.title).trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('risks.save')}</Button>
        </>)}
    </>
  );

  const main = (
    <Card title={t('risks.cardTitle')} action={<SaveState version={form.version} dirty={form.dirty} retired={!live} />}>
      {materialised && <Alert severity="info">{t('risks.materialisedNote')}</Alert>}
      <SimpleSelect id="rsk-status_code" label={t('risks.field.status_code')} value={v.status_code}
        disabled={!editable || materialised} onChange={(c) => form.set('status_code', c)}
        options={statusOptions.map((c) => ({ value: c.code, label: c.label }))} />
      <RiskFields projectId={projectId} refs={refs} v={v} set={form.set} disabled={!editable} lock={materialised} />
    </Card>
  );
  const side = (
    <Card title={t('risks.scoreTitle')} bodySx={{ gap: 1 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <ExposureTag size="md" score={risk.exposure_score} rule={refs.rule} open={live && risk.status_behaviour === 'OPEN'} />
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('risks.scoreHow')}</Typography>
      </Box>
      {refs.rule && !refs.rule.is_enabled && (
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('risks.ruleOff')}</Typography>)}
      {risk.materialised_issue_id && (
        <Typography sx={{ fontSize: 13.5 }}>
          {t('risks.materialisedAs')}{' '}
          <Link component={RouterLink} to={links.issue(projectId, risk.materialised_issue_id)} underline="hover">
            <Code>{risk.materialised_issue_number}</Code></Link>
        </Typography>)}
    </Card>
  );

  return (
    <Page title={<CodeTitle code={risk.risk_number} name={risk.title} />} subtitle={t('risks.detailSubtitle')}
      crumb={risk.risk_number} actions={actions}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      <TwoCol main={main} side={side} />
      {promoting && <PromoteDialog projectId={projectId} risk={risk} onClose={() => setPromoting(false)}
        onDone={(out) => { landed(out.risk, t('risks.promoted', { number: out.issue.issue_number }));
          qc.invalidateQueries({ queryKey: keys.issues(projectId) }); }}
        onStale={() => { setPromoting(false); refreshAll(); setActionError(t('risks.stale')); }} />}
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('risks.retireTitle')}
        body={t('risks.retireBody', { number: risk.risk_number })} confirmLabel={t('risks.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)}
        onConfirm={() => retire.mutate(undefined, { onSuccess: () => navigate(links.risks(projectId)) })} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
