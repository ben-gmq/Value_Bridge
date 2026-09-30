import { useCallback, useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Handle, MarkerType, Position, useNodesState, useStore } from '@xyflow/react';
import { Alert, Box, Button, Stack, Table, TableBody, TableCell, TableHead, TableRow, ToggleButton,
  ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { errorText } from '../../api/client';
import { dfdApi, layoutApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { ModelCanvas } from '../../canvas/ModelCanvas';
import { LAYERED_RIGHT, LOW_ZOOM, elkLayout, pushClear } from '../../canvas/layout';
import { useLayoutSave } from '../../canvas/useLayoutSave';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { CopyMermaidButton } from '../../components/CopyMermaidButton';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { DiagramKindToggle, Mono } from './chartKit';

// The DFD of one parent node (design §7.2a generate_dfd, D-31; slice 3a). A picture of the step
// I/O without sequence, so there is nothing to edit here: a step's data is edited on the step.
const STEP = { w: 200, h: 72 };
const STORE = { w: 180, h: 76, rim: 9 };
const PARTY = { w: 150, h: 72 };
const DIAGRAM = 'DFD';
const stepNode = (id) => `s${id}`;
const storeNode = (id) => `d${id}`;
const partyNode = (id) => `x${id}`;

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
    <Box sx={(th) => ({ width: STEP.w, height: STEP.h, px: 1.5, py: 1, borderRadius: 2, border: 1.5,
      borderColor: th.vars.palette.primary.main, bgcolor: th.vars.palette.background.paper })}>
      <Ends />
      <Box sx={{ visibility: low ? 'hidden' : 'visible', height: '100%', overflow: 'hidden' }}>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}><Mono>{data.node.hier_code}</Mono></Typography>
        <Typography sx={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{data.node.node_name}</Typography>
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

const NODE_TYPES = { step: StepBox, store: StoreCylinder, party: PartySquare };

/** The far end of a flow: its store or its party. */
const farNode = (f) => (f.kind === 'STORE' ? storeNode(f.data_entity_id) : partyNode(f.external_entity_id));
const flowId = (f) => (f.kind === 'STORE' ? `io${f.bfc_node_data_entity_id}` : `xf${f.bfc_node_external_flow_id}`);

/** Graph → React Flow nodes and edges: ELK first, then saved positions, then push clear (§14.6). */
async function buildLayout(g, palette) {
  const cross = new Set(g.cross_area);
  const items = [
    ...g.processes.map((n) => ({ id: stepNode(n.bfc_node_id), type: 'step', data: { node: n }, ...STEP,
      object: { object_type: 'STEP', object_id: n.bfc_node_id } })),
    ...g.stores.map((s) => ({ id: storeNode(s.data_entity_id), type: 'store',
      data: { store: s, crossArea: cross.has(s.data_entity_id) }, ...STORE,
      object: { object_type: 'ENTITY', object_id: s.data_entity_id } })),
    ...g.externals.map((x) => ({ id: partyNode(x.external_entity_id), type: 'party', data: { party: x }, ...PARTY,
      object: { object_type: 'EXTERNAL', object_id: x.external_entity_id } })),
  ];
  // Direction is the step's point of view: I flows into the step, O flows out of it.
  const edges = g.flows.map((f) => {
    const into = f.direction === 'I';
    return {
      id: flowId(f), type: 'labelled', data: { flow: f }, interactionWidth: 16,
      source: into ? farNode(f) : stepNode(f.bfc_node_id), sourceHandle: 's-R',
      target: into ? stepNode(f.bfc_node_id) : farNode(f), targetHandle: 't-L',
      label: f.label ?? undefined,
      markerEnd: { type: MarkerType.ArrowClosed, color: palette.text.secondary },
      style: { stroke: palette.text.secondary, strokeWidth: 1.5 },
      labelBgStyle: { fill: palette.background.paper }, labelStyle: { fill: palette.text.primary, fontSize: 12 },
    };
  });
  const laid = await elkLayout({ id: 'root', layoutOptions: LAYERED_RIGHT,
    children: items.map((i) => ({ id: i.id, width: i.w, height: i.h })),
    edges: edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })) });
  const auto = new Map(laid.children.map((c) => [c.id, { x: c.x, y: c.y }]));
  // Saved positions win over auto-layout (D-30); every other box is pushed down clear of them.
  const saved = new Map(g.layout.map((p) => [`${p.object_type}:${p.object_id}`, p]));
  const clear = pushClear(items.map((i) => {
    const p = saved.get(`${i.object.object_type}:${i.object.object_id}`);
    return { id: i.id, ...(p ? { x: p.x, y: p.y } : auto.get(i.id)), w: i.w, h: i.h, pinned: Boolean(p) };
  }), { axis: 'y' });
  const nodes = items.map((i) => ({ id: i.id, type: i.type, position: clear.get(i.id),
    data: { ...i.data, object: i.object } }));
  return { nodes, edges };
}

/** One row per flow (criterion 9): from, to, data, kind. */
function DfdTable({ g }) {
  const step = new Map(g.processes.map((n) => [stepNode(n.bfc_node_id), `${n.hier_code} ${n.node_name}`]));
  const store = new Map(g.stores.map((s) => [storeNode(s.data_entity_id), `${s.de_number} ${s.de_name}`]));
  const party = new Map(g.externals.map((x) => [partyNode(x.external_entity_id), `${x.ext_number} ${x.ext_name}`]));
  const name = (id) => step.get(id) ?? store.get(id) ?? party.get(id) ?? id;
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>{t('processes.flowFrom')}</TableCell><TableCell>{t('processes.flowTo')}</TableCell>
          <TableCell>{t('processes.dfdFlowData')}</TableCell><TableCell>{t('processes.dfdFlowKind')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {g.flows.map((f) => {
            const [from, to] = f.direction === 'I' ? [farNode(f), stepNode(f.bfc_node_id)] : [stepNode(f.bfc_node_id), farNode(f)];
            return (
              <TableRow key={flowId(f)}>
                <TableCell>{name(from)}</TableCell><TableCell>{name(to)}</TableCell>
                <TableCell>{f.label ?? ''}</TableCell><TableCell>{t(`processes.dfdKind.${f.kind}`)}</TableCell>
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
  const [layoutError, setLayoutError] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const palette = theme.vars.palette;
  useEffect(() => {
    if (!g) return undefined;
    let live = true;
    buildLayout(g, palette).then((r) => { if (live) { setNodes(r.nodes); setEdges(r.edges); setLayoutError(''); } })
      .catch((err) => { if (live) setLayoutError(err.message); });
    return () => { live = false; };
  }, [g, palette, setNodes]);

  // As on the flow: positions save when a move ends, through the one shared hook (§14.6).
  // A REVIEWER places nothing (the hook ignores their moves).
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
    if (n.type === 'step') navigate(links.node(projectId, n.data.node.bfc_node_id));
  }, [navigate, projectId]);

  const title = g ? t('processes.dfdPageTitle', { name: `${g.scope.hier_code} ${g.scope.node_name}` }) : t('processes.dfdTitle');
  return (
    <Page title={title} subtitle={t('processes.dfdPageHelp')} error={q.error ? errorText(q.error) : ''}
      actions={(
        <>
          <Button component={RouterLink} to={links.node(projectId, nodeId)}>{t('processes.backToChart')}</Button>
          <CopyMermaidButton area="processes" disabled={!g} fetchText={() => dfdApi.mermaid(nodeId)} />
          {canEdit && (
            <Button color="warning" disabled={!g || reset.isPending}
              onClick={() => setConfirmReset(true)}>{t('processes.resetLayout')}</Button>)}
        </>)}>
      {layoutError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setLayoutError('')}>{layoutError}</Alert>}
      <Stack direction="row" spacing={2} useFlexGap sx={{ mb: 2, flexWrap: 'wrap' }}>
        <DiagramKindToggle projectId={projectId} nodeId={nodeId} current="dfd" />
        <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)}
          aria-label={t('processes.flowView')}>
          <ToggleButton value="diagram">{t('processes.viewDiagram')}</ToggleButton>
          <ToggleButton value="table">{t('processes.viewTable')}</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      {g && g.processes.length === 0 && <Alert severity="info">{t('processes.dfdNoSteps')}</Alert>}
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
