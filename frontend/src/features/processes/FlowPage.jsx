import { useCallback, useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Handle, MarkerType, Position, useNodesState, useStore } from '@xyflow/react';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Table, TextField, TableBody, TableCell, TableHead, TableRow, ToggleButton,
  ToggleButtonGroup, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { errorText } from '../../api/client';
import { bfcApi, flowApi, layoutApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { ModelCanvas } from '../../canvas/ModelCanvas';
import { LAYERED_RIGHT, LOW_ZOOM, elkLayout, pushClear } from '../../canvas/layout';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, Mono } from './chartKit';
import { EdgeDialog } from './FlowSections';

const BOX = { w: 200, h: 72 };
const EVENT = 36;
const LANE_PAD = 24;
const ROW_H = BOX.h + 32;
const LABEL_W = 150;
const UNASSIGNED = 'none';
const OUTSIDE = 'outside';
const stepId = (id) => `s${id}`;
const eventId = (flowId) => `e${flowId}`;

const useLowZoom = () => useStore((s) => s.transform[2] < LOW_ZOOM);

/** The canvas node under the pointer where a drag was released, if any. */
function nodeUnder(event) {
  const pt = event?.changedTouches?.[0] ?? event;
  if (pt?.clientX == null) return null;
  return document.elementFromPoint(pt.clientX, pt.clientY)?.closest('.react-flow__node')?.getAttribute('data-id') ?? null;
}

// Text is hidden with `visibility`, never `display: none`, so handle positions stay valid (§14.6).
function StepBox({ data }) {
  const low = useLowZoom();
  return (
    <Box sx={(th) => ({ width: BOX.w, height: BOX.h, px: 1.5, py: 1, borderRadius: 2,
      border: 1.5, borderStyle: data.outside ? 'dashed' : 'solid',
      borderColor: data.outside ? th.vars.palette.brand.lineStrong : th.vars.palette.primary.main,
      bgcolor: th.vars.palette.background.paper })}>
      <Handle type="target" position={Position.Left} id="t-L" />
      {/* The text clips, not the box: the connectors sit half outside its edge. */}
      <Box sx={{ visibility: low ? 'hidden' : 'visible', height: '100%', overflow: 'hidden' }}>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
          <Mono>{data.node.hier_code}</Mono>{data.node.br_number ? ` · ${data.node.br_number}` : ''}
          {data.outside ? ` · ${t('processes.flowOutside')}` : ''}</Typography>
        <Typography sx={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{data.node.node_name}</Typography>
      </Box>
      <Handle type="source" position={Position.Right} id="s-R" />
    </Box>
  );
}

function EventDot({ data }) {
  return (
    <Box title={t(data.start ? 'processes.flowStart' : 'processes.flowEnd')}
      sx={(th) => ({ width: EVENT, height: EVENT, borderRadius: '50%', bgcolor: th.vars.palette.background.paper,
        border: data.start ? 2 : 4, borderColor: th.vars.palette.text.primary })}>
      {data.start ? <Handle type="source" position={Position.Right} id="s-R" isConnectable={false} style={{ opacity: 0 }} />
        : <Handle type="target" position={Position.Left} id="t-L" isConnectable={false} style={{ opacity: 0 }} />}
    </Box>
  );
}

function LaneBand({ data }) {
  const low = useLowZoom();
  return (
    <Box sx={(th) => ({ width: data.width, height: data.height, borderTop: 1, borderBottom: 1,
      borderColor: th.vars.palette.divider, bgcolor: data.shade ? th.vars.palette.background.subtle : 'transparent' })}>
      <Box sx={(th) => ({ width: LABEL_W - 16, height: '100%', p: 1, borderRight: 1, borderColor: th.vars.palette.divider,
        visibility: low ? 'hidden' : 'visible' })}>
        <Typography sx={{ fontSize: 12.5, fontWeight: 700 }}>{data.title}</Typography>
        {data.subtitle && <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>{data.subtitle}</Typography>}
      </Box>
    </Box>
  );
}

const NODE_TYPES = { step: StepBox, event: EventDot, lane: LaneBand };

/** Graph → React Flow nodes and edges, with lanes as background bands (§7.2a, A-46). */
async function buildLayout(g, palette) {
  const laneOf = new Map(g.nodes.map((n) => [n.bfc_node_id, n.lane_org_role_id ?? UNASSIGNED]));
  g.outside.forEach((n) => laneOf.set(n.bfc_node_id, OUTSIDE));
  const bands = [...g.lanes.map((l) => ({ key: l.org_role_id, title: l.org_role_name, subtitle: l.org_unit_name }))];
  if (g.nodes.some((n) => n.lane_org_role_id == null)) bands.push({ key: UNASSIGNED, title: t('processes.laneUnassigned') });
  if (g.outside.length) bands.push({ key: OUTSIDE, title: t('processes.laneOutside') });

  const items = [
    ...g.nodes.map((n) => ({ id: stepId(n.bfc_node_id), type: 'step', data: { node: n }, lane: laneOf.get(n.bfc_node_id),
      w: BOX.w, h: BOX.h, object: { object_type: 'STEP', object_id: n.bfc_node_id } })),
    ...g.outside.map((n) => ({ id: stepId(n.bfc_node_id), type: 'step', data: { node: n, outside: true }, lane: OUTSIDE,
      w: BOX.w, h: BOX.h, object: { object_type: 'STEP', object_id: n.bfc_node_id } })),
  ];
  const edges = [];
  for (const e of g.edges) {
    const start = e.from_bfc_node_id == null;
    const end = e.to_bfc_node_id == null;
    if (start || end) {
      const anchor = start ? e.to_bfc_node_id : e.from_bfc_node_id;
      items.push({ id: eventId(e.bfc_node_flow_id), type: 'event', data: { start }, lane: laneOf.get(anchor),
        w: EVENT, h: EVENT, object: { object_type: 'EVENT', object_id: e.bfc_node_flow_id } });
    }
    const dashed = e.flow_type === 'HANDOFF';
    edges.push({
      id: `f${e.bfc_node_flow_id}`, type: 'labelled', data: { flow: e }, interactionWidth: 24,
      source: start ? eventId(e.bfc_node_flow_id) : stepId(e.from_bfc_node_id), sourceHandle: 's-R',
      target: end ? eventId(e.bfc_node_flow_id) : stepId(e.to_bfc_node_id), targetHandle: 't-L',
      label: e.condition_label ?? undefined,
      markerEnd: { type: MarkerType.ArrowClosed, color: palette.text.secondary },
      style: { stroke: palette.text.secondary, strokeWidth: 1.5, strokeDasharray: dashed ? '6 4' : undefined },
      labelBgStyle: { fill: palette.background.paper }, labelStyle: { fill: palette.text.primary, fontSize: 12 },
    });
  }

  const laid = await elkLayout({ id: 'root', layoutOptions: LAYERED_RIGHT,
    children: items.map((i) => ({ id: i.id, width: i.w, height: i.h })),
    edges: edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })) });
  const xOf = new Map(laid.children.map((c) => [c.id, c.x]));

  // Keep ELK's left-to-right order; stack within a lane where two items would overlap.
  const nodes = [];
  let top = 0;
  const bandTops = [];
  for (const band of bands) {
    const mine = items.filter((i) => i.lane === band.key).sort((a, b) => xOf.get(a.id) - xOf.get(b.id));
    const rows = [];
    for (const i of mine) {
      const x = LABEL_W + xOf.get(i.id);
      let r = rows.findIndex((right) => right + 24 <= x);
      if (r < 0) { r = rows.length; rows.push(0); }
      rows[r] = x + i.w;
      nodes.push({ id: i.id, type: i.type, data: { ...i.data, object: i.object }, size: { w: i.w, h: i.h },
        position: { x, y: top + LANE_PAD + r * ROW_H + (BOX.h - i.h) / 2 } });
    }
    const height = Math.max(1, rows.length) * ROW_H + LANE_PAD * 2 - (ROW_H - BOX.h);
    bandTops.push({ band, top, height });
    top += height;
  }
  // Saved positions win over auto-layout (D-30): what a consultant placed stays placed. Every
  // other box is pushed right, clear of it, inside its own lane (§14.6, sara L7).
  const saved = new Map(g.layout.map((p) => [`${p.object_type}:${p.object_id}`, p]));
  const boxes = nodes.map((n) => {
    const p = saved.get(`${n.data.object.object_type}:${n.data.object.object_id}`);
    const at = p ? { x: p.x, y: p.y } : n.position;
    return { id: n.id, ...at, w: n.size.w, h: n.size.h, pinned: Boolean(p) };
  });
  const clear = pushClear(boxes, { axis: 'x' });
  let maxX = 0;
  for (const n of nodes) {
    n.position = clear.get(n.id);
    maxX = Math.max(maxX, n.position.x + n.size.w);
    delete n.size;
  }
  const lanes = bandTops.map(({ band, top: y, height }, i) => ({
    id: `lane-${band.key}`, type: 'lane', position: { x: 0, y }, draggable: false, selectable: false,
    connectable: false, focusable: false, zIndex: -1,
    data: { title: band.title, subtitle: band.subtitle, width: maxX + 80, height, shade: i % 2 === 1 } }));
  return { nodes: [...lanes, ...nodes], edges };
}

function FlowTable({ g }) {
  const name = (id, fallback) => {
    if (id == null) return t(fallback);
    const n = g.nodes.find((x) => x.bfc_node_id === id) ?? g.outside.find((x) => x.bfc_node_id === id);
    return n ? `${n.hier_code} ${n.node_name}` : `#${id}`;
  };
  const lane = (id) => g.lanes.find((l) => l.org_role_id === id)?.org_role_name ?? t('processes.laneUnassigned');
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Typography component="h2" variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>{t('processes.tableSteps')}</Typography>
      <Table size="small" sx={{ mb: 3 }}>
        <TableHead><TableRow>
          <TableCell>{t('processes.code')}</TableCell><TableCell>{t('processes.name')}</TableCell>
          <TableCell>{t('processes.tableLane')}</TableCell><TableCell>{t('processes.tableBr')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {g.nodes.map((n) => (
            <TableRow key={n.bfc_node_id}>
              <TableCell><Mono>{n.hier_code}</Mono></TableCell><TableCell>{n.node_name}</TableCell>
              <TableCell>{lane(n.lane_org_role_id)}</TableCell><TableCell>{n.br_number ?? ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Typography component="h2" variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>{t('processes.tableFlows')}</Typography>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>{t('processes.flowFrom')}</TableCell><TableCell>{t('processes.flowTo')}</TableCell>
          <TableCell>{t('processes.flowType')}</TableCell><TableCell>{t('processes.condition')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {g.edges.map((e) => (
            <TableRow key={e.bfc_node_flow_id}>
              <TableCell>{name(e.from_bfc_node_id, 'processes.flowStart')}</TableCell>
              <TableCell>{name(e.to_bfc_node_id, 'processes.flowEnd')}</TableCell>
              <TableCell>{t(`processes.flowType.${e.flow_type}`)}</TableCell>
              <TableCell sx={{ whiteSpace: 'pre-wrap' }}>{e.condition_label ?? ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

/** A box's pop-up: rename the step, retire it, or open it in the chart. Retire names its
 * blockers (the requirement, flows, step data) rather than cascading — nothing cascades (§7.12). */
function StepDialog({ projectId, stepId, onClose, onDone }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: keys.node(stepId), queryFn: () => bfcApi.get(stepId) });
  const step = q.data;
  const [name, setName] = useState(null);
  const [error, setError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);
  const shown = name ?? step?.node_name ?? '';
  const done = (row) => { if (row) qc.setQueryData(keys.node(stepId), row); qc.invalidateQueries({ queryKey: keys.node(stepId) }); onDone(); };
  const fail = (err) => { done(); setConfirmRetire(false); setError(errorText(err, t('common.saveFailed'))); };
  const rename = useMutation({
    mutationFn: () => bfcApi.update(stepId, { row_version: step.row_version, node_name: shown.trim() }),
    onSuccess: (row) => { done(row); onClose(); },
    onError: fail,
  });
  const retire = useMutation({
    mutationFn: () => bfcApi.retire(stepId, step.row_version),
    onSuccess: () => { done(); onClose(); },
    onError: fail,
  });
  const busy = rename.isPending || retire.isPending;
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{step ? t('processes.stepTitle', { code: step.hier_code }) : t('processes.loading')}</DialogTitle>
      <DialogContent>
        {(error || q.error) && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error || errorText(q.error)}</Alert>}
        {step && (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField id="flow-step-name" label={t('processes.name')} required value={shown}
              onChange={(e) => setName(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
            <Button component={RouterLink} to={links.node(projectId, stepId)} sx={{ alignSelf: 'flex-start' }}>
              {t('processes.openInChart')}</Button>
            {confirmRetire && (
              <Alert severity="warning" action={(
                <Button color="warning" size="small" disabled={busy} onClick={() => retire.mutate()}>
                  {t('processes.retire')}</Button>)}>{t('processes.retireStepConfirm')}</Alert>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {step && !confirmRetire && (
          <Button color="warning" disabled={busy} onClick={() => setConfirmRetire(true)} sx={{ mr: 'auto' }}>
            {t('processes.retire')}</Button>
        )}
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!step || !shown.trim() || shown.trim() === step.node_name || busy}
          onClick={() => { setError(''); rename.mutate(); }}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/** A new process step under the node this flow is drawn for — the chart's own create (§7.2). */
function AddStepDialog({ projectId, parentId, onDone, onClose }) {
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => bfcApi.create(projectId, { parent_bfc_node_id: parentId, node_name: name.trim(), is_process: true }),
    onSuccess: (row) => { onDone(row); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('processes.addStepTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="flow-add-step" label={t('processes.name')} required autoFocus value={name}
            onChange={(e) => setName(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }}
            onKeyDown={(e) => { if (e.key === 'Enter' && name.trim() && !m.isPending) m.mutate(); }} />
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.addStepHelp')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!name.trim() || m.isPending}
          onClick={() => { setError(''); m.mutate(); }}>{t('processes.add')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/** The process flow of one parent node: a view of the chart (S1-9), drawn on the shared canvas. */
export default function FlowPage() {
  const { projectId, nodeId } = useParams();
  const qc = useQueryClient();
  const theme = useTheme();
  const canEdit = useCanEdit();
  const graphKey = keys.flowGraph(projectId, nodeId);
  const q = useQuery({ queryKey: graphKey, queryFn: () => flowApi.graph(nodeId) });
  const g = q.data;
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges] = useState([]);
  const [view, setView] = useState('diagram');
  const [layoutError, setLayoutError] = useState('');
  const [connecting, setConnecting] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [addingStep, setAddingStep] = useState(false);
  const [stepOpen, setStepOpen] = useState(null);
  const scopeQ = useQuery({ queryKey: keys.node(nodeId), queryFn: () => bfcApi.get(nodeId) });
  // A step sits at level 3–5 (A-47), so a level-1 area takes its steps through a level-2 child.
  const canAddStep = canEdit && Boolean(scopeQ.data?.is_active && scopeQ.data.level_no >= FIRST_PROCESS_LEVEL - 1);
  const refreshAll = useCallback(() => {
    for (const k of [keys.flows(projectId), keys.tree(projectId), keys.flowGaps(projectId), keys.brs(projectId)]) {
      qc.invalidateQueries({ queryKey: k });
    }
  }, [qc, projectId]);
  const pendingSave = useRef(new Map());
  const timer = useRef(null);

  const palette = theme.vars.palette;
  useEffect(() => {
    if (!g) return undefined;
    let live = true;
    buildLayout(g, palette).then((r) => { if (live) { setNodes(r.nodes); setEdges(r.edges); setLayoutError(''); } })
      .catch((err) => { if (live) setLayoutError(err.message); });
    return () => { live = false; };
  }, [g, palette, setNodes]);

  const save = useMutation({
    mutationFn: (items) => layoutApi.save(projectId, 'PROCESS_FLOW', nodeId, items),
    onError: (err) => setLayoutError(errorText(err, t('common.saveFailed'))),
  });
  // Positions save when a move ends — a mouse drag or arrow keys — debounced (§14.6); last write
  // wins per object (A-52). A move still pending when the page closes is sent, not dropped.
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const flush = useCallback(() => {
    clearTimeout(timer.current);
    const items = [...pendingSave.current.values()];
    pendingSave.current.clear();
    return items;
  }, []);
  const handleNodesChange = useCallback((changes) => {
    onNodesChange(changes);
    let moved = false;
    for (const c of changes) {
      if (c.type !== 'position' || c.dragging) continue;
      const n = nodesRef.current.find((x) => x.id === c.id);
      const pos = c.position ?? n?.position;
      if (!n?.data?.object || !pos) continue;
      pendingSave.current.set(n.id, { ...n.data.object, x: Math.round(pos.x), y: Math.round(pos.y) });
      moved = true;
    }
    if (!moved) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const items = flush();
      if (items.length) save.mutate(items);
    }, 600);
  }, [onNodesChange, flush, save]);
  useEffect(() => () => {
    const items = flush();
    if (items.length) {
      layoutApi.save(projectId, 'PROCESS_FLOW', nodeId, items)
        .catch((err) => console.error('Diagram positions not saved on leaving the page', err));
    }
  }, [flush, projectId, nodeId]);

  const reset = useMutation({
    mutationFn: () => layoutApi.reset(projectId, 'PROCESS_FLOW', nodeId),
    onSuccess: () => { setConfirmReset(false); qc.invalidateQueries({ queryKey: graphKey }); },
    onError: (err) => { setConfirmReset(false); setLayoutError(errorText(err, t('common.saveFailed'))); },
  });

  const onConnect = useCallback(({ source, target }) => {
    if (!source?.startsWith('s') || !target?.startsWith('s')) return;
    setConnecting({ ends: { from_bfc_node_id: Number(source.slice(1)), to_bfc_node_id: Number(target.slice(1)) } });
  }, []);
  // A line dropped anywhere on a box connects to it, not only on its dot (Ben, 2026-09-30).
  const onConnectEnd = useCallback((event, state) => {
    if (state.isValid || !state.fromNode) return;             // onConnect already has it
    const over = nodeUnder(event);
    if (!over || over === state.fromNode.id) return;
    const [from, to] = state.fromHandle?.type === 'target' ? [over, state.fromNode.id] : [state.fromNode.id, over];
    onConnect({ source: from, target: to });
  }, [onConnect]);
  // A click opens the pop-up: an arrow's flow dialog, or a box's step dialog (Ben, 2026-09-30).
  const onEdgeClick = useCallback((_, edge) => { if (edge.data?.flow) setConnecting({ edge: edge.data.flow }); }, []);
  const onNodeClick = useCallback((_, n) => { if (n.type === 'step') setStepOpen(n.data.node.bfc_node_id); }, []);
  // Dragging an arrow's end to another box re-points it: add the new flow, remove the old (S2-2).
  const onReconnectEnd = useCallback((event, edge, handleType, state) => {
    const flow = edge.data?.flow;
    const over = state?.isValid ? state.toNode?.id : nodeUnder(event);
    if (!flow || !over?.startsWith('s')) return;
    const moved = Number(over.slice(1));
    const ends = { from_bfc_node_id: flow.from_bfc_node_id, to_bfc_node_id: flow.to_bfc_node_id };
    const key = handleType === 'source' ? 'from_bfc_node_id' : 'to_bfc_node_id';
    if (ends[key] === moved) return;                            // dropped back where it was
    setConnecting({ edge: flow, ends: { ...ends, [key]: moved } });
  }, []);


  const title = g ? t('processes.flowPageTitle', { name: `${g.scope.hier_code} ${g.scope.node_name}` }) : t('processes.flowTitle');
  return (
    <Page title={title} subtitle={t('processes.flowPageHelp')} error={q.error ? errorText(q.error) : ''}
      actions={(
        <>
          <Button component={RouterLink} to={links.node(projectId, nodeId)}>{t('processes.backToChart')}</Button>
          {canAddStep && <Button variant="contained" onClick={() => setAddingStep(true)}>{t('processes.addStep')}</Button>}
          {canEdit && (
            <Button color="warning" disabled={!g || reset.isPending}
              onClick={() => setConfirmReset(true)}>{t('processes.resetLayout')}</Button>)}
        </>)}>
      {layoutError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setLayoutError('')}>{layoutError}</Alert>}
      <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)} sx={{ mb: 2 }}
        aria-label={t('processes.flowView')}>
        <ToggleButton value="diagram">{t('processes.viewDiagram')}</ToggleButton>
        <ToggleButton value="table">{t('processes.viewTable')}</ToggleButton>
      </ToggleButtonGroup>
      {g && g.nodes.length === 0 && <Alert severity="info">{t('processes.flowNoSteps')}</Alert>}
      {g && g.nodes.length > 0 && view === 'diagram' && (
        <>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1 }}>
            {t(canEdit ? 'processes.flowCanvasHelp' : 'processes.flowCanvasHelpReadOnly')}</Typography>
          <ModelCanvas kind="flow" nodes={nodes} edges={edges} nodeTypes={NODE_TYPES}
            connectable={canEdit} draggable={canEdit} onNodesChange={handleNodesChange}
            onConnect={onConnect} onConnectEnd={onConnectEnd} onReconnectEnd={onReconnectEnd}
            onEdgeClick={canEdit ? onEdgeClick : undefined} onNodeClick={canEdit ? onNodeClick : undefined}
            ariaLabel={title} />
        </>
      )}
      {g && g.nodes.length > 0 && view === 'table' && <FlowTable g={g} />}
      {connecting && (
        <EdgeDialog projectId={projectId} ends={connecting.ends} edge={connecting.edge}
          onClose={() => setConnecting(null)}
          onDone={refreshAll} />
      )}
      {stepOpen && (
        <StepDialog projectId={projectId} stepId={stepOpen} onClose={() => setStepOpen(null)} onDone={refreshAll} />
      )}
      {addingStep && (
        <AddStepDialog projectId={projectId} parentId={Number(nodeId)} onClose={() => setAddingStep(false)}
          onDone={refreshAll} />
      )}
      <ConfirmDialog open={confirmReset} title={t('processes.resetLayoutTitle')} body={t('processes.resetLayoutBody')}
        confirmLabel={t('processes.resetLayout')} busy={reset.isPending}
        onClose={() => setConfirmReset(false)} onConfirm={() => reset.mutate()} />
    </Page>
  );
}
