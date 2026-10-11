import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Divider, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import { errorKind, errorText, isStale } from '../../api/client';
import { bfcApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, SectionLabel, Status, Tag } from '../../components/kit';
import { MONO } from '../../theme/theme';
import { useComponents } from '../../app/useComponents';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, RaciPanel, blankToNull, useEditForm, useFormSave } from './chartKit';
import { CompletenessPanel, PerformerPanel, TriggerPanel } from './StepDfd';
import { RetireStepDialog } from './RetireStepDialog';
import { StepData, StepFlows, stepKey } from './StepSections';
import { AppLinkPanel } from '../applications/AppLinkPanel';

const STEP_SINGLE = ['ACCOUNTABLE'];      // services/raci.py SINGLE[BfcNodeOrgRole] — several R are normal (D-46)

const pickNode = (n) => ({ node_name: n.node_name ?? '', purpose_desc: n.purpose_desc ?? '',
  data_processing_desc: n.data_processing_desc ?? '' });

const firstLine = (s) => (s ?? '').split('\n')[0];

// "Restore these first: A; B" → ['A', 'B'] — the names are the server's, shown as text.
const restoreFirstList = (err) => {
  const detail = errorText(err, '');
  return detail.slice(detail.indexOf(':') + 1).split(';').map((s) => s.trim()).filter(Boolean);
};

export function NodePanel({ projectId, nodeId, parent, br, showRetired, onNotice, onGone }) {
  const { isOn } = useComponents(projectId);
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const nodeQ = useQuery({ queryKey: keys.node(nodeId), queryFn: () => bfcApi.get(nodeId) });
  const node = nodeQ.data;
  const form = useEditForm(node, pickNode);
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);
  const [retiringStep, setRetiringStep] = useState(false);
  // Which restore fits a retired step is the server's call (SR-1): a step is offered the
  // with-dependents restore until a 409 says it was retired on its own.
  const [plainFor, setPlainFor] = useState(null);
  const [restoreNote, setRestoreNote] = useState(null);       // { nodeId, hint?, first? }

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });
    qc.invalidateQueries({ queryKey: keys.node(nodeId) });
    qc.invalidateQueries({ queryKey: keys.brs(projectId) });
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });      // every DFD and its gaps
  };

  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'data_processing_desc' && !node.is_process) continue;
        body[k] = k === 'node_name' ? form.values[k].trim() : blankToNull(form.values[k]);
      }
      return bfcApi.update(nodeId, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.node(nodeId), row); refreshAll(); onNotice(t('processes.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.node(nodeId), queryFn: () => bfcApi.get(nodeId) });
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
  const mark = useMutation({
    mutationFn: (isProcess) => bfcApi.markProcess(nodeId, { row_version: node.row_version, is_process: isProcess }),
    onSuccess: (res) => {
      setActionError('');
      qc.setQueryData(keys.node(nodeId), res.node);
      form.rebase(res.node);                       // our own click is not someone else's edit
      refreshAll();
      onNotice(res.business_requirement
        ? t('processes.promoted', { br: res.business_requirement.br_number }) : t('processes.demoted'));
    },
    onError: actionFail,
  });
  const retire = useMutation({
    mutationFn: () => bfcApi.retire(nodeId, node.row_version),
    onSuccess: () => {
      setConfirmRetire(false); setActionError(''); refreshAll(); onNotice(t('processes.retired'));
      if (!showRetired) onGone();
    },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: (withDependents) => (withDependents ? bfcApi.restoreWithDependents(nodeId) : bfcApi.restore(nodeId)),
    onSuccess: (res, withDependents) => {
      setActionError(''); setRestoreNote(null);
      if (!withDependents) qc.setQueryData(keys.node(nodeId), res);
      refreshAll();
      onNotice(withDependents ? t('processes.restoredWithDependents', { n: res.restored }) : t('processes.restored'));
    },
    onError: (err) => {
      const kind = errorKind(err);
      if (kind === 'USE_PLAIN_RESTORE' || kind === 'USE_RESTORE_WITH_DEPENDENTS') {
        const plain = kind === 'USE_PLAIN_RESTORE';
        setPlainFor(plain ? nodeId : null); setActionError('');
        setRestoreNote({ nodeId, hint: t(plain ? 'processes.restorePlainFits' : 'processes.restoreDependentsFits') });
      } else if (kind === 'RESTORE_FIRST') {
        setActionError(''); setRestoreNote({ nodeId, first: restoreFirstList(err) });
      } else {
        actionFail(err);
      }
    },
  });

  if (nodeQ.error) return <Card><Alert severity="error">{errorText(nodeQ.error)}</Alert></Card>;
  if (!node || !form.values) return <Card><Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography></Card>;

  const live = node.is_active;
  const editable = live && canEdit;      // a read-only user sees the panel, not its controls (sara LOW-3)
  const asIs = node.bfc_set_code === 'AS_IS';
  const dfdOn = asIs ? isOn('AS_IS') : isOn('TO_BE_DFD');      // the chart's DFD component (D-37, D-47)
  const v = form.values;
  const busy = save.m.isPending || mark.isPending || retire.isPending || restore.isPending;
  const restoreWithDependents = node.is_process && plainFor !== nodeId;
  const note = !live && restoreNote?.nodeId === nodeId ? restoreNote : null;
  const canSwitch = editable && node.level_no >= FIRST_PROCESS_LEVEL;
  const labels = { node_name: t('processes.name'), purpose_desc: t('processes.purpose'),
    data_processing_desc: t('processes.dataProcessing') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], v[k]]));

  const headerAction = (
    <Stack direction="row" useFlexGap sx={{ gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
      {node.is_process && <Tag tone="purple">{t('processes.processChip')}</Tag>}
      {!live && <Tag tone="neutral">{t('processes.retiredChip')}</Tag>}
      {form.dirty
        ? <Status tone="caution" size="sm">{t('processes.unsaved')}</Status>
        : <Status tone="ok" size="sm">{t('processes.savedVersion', { v: node.row_version })}</Status>}
    </Stack>
  );
  const twoCol = { display: 'grid', gap: 3, gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1fr) minmax(0,1.15fr)' } };

  return (
    <Card title={t('processes.panelTitle', { n: node.level_no, name: node.node_name })} action={headerAction}>
        {actionError && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
        {save.error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
        {note?.hint && <Alert severity="info" onClose={() => setRestoreNote(null)}>{note.hint}</Alert>}
        {note?.first && (
          <Alert severity="warning" onClose={() => setRestoreNote(null)}>
            <Typography sx={{ fontSize: 13, mb: 0.5 }}>{t('processes.restoreFirstTitle')}</Typography>
            <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
              {note.first.map((name, i) => <Typography component="li" key={i} sx={{ fontSize: 13 }}>{name}</Typography>)}
            </Box>
          </Alert>
        )}

        {node.is_process && br && (
          <Box sx={(th) => ({ px: 2, py: 1.5, borderRadius: '18px', bgcolor: th.vars.palette.brand.ftc,
            display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' })}>
            <AutoAwesomeOutlined aria-hidden sx={(th) => ({ fontSize: 20, color: th.vars.palette.brand.purpleLight })} />
            <Box sx={{ flex: '1 1 220px', minWidth: 0 }}>
              <Typography sx={(th) => ({ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase',
                color: th.vars.palette.brand.onFtcTile })}>{t('processes.brBanner')}</Typography>
              <Typography sx={(th) => ({ fontSize: 14.5, fontWeight: 600, color: th.vars.palette.brand.onFtc,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' })}>
                <Box component="span" sx={(th) => ({ fontFamily: MONO, fontSize: 13.5, mr: 1,
                  color: th.vars.palette.brand.purpleLight })}>{br.br_number}</Box>
                {!br.is_active && <Tag tone="neutral" sx={{ mr: 1, height: 20 }}>{t('processes.retiredChip')}</Tag>}
                {firstLine(br.br_statement) || <Box component="span" sx={(th) => ({ color: th.vars.palette.brand.onFtcTile, fontWeight: 400 })}>
                  {t('processes.brNoStatement')}</Box>}
              </Typography>
            </Box>
            <Button variant="contained" size="small" component={RouterLink} to={links.requirement(projectId, br.br_id)}
              sx={(th) => ({ bgcolor: th.vars.palette.brand.onFtc, color: th.vars.palette.brand.ftc,
                '&:hover': { bgcolor: th.vars.palette.brand.onFtcTile } })}>
              {t('processes.openRequirement')}</Button>
          </Box>
        )}

        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'minmax(0,1fr) minmax(0,1fr)' } }}>
          <TextField fullWidth id="node-parent" label={node.level_no > 1 ? t('processes.parentLevel', { n: node.level_no - 1 }) : t('processes.parent')} disabled
            value={parent ? `${parent.hier_code} ${parent.node_name}` : t('processes.noParent')} />
          <TextField fullWidth id="node-code" label={t('processes.code')} disabled value={node.hier_code}
            helperText={t('processes.codeHelp')}
            sx={(th) => ({ '& .MuiInputBase-input.Mui-disabled': { fontFamily: MONO,
              WebkitTextFillColor: th.vars.palette.brand.purpleText, color: th.vars.palette.brand.purpleText } })} />
          <TextField fullWidth id="node-name" label={t('processes.name')} required disabled={!editable}
            value={v.node_name} onChange={(e) => form.set('node_name', e.target.value)}
            sx={{ gridColumn: '1 / -1' }} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <TextField fullWidth multiline minRows={2} id="node-purpose" label={t('processes.purpose')} disabled={!editable}
            value={v.purpose_desc} onChange={(e) => form.set('purpose_desc', e.target.value)}
            sx={{ gridColumn: '1 / -1' }} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          {node.is_process && (
            <TextField fullWidth multiline minRows={2} id="node-dpd" label={t('processes.dataProcessing')} disabled={!editable}
              value={v.data_processing_desc} onChange={(e) => form.set('data_processing_desc', e.target.value)}
              sx={{ gridColumn: '1 / -1' }} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          )}
        </Box>

        <Box sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', px: 1.5, py: 0.75,
          borderRadius: '14px', bgcolor: th.vars.palette.background.subtle })}>
          <FormControlLabel label={t('processes.isProcess')} sx={{ mr: 1 }}
            control={<Switch id="node-is-process" checked={node.is_process} disabled={!canSwitch || busy}
              onChange={(e) => { setActionError(''); mark.mutate(e.target.checked); }} />} />
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', flex: '1 1 200px' }}>
            {canSwitch ? t('processes.processHelp') : t('processes.processLevels')}</Typography>
        </Box>

        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }} useFlexGap>
          {!canEdit ? null : live ? (
            <Button color="warning" disabled={busy}
              onClick={() => { setActionError(''); if (node.is_process) setRetiringStep(true); else setConfirmRetire(true); }}>
              {t('processes.retire')}</Button>
          ) : (
            <Button disabled={busy} onClick={() => { setActionError(''); setRestoreNote(null); restore.mutate(restoreWithDependents); }}>
              {t(restoreWithDependents ? 'processes.restoreWithDependents' : 'processes.restore')}</Button>
          )}
          <Box sx={{ flex: 1 }} />
          {canEdit && (<>
          <Button variant="outlined" color="warning" disabled={!form.dirty || busy} onClick={form.discard}>{t('processes.discard')}</Button>
          <Button variant="contained" disabled={!live || !form.dirty || busy || !v.node_name.trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('processes.save')}</Button>
          </>)}
        </Stack>

        {node.is_process && (
          <>
            <Divider />
            <Box sx={twoCol}>
              <StepData projectId={projectId} node={node} disabled={!editable} />
              <RaciPanel projectId={projectId} queryKey={stepKey(nodeId, 'roles')} disabled={!editable}
                list={() => bfcApi.roles(nodeId)} link={(body) => bfcApi.linkRole(nodeId, body)}
                unlink={(id, rv) => bfcApi.unlinkRole(nodeId, id, rv)} linkId="bfc_node_org_role_id" single={STEP_SINGLE} />
            </Box>
            {dfdOn && <>
              <Divider />
              <Box sx={twoCol}>
                <PerformerPanel projectId={projectId} node={node} disabled={!editable} />
                <TriggerPanel projectId={projectId} node={node} disabled={!editable} />
              </Box>
              <Divider />
              <StepFlows projectId={projectId} node={node} disabled={!editable} />
            </>}
            {/* Supporting systems of an as-is step (Q-23): a to-be step's come from its solutions. */}
            {asIs && isOn('APPLICATION', 'AS_IS') && <><Divider /><AppLinkPanel projectId={projectId} title={t('applications.links.supportedBy')}
              empty={t('applications.links.noneSupported')} ownerKey={['step', nodeId]}
              rowId="application_bfc_node_id" disabled={!editable}
              api={{ list: () => bfcApi.apps(nodeId),
                link: (applicationId, note) => bfcApi.linkApp(nodeId, { application_id: applicationId, note }),
                edit: (row, note) => bfcApi.editAppLink(nodeId, row.application_bfc_node_id, { row_version: row.row_version, note }),
                unlink: (row) => bfcApi.unlinkApp(nodeId, row.application_bfc_node_id, row.row_version) }} /></>}
          </>
        )}
        {!node.is_process && (
          <>
            <Divider />
            <Box>
              <SectionLabel sx={{ mb: 1 }}>{t('processes.stepFacts')}</SectionLabel>
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.stepFactsHelp')}</Typography>
              {live && node.level_no >= FIRST_PROCESS_LEVEL - 1 && dfdOn && (
                <>
                  <Button variant="outlined" sx={{ mt: 2 }} component={RouterLink} to={links.dfd(projectId, nodeId)}>
                    {t('processes.openDfd')}</Button>
                  <Box sx={{ mt: 3 }}><CompletenessPanel projectId={projectId} node={node} /></Box>
                </>
              )}
            </Box>
          </>
        )}
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('processes.retireTitle')}
        body={t('processes.retireBody', { name: `${node.hier_code} ${node.node_name}` })}
        confirmLabel={t('processes.retire')} busy={retire.isPending}
        onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      {retiringStep && (
        <RetireStepDialog step={node} onClose={() => setRetiringStep(false)}
          onRetired={() => {
            setRetiringStep(false); setActionError(''); setPlainFor(null); refreshAll();
            onNotice(t('processes.retiredWithDependents'));
            if (!showRetired) onGone();
          }} />
      )}
    </Card>
  );
}
