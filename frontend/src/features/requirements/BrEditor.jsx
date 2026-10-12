import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Divider, Link, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { brApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Code, SectionLabel, Status, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CrudGrid } from './CrudGrid';
import { BrRaci } from './BrRaci';
import { BrSolutionTags } from './BrSolutionTags';
import { CoveragePanel } from './CoveragePanel';
import { BrStatusTag } from './reqKit';

// S1-8: a person sets Draft or Confirmed. Baselined / Superseded are set by the freeze and are
// shown read-only (the server refuses them too: business_requirement.SYSTEM_SET_STATUSES).
const SETTABLE_STATUSES = ['DRAFT', 'CONFIRMED'];

const pickBr = (b) => ({ br_statement: b.br_statement ?? '', business_logic: b.business_logic ?? '',
  output_expectation: b.output_expectation ?? '', status_code: b.status_code });

// The two-column splits follow the editor's own width (a container), not the window's.
const WIDE = '@container (min-width: 700px)';

/**
 * One business requirement, read and edited (mockup 03). D-53: the same editor serves the BR page and
 * the process's panel in the function chart, so the two never drift. Returns the parts; the caller
 * lays them out. `onNotice` receives the success messages.
 */
export function useBrEditor({ projectId, brId, onNotice }) {
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit();             // UAT 7b: a viewer sees the requirement, not its controls
  const qc = useQueryClient();
  const brQ = useQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId), enabled: brId != null });
  const br = brQ.data;
  const { codes: statuses, getLabel } = useCodes(projectId, 'BR_STATUS');
  const form = useEditForm(br, pickBr);
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

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
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.br(brId), row); refreshAll(); onNotice(t('requirements.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId) });
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

  if (!br || !form.values) return { br: null, error: brQ.error, getLabel };

  const v = form.values;
  const live = br.is_active;
  const editable = live && canEdit;
  const statusSettable = SETTABLE_STATUSES.includes(form.base.status_code);
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const statusOptions = statuses.filter((c) => SETTABLE_STATUSES.includes(c.code)).map((c) => ({ value: c.code, label: c.label }));
  const labels = { br_statement: t('requirements.statement'), business_logic: t('requirements.logic'),
    output_expectation: t('requirements.output'), status_code: t('requirements.status') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], k === 'status_code' ? getLabel(v[k]) : v[k]]));
  const text = (name, label, rows = 1) => (
    <TextField fullWidth multiline minRows={rows} id={`br-${name}`} label={label} disabled={!editable} value={v[name]}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: 8000 } }} />
  );

  const actions = (
    <>
      {!live && <Tag tone="neutral">{t('processes.retiredChip')}</Tag>}
      {canEdit && (live ? (
        <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('requirements.retire')}</Button>
      ) : (
        <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('requirements.restore')}</Button>
      ))}
      {canEdit && <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('processes.discard')}</Button>}
      {canEdit && <Button variant="contained" disabled={!editable || !form.dirty || busy}
        onClick={() => { save.setError(''); save.m.mutate(); }}>{t('requirements.save')}</Button>}
    </>
  );
  const saveState = form.dirty
    ? <Status tone="caution" size="sm">{t('requirements.unsaved')}</Status>
    : <Status tone="ok" size="sm">{t('requirements.savedVersion', { v: form.version })}</Status>;
  const alerts = (
    <>
      {actionError && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
    </>
  );
  // Fields, then CRUD beside RACI and solutions. The caller gives it a container (containerType: inline-size).
  const fields = (
    <>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'minmax(0,1fr)',
        [WIDE]: { gridTemplateColumns: 'minmax(0,3fr) minmax(0,1fr)' } }}>
        <Box sx={{ gridColumn: '1 / -1' }}>{text('br_statement', t('requirements.statement'))}</Box>
        <Box sx={{ gridColumn: '1 / -1' }}>{text('business_logic', t('requirements.logic'), 2)}</Box>
        {text('output_expectation', t('requirements.output'))}
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
      <Divider />
      <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: 'minmax(0,1fr)',
        [WIDE]: { gridTemplateColumns: 'minmax(0,1.25fr) minmax(0,1fr)' } }}>
        <CrudGrid projectId={projectId} br={br} disabled={!editable} />
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, minWidth: 0 }}>
          <BrRaci projectId={projectId} br={br} disabled={!editable} />
          {isOn('SOLUTION') && <BrSolutionTags projectId={projectId} br={br} disabled={!editable} />}
        </Box>
      </Box>
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
  return { br, error: brQ.error, getLabel, live, actions, saveState, alerts, fields, dialogs,
    coverage: isOn('FUNCTION_REQUIREMENT') ? <CoveragePanel projectId={projectId} brId={br.br_id} /> : null };
}

/** The process's business requirement inside its panel in the function chart (D-53). */
export function BrSection({ projectId, brId, onNotice }) {
  const ed = useBrEditor({ projectId, brId, onNotice });
  if (ed.error) return <Alert severity="error">{errorText(ed.error)}</Alert>;
  if (!ed.br) return <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>;
  const { br } = ed;
  return (
    <Box component="section" aria-labelledby="br-section-title"
      sx={{ containerType: 'inline-size', display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Box id="br-section-title"><SectionLabel>{t('requirements.panelTitle')}</SectionLabel></Box>
        <Link component={RouterLink} to={links.requirement(projectId, br.br_id)} underline="hover"
          title={t('requirements.openPage')}><Code tone="purple">{br.br_number}</Code></Link>
        <BrStatusTag code={br.status_code} label={ed.getLabel(br.status_code)} />
        <Box sx={{ flexGrow: 1 }} />
        {ed.saveState}
      </Box>
      {ed.alerts}
      {ed.fields}
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end' }}>
        <Button component={RouterLink} to={links.requirement(projectId, br.br_id)} sx={{ mr: 'auto' }}>
          {t('requirements.openPage')}</Button>
        {ed.actions}
      </Box>
      {ed.coverage}
      {ed.dialogs}
    </Box>
  );
}
