import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Link, Snackbar, Stack, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { changeApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, Code, KV } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, useEditForm, useFormSave } from '../processes/chartKit';
import { CodeTitle, SaveState, TwoCol } from '../frs/frKit';
import { ObjectLink, StatusTag, UNDECIDED, changeLink, days } from './changeKit';
import { CorrectDialog, DecideDialog, SeedsCard } from './changeDialogs';

const FIELDS = ['title', 'rationale', 'origin_code'];
const pick = (r) => Object.fromEntries(FIELDS.map((k) => [k, r[k] ?? '']));
const KINDS = ['BR', 'FR', 'SOLUTION', 'APPLICATION', 'DATA_ENTITY', 'WAVE', 'BENEFIT'];
const muted = { fontSize: 12.5, color: 'text.secondary' };

// The trace, by kind (criterion 64: computed, never typed). A retired object stays listed, marked.
function ImpactCard({ projectId, cr }) {
  const groups = KINDS.map((k) => [k, cr.impacts.filter((i) => i.kind === k)]).filter(([, rows]) => rows.length);
  return (
    <Card title={t('changes.impactTitle')} bodySx={{ gap: 1.5 }}>
      {!cr.priced_at && <Typography sx={muted}>{t('changes.notTraced')}</Typography>}
      {cr.priced_at && !groups.length && <Typography sx={muted}>{t('changes.nothingReached')}</Typography>}
      {cr.skipped_parts.length > 0 && (
        <Typography sx={muted}>{t('changes.skipped', { parts: cr.skipped_parts.map((c) => t(`changes.part.${c}`)).join(', ') })}</Typography>)}
      {groups.map(([kind, rows]) => (
        <Box key={kind}>
          <Typography sx={{ fontSize: 12.5, fontWeight: 700, letterSpacing: 0.4, mb: 0.5 }}>
            {t(`changes.kind.${kind}`).toUpperCase()} · {rows.length}</Typography>
          {rows.map((i) => (
            <Box key={i.cr_impact_id} sx={{ display: 'flex', gap: 1, alignItems: 'baseline', py: 0.25 }}>
              <ObjectLink projectId={projectId} row={i} />
              <Typography noWrap sx={{ flex: 1, minWidth: 0, fontSize: 13.5 }}>{i.name}</Typography>
              {i.object_retired && <Typography sx={muted}>{t('changes.retiredMark')}</Typography>}
              {kind === 'FR' && <Typography sx={muted}>{t('changes.agreedDays', { n: i.agreed_effort_days ?? '–' })}</Typography>}
              {kind === 'BENEFIT' && i.value_unit && (
                <Typography sx={muted}>{t('changes.atStake', { n: i.value_at_stake, unit: i.value_unit })}</Typography>)}
              <Typography sx={{ ...muted, width: 120, textAlign: 'right' }}>{t(`changes.via.${i.reached_via}`)}</Typography>
            </Box>))}
        </Box>))}
    </Card>
  );
}

// The price the decider sees (CR-1, Q3, Q9): the seed delta, exposure beside it, benefit per unit only.
function PriceCard({ cr }) {
  return (
    <Card title={t('changes.priceTitle')} bodySx={{ gap: 1 }}>
      {!cr.priced_at ? <Typography sx={muted}>{t('changes.notPriced')}</Typography> : (
        <>
          <KV k={t('changes.field.delta')} v={days(cr.effort_delta_days)} />
          <KV k={t('changes.field.exposure')} v={t('changes.days', { n: cr.effort_exposed_days })} />
          {cr.unrated_fr_count > 0 && (
            <Alert severity="warning">{t('changes.unrated', { n: cr.unrated_fr_count })}</Alert>)}
          <Typography sx={muted}>{t('changes.exposureHelp')}</Typography>
          {cr.value_by_unit.map((u) => (
            <KV key={u.unit} k={t('changes.valueUnit', { unit: u.unit })}
              v={t('changes.valueLine', { stake: u.value_at_stake,
                change: u.value_change ?? t('changes.notMeasured') })} />))}
          {!cr.value_measured && cr.value_by_unit.length > 0 && (
            <Typography sx={muted}>{t('changes.valueNotMeasured', { label: cr.against_label })}</Typography>)}
          {cr.waves.length > 0 && <KV k={t('changes.waves')} v={cr.waves.join(', ')} />}
          {cr.dependencies.length > 0 && (
            <KV k={t('changes.dependencies')} v={cr.dependencies.map((d) =>
              `${d.solution_number} → ${d.depends_on_number}${d.both_impacted ? '' : ' *'}`).join(', ')} />)}
          {cr.displacement_candidates.length > 0 && (
            <Box>
              <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{t('changes.displacement')}</Typography>
              {cr.displacement_candidates.map((d) => (
                <Typography key={`${d.unit}-${d.solution_number}`} sx={muted}>
                  {t('changes.displacementLine', { number: d.solution_number, name: d.solution_name, value: d.value,
                    unit: d.unit, days: d.effort_days })}</Typography>))}
            </Box>)}
          {cr.moved_since_pricing.length > 0 && (
            <Alert severity="warning">{t('changes.moved', { list: cr.moved_since_pricing.join(', ') })}</Alert>)}
          <Typography sx={muted}>{t('changes.pricedAt', { at: new Date(cr.priced_at).toLocaleString() })}</Typography>
        </>)}
    </Card>
  );
}

function DecisionCard({ projectId, cr, getLabel }) {
  return (
    <Card title={t('changes.decisionTitle')} bodySx={{ gap: 1 }}>
      {!cr.decision_id ? <Typography sx={muted}>{t('changes.undecided')}</Typography> : (
        <>
          <KV k={t('changes.field.decision')} v={(
            <Link component={RouterLink} to={links.decision(projectId, cr.decision_id)} underline="hover">
              <Code>{cr.decision_number}</Code></Link>)} />
          <KV k={t('changes.field.status_code')} v={getLabel(cr.status_code)} />
          <KV k={t('changes.field.decided_on')} v={cr.decided_on} />
          <KV k={t('changes.field.decided_by')} v={cr.decided_by_name} />
          {cr.displaces_cr_id && <KV k={t('changes.field.cut')} v={changeLink(projectId, cr.displaces_cr_id, cr.displaces_cr_number)} />}
          {cr.budget_increase_days && (
            <>
              <KV k={t('changes.field.budget_increase_days')} v={t('changes.days', { n: cr.budget_increase_days })} />
              <KV k={t('changes.field.budget_reference')} v={cr.budget_reference} />
              <KV k={t('changes.field.budget_approved_by')} v={cr.budget_approved_by} />
            </>)}
        </>)}
    </Card>
  );
}

export default function ChangePage() {
  const { projectId, crId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('CHANGE_REQUEST');
  const q = useQuery({ queryKey: keys.change(crId), queryFn: () => changeApi.get(crId) });
  const cr = q.data;
  const sts = useCodes(projectId, 'CR_STATUS');
  const origin = useCodes(projectId, 'CR_ORIGIN');
  const form = useEditForm(cr, pick);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [dialog, setDialog] = useState('');

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.change(crId) });
    qc.invalidateQueries({ queryKey: ['changes', String(projectId)] });
    qc.invalidateQueries({ queryKey: keys.decisions(projectId) });
    qc.invalidateQueries({ queryKey: keys.baselines(projectId) });
  };
  const landed = (row, msg) => { form.saved(row); qc.setQueryData(keys.change(crId), row); refreshAll(); setNotice(msg); };
  const save = useFormSave({
    save: () => {
      const body = { row_version: form.version };
      for (const k of form.changed) body[k] = typeof form.values[k] === 'string' ? form.values[k].trim() : form.values[k];
      return changeApi.update(cr.change_request_id, body);
    },
    onSaved: (row) => landed(row, t('changes.saved')),
  });
  const reload = async () => {
    try {
      form.rebase(await qc.fetchQuery({ queryKey: keys.change(crId), queryFn: () => changeApi.get(crId) }));
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => { refreshAll(); setActionError(isStale(err) ? errorText(err, t('changes.stale')) : errorText(err, t('common.saveFailed'))); };
  const analyse = useMutation({
    mutationFn: () => changeApi.analyse(cr.change_request_id, cr.row_version),
    onSuccess: (row) => { setActionError(''); landed(row, t(row.status_behaviour === 'PRICED' ? 'changes.pricedDone' : 'changes.analysedDone')); },
    onError: actionFail,
  });
  const retire = useMutation({
    mutationFn: () => changeApi.retire(cr.change_request_id, cr.row_version),
    onSuccess: () => { setDialog(''); refreshAll(); navigate(links.changes(projectId)); },
    onError: (err) => { setDialog(''); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => changeApi.restore(cr.change_request_id),
    onSuccess: (row) => { setActionError(''); landed(row, t('changes.restored')); },
    onError: actionFail,
  });

  if (q.error) return <Page title={t('changes.title')} error={errorText(q.error)} />;
  if (!cr || !form.values) return <Page title={t('changes.loading')} />;

  const v = form.values;
  const live = cr.is_active;
  const open = UNDECIDED.includes(cr.status_behaviour);
  const editable = live && open && canEdit;
  const busy = save.m.isPending || analyse.isPending || retire.isPending || restore.isPending;
  const unsaved = Object.fromEntries(form.changed.map((k) => [t(`changes.field.${k}`), v[k]]));
  const final = cr.status_behaviour === 'APPROVED' || cr.status_behaviour === 'REJECTED';

  const actions = canEdit && (
    <>
      {editable && (
        <Button variant="outlined" disabled={busy || form.dirty || cr.seeds.length === 0}
          onClick={() => { setActionError(''); analyse.mutate(); }}>{t('changes.analyse')}</Button>)}
      {editable && (
        <Button variant="contained" disabled={busy || form.dirty}
          onClick={() => { setActionError(''); setDialog('decide'); }}>{t('changes.decide')}</Button>)}
      {live && final && cr.decision_id && (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); setDialog('correct'); }}>
          {t('changes.correct')}</Button>)}
      {editable && (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setDialog('retire'); }}>
          {t('changes.retire')}</Button>)}
      {!live && (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('changes.restore')}</Button>)}
    </>
  );

  const details = (
    <Card title={t('changes.cardTitle')} action={(
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        {editable && form.dirty && (
          <>
            <Button size="small" disabled={busy} onClick={form.discard}>{t('changes.discard')}</Button>
            <Button size="small" variant="contained" disabled={busy || !String(v.title).trim() || !String(v.rationale).trim()}
              onClick={() => { save.setError(''); save.m.mutate(); }}>{t('changes.save')}</Button>
          </>)}
        <SaveState version={form.version} dirty={form.dirty} retired={!live} />
      </Stack>)}>
      <TextField id="cr-title" size="small" fullWidth label={t('changes.field.title')} value={v.title} disabled={!editable}
        onChange={(e) => form.set('title', e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
      <TextField id="cr-rationale" size="small" fullWidth multiline minRows={3} label={t('changes.field.rationale')}
        value={v.rationale} disabled={!editable} onChange={(e) => form.set('rationale', e.target.value)} />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
        <SimpleSelect id="cr-origin" label={t('changes.field.origin_code')} value={v.origin_code} disabled={!editable}
          onChange={(c) => form.set('origin_code', c)}
          options={origin.options(cr.origin_code).map((c) => ({ value: c.code, label: c.label }))} />
        <TextField id="cr-target" size="small" label={t('changes.field.against')} value={cr.against_label} disabled
          helperText={t('changes.targetFixed')} />
      </Box>
      <Typography sx={muted}>{t('changes.raisedBy', { name: cr.raised_by_name ?? '', at: new Date(cr.created_at).toLocaleDateString() })}</Typography>
    </Card>
  );
  const main = (
    <Stack spacing={2}>
      {details}
      <SeedsCard key={cr.row_version} projectId={projectId} cr={cr} editable={editable}
        onSaved={(row) => landed(row, t('changes.seedsSaved'))} onStale={refreshAll} />
      <ImpactCard projectId={projectId} cr={cr} />
    </Stack>
  );
  const side = (
    <Stack spacing={2}>
      <PriceCard cr={cr} />
      <DecisionCard projectId={projectId} cr={cr} getLabel={sts.getLabel} />
      {cr.unagreed_edits.length > 0 && (
        <Alert severity="warning">
          {t('changes.carriesEdit', { list: cr.unagreed_edits.map((e) => e.number).join(', '), label: cr.against_label })}
        </Alert>)}
    </Stack>
  );

  return (
    <Page title={<CodeTitle code={cr.cr_number} name={cr.title} tone={live ? 'navy' : 'muted'} />}
      eyebrow={<StatusTag cr={cr} getLabel={sts.getLabel} />}
      subtitle={t('changes.detailSubtitle', { label: cr.against_label })} crumb={cr.cr_number} actions={actions}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      <TwoCol main={main} side={side} sideWidth={380} />
      {dialog === 'decide' && <DecideDialog projectId={projectId} cr={cr} onClose={() => setDialog('')} onStale={refreshAll}
        onDone={(row) => landed(row, t('changes.decided', { number: row.decision_number }))} />}
      {dialog === 'correct' && <CorrectDialog cr={cr} onClose={() => setDialog('')} onStale={refreshAll}
        onDone={(row) => landed(row, t('changes.decided', { number: row.decision_number }))} />}
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={dialog === 'retire'} title={t('changes.retireTitle')}
        body={t('changes.retireBody', { number: cr.cr_number })} confirmLabel={t('changes.retire')}
        busy={retire.isPending} onClose={() => setDialog('')} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
