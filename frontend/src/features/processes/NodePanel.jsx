import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Card, CardContent, Chip, Divider, FormControlLabel, Grid, Stack, Switch,
  TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { bfcApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, Mono, RaciPanel, SectionTitle, blankToNull, useEditForm, useFormSave } from './chartKit';
import { FlowGaps, StepSequence } from './FlowSections';
import { StepData, StepFlows, stepKey } from './StepSections';

const STEP_SINGLE = ['ACCOUNTABLE', 'RESPONSIBLE'];      // services/raci.py SINGLE[BfcNodeOrgRole]

const pickNode = (n) => ({ node_name: n.node_name ?? '', purpose_desc: n.purpose_desc ?? '',
  data_processing_desc: n.data_processing_desc ?? '' });

const firstLine = (s) => (s ?? '').split('\n')[0];

export function NodePanel({ projectId, nodeId, parent, br, showRetired, onNotice, onGone }) {
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const nodeQ = useQuery({ queryKey: keys.node(nodeId), queryFn: () => bfcApi.get(nodeId) });
  const node = nodeQ.data;
  const form = useEditForm(node, pickNode);
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });
    qc.invalidateQueries({ queryKey: keys.node(nodeId) });
    qc.invalidateQueries({ queryKey: keys.brs(projectId) });
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
    mutationFn: () => bfcApi.restore(nodeId),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.node(nodeId), row); refreshAll(); onNotice(t('processes.restored')); },
    onError: actionFail,
  });

  if (nodeQ.error) return <Alert severity="error">{errorText(nodeQ.error)}</Alert>;
  if (!node || !form.values) return <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>;

  const live = node.is_active;
  const editable = live && canEdit;      // a REVIEWER sees the panel, not its controls (sara LOW-3)
  const v = form.values;
  const busy = save.m.isPending || mark.isPending || retire.isPending || restore.isPending;
  const canSwitch = editable && node.level_no >= FIRST_PROCESS_LEVEL;
  const labels = { node_name: t('processes.name'), purpose_desc: t('processes.purpose'),
    data_processing_desc: t('processes.dataProcessing') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], v[k]]));

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 2, flexWrap: 'wrap' }}>
          <Typography component="h2" variant="h6">
            {t('processes.panelTitle', { n: node.level_no, name: node.node_name })}
          </Typography>
          <Stack direction="row" spacing={1}>
            {node.is_process && <Chip size="small" color="primary" label={t('processes.processChip')} />}
            {!live && <Chip size="small" variant="outlined" label={t('processes.retiredChip')} />}
          </Stack>
        </Stack>

        {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
        {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}

        {node.is_process && br && (
          <Box sx={(th) => ({ mb: 2, p: 2, borderRadius: 2, bgcolor: th.vars.palette.brand.selected,
            display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' })}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: 11.5, fontWeight: 700, letterSpacing: 0.8, textTransform: 'uppercase', color: 'text.secondary' }}>
                {t('processes.brBanner')}</Typography>
              <Typography sx={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                <Mono sx={{ mr: 1 }}>{br.br_number}</Mono>
                {!br.is_active && <Chip size="small" variant="outlined" sx={{ mr: 1 }} label={t('processes.retiredChip')} />}
                {firstLine(br.br_statement) || <Box component="span" sx={{ color: 'text.secondary', fontWeight: 400 }}>{t('processes.brNoStatement')}</Box>}
              </Typography>
            </Box>
            <Button variant="contained" component={RouterLink} to={links.requirement(projectId, br.br_id)}>
              {t('processes.openRequirement')}</Button>
          </Box>
        )}

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField fullWidth id="node-parent" label={t('processes.parent')} disabled
              value={parent ? `${parent.hier_code} ${parent.node_name}` : t('processes.noParent')} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField fullWidth id="node-code" label={t('processes.code')} disabled value={node.hier_code}
              helperText={t('processes.codeHelp')} slotProps={{ htmlInput: { style: { fontFamily: MONO } } }} />
          </Grid>
          <Grid size={12}>
            <TextField fullWidth id="node-name" label={t('processes.name')} required disabled={!editable}
              value={v.node_name} onChange={(e) => form.set('node_name', e.target.value)}
              slotProps={{ htmlInput: { maxLength: 200 } }} />
          </Grid>
          <Grid size={12}>
            <TextField fullWidth multiline minRows={2} id="node-purpose" label={t('processes.purpose')} disabled={!editable}
              value={v.purpose_desc} onChange={(e) => form.set('purpose_desc', e.target.value)}
              slotProps={{ htmlInput: { maxLength: 4000 } }} />
          </Grid>
          {node.is_process && (
            <Grid size={12}>
              <TextField fullWidth multiline minRows={2} id="node-dpd" label={t('processes.dataProcessing')} disabled={!editable}
                value={v.data_processing_desc} onChange={(e) => form.set('data_processing_desc', e.target.value)}
                slotProps={{ htmlInput: { maxLength: 4000 } }} />
            </Grid>
          )}
        </Grid>

        <Stack direction="row" sx={{ mt: 2, alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <FormControlLabel label={t('processes.isProcess')}
            control={<Switch id="node-is-process" checked={node.is_process} disabled={!canSwitch || busy}
              onChange={(e) => { setActionError(''); mark.mutate(e.target.checked); }} />} />
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', flex: 1, minWidth: 200 }}>
            {canSwitch ? t('processes.processHelp') : t('processes.processLevels')}</Typography>
        </Stack>

        <Stack direction="row" spacing={1} sx={{ mt: 2, justifyContent: 'flex-end', flexWrap: 'wrap' }} useFlexGap>
          {!canEdit ? null : live ? (
            <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>
              {t('processes.retire')}</Button>
          ) : (
            <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('processes.restore')}</Button>
          )}
          <Box sx={{ flex: 1 }} />
          {canEdit && (<>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('processes.discard')}</Button>
          <Button variant="contained" disabled={!live || !form.dirty || busy || !v.node_name.trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('processes.save')}</Button>
          </>)}
        </Stack>

        {node.is_process && (
          <>
            <Divider sx={{ my: 3 }} />
            <StepData projectId={projectId} node={node} disabled={!editable} />
            <Divider sx={{ my: 3 }} />
            <StepSequence projectId={projectId} node={node} disabled={!editable} />
            <Divider sx={{ my: 3 }} />
            <RaciPanel projectId={projectId} queryKey={stepKey(nodeId, 'roles')} disabled={!editable}
              list={() => bfcApi.roles(nodeId)} link={(body) => bfcApi.linkRole(nodeId, body)}
              unlink={(id, rv) => bfcApi.unlinkRole(nodeId, id, rv)} linkId="bfc_node_org_role_id" single={STEP_SINGLE} />
            <Divider sx={{ my: 3 }} />
            <StepFlows projectId={projectId} node={node} disabled={!editable} />
          </>
        )}
        {!node.is_process && (
          <Box sx={{ mt: 3 }}>
            <SectionTitle>{t('processes.stepFacts')}</SectionTitle>
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.stepFactsHelp')}</Typography>
            {live && node.level_no >= FIRST_PROCESS_LEVEL - 1 && (
              <>
                <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2, flexWrap: 'wrap' }}>
                  <Button variant="outlined" component={RouterLink} to={links.flow(projectId, nodeId)}>
                    {t('processes.openFlow')}</Button>
                  <Button variant="outlined" component={RouterLink} to={links.dfd(projectId, nodeId)}>
                    {t('processes.openDfd')}</Button>
                </Stack>
                <Box sx={{ mt: 3 }}><FlowGaps projectId={projectId} node={node} /></Box>
              </>
            )}
          </Box>
        )}
      </CardContent>
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('processes.retireTitle')}
        body={t('processes.retireBody', { name: `${node.hier_code} ${node.node_name}` })}
        confirmLabel={t('processes.retire')} busy={retire.isPending}
        onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
    </Card>
  );
}
