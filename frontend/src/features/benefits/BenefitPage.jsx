import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, IconButton, Link, Snackbar, Stack, TextField, Tooltip, Typography } from '@mui/material';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import { errorText, isStale } from '../../api/client';
import { benefitApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CodeTitle, SaveState, TwoCol } from '../frs/frKit';
import { BenefitFields, useBenefitRefs } from './benefitKit';

const FIELDS = ['benefit_name', 'description', 'benefit_type_code', 'measure_name', 'measure_unit', 'baseline_value',
  'target_value', 'realisation_date', 'accountable_org_role_id', 'status_code'];
const TRIMMED = ['benefit_name', 'measure_name', 'measure_unit'];
const pick = (r) => Object.fromEntries(FIELDS.map((k) => [k, r[k] ?? '']));

// One link row: the % is edited in place; Enter or "Change %" saves it (PUT is idempotent).
function LinkRow({ row, editable, busy, onSave, onRemove }) {
  const [pct, setPct] = useState(row.contribution_pct);
  const changed = Number(pct) !== Number(row.contribution_pct);
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', fontSize: 13.5 }}>
      <Code>{row.solution_number}</Code>
      <Box component="span" sx={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.solution_name}</Box>
      {row.solution_rejected && <Tag tone="neutral" size="sm">{t('benefits.links.rejected')}</Tag>}
      <TextField size="small" type="number" value={pct} disabled={!editable || busy} sx={{ width: 90 }}
        slotProps={{ htmlInput: { step: '0.01', min: 0.01, max: 100, 'aria-label': t('benefits.links.pct') } }}
        onChange={(e) => setPct(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && changed) onSave(pct); }} />
      <Box component="span" sx={{ width: 110, textAlign: 'right', color: 'text.secondary' }}>{row.value}</Box>
      {editable && changed && <Button size="small" disabled={busy} onClick={() => onSave(pct)}>{t('benefits.links.change')}</Button>}
      {editable && (
        <Tooltip title={t('benefits.links.remove')}>
          <span><IconButton size="small" color="warning" disabled={busy} aria-label={t('benefits.links.remove')}
            onClick={onRemove}><DeleteOutlineRounded fontSize="small" /></IconButton></span>
        </Tooltip>)}
    </Stack>
  );
}

function LinksCard({ benefit, refs, editable, onChanged, onError }) {
  const [solutionId, setSolutionId] = useState('');
  const [pct, setPct] = useState('');
  const put = useMutation({
    mutationFn: ({ sid, value }) => benefitApi.link(benefit.benefit_id, sid, value),
    onSuccess: () => { setSolutionId(''); setPct(''); onChanged(t('benefits.links.linked')); },
    onError,
  });
  const remove = useMutation({
    mutationFn: (sid) => benefitApi.unlink(benefit.benefit_id, sid),
    onSuccess: () => onChanged(t('benefits.links.removed')),
    onError,
  });
  const busy = put.isPending || remove.isPending;
  const unassigned = 100 - Number(benefit.link_total_pct);
  return (
    <Card title={t('benefits.links.title')} bodySx={{ gap: 1 }}>
      {benefit.links.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('benefits.links.empty')}</Typography>)}
      {benefit.links.map((row) => (
        <LinkRow key={`${row.benefit_solution_id}-${row.row_version}`} row={row} editable={editable} busy={busy}
          onSave={(value) => put.mutate({ sid: row.solution_id, value })} onRemove={() => remove.mutate(row.solution_id)} />))}
      {unassigned > 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
          {t('benefits.unassigned', { pct: unassigned.toFixed(2) })}</Typography>)}
      {editable && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', pt: 1 }}>
          <Box sx={{ flex: 1 }}>
            <SimpleSelect id="ben-link-solution" label={t('benefits.links.pick')} value={solutionId}
              onChange={setSolutionId} options={refs.solutionOptions(benefit.links.map((l) => l.solution_id))} />
          </Box>
          <TextField size="small" type="number" label={t('benefits.links.pct')} value={pct} sx={{ width: 110 }}
            id="ben-link-pct" slotProps={{ htmlInput: { step: '0.01', min: 0.01, max: 100 } }}
            onChange={(e) => setPct(e.target.value)} />
          <Button variant="outlined" disabled={busy || !solutionId || !(Number(pct) > 0)}
            onClick={() => put.mutate({ sid: solutionId, value: pct })}>{t('benefits.links.add')}</Button>
        </Stack>)}
    </Card>
  );
}

// The benefit page (spec §9): the form, the solutions delivering it, retire / restore.
export default function BenefitPage() {
  const { projectId, benefitId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('BENEFIT');
  const refs = useBenefitRefs(projectId);
  const q = useQuery({ queryKey: keys.benefit(benefitId), queryFn: () => benefitApi.get(benefitId) });
  const b = q.data;
  const sts = useCodes(projectId, 'BENEFIT_STATUS');
  const form = useEditForm(b, pick);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.benefit(benefitId) });
    qc.invalidateQueries({ queryKey: keys.benefits(projectId) });
    qc.invalidateQueries({ queryKey: ['solution'] });
    qc.invalidateQueries({ queryKey: ['control', String(projectId)] });
  };
  const landed = (row, msg) => { form.saved(row); qc.setQueryData(keys.benefit(benefitId), row); refreshAll(); setNotice(msg); };
  const save = useFormSave({
    save: () => {
      const body = { row_version: form.version };
      for (const k of form.changed) body[k] = TRIMMED.includes(k) ? String(form.values[k]).trim() : blankToNull(form.values[k]);
      return benefitApi.update(b.benefit_id, body);
    },
    onSaved: (row) => landed(row, t('benefits.saved')),
  });
  const reload = async () => {
    try {
      form.rebase(await qc.fetchQuery({ queryKey: keys.benefit(benefitId), queryFn: () => benefitApi.get(benefitId) }));
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => { refreshAll(); setActionError(isStale(err) ? t('benefits.stale') : errorText(err, t('common.saveFailed'))); };
  const retire = useMutation({
    mutationFn: () => benefitApi.retire(b.benefit_id, b.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('benefits.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => benefitApi.restore(b.benefit_id),
    onSuccess: (row) => { setActionError(''); landed(row, t('benefits.restored')); },
    onError: actionFail,
  });

  if (q.error) return <Page title={t('benefits.title')} error={errorText(q.error)} />;
  if (!b || !form.values) return <Page title={t('benefits.loading')} />;

  const v = form.values;
  const live = b.is_active;
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const unsaved = Object.fromEntries(form.changed.map((k) => [t(`benefits.field.${k}`), v[k]]));
  const ready = TRIMMED.every((k) => String(v[k]).trim()) && v.baseline_value !== '' && v.target_value !== '';

  const actions = canEdit && (
    <>
      {live && (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>
          {t('benefits.retire')}</Button>)}
      {!live && (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('benefits.restore')}</Button>)}
      {editable && (
        <>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('benefits.discard')}</Button>
          <Button variant="contained" disabled={!form.dirty || busy || !ready}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('benefits.save')}</Button>
        </>)}
    </>
  );

  const main = (
    <Card title={t('benefits.cardTitle')} action={<SaveState version={form.version} dirty={form.dirty} retired={!live} />}>
      <SimpleSelect id="ben-status_code" label={t('benefits.field.status_code')} value={v.status_code}
        disabled={!editable} onChange={(c) => form.set('status_code', c)}
        options={sts.options(b.status_code).map((c) => ({ value: c.code, label: c.label }))} />
      <BenefitFields projectId={projectId} refs={refs} v={v} set={form.set} disabled={!editable} />
    </Card>
  );
  const side = (
    <LinksCard benefit={b} refs={refs} editable={editable}
      onChanged={(msg) => { setActionError(''); refreshAll(); setNotice(msg); }} onError={actionFail} />
  );

  return (
    <Page title={<CodeTitle code={b.benefit_number} name={b.benefit_name} />} subtitle={t('benefits.detailSubtitle')}
      crumb={b.benefit_number} actions={actions}>
      <Box sx={{ mb: 1.5 }}>
        <Link component={RouterLink} to={links.benefits(projectId)} underline="hover" sx={{ fontSize: 13.5 }}>
          ← {t('benefits.title')}</Link>
      </Box>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      {refs.error && <Alert severity="error" sx={{ mb: 2 }}>{errorText(refs.error)}</Alert>}
      <TwoCol main={main} side={side} sideWidth={440} />
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('benefits.retireTitle')}
        body={t('benefits.retireBody', { number: b.benefit_number })} confirmLabel={t('benefits.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)}
        onConfirm={() => retire.mutate(undefined, { onSuccess: () => navigate(links.benefits(projectId)) })} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
