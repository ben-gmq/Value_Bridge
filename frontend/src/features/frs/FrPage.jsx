import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Snackbar, TextField } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { frApi, solutionApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, SectionLabel, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CodeTitle, FrWarnings, SaveState, TwoCol, solutionOptions, warningList } from './frKit';
import { FrTraceCard } from './FrTraceCard';
import { InterfaceCard } from './InterfaceCard';
import { FrEffort, FrEffortSide } from '../effort/FrEffort';

const pickFr = (f) => ({ fr_name: f.fr_name ?? '', fr_type_code: f.fr_type_code,
  fulfilment_status_code: f.fulfilment_status_code, solution_id: f.solution_id ?? '',
  description: f.description ?? '', acceptance_note: f.acceptance_note ?? '' });
const CODES = new Set(['fr_type_code', 'fulfilment_status_code']);

export default function FrPage() {
  const { projectId, frId } = useParams();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.fr(frId), queryFn: () => frApi.get(frId) });
  const fr = q.data;
  const solsQ = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId) });
  const { options: typeOptions, getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const { options: statusOptions, getLabel: statusLabel } = useCodes(projectId, 'FR_FULFILMENT_STATUS');
  const form = useEditForm(fr, pickFr);
  const [notice, setNotice] = useState('');
  const [warnings, setWarnings] = useState([]);
  const [effortChange, setEffortChange] = useState(null);     // DR6c-P2: a type change re-priced the FR
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.fr(frId) });
    qc.invalidateQueries({ queryKey: keys.frs(projectId) });
    qc.invalidateQueries({ queryKey: keys.frTrace() });
  };
  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'solution_id') body.solution_id = form.values.solution_id === '' ? null : form.values.solution_id;
        else body[k] = CODES.has(k) ? form.values[k] : blankToNull(form.values[k]);
      }
      if ('fr_name' in body) body.fr_name = form.values.fr_name.trim();
      return frApi.update(fr.fr_id, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.fr(frId), row); refreshAll();
      setWarnings(warningList(row.warnings).filter((w) => w.code !== 'effort_changed')); setEffortChange(row.effort_change ?? null);
      setNotice(t('frs.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.fr(frId), queryFn: () => frApi.get(frId) });
      form.rebase(fresh);
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  // A retire refused while BRs still link the FR (Q-13, S10b-2) shows the server's detail, which names them.
  const actionFail = (err) => {
    refreshAll();
    setActionError(isStale(err) ? t('frs.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const retire = useMutation({
    mutationFn: () => frApi.retire(fr.fr_id, fr.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('frs.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => frApi.restore(fr.fr_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.fr(frId), row); refreshAll();
      setNotice(t('frs.restored', { number: row.fr_number })); },
    onError: actionFail,
  });

  if (q.error) return <Page title={t('frs.back')} error={errorText(q.error)} />;
  if (!fr || !form.values) return <Page title={t('frs.loading')} />;

  const v = form.values;
  const live = fr.is_active;
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  // The current solution stays selectable even if the list has not loaded it yet.
  const solOpts = solutionOptions(solsQ.data);
  if (fr.solution_id && !solOpts.some((o) => o.value === fr.solution_id)) {
    solOpts.unshift({ value: fr.solution_id, label: t('frs.loading') });
  }
  const sol = (solsQ.data ?? []).find((s) => s.solution_id === fr.solution_id);
  const labels = { fr_name: t('frs.name'), fr_type_code: t('frs.type'), fulfilment_status_code: t('frs.status'),
    solution_id: t('frs.solution'), description: t('frs.description'), acceptance_note: t('frs.acceptanceNote') };
  const shown = (k) => (k === 'fr_type_code' ? typeLabel(v[k]) : k === 'fulfilment_status_code' ? statusLabel(v[k])
    : k === 'solution_id' ? (solOpts.find((o) => o.value === v[k])?.label ?? t('frs.noSolution')) : v[k]);
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], shown(k)]));
  const text = (name, rows = 2, max = 4000) => (
    <TextField fullWidth multiline={rows > 1} minRows={rows > 1 ? rows : undefined} id={`fr-${name}`}
      label={labels[name]} disabled={!editable} value={v[name]} required={name === 'fr_name'}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: max } }} />
  );
  const select = (name, options, extra = {}) => (editable ? (
    <SimpleSelect id={`fr-${name}`} label={labels[name]} value={v[name]} onChange={(c) => form.set(name, c)}
      options={options} {...extra} />
  ) : <TextField fullWidth size="small" disabled label={labels[name]} value={shown(name)} />);

  const actions = (
    <>
      {canEdit && (live ? (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('frs.retire')}</Button>
      ) : (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('frs.restore')}</Button>
      ))}
      {editable && (
        <>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('frs.discard')}</Button>
          <Button variant="contained" disabled={!form.dirty || busy || !v.fr_name.trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('frs.save')}</Button>
        </>)}
    </>
  );

  const main = (
    <>
      <Card title={t('frs.cardTitle')} action={<SaveState version={form.version} dirty={form.dirty} retired={!live} />}>
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', md: 'repeat(2, minmax(0,1fr))' } }}>
          {select('solution_id', solOpts, { allowEmpty: true, emptyLabel: t('frs.noSolution') })}
          {select('fulfilment_status_code', statusOptions(fr.fulfilment_status_code).map((c) => ({ value: c.code, label: c.label })))}
          <Box sx={{ gridColumn: '1 / -1' }}>{text('fr_name', 1, 200)}</Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
            <SectionLabel>{labels.fr_type_code}</SectionLabel>
            {editable ? (
              <Segmented label={labels.fr_type_code} value={v.fr_type_code} onChange={(c) => form.set('fr_type_code', c)}
                options={typeOptions(fr.fr_type_code).map((c) => ({ value: c.code, label: c.label }))} />
            ) : <Box><Tag tone="navy">{typeLabel(v.fr_type_code)}</Tag></Box>}
          </Box>
          <FrEffort key={`${fr.row_version}-${fr.complexity_code}`} projectId={projectId} fr={fr}
            onRated={(row) => { qc.setQueryData(keys.fr(frId), row); form.rebase(row); refreshAll();   // keeps typed edits (sara M-1)
              setNotice(row.effort_days != null ? t('effort.fr.rated', { days: row.effort_days }) : t('frs.saved')); }} />
        </Box>
        {text('description', 3)}
        {text('acceptance_note', 3)}
      </Card>
      {/* D-27: only an FR whose type behaves as an interface carries interface detail (never a code test) */}
      {fr.fr_type_behaviour === 'INTERFACE' && <InterfaceCard projectId={projectId} fr={fr} onNotice={setNotice} />}
    </>
  );

  const side = (
    <>
      <FrEffortSide projectId={projectId} fr={fr} />
      <FrTraceCard projectId={projectId} solutionId={fr.solution_id} solution={sol} brCount={fr.br_count} />
    </>
  );

  return (
    <Page title={<CodeTitle code={fr.fr_number} name={fr.fr_name} />} subtitle={t('frs.detailSubtitle')}
      crumb={fr.fr_number} actions={actions}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      <FrWarnings warnings={warnings} onClose={() => setWarnings([])} />
      {effortChange && (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setEffortChange(null)}>
          {t('effort.fr.changed', { from: effortChange.previous_days ?? t('effort.fr.notRated'), to: effortChange.new_days })}</Alert>)}
      <TwoCol main={main} side={side} />

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('frs.retireTitle')}
        body={t('frs.retireBody', { number: fr.fr_number })} confirmLabel={t('frs.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
