import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, IconButton, Link, Stack, TextField, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { errorText, isStale } from '../../api/client';
import { bfcApi, dataApi, partyApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { t } from '../../i18n/t';
import { PickDialog, SectionTitle, SimpleSelect, blankToNull, entityLabel, Mono } from './chartKit';

export const stepKey = (nodeId, what) => [...keys.node(nodeId), what];

function useEntities(projectId) {
  const q = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const byId = useMemo(() => new Map((q.data ?? []).map((e) => [e.data_entity_id, e])), [q.data]);
  return { list: (q.data ?? []).filter((e) => e.is_active), byId, error: q.error };
}

export function LoadError({ errors }) {
  const e = errors.find(Boolean);
  return e ? <Alert severity="error" sx={{ mb: 1 }}>{errorText(e)}</Alert> : null;
}

const NoEntities = ({ projectId }) => (
  <Alert severity="info">
    {t('processes.noEntities')}{' '}
    <Link component={RouterLink} to={links.data(projectId)}>{t('processes.goData')}</Link>
  </Alert>
);

function EntityChip({ projectId, de, deId, onDelete, disabled }) {
  return (
    <Chip variant="outlined" component={RouterLink} to={links.entity(projectId, deId)} clickable
      label={de ? <><Mono>{de.de_number}</Mono> {de.de_name}</> : `#${deId}`}
      onDelete={disabled ? undefined : (e) => { e.preventDefault(); onDelete(); }}
      sx={(th) => ({ color: th.vars.palette.brand.tealText, borderColor: th.vars.palette.brand.teal })} />
  );
}

/** Data in / Data out of a process step (bfc_node_data_entity). */
export function StepData({ projectId, node, disabled }) {
  const qc = useQueryClient();
  const qk = stepKey(node.bfc_node_id, 'data');
  const q = useQuery({ queryKey: qk, queryFn: () => bfcApi.stepData(node.bfc_node_id) });
  const entities = useEntities(projectId);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [direction, setDirection] = useState('I');
  const refresh = (deId) => {
    qc.invalidateQueries({ queryKey: qk });
    if (deId) qc.invalidateQueries({ queryKey: keys.entity(deId) });
  };
  const unlink = useMutation({
    mutationFn: (row) => bfcApi.unlinkStepData(node.bfc_node_id, row.bfc_node_data_entity_id, row.row_version),
    onSuccess: (_, row) => { setError(''); refresh(row.data_entity_id); },
    onError: (err) => { refresh(); setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed'))); },
  });
  const rows = q.data ?? [];
  const column = (dir) => (
    <Box sx={{ flex: 1, minWidth: 220 }}>
      <SectionTitle>{t(dir === 'I' ? 'processes.dataIn' : 'processes.dataOut')}</SectionTitle>
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 1 }}>
        {rows.filter((r) => r.direction === dir).map((r) => (
          <EntityChip key={r.bfc_node_data_entity_id} projectId={projectId} deId={r.data_entity_id}
            de={entities.byId.get(r.data_entity_id)} disabled={disabled || unlink.isPending}
            onDelete={() => unlink.mutate(r)} />
        ))}
        {!q.isLoading && !q.error && !rows.some((r) => r.direction === dir) && (
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.noData')}</Typography>
        )}
      </Stack>
    </Box>
  );
  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <LoadError errors={[q.error, entities.error]} />
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 3 }}>
        {column('I')}
        {column('O')}
      </Stack>
      {!disabled && (
        <Button size="small" sx={{ mt: 1 }} onClick={() => { setError(''); setDirection('I'); setAdding(true); }}>
          {t('processes.addEntity')}</Button>
      )}
      {adding && (
        <PickDialog open title={t('processes.addEntityTitle')} optionLabel={t('processes.entity')}
          options={entities.list} getOptionLabel={entityLabel} submitLabel={t('processes.add')}
          emptyHint={<NoEntities projectId={projectId} />}
          extra={(
            <SimpleSelect id="step-data-dir" label={t('processes.direction')} value={direction} onChange={setDirection}
              options={['I', 'O'].map((d) => ({ value: d, label: t(d === 'I' ? 'processes.dataIn' : 'processes.dataOut') }))} />)}
          onSubmit={(de) => bfcApi.linkStepData(node.bfc_node_id, { data_entity_id: de.data_entity_id, direction })}
          onDone={(r) => refresh(r?.data_entity_id)} onClose={() => setAdding(false)} />
      )}
    </Box>
  );
}

/** External parties the step exchanges data with (bfc_node_external_flow). */
export function StepFlows({ projectId, node, disabled }) {
  const qc = useQueryClient();
  const qk = stepKey(node.bfc_node_id, 'flows');
  const q = useQuery({ queryKey: qk, queryFn: () => bfcApi.flows(node.bfc_node_id) });
  const partiesQ = useQuery({ queryKey: keys.parties(projectId), queryFn: () => partyApi.list(projectId) });
  const entities = useEntities(projectId);
  const partyById = useMemo(() => new Map((partiesQ.data ?? []).map((p) => [p.external_entity_id, p])), [partiesQ.data]);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ direction: 'I', data_entity_id: '', flow_label: '' });
  const refresh = () => qc.invalidateQueries({ queryKey: keys.node(node.bfc_node_id) });  // flows can add step data
  const unlink = useMutation({
    mutationFn: (row) => bfcApi.unlinkFlow(node.bfc_node_id, row.bfc_node_external_flow_id, row.row_version),
    onSuccess: () => { setError(''); refresh(); },
    onError: (err) => { refresh(); setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed'))); },
  });
  const parties = (partiesQ.data ?? []).filter((p) => p.is_active);
  const rows = q.data ?? [];
  const partyLabel = (p) => (p ? `${p.ext_number} ${p.ext_name}` : '');
  return (
    <Box>
      <SectionTitle action={!disabled && (
        <Button size="small" onClick={() => {
          setError(''); setDraft({ direction: 'I', data_entity_id: '', flow_label: '' }); setAdding(true);
        }}>{t('processes.addParty')}</Button>)}>{t('processes.parties')}</SectionTitle>
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <LoadError errors={[q.error, partiesQ.error, entities.error]} />
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.noFlows')}</Typography>
      )}
      <Stack spacing={0.75}>
        {rows.map((r) => {
          const p = partyById.get(r.external_entity_id);
          const de = r.data_entity_id ? entities.byId.get(r.data_entity_id) : null;
          return (
            <Stack key={r.bfc_node_external_flow_id} direction="row" sx={{ alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Chip size="small" label={t(r.direction === 'I' ? 'processes.fromParty' : 'processes.toParty')} />
              <Typography sx={{ fontWeight: 600 }}>{p ? <><Mono>{p.ext_number}</Mono> {p.ext_name}</> : `#${r.external_entity_id}`}</Typography>
              {r.data_entity_id && (
                <Link component={RouterLink} to={links.entity(projectId, r.data_entity_id)} sx={{ fontSize: 13 }}>
                  {de ? entityLabel(de) : `#${r.data_entity_id}`}</Link>
              )}
              {r.flow_label && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{r.flow_label}</Typography>}
              {!disabled && (
                <IconButton size="small" aria-label={t('processes.removeFlow', { party: partyLabel(p) })}
                  disabled={unlink.isPending} onClick={() => unlink.mutate(r)}><CloseIcon fontSize="small" /></IconButton>
              )}
            </Stack>
          );
        })}
      </Stack>
      {adding && (
        <PickDialog open title={t('processes.addPartyTitle')} optionLabel={t('processes.party')}
          options={parties} getOptionLabel={partyLabel} submitLabel={t('processes.add')}
          emptyHint={(
            <Alert severity="info">
              {t('processes.noParties')}{' '}
              <Link component={RouterLink} to={links.parties(projectId)}>{t('processes.goParties')}</Link>
            </Alert>)}
          extra={(
            <>
              <SimpleSelect id="flow-dir" label={t('processes.direction')} value={draft.direction}
                onChange={(v) => setDraft((d) => ({ ...d, direction: v }))}
                options={[{ value: 'I', label: t('processes.fromParty') }, { value: 'O', label: t('processes.toParty') }]} />
              <SimpleSelect id="flow-entity" label={t('processes.flowEntity')} value={draft.data_entity_id} allowEmpty
                onChange={(v) => setDraft((d) => ({ ...d, data_entity_id: v }))}
                options={entities.list.map((e) => ({ value: e.data_entity_id, label: entityLabel(e) }))} />
              <TextField id="flow-label" label={t('processes.flowLabel')} value={draft.flow_label}
                slotProps={{ htmlInput: { maxLength: 200 } }}
                onChange={(e) => setDraft((d) => ({ ...d, flow_label: e.target.value }))} />
            </>)}
          onSubmit={(p) => bfcApi.linkFlow(node.bfc_node_id, {
            external_entity_id: p.external_entity_id, direction: draft.direction,
            data_entity_id: draft.data_entity_id === '' ? null : draft.data_entity_id,
            flow_label: blankToNull(draft.flow_label) })}
          onDone={(r) => { refresh(); if (r?.data_entity_id) qc.invalidateQueries({ queryKey: keys.entity(r.data_entity_id) }); }}
          onClose={() => setAdding(false)} />
      )}
    </Box>
  );
}

