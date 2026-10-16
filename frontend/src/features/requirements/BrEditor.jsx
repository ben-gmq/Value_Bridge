import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Divider, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { brApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Status, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CrudGrid } from './CrudGrid';
import { BrRaci } from './BrRaci';
import { BrSolutionTags } from './BrSolutionTags';
import { BrFrLinks } from './BrFrLinks';
import { warningList } from '../frs/frKit';
import { CoveragePanel } from './CoveragePanel';
import { BrLines } from './BrLines';
import { BrFlows } from './BrFlows';
import { BrStatusTag, OFFER_RETIRE_BR } from './reqKit';

// S1-8: a person sets Draft or Confirmed. Baselined / Superseded are set by the freeze and are
// shown read-only (the server refuses them too: business_requirement.SYSTEM_SET_STATUSES).
const SETTABLE_STATUSES = ['DRAFT', 'CONFIRMED'];

// D-59: business_logic / output_expectation are read-only legacy now — the lines carry what a requirement says.
const pickBr = (b) => ({ br_statement: b.br_statement ?? '', status_code: b.status_code });

// The two-column splits follow the editor's own width (a container), not the window's.
const WIDE = '@container (min-width: 700px)';

/**
 * One business requirement, read and edited (mockup 03). D-53: the same editor serves the BR page and
 * the process's panel in the function chart, so the two never drift. Returns the parts; the caller
 * lays them out. `onNotice` receives the success messages.
 * `embedded`: the process panel owns Save and Discard (one Save for the function and its BR, Ben
 * 2026-10-12) — `actions` then carries only retire/restore, and the panel calls `saveNow`/`discard`.
 */
export function useBrEditor({ projectId, brId, onNotice, embedded = false, crudMark = null }) {
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit();             // UAT 7b: a viewer sees the requirement, not its controls
  const qc = useQueryClient();
  const brQ = useQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId), enabled: brId != null });
  const br = brQ.data;
  const { codes: statuses, getLabel } = useCodes(projectId, 'BR_STATUS');
  const form = useEditForm(br, pickBr);
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);
  // A refused save (stale version or a validation error) stays marked "not saved" after its dialog
  // closes, until a save succeeds, the edits are discarded or the record is reloaded.
  const [refused, setRefused] = useState(false);
  // D-52 drift warnings from the FR links or a solution unlink, shown in the FR section. Kept per BR, so
  // the panel moving to another process never carries them over.
  const [frWarn, setFrWarn] = useState({ brId: null, list: [] });
  const frWarnings = String(frWarn.brId) === String(brId) ? frWarn.list : [];
  const setFrWarnings = (fn) => setFrWarn((prev) => ({ brId,
    list: fn(String(prev.brId) === String(brId) ? prev.list : []) }));
  const onLinkWarnings = (ws) => { const l = warningList(ws); if (l.length) setFrWarn({ brId, list: l }); };

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.br(brId) });
    qc.invalidateQueries({ queryKey: keys.brs(projectId) });
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });
  };

  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'status_code') { if (SETTABLE_STATUSES.includes(form.base.status_code)) body.status_code = form.values.status_code; }
        else body[k] = blankToNull(form.values[k]);
      }
      return brApi.update(br.br_id, body);
    },
    onSaved: (row) => {
      form.saved(row); qc.setQueryData(keys.br(brId), row); refreshAll();
      if (!embedded) onNotice(t('requirements.saved'));           // the panel announces its one Save itself
    },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId) });
      form.rebase(fresh);
      save.setError('');
      setRefused(false);
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => {
    refreshAll();
    setActionError(isStale(err) ? t('processes.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const retire = useMutation({
    mutationFn: () => brApi.retire(br.br_id, br.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); onNotice(t('requirements.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => brApi.restore(br.br_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.br(brId), row); refreshAll(); onNotice(t('requirements.restored')); },
    onError: actionFail,
  });

  // Resolves true when saved, false when refused (the refusal itself is shown by useFormSave).
  const saveNow = () => {
    save.setError('');
    return save.m.mutateAsync().then(() => { setRefused(false); return true; }, () => { setRefused(true); return false; });
  };
  const discard = () => { form.discard(); setRefused(false); };

  if (!br || !form.values) return { br: null, error: brQ.error, getLabel };

  const v = form.values;
  const live = br.is_active;
  const editable = live && canEdit;
  const statusSettable = SETTABLE_STATUSES.includes(form.base.status_code);
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const statusOptions = statuses.filter((c) => SETTABLE_STATUSES.includes(c.code)).map((c) => ({ value: c.code, label: c.label }));
  const labels = { br_statement: t('requirements.statement'), status_code: t('requirements.status') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], k === 'status_code' ? getLabel(v[k]) : v[k]]));
  const text = (name, label, rows = 1) => (
    <TextField fullWidth multiline minRows={rows} id={`br-${name}`} label={label} disabled={!editable} value={v[name]}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: 8000 } }} />
  );

  const actions = (
    <>
      {!live && <Tag tone="neutral">{t('processes.retiredChip')}</Tag>}
      {canEdit && (live ? (OFFER_RETIRE_BR &&
        <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('requirements.retire')}</Button>
      ) : (
        <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('requirements.restore')}</Button>
      ))}
      {canEdit && !embedded && <Button variant="outlined" disabled={!form.dirty || busy} onClick={discard}>{t('processes.discard')}</Button>}
      {canEdit && !embedded && <Button variant="contained" disabled={!editable || !form.dirty || busy}
        onClick={saveNow}>{t('requirements.save')}</Button>}
    </>
  );
  const saveState = refused && form.dirty
    ? <Status tone="escalate" size="sm">{t('requirements.notSaved')}</Status>
    : form.dirty
    ? <Status tone="caution" size="sm">{t('requirements.unsaved')}</Status>
    : <Status tone="ok" size="sm">{t('requirements.savedVersion', { v: form.version })}</Status>;
  const alerts = (
    <>
      {actionError && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
    </>
  );
  const lines = <BrLines projectId={projectId} br={br} priorityCode={br.priority_code} disabled={!editable} />;
  // Fields, then CRUD beside RACI and solutions. The caller gives it a container (containerType: inline-size).
  const fields = (
    <>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'minmax(0,1fr)',
        [WIDE]: { gridTemplateColumns: 'minmax(0,3fr) minmax(0,1fr)' } }}>
        <Box sx={{ gridColumn: '1 / -1' }}>{text('br_statement', t('requirements.statement'))}</Box>
        {statusSettable && editable ? (
          <SimpleSelect id="br-status" label={t('requirements.status')} value={v.status_code}
            onChange={(s) => form.set('status_code', s)} options={statusOptions} />
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, alignItems: 'flex-start' }}>
            <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('requirements.status')}</Typography>
            <BrStatusTag code={br.status_code} label={getLabel(br.status_code)} />
            {!statusSettable && (
              <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('requirements.statusByFreeze')}</Typography>)}
          </Box>
        )}
      </Box>
      {lines}
      <Divider />
      <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: 'minmax(0,1fr)',
        [WIDE]: { gridTemplateColumns: 'minmax(0,1.25fr) minmax(0,1fr)' } }}>
        <CrudGrid projectId={projectId} br={br} disabled={!editable} mark={crudMark?.(br.bfc_node_id)} />
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, minWidth: 0 }}>
          <BrRaci projectId={projectId} br={br} disabled={!editable} />
          {isOn('SOLUTION') && <BrSolutionTags projectId={projectId} br={br} disabled={!editable} onWarnings={onLinkWarnings} />}
        </Box>
      </Box>
      {/* D-61: the data this requirement copies between systems; needs APPLICATION */}
      {isOn('APPLICATION') && (
        <>
          <Divider />
          <BrFlows projectId={projectId} br={br} disabled={!editable} frOn={isOn('FUNCTION_REQUIREMENT')} />
        </>)}
      {/* D-52: the BR maps to FRs directly, here; linking needs FUNCTION_REQUIREMENT only, the solution picker SOLUTION too */}
      {isOn('FUNCTION_REQUIREMENT') && (
        <>
          <Divider />
          <BrFrLinks projectId={projectId} br={br} disabled={!editable} solutionsOn={isOn('SOLUTION')}
            warnings={frWarnings} setWarnings={setFrWarnings} onNotice={onNotice} />
        </>)}
    </>
  );
  const dialogs = (
    <>
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('requirements.retireTitle')}
        body={t('requirements.retireBody', { number: br.br_number })} confirmLabel={t('requirements.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
    </>
  );

  return { br, error: brQ.error, getLabel, live, actions, saveState, alerts, fields, dialogs, lines,
    dirty: form.dirty, canSave: editable && form.dirty, busy, saveNow, discard,
    coverage: isOn('FUNCTION_REQUIREMENT') ? <CoveragePanel projectId={projectId} brId={br.br_id} /> : null,
    // 10d: the process panel lays the parts out itself (ranked), so it reads these instead of `fields`.
    values: v, set: form.set, changedCount: form.changed.length, editable, statusSettable, statusOptions,
    refused, saveError: save.error, actionError, clearActionError: () => setActionError(''),
    askRetire: () => { setActionError(''); setConfirmRetire(true); }, restoreNow: () => { setActionError(''); restore.mutate(); },
    frWarnings, setFrWarnings, onLinkWarnings };
}
