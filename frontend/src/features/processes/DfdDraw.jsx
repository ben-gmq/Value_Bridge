import { useCallback, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField,
  Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { bfcApi, dataApi, dfdApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Code, Segmented } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, entityLabel } from './chartKit';

// Drawing connections on the DFD (D-65; slice13_spec §4.4, §7.4). A drawn line writes exactly the row the
// step panel writes for the same choice, through the same route: step I/O, an external flow, a trigger
// link — and, process to process, the one hand-off route (A's output and B's input together). Order is
// still derived from the data (D-38): a hand-off makes the order arrow appear by itself. Nothing here
// writes a requirement's CRUD (Q-11). A pair the server would refuse is refused here first.
// Removing: only STORE, EXTERNAL and TRIGGER flows, each by its one row; an order arrow is never removable
// (DR13-P3). There is no keyboard delete (§7.14).

/** What a canvas node id is: s = step, d = data store, x = outside party, t = trigger. */
export const endKind = (id) => ({ s: 'step', d: 'store', x: 'party', t: 'trigger' }[String(id ?? '')[0]]);
const idOf = (id) => Number(String(id).slice(1));

/** The write a line from `src` to `dst` means, or the reason it is refused (§7.4). */
export function classify(src, dst) {
  const a = endKind(src);
  const b = endKind(dst);
  if (a === 'store' && b === 'step') return { action: 'STORE_IO', step: idOf(dst), de: idOf(src), direction: 'I' };
  if (a === 'step' && b === 'store') return { action: 'STORE_IO', step: idOf(src), de: idOf(dst), direction: 'O' };
  if (a === 'party' && b === 'step') return { action: 'PARTY', step: idOf(dst), party: idOf(src), direction: 'I' };
  if (a === 'step' && b === 'party') return { action: 'PARTY', step: idOf(src), party: idOf(dst), direction: 'O' };
  if (a === 'trigger' && b === 'step') return { action: 'TRIGGER', step: idOf(dst), trigger: idOf(src) };
  if (a === 'step' && b === 'step') {
    return src === dst ? { refused: 'processes.draw.refusedSelf' } : { action: 'HAND_OFF', from: idOf(src), to: idOf(dst) };
  }
  if (a === 'trigger' || b === 'trigger') return { refused: 'processes.draw.refusedTrigger' };
  return { refused: 'processes.draw.refusedPair' };
}

/** Whether the step already has this data in this direction — drawn as a store, or from/to a party. */
const hasIo = (g, step, de, direction) => g.flows.some((f) => f.bfc_node_id === step && f.data_entity_id === de
  && f.direction === direction && (f.kind === 'STORE' || f.kind === 'EXTERNAL'));

/** The box under a point (flow coordinates), lanes excluded: a line dropped on a box, not on its handle. */
function boxAt(nodes, p) {
  return nodes.find((n) => n.type !== 'lane' && n.position && p.x >= n.position.x && p.y >= n.position.y
    && p.x <= n.position.x + (n.measured?.width ?? n.width ?? 0) && p.y <= n.position.y + (n.measured?.height ?? n.height ?? 0));
}

/**
 * The drawing behaviour of one DFD. `canDraw` is false for a viewer, a chart whose DFD is off, or a
 * read-only view; then nothing here runs. `layout` is the page's one position saver (useLayoutSave).
 */
export function useDfdDraw({ projectId, g, canDraw, getNodes, toFlow, layout }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(null);        // an open dialog: hand-off, empty drop or party form
  const [removing, setRemoving] = useState(null);  // a flow chosen for removal
  const [notice, setNotice] = useState(null);      // { severity, text, step? }

  const refresh = useCallback((stepIds = [], deId = null) => {
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });     // every DFD graph and the gaps
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });      // DR13-D2: the light
    for (const id of stepIds) qc.invalidateQueries({ queryKey: keys.node(id) });
    if (deId) {
      qc.invalidateQueries({ queryKey: keys.entities(projectId) });
      qc.invalidateQueries({ queryKey: keys.entity(deId) });
    }
  }, [qc, projectId]);

  const fail = useCallback((err) => setNotice({ severity: 'error', text: errorText(err, t('common.saveFailed')) }), []);
  const already = useCallback(() => setNotice({ severity: 'info', text: t('processes.draw.already') }), []);

  const direct = useMutation({
    mutationFn: (c) => (c.action === 'TRIGGER'
      ? bfcApi.linkTrigger(c.step, { process_trigger_id: c.trigger })
      : bfcApi.linkStepData(c.step, { data_entity_id: c.de, direction: c.direction })),
    onSuccess: (_, c) => { setNotice(null); refresh([c.step], c.de); },
    onError: (err, c) => { refresh([c.step]); fail(err); },
  });

  /** A line between two boxes (src → dst, as drawn). */
  const connect = useCallback((src, dst) => {
    const c = classify(src, dst);
    if (c.refused) { setNotice({ severity: 'warning', text: t(c.refused) }); return; }
    if (c.action === 'STORE_IO') {
      if (hasIo(g, c.step, c.de, c.direction)) { already(); return; }
      direct.mutate(c);
    } else if (c.action === 'TRIGGER') {
      if (g.flows.some((f) => f.kind === 'TRIGGER' && f.bfc_node_id === c.step && f.process_trigger_id === c.trigger)) {
        already();
        return;
      }
      direct.mutate(c);
    } else {
      setNotice(null);
      setDraft(c);
    }
  }, [g, direct, already]);

  // React Flow calls this when any drag ends: on a handle (a valid connection), on a box body, or on
  // empty canvas. A drag that started on a box's left (input) handle runs backwards. The drop point is
  // turned into diagram coordinates (React Flow's `to` is in screen pixels).
  const onConnectEnd = useCallback((event, state) => {
    if (!canDraw || !g || !state?.fromNode) return;
    const from = state.fromNode.id;
    const forward = state.fromHandle?.type !== 'target';
    const pt = event?.changedTouches?.[0] ?? event;
    const at = pt && Number.isFinite(pt.clientX) ? toFlow()?.({ x: pt.clientX, y: pt.clientY }) : null;
    const target = state.isValid && state.toNode ? state.toNode : at && boxAt(getNodes(), at);
    if (target) {
      if (target.id === from && !state.isValid) return;             // a click on a box, not a line
      const [src, dst] = forward ? [from, target.id] : [target.id, from];
      connect(src, dst);
      return;
    }
    if (endKind(from) === 'step' && at) {                           // Q-12: a store where it was dropped
      setNotice(null);
      setDraft({ action: 'DROP', step: idOf(from), direction: forward ? 'O' : 'I', at });
    }
  }, [canDraw, g, getNodes, toFlow, connect]);

  const onEdgeClick = useCallback((_event, edge) => {
    if (!canDraw || !edge?.data?.flow) return;                      // an order arrow is never removable
    setRemoving(edge.data.flow);
  }, [canDraw]);

  const dialogs = (
    <>
      {draft && draft.action !== 'PARTY' && (
        <EntityDialog projectId={projectId} g={g} draft={draft} layout={layout} onClose={() => setDraft(null)}
          onDone={(r) => {
            if (r?.already) already(); else setNotice(null);
            refresh(r?.steps ?? [], r?.deId);
          }} />)}
      {draft && draft.action === 'PARTY' && (
        <PartyFlowDialog projectId={projectId} g={g} draft={draft} onClose={() => setDraft(null)}
          onDone={(r) => { setNotice(null); refresh([draft.step], r?.data_entity_id); }} />)}
      {removing && (
        <RemoveFlowDialog g={g} flow={removing} onClose={() => setRemoving(null)}
          onDone={() => { setNotice(null); refresh([removing.bfc_node_id], removing.data_entity_id); }}
          onRefused={(err) => {
            refresh([removing.bfc_node_id]);
            setNotice({ severity: 'error', step: removing.bfc_node_id,
              text: isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed')) });
          }} />)}
    </>);
  const clearNotice = useCallback(() => setNotice(null), []);
  return { onConnectEnd, onEdgeClick, dialogs, notice, clearNotice, busy: direct.isPending };
}

/** The drawn-on notice: "Already on the diagram", a refusal, or a removal the requirement blocks — the
 * last with a link to the step, where its requirement's data use is edited (D3). */
export function DrawNotice({ notice, onClose, g, projectId }) {
  if (!notice) return null;
  const step = notice.step && g?.processes.find((p) => p.bfc_node_id === notice.step);
  return (
    <Alert severity={notice.severity} sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={onClose}
      action={step && (
        <Button color="inherit" size="small" component={RouterLink} to={links.node(projectId, step.bfc_node_id, step.bfc_set_code)}>
          {t('processes.draw.openRequirement')}</Button>)}>
      {notice.text}
    </Alert>
  );
}

const stepName = (g, id) => {
  const p = g.processes.find((x) => x.bfc_node_id === id);
  return p ? `${p.hier_code} ${p.node_name}` : `#${id}`;
};

/** Pick a data entity — an existing one by DE- number or name, or a new one (Q-12, numbered on save). */
function EntityDialog({ projectId, g, draft, layout, onClose, onDone }) {
  const listQ = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const options = (listQ.data ?? []).filter((e) => e.is_active);
  const [mode, setMode] = useState('existing');
  const [picked, setPicked] = useState(null);
  const [name, setName] = useState('');
  const [direction, setDirection] = useState(draft.direction ?? 'O');
  const [error, setError] = useState('');
  const handOff = draft.action === 'HAND_OFF';
  const m = useMutation({
    mutationFn: async () => {
      const de = mode === 'new' ? await dataApi.create(projectId, { de_name: name.trim() }) : picked;
      if (handOff) {
        const r = await dfdApi.handOff(draft.from, { to_bfc_node_id: draft.to, data_entity_id: de.data_entity_id });
        return { already: r.already, steps: [draft.from, draft.to], deId: de.data_entity_id };
      }
      if (hasIo(g, draft.step, de.data_entity_id, direction)) return { already: true, steps: [], deId: null };
      await bfcApi.linkStepData(draft.step, { data_entity_id: de.data_entity_id, direction });
      // A store new to this diagram stands where the line was dropped (D-30, one position saver).
      if (!g.stores.some((s) => s.data_entity_id === de.data_entity_id)) {
        await layout.place({ object_type: 'ENTITY', object_id: de.data_entity_id,
          x: Math.round(draft.at.x), y: Math.round(draft.at.y) });
      }
      return { already: false, steps: [draft.step], deId: de.data_entity_id };
    },
    onSuccess: (r) => { onDone(r); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const ready = mode === 'new' ? name.trim().length > 0 : Boolean(picked);
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t(handOff ? 'processes.draw.handOffTitle' : 'processes.draw.dropTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary', wordBreak: 'break-word' }}>
            {handOff ? t('processes.draw.handOffHelp', { from: stepName(g, draft.from), to: stepName(g, draft.to) })
              : t('processes.draw.dropHelp', { step: stepName(g, draft.step) })}</Typography>
          <Segmented size="sm" label={t('processes.draw.entityMode')} value={mode} onChange={setMode}
            options={[{ value: 'existing', label: t('processes.draw.existing') }, { value: 'new', label: t('processes.draw.new') }]} />
          {mode === 'existing' ? (
            <Autocomplete options={options} getOptionLabel={entityLabel} value={picked} onChange={(_, v) => setPicked(v)}
              loading={listQ.isLoading} noOptionsText={t('processes.draw.noEntities')}
              renderInput={(params) => <TextField {...params} autoFocus label={t('processes.entity')} />} />
          ) : (
            <TextField autoFocus label={t('processes.draw.newName')} value={name} helperText={t('processes.draw.newHelp')}
              slotProps={{ htmlInput: { maxLength: 200 } }} onChange={(e) => setName(e.target.value)} />
          )}
          {!handOff && (
            <SimpleSelect id="draw-dir" label={t('processes.direction')} value={direction} onChange={setDirection}
              options={['I', 'O'].map((d) => ({ value: d, label: t(d === 'I' ? 'processes.dataIn' : 'processes.dataOut') }))} />)}
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.draw.noCrud')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!ready || m.isPending} onClick={() => { setError(''); m.mutate(); }}>
          {t('processes.draw.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/** A line between a party and a step: the panel's form — a data entity (optional) or a flow label. */
function PartyFlowDialog({ projectId, g, draft, onClose, onDone }) {
  const listQ = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const options = (listQ.data ?? []).filter((e) => e.is_active);
  const party = g.externals.find((x) => x.external_entity_id === draft.party);
  const [deId, setDeId] = useState('');
  const [label, setLabel] = useState('');
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => bfcApi.linkFlow(draft.step, { external_entity_id: draft.party, direction: draft.direction,
      data_entity_id: deId === '' ? null : deId, flow_label: blankToNull(label) }),
    onSuccess: (r) => { onDone(r); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const partyName = party ? `${party.ext_number} ${party.ext_name}` : `#${draft.party}`;
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('processes.draw.partyTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary', wordBreak: 'break-word' }}>
            {t(draft.direction === 'I' ? 'processes.draw.partyIn' : 'processes.draw.partyOut',
              { party: partyName, step: stepName(g, draft.step) })}</Typography>
          <SimpleSelect id="draw-flow-entity" label={t('processes.flowEntity')} value={deId} allowEmpty onChange={setDeId}
            options={options.map((e) => ({ value: e.data_entity_id, label: entityLabel(e) }))} />
          <TextField label={t('processes.flowLabel')} value={label} slotProps={{ htmlInput: { maxLength: 200 } }}
            onChange={(e) => setLabel(e.target.value)} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending} onClick={() => { setError(''); m.mutate(); }}>
          {t('processes.draw.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/** "Remove this flow": the flow's one row, through the route the panel uses. A 409 (a requirement's
 * data use or an external flow still needs the row) closes the dialog and shows its message. */
function RemoveFlowDialog({ g, flow, onClose, onDone, onRefused }) {
  const m = useMutation({
    mutationFn: () => {
      if (flow.kind === 'STORE') return bfcApi.unlinkStepData(flow.bfc_node_id, flow.link_id, flow.row_version);
      if (flow.kind === 'EXTERNAL') return bfcApi.unlinkFlow(flow.bfc_node_id, flow.link_id, flow.row_version);
      return bfcApi.unlinkTrigger(flow.bfc_node_id, flow.link_id, flow.row_version);
    },
    onSuccess: () => { onDone(); onClose(); },
    onError: (err) => { onRefused(err); onClose(); },
  });
  const far = flow.kind === 'STORE' ? g.stores.find((s) => s.data_entity_id === flow.data_entity_id)
    : flow.kind === 'EXTERNAL' ? g.externals.find((x) => x.external_entity_id === flow.external_entity_id) : null;
  const farCode = far?.de_number ?? far?.ext_number;
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('processes.draw.removeTitle')}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography sx={{ fontSize: 13.5, wordBreak: 'break-word' }}>
            {t(`processes.draw.removeBody.${flow.kind}`, { step: stepName(g, flow.bfc_node_id) })}</Typography>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline', flexWrap: 'wrap' }}>
            {farCode && <Code tone={flow.kind === 'STORE' ? 'teal' : 'navy'}>{farCode}</Code>}
            <Typography sx={{ fontSize: 13.5, fontWeight: 600, wordBreak: 'break-word' }}>{flow.label ?? ''}</Typography>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t(`processes.dfdDir.${flow.direction}`)}</Typography>
          </Box>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.draw.removeHelp')}</Typography>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button color="warning" variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>
          {t('processes.draw.remove')}</Button>
      </DialogActions>
    </Dialog>
  );
}
