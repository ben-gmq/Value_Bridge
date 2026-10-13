import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, IconButton, Link, Stack, TextField, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseIcon from '@mui/icons-material/Close';
import { errorText, isStale } from '../../api/client';
import { bfcApi, dataApi, partyApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Code, InfoTip, SectionLabel, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { PickDialog, SectionTitle, SimpleSelect, blankToNull, entityLabel } from './chartKit';

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

// A data entity on a step: the mockup's teal pill — code, name, and a remove button for editors.
function EntityChip({ projectId, de, deId, onDelete, disabled, busy }) {
  const name = de ? de.de_name : `#${deId}`;
  return (
    <Box sx={(th) => ({ display: 'inline-flex', alignItems: 'center', gap: 1, height: 32, pl: 1.25, pr: disabled ? 1.25 : 0.5,
      borderRadius: 999, bgcolor: th.vars.palette.brand.tealTint, border: `1px solid ${th.vars.palette.brand.teal}`, maxWidth: '100%' })}>
      <Box component={RouterLink} to={links.entity(projectId, deId)}
        sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, minWidth: 0, color: 'text.primary', textDecoration: 'none',
          '&:hover .vb-de-name': { textDecoration: 'underline' } }}>
        {de && <Code tone="teal" sx={{ fontSize: 12.5 }}>{de.de_number}</Code>}
        <Box component="span" className="vb-de-name" sx={{ fontSize: 13.5, overflow: 'hidden', textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' }}>{name}</Box>
      </Box>
      {!disabled && (
        <IconButton size="small" aria-label={t('processes.removeEntity', { name })} onClick={onDelete} disabled={busy}
          sx={{ width: 24, height: 24 }}><CloseIcon sx={{ fontSize: 15 }} /></IconButton>
      )}
    </Box>
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
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });   // the flow and DFD graphs draw step I/O
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });    // DR13-D2: the DFD light
    if (deId) qc.invalidateQueries({ queryKey: keys.entity(deId) });
  };
  const unlink = useMutation({
    mutationFn: (row) => bfcApi.unlinkStepData(node.bfc_node_id, row.bfc_node_data_entity_id, row.row_version),
    onSuccess: (_, row) => { setError(''); refresh(row.data_entity_id); },
    onError: (err) => { refresh(); setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed'))); },
  });
  const rows = q.data ?? [];
  const column = (dir) => (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      <SectionLabel>{t(dir === 'I' ? 'processes.dataIn' : 'processes.dataOut')}</SectionLabel>
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 1 }}>
        {rows.filter((r) => r.direction === dir).map((r) => (
          <EntityChip key={r.bfc_node_data_entity_id} projectId={projectId} deId={r.data_entity_id}
            de={entities.byId.get(r.data_entity_id)} disabled={disabled} busy={unlink.isPending}
            onDelete={() => unlink.mutate(r)} />
        ))}
        {!q.isLoading && !q.error && !rows.some((r) => r.direction === dir) && (
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.noData')}</Typography>
        )}
      </Stack>
    </Box>
  );
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <LoadError errors={[q.error, entities.error]} />
      {column('I')}
      {column('O')}
      {!disabled && (
        <Button size="small" variant="outlined" startIcon={<AddRounded />} sx={{ alignSelf: 'flex-start' }}
          onClick={() => { setError(''); setDirection('I'); setAdding(true); }}>
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
export function StepFlows({ projectId, node, disabled, bare = false }) {
  const qc = useQueryClient();
  const qk = stepKey(node.bfc_node_id, 'flows');
  const q = useQuery({ queryKey: qk, queryFn: () => bfcApi.flows(node.bfc_node_id) });
  const partiesQ = useQuery({ queryKey: keys.parties(projectId), queryFn: () => partyApi.list(projectId) });
  const entities = useEntities(projectId);
  const partyById = useMemo(() => new Map((partiesQ.data ?? []).map((p) => [p.external_entity_id, p])), [partiesQ.data]);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ direction: 'I', data_entity_id: '', flow_label: '' });
  const refresh = () => {                                    // flows can add step data
    qc.invalidateQueries({ queryKey: keys.node(node.bfc_node_id) });
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });  // the flow and DFD graphs draw them
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });   // DR13-D2: an inbound party starts it → the light
  };
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
      {/* `bare`: inside a section already titled "External parties" (10d), only the action shows */}
      {(!bare || !disabled) && <SectionTitle action={!disabled && (
        <Button size="small" startIcon={<AddRounded />} onClick={() => {
          setError(''); setDraft({ direction: 'I', data_entity_id: '', flow_label: '' }); setAdding(true);
        }}>{t('processes.addParty')}</Button>)}>{bare ? null : t('processes.parties')}</SectionTitle>}
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
              <Tag tone={r.direction === 'I' ? 'navy' : 'teal'} size="lg">{t(r.direction === 'I' ? 'processes.fromParty' : 'processes.toParty')}</Tag>
              <Typography sx={{ fontWeight: 600 }}>{p ? <><Code sx={{ mr: 0.5 }}>{p.ext_number}</Code> {p.ext_name}</> : `#${r.external_entity_id}`}</Typography>
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


/** D-64 / DR 10d-4: a to-be step's data in/out that its requirement's CRUD does not carry (written by an
 * external flow, a chart copy or the retired step editor). Shown read-only so nothing is hidden. */
export function StepDataNotOnBr({ projectId, node, brRows }) {
  const q = useQuery({ queryKey: stepKey(node.bfc_node_id, 'data'), queryFn: () => bfcApi.stepData(node.bfc_node_id) });
  const entities = useEntities(projectId);
  const onBr = new Set((brRows ?? []).map((r) => `${r.data_entity_id}:${r.direction}`));
  const extra = (q.data ?? []).filter((r) => !onBr.has(`${r.data_entity_id}:${r.direction}`));
  if (extra.length === 0) return null;
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{t('processes.run.dfdOnly')}</Typography>
        <InfoTip title={t('processes.run.dfdOnlyInfo')} />
      </Box>
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 1 }}>
        {extra.map((r) => (
          <Box key={r.bfc_node_data_entity_id} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
            <Tag tone={r.direction === 'I' ? 'navy' : 'teal'} size="lg">{t(r.direction === 'I' ? 'processes.dataIn' : 'processes.dataOut')}</Tag>
            <EntityChip projectId={projectId} deId={r.data_entity_id} de={entities.byId.get(r.data_entity_id)} disabled />
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

/**
 * D-49 / DR10c-D1: what else starts a process besides its time/event triggers — its input data entities and the
 * outside parties that send it something — from the same step reads the DFD uses (VIEW-guarded, no new route).
 * The DFD light's STARTED mark counts the same three (D-69). Each start is labelled by its kind.
 */
export function useOtherStarts(projectId, nodeId, enabled = true) {
  const dataQ = useQuery({ queryKey: stepKey(nodeId, 'data'), queryFn: () => bfcApi.stepData(nodeId), enabled });
  const flowsQ = useQuery({ queryKey: stepKey(nodeId, 'flows'), queryFn: () => bfcApi.flows(nodeId), enabled });
  const partiesQ = useQuery({ queryKey: keys.parties(projectId), queryFn: () => partyApi.list(projectId), enabled });
  const entities = useEntities(projectId);
  return useMemo(() => {
    const items = [];
    const seen = new Set();
    for (const r of dataQ.data ?? []) {
      if (r.direction !== 'I' || seen.has(`de${r.data_entity_id}`)) continue;
      seen.add(`de${r.data_entity_id}`);
      const de = entities.byId.get(r.data_entity_id);
      items.push({ key: `de${r.data_entity_id}`, kind: 'data', label: de ? entityLabel(de) : `#${r.data_entity_id}` });
    }
    const partyById = new Map((partiesQ.data ?? []).map((p) => [p.external_entity_id, p]));
    for (const f of flowsQ.data ?? []) {
      if (f.direction !== 'I' || seen.has(`ext${f.external_entity_id}`)) continue;
      seen.add(`ext${f.external_entity_id}`);
      const p = partyById.get(f.external_entity_id);
      items.push({ key: `ext${f.external_entity_id}`, kind: 'party', label: p ? `${p.ext_number} ${p.ext_name}` : `#${f.external_entity_id}` });
    }
    return { items, loading: dataQ.isLoading || flowsQ.isLoading, error: dataQ.error || flowsQ.error || partiesQ.error || entities.error };
  }, [dataQ.data, dataQ.isLoading, dataQ.error, flowsQ.data, flowsQ.isLoading, flowsQ.error, partiesQ.data, partiesQ.error, entities.byId, entities.error]);
}

/** The read-only line under the trigger editor: the process's other starts, or "Nothing starts this process". */
export function OtherStarts({ projectId, node, triggerCount }) {
  const o = useOtherStarts(projectId, node.bfc_node_id);
  if (o.loading) return null;
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
        <Typography component="h4" sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>{t('processes.starts.others')}</Typography>
        <InfoTip title={t('processes.starts.where')} />
      </Box>
      <LoadError errors={[o.error]} />
      {o.items.length === 0 ? (
        <Typography sx={{ fontSize: 13, color: triggerCount === 0 ? 'warning.main' : 'text.secondary' }}>
          {t(triggerCount === 0 ? 'processes.starts.nothing' : 'processes.starts.none')}</Typography>
      ) : (
        <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 0.75 }}>
          {o.items.map((i) => (
            <Tag key={i.key} tone={i.kind === 'data' ? 'teal' : 'neutral'} sx={{ maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {t(`processes.starts.kind.${i.kind}`)} · {i.label}</Tag>))}
        </Stack>
      )}
    </Box>
  );
}
