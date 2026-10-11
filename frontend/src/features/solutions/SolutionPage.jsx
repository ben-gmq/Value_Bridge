import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Snackbar, TextField } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { solutionApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, SectionLabel, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { SolutionLinkPanel } from './SolutionLinkPanel';
import { FrTracePanel } from '../frs/FrTracePanel';
import { AppLinkPanel } from '../applications/AppLinkPanel';
import { CodeTitle, SaveState, TwoCol } from '../frs/frKit';
import { SolutionMix } from './SolutionMix';

const pickSolution = (s) => ({ solution_name: s.solution_name ?? '', category_code: s.category_code,
  status_code: s.status_code, description: s.description ?? '', benefit_note: s.benefit_note ?? '',
  effort_note: s.effort_note ?? '' });
const CODES = new Set(['category_code', 'status_code']);

export default function SolutionPage() {
  const { projectId, solutionId } = useParams();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.solution(solutionId), queryFn: () => solutionApi.get(solutionId) });
  const sol = q.data;
  const { codes: categories, getLabel: categoryLabel } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const { codes: statuses, getLabel: statusLabel } = useCodes(projectId, 'SOLUTION_STATUS');
  const form = useEditForm(sol, pickSolution);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.solution(solutionId) });
    qc.invalidateQueries({ queryKey: keys.solutions(projectId) });
    qc.invalidateQueries({ queryKey: keys.solutionLinks() });
  };
  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) body[k] = CODES.has(k) ? form.values[k] : blankToNull(form.values[k]);
      if ('solution_name' in body) body.solution_name = form.values.solution_name.trim();
      return solutionApi.update(sol.solution_id, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.solution(solutionId), row); refreshAll(); setNotice(t('solutions.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.solution(solutionId), queryFn: () => solutionApi.get(solutionId) });
      form.rebase(fresh);
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => {
    refreshAll();
    setActionError(isStale(err) ? t('solutions.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const retire = useMutation({
    mutationFn: () => solutionApi.retire(sol.solution_id, sol.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('solutions.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => solutionApi.restore(sol.solution_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.solution(solutionId), row); refreshAll();
      setNotice(t('solutions.restored', { label: row.solution_number })); },
    onError: actionFail,
  });

  if (q.error) return <Page title={t('solutions.back')} error={errorText(q.error)} />;
  if (!sol || !form.values) return <Page title={t('solutions.loading')} />;

  const v = form.values;
  const live = sol.is_active;
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const labels = { solution_name: t('solutions.name'), category_code: t('solutions.category'),
    status_code: t('solutions.status'), description: t('solutions.description'),
    benefit_note: t('solutions.benefitNote'), effort_note: t('solutions.effortNote') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k],
    k === 'category_code' ? categoryLabel(v[k]) : k === 'status_code' ? statusLabel(v[k]) : v[k]]));
  const text = (name, rows = 2, max = 4000) => (
    <TextField fullWidth multiline={rows > 1} minRows={rows > 1 ? rows : undefined} id={`sol-${name}`}
      label={labels[name]} disabled={!editable} value={v[name]} required={name === 'solution_name'}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: max } }} />
  );

  const actions = (
    <>
      {canEdit && (live ? (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('solutions.retire')}</Button>
      ) : (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('solutions.restore')}</Button>
      ))}
      {editable && (
        <>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('solutions.discard')}</Button>
          <Button variant="contained" disabled={!form.dirty || busy || !v.solution_name.trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('solutions.save')}</Button>
        </>)}
    </>
  );

  const main = (
    <Card title={t('solutions.cardTitle')} action={<SaveState version={form.version} dirty={form.dirty} retired={!live} />}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <SectionLabel>{labels.category_code}</SectionLabel>
        {editable ? (
          <Segmented label={labels.category_code} value={v.category_code} onChange={(c) => form.set('category_code', c)}
            options={categories.map((c) => ({ value: c.code, label: c.label }))} />
        ) : <Tag>{categoryLabel(v.category_code)}</Tag>}
      </Box>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', md: 'minmax(0,2fr) minmax(0,1fr)' } }}>
        {text('solution_name', 1, 200)}
        {editable ? (
          <SimpleSelect id="sol-status" label={labels.status_code} value={v.status_code}
            onChange={(c) => form.set('status_code', c)} options={statuses.map((c) => ({ value: c.code, label: c.label }))} />
        ) : <TextField fullWidth size="small" disabled label={labels.status_code} value={statusLabel(v.status_code)} />}
        <Box sx={{ gridColumn: '1 / -1' }}>{text('description', 3)}</Box>
      </Box>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', md: 'repeat(2, minmax(0,1fr))' } }}>
        {text('benefit_note')}
        {text('effort_note')}
      </Box>
      <SolutionLinkPanel projectId={projectId} side="solution" solution={sol} disabled={!live} />
      <FrTracePanel projectId={projectId} side="solution" id={sol.solution_id} />
    </Card>
  );

  const side = (
    <>
      <SolutionMix projectId={projectId} current={v.category_code} />
      <Card>
        {/* To-be allocation (D-8). An as-is only application cannot deliver a future solution (R2-D11). */}
        <AppLinkPanel projectId={projectId} title={t('applications.links.deliveredBy')}
          empty={t('applications.links.noneDelivered')} ownerKey={['solution', sol.solution_id]}
          rowId="application_solution_id" disabled={!live} ruleHint={t('applications.links.asIsOnly')}
          allow={(a) => a.lifecycle_code !== 'AS_IS'}
          api={{ list: () => solutionApi.apps(sol.solution_id),
            link: (applicationId, note) => solutionApi.allocate(sol.solution_id, { application_id: applicationId, note }),
            edit: (row, note) => solutionApi.editAllocation(sol.solution_id, row.application_solution_id, { row_version: row.row_version, note }),
            unlink: (row) => solutionApi.unallocate(sol.solution_id, row.application_solution_id, row.row_version) }} />
      </Card>
    </>
  );

  return (
    <Page title={<CodeTitle code={sol.solution_number} name={sol.solution_name} />} subtitle={t('solutions.detailSubtitle')}
      crumb={sol.solution_number} actions={actions}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      <TwoCol main={main} side={side} sideWidth={380} />

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('solutions.retireTitle')}
        body={t('solutions.retireBody', { number: sol.solution_number })} confirmLabel={t('solutions.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
