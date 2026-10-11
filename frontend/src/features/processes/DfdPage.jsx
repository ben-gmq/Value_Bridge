import { useCallback, useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Handle, MarkerType, Position, useNodesState, useStore } from '@xyflow/react';
import { Alert, Box, Button, Chip, FormControlLabel, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow,
  ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { errorText } from '../../api/client';
import { dfdApi, layoutApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { ModelCanvas } from '../../canvas/ModelCanvas';
import { LOW_ZOOM, pushClear } from '../../canvas/layout';
import { useLayoutSave } from '../../canvas/useLayoutSave';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { CopyMermaidButton } from '../../components/CopyMermaidButton';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { Mono } from './chartKit';

// The DFD of one parent node — the one process diagram (D-38, D-46, D-47, D-49; slice7_schema §9.8).
// Lanes are performers; a process sits in its lane at the column of its derived rank (order comes
// from the data: B follows A when B reads what A writes). Stores, parties and triggers sit in a band
// under the lanes. Nothing is edited here except where boxes stand: a step's facts are edited on the step.
const STEP = { w: 210, h: 84 };
const STORE = { w: 180, h: 76, rim: 9 };
const PARTY = { w: 150, h: 72 };
const TRIG = 56;
const LABEL_W = 170;
const COL_W = 290;
const LANE_PAD = 22;
const ROW_H = STEP.h + 28;
const DIAGRAM = 'DFD';
const stepNode = (id) => `s${id}`;
const storeNode = (id) => `d${id}`;
const partyNode = (id) => `x${id}`;
const trigNode = (id) => `t${id}`;

const useLowZoom = () => useStore((s) => s.transform[2] < LOW_ZOOM);

// Connectors are hidden: nothing is drawn by hand on a DFD. They stay mounted so edges attach.
const HIDDEN = { opacity: 0, pointerEvents: 'none' };
function Ends() {
  return (
    <>
      <Handle type="target" position={Position.Left} id="t-L" isConnectable={false} style={HIDDEN} />
      <Handle type="source" position={Position.Right} id="s-R" isConnectable={false} style={HIDDEN} />
    </>
  );
}

// Text is hidden with `visibility`, never `display: none`, so handle positions stay valid (§14.6).
function StepBox({ data }) {
  const low = useLowZoom();
  return (
    <Box sx={(th) => ({ position: 'relative', width: STEP.w, height: STEP.h, px: 1.5, py: 1, borderRadius: 2, border: 1.5,
      borderColor: th.vars.palette.primary.main, bgcolor: th.vars.palette.background.paper })}>
      <Ends />
      <Box sx={{ visibility: low ? 'hidden' : 'visible', height: '100%', overflow: 'hidden' }}>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}><Mono>{data.node.hier_code}</Mono></Typography>
        <Typography sx={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{data.node.node_name}</Typography>
        {data.node.systems.length > 0 && (
          <Typography sx={{ fontSize: 11, color: 'text.secondary', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
            {data.node.systems.map((a) => a.application_code).join(' · ')}</Typography>)}
      </Box>
      {data.gap && (
        <Tooltip title={t('processes.dfdGapHelp')}>
          <Box component="span" sx={(th) => ({ position: 'absolute', top: -10, right: -8, px: 0.75, borderRadius: 999,
            fontSize: 10.5, fontWeight: 700, lineHeight: '18px', color: th.vars.palette.warning.main,
            bgcolor: th.vars.palette.background.paper, border: 1.5, borderColor: th.vars.palette.warning.main })}>
            {t('processes.dfdGap')}</Box>
        </Tooltip>)}
    </Box>
  );
}

function TriggerDot({ data }) {
  const low = useLowZoom();
  return (
    <Tooltip title={data.trigger.schedule_note ? `${data.trigger.trigger_name} — ${data.trigger.schedule_note}` : data.trigger.trigger_name}>
      <Box aria-label={t('processes.dfdTrigger')} sx={(th) => ({ width: TRIG, height: TRIG, borderRadius: '50%', border: 2,
        borderStyle: data.trigger.trigger_kind === 'TIME' ? 'double' : 'solid', borderColor: th.vars.palette.text.primary,
        bgcolor: th.vars.palette.background.paper, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 0.5 })}>
        <Ends />
        <Typography sx={{ fontSize: 9.5, fontWeight: 700, textAlign: 'center', lineHeight: 1.1, overflow: 'hidden',
          visibility: low ? 'hidden' : 'visible', maxHeight: TRIG - 12 }}>{data.trigger.trigger_name}</Typography>
      </Box>
    </Tooltip>
  );
}

function LaneBand({ data }) {
  const low = useLowZoom();
  return (
    <Box sx={(th) => ({ width: data.width, height: data.height, borderTop: 1, borderBottom: 1,
      borderColor: th.vars.palette.divider, bgcolor: data.shade ? th.vars.palette.background.subtle : 'transparent' })}>
      <Box sx={(th) => ({ width: LABEL_W - 16, height: '100%', p: 1, borderRight: 1, borderColor: th.vars.palette.divider,
        visibility: low ? 'hidden' : 'visible' })}>
        <Typography sx={{ fontSize: 10.5, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 0.6 }}>{data.kind}</Typography>
        <Typography sx={{ fontSize: 12.5, fontWeight: 700 }}>{data.title}</Typography>
        {data.subtitle && <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>{data.subtitle}</Typography>}
      </Box>
    </Box>
  );
}

/** A data store as a cylinder: an SVG body and rim in the data-entity teal. */
function StoreCylinder({ data }) {
  const low = useLowZoom();
  const { w, h, rim } = STORE;
  const rx = w / 2;
  return (
    <Box sx={{ position: 'relative', width: w, height: h }} aria-label={t('processes.dfdStore')}>
      <Box component="svg" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden
        sx={(th) => ({ position: 'absolute', inset: 0, overflow: 'visible',
          '& path, & ellipse': { fill: th.vars.palette.background.paper, stroke: th.vars.palette.brand.teal, strokeWidth: 1.5 } })}>
        <path d={`M0 ${rim} L0 ${h - rim} A ${rx} ${rim} 0 0 0 ${w} ${h - rim} L${w} ${rim}`} />
        <ellipse cx={rx} cy={rim} rx={rx} ry={rim} />
      </Box>
      <Ends />
      <Box sx={{ position: 'absolute', inset: 0, pt: `${rim * 2 + 2}px`, px: 1.5, overflow: 'hidden',
        visibility: low ? 'hidden' : 'visible', textAlign: 'center' }}>
        <Typography sx={(th) => ({ fontSize: 11, color: th.vars.palette.brand.tealText })}><Mono>{data.store.de_number}</Mono></Typography>
        <Typography sx={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2, overflow: 'hidden', whiteSpace: 'nowrap',
          textOverflow: 'ellipsis' }}>{data.store.de_name}</Typography>
      </Box>
      {data.crossArea && (
        <Tooltip title={t('processes.dfdCrossAreaHelp')}>
          <Box component="span" sx={(th) => ({ position: 'absolute', top: -10, right: -8, px: 0.75, borderRadius: 999,
            fontSize: 10.5, fontWeight: 700, lineHeight: '18px', color: th.vars.palette.brand.tealText,
            bgcolor: th.vars.palette.background.paper, border: 1.5, borderColor: th.vars.palette.brand.tealText })}>
            {t('processes.dfdCrossArea')}</Box>
        </Tooltip>
      )}
    </Box>
  );
}

function PartySquare({ data }) {
  const low = useLowZoom();
  return (
    <Box aria-label={t('processes.dfdParty')} sx={(th) => ({ width: PARTY.w, height: PARTY.h, px: 1.25, py: 1, border: 4,
      borderColor: th.vars.palette.text.primary, bgcolor: th.vars.palette.background.subtle })}>
      <Ends />
      <Box sx={{ visibility: low ? 'hidden' : 'visible', height: '100%', overflow: 'hidden' }}>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}><Mono>{data.party.ext_number}</Mono></Typography>
        <Typography sx={{ fontSize: 13, fontWeight: 700, lineHeight: 1.2, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{data.party.ext_name}</Typography>
      </Box>
    </Box>
  );
}

const NODE_TYPES = { step: StepBox, store: StoreCylinder, party: PartySquare, trigger: TriggerDot, lane: LaneBand };

/** The far end of a flow: its store, its party or its trigger. */
const farNode = (f) => ({ STORE: storeNode(f.data_entity_id), EXTERNAL: partyNode(f.external_entity_id),
  TRIGGER: trigNode(f.process_trigger_id) }[f.kind]);
const flowId = (f, i) => `f${i}-${f.kind}-${f.bfc_node_id}-${f.direction}`;

const laneTitle = (lane) => (lane.kind === 'UNASSIGNED' ? t('processes.laneUnassigned')
  : lane.code ? `${lane.code} ${lane.name ?? ''}`.trim() : lane.name);

/** Graph → React Flow nodes and edges. Lanes are bands; a process stands at (its lane, its rank);
 * stores, parties and triggers stand in the band below, each under the steps it touches. Saved
 * positions win (D-30); every other box is pushed clear of them (§14.6). */
function buildLayout(g, palette, showOrder) {
  const gap = new Set([...g.completeness.missing_input, ...g.completeness.missing_output].map((r) => r.bfc_node_id));
  const nodes = [];
  let top = 0;
  const bands = [];
  const xOf = new Map();
  for (const lane of g.lanes) {
    const mine = g.processes.filter((p) => p.lane_key === lane.lane_key).sort((a, b) => a.rank - b.rank || a.hier_code.localeCompare(b.hier_code));
    const rowsAt = new Map();
    let rowsUsed = 1;
    for (const p of mine) {
      const r = rowsAt.get(p.rank) ?? 0;
      rowsAt.set(p.rank, r + 1);
      rowsUsed = Math.max(rowsUsed, r + 1);
      const x = LABEL_W + p.rank * COL_W;
      xOf.set(p.bfc_node_id, x);
      nodes.push({ id: stepNode(p.bfc_node_id), type: 'step', data: { node: p, gap: gap.has(p.bfc_node_id),
        object: { object_type: 'STEP', object_id: p.bfc_node_id } }, size: STEP,
        position: { x, y: top + LANE_PAD + r * ROW_H } });
    }
    const height = rowsUsed * ROW_H + LANE_PAD * 2 - (ROW_H - STEP.h);
    bands.push({ lane, top, height });
    top += height;
  }
  // The data band: each store, party and trigger under the mean column of the steps it touches.
  const touches = new Map();
  for (const f of g.flows) {
    const k = farNode(f);
    touches.set(k, [...(touches.get(k) ?? []), xOf.get(f.bfc_node_id) ?? LABEL_W]);
  }
  const at = (k) => { const xs = touches.get(k) ?? [LABEL_W]; return xs.reduce((a, b) => a + b, 0) / xs.length; };
  const dataTop = top + 40;
  const data = [
    ...g.triggers.map((x) => ({ id: trigNode(x.process_trigger_id), type: 'trigger', data: { trigger: x }, size: { w: TRIG, h: TRIG },
      object: { object_type: 'TRIGGER', object_id: x.process_trigger_id }, x: at(trigNode(x.process_trigger_id)) - TRIG - 30 })),
    ...g.externals.map((x) => ({ id: partyNode(x.external_entity_id), type: 'party', data: { party: x }, size: PARTY,
      object: { object_type: 'EXTERNAL', object_id: x.external_entity_id }, x: at(partyNode(x.external_entity_id)) })),
    ...g.stores.map((s) => ({ id: storeNode(s.data_entity_id), type: 'store', data: { store: s, crossArea: g.cross_area.includes(s.data_entity_id) },
      size: STORE, object: { object_type: 'ENTITY', object_id: s.data_entity_id }, x: at(storeNode(s.data_entity_id)) })),
  ];
  for (const d of data) {
    nodes.push({ id: d.id, type: d.type, data: { ...d.data, object: d.object }, size: d.size, position: { x: Math.max(LABEL_W, d.x), y: dataTop } });
  }
  const saved = new Map(g.layout.map((p) => [`${p.object_type}:${p.object_id}`, p]));
  const clear = pushClear(nodes.map((n) => {
    const p = saved.get(`${n.data.object.object_type}:${n.data.object.object_id}`);
    return { id: n.id, ...(p ? { x: p.x, y: p.y } : n.position), w: n.size.w, h: n.size.h, pinned: Boolean(p) };
  }), { axis: 'x' });
  let maxX = 0;
  for (const n of nodes) { n.position = clear.get(n.id); maxX = Math.max(maxX, n.position.x + n.size.w); delete n.size; }
  const lanes = bands.map(({ lane, top: y, height }, i) => ({
    id: `lane-${lane.lane_key}`, type: 'lane', position: { x: 0, y }, draggable: false, selectable: false,
    connectable: false, focusable: false, zIndex: -1,
    data: { kind: t(`processes.performer.kind.${lane.kind}`), title: laneTitle(lane), subtitle: lane.unit_name,
      width: maxX + 80, height, shade: i % 2 === 1 } }));

  const style = { stroke: palette.text.secondary, strokeWidth: 1.5 };
  const edges = g.flows.map((f, i) => {
    const into = f.direction === 'I';
    return {
      id: flowId(f, i), type: 'labelled', data: { flow: f }, interactionWidth: 16,
      source: into ? farNode(f) : stepNode(f.bfc_node_id), sourceHandle: 's-R',
      target: into ? stepNode(f.bfc_node_id) : farNode(f), targetHandle: 't-L',
      label: f.kind === 'TRIGGER' ? undefined : f.label ?? undefined,
      markerEnd: { type: MarkerType.ArrowClosed, color: palette.text.secondary }, style,
      labelBgStyle: { fill: palette.background.paper }, labelStyle: { fill: palette.text.primary, fontSize: 12 },
    };
  });
  if (showOrder) {
    // The derived order (D-38), dashed: never stored, drawn on request.
    g.order.forEach((o, i) => edges.push({ id: `o${i}`, type: 'labelled', source: stepNode(o.from_bfc_node_id), sourceHandle: 's-R',
      target: stepNode(o.to_bfc_node_id), targetHandle: 't-L', interactionWidth: 8,
      markerEnd: { type: MarkerType.ArrowClosed, color: palette.primary.main },
      style: { stroke: palette.primary.main, strokeWidth: 1.25, strokeDasharray: '6 4', opacity: 0.8 } }));
  }
  return { nodes: [...lanes, ...nodes], edges };
}

/** One row per flow (criterion 9): from, to, data, kind. */
function DfdTable({ g }) {
  const step = new Map(g.processes.map((n) => [stepNode(n.bfc_node_id), `${n.hier_code} ${n.node_name}`]));
  const store = new Map(g.stores.map((s) => [storeNode(s.data_entity_id), `${s.de_number} ${s.de_name}`]));
  const party = new Map(g.externals.map((x) => [partyNode(x.external_entity_id), `${x.ext_number} ${x.ext_name}`]));
  const trig = new Map(g.triggers.map((x) => [trigNode(x.process_trigger_id), x.trigger_name]));
  const lane = new Map(g.lanes.map((l) => [l.lane_key, laneTitle(l)]));
  const laneOf = new Map(g.processes.map((p) => [stepNode(p.bfc_node_id), lane.get(p.lane_key)]));
  const name = (id) => step.get(id) ?? store.get(id) ?? party.get(id) ?? trig.get(id) ?? id;
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>{t('processes.flowFrom')}</TableCell><TableCell>{t('processes.flowTo')}</TableCell>
          <TableCell>{t('processes.dfdFlowData')}</TableCell><TableCell>{t('processes.dfdFlowKind')}</TableCell>
          <TableCell>{t('processes.dfdLane')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {g.flows.map((f, i) => {
            const [from, to] = f.direction === 'I' ? [farNode(f), stepNode(f.bfc_node_id)] : [stepNode(f.bfc_node_id), farNode(f)];
            return (
              <TableRow key={flowId(f, i)}>
                <TableCell>{name(from)}</TableCell><TableCell>{name(to)}</TableCell>
                <TableCell>{f.kind === 'TRIGGER' ? '' : f.label ?? ''}</TableCell><TableCell>{t(`processes.dfdKind.${f.kind}`)}</TableCell>
                <TableCell>{laneOf.get(stepNode(f.bfc_node_id)) ?? ''}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

/** The data flow diagram of one parent node, on the shared canvas. Read-only apart from placing boxes. */
export default function DfdPage() {
  const { projectId, nodeId } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const theme = useTheme();
  const canEdit = useCanEdit();
  const graphKey = keys.dfdGraph(projectId, nodeId);
  const q = useQuery({ queryKey: graphKey, queryFn: () => dfdApi.graph(nodeId) });
  const g = q.data;
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges] = useState([]);
  const [view, setView] = useState('diagram');
  const [showOrder, setShowOrder] = useState(false);
  const [layoutError, setLayoutError] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const palette = theme.vars.palette;
  useEffect(() => {
    if (!g) return undefined;
    let live = true;
    Promise.resolve().then(() => buildLayout(g, palette, showOrder))
      .then((r) => { if (live) { setNodes(r.nodes); setEdges(r.edges); setLayoutError(''); } })
      .catch((err) => { if (live) setLayoutError(err.message); });
    return () => { live = false; };
  }, [g, palette, setNodes, showOrder]);

  // As on the flow: positions save when a move ends, through the one shared hook (§14.6).
  // A read-only user places nothing (the hook ignores their moves).
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const layout = useLayoutSave({
    projectId, diagramType: DIAGRAM, scopeKey: nodeId, canEdit,
    getNode: (id) => nodesRef.current.find((n) => n.id === id),
    toItem: (n) => (n.data?.object && n.position
      ? { ...n.data.object, x: Math.round(n.position.x), y: Math.round(n.position.y) } : null),
    onError: (err) => setLayoutError(errorText(err, t('common.saveFailed'))),
  });
  const handleNodesChange = useCallback((changes) => {
    onNodesChange(changes);
    layout.onChanges(changes);
  }, [onNodesChange, layout]);

  const reset = useMutation({
    mutationFn: () => layoutApi.reset(projectId, DIAGRAM, nodeId),
    onMutate: () => layout.discard(),           // a queued move must not re-pin after the reset (sara L3)
    onSuccess: () => { setConfirmReset(false); qc.invalidateQueries({ queryKey: graphKey }); },
    onError: (err) => { setConfirmReset(false); setLayoutError(errorText(err, t('common.saveFailed'))); },
  });

  // A step opens in the chart, where its data in and out is edited (spec 3a: no editing here).
  const onNodeClick = useCallback((_, n) => {
    if (n.type === 'step') navigate(links.node(projectId, n.data.node.bfc_node_id, n.data.node.bfc_set_code));
  }, [navigate, projectId]);

  const title = g ? t('processes.dfdPageTitle', { name: `${g.scope.hier_code} ${g.scope.node_name}` }) : t('processes.dfdTitle');
  // Steps with a gap, each counted once (UAT 7c: a step missing both is one step).
  const gaps = g ? new Set([...g.completeness.missing_input, ...g.completeness.missing_output].map((r) => r.bfc_node_id)).size : 0;
  return (
    <Page title={title} subtitle={t('processes.dfdPageHelp')} error={q.error ? errorText(q.error) : ''}
      actions={(
        <>
          <Button component={RouterLink} to={links.node(projectId, nodeId, g?.scope.bfc_set_code)}>{t('processes.backToChart')}</Button>
          <CopyMermaidButton area="processes" disabled={!g} fetchText={() => dfdApi.mermaid(nodeId, showOrder)} />
          {canEdit && (
            <Button color="warning" disabled={!g || reset.isPending}
              onClick={() => setConfirmReset(true)}>{t('processes.resetLayout')}</Button>)}
        </>)}>
      {layoutError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setLayoutError('')}>{layoutError}</Alert>}
      <Stack direction="row" spacing={2} useFlexGap sx={{ mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        {g && <Chip label={t(`processes.chart.${g.scope.bfc_set_code}`)} variant="outlined" />}
        <FormControlLabel label={t('processes.dfdShowOrder')}
          control={<Switch id="dfd-order" checked={showOrder} onChange={(e) => setShowOrder(e.target.checked)} />} />
        <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)}
          aria-label={t('processes.flowView')}>
          <ToggleButton value="diagram">{t('processes.viewDiagram')}</ToggleButton>
          <ToggleButton value="table">{t('processes.viewTable')}</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      {g && g.processes.length === 0 && <Alert severity="info">{t('processes.dfdNoSteps')}</Alert>}
      {gaps > 0 && <Alert severity="warning" sx={{ mb: 2 }}>{t('processes.dfdGapsAlert', { n: gaps })}</Alert>}
      {g && g.processes.length > 0 && g.flows.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>{t('processes.dfdNoFlows')}</Alert>)}
      {g && g.processes.length > 0 && view === 'diagram' && (
        <>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1 }}>
            {t(canEdit ? 'processes.dfdCanvasHelp' : 'processes.dfdCanvasHelpReadOnly')} {t('processes.dfdLegend')}</Typography>
          <ModelCanvas kind="dfd" nodes={nodes} edges={edges} nodeTypes={NODE_TYPES}
            draggable={canEdit} onNodesChange={handleNodesChange} onNodeClick={onNodeClick} ariaLabel={title} />
        </>
      )}
      {g && g.processes.length > 0 && view === 'table' && <DfdTable g={g} />}
      <ConfirmDialog open={confirmReset} title={t('processes.resetLayoutTitle')} body={t('processes.resetLayoutBody')}
        confirmLabel={t('processes.resetLayout')} busy={reset.isPending}
        onClose={() => setConfirmReset(false)} onConfirm={() => reset.mutate()} />
    </Page>
  );
}
