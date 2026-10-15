import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Handle, MarkerType, Position, useNodesState, useStore } from '@xyflow/react';
import { Alert, Box, Button, Divider, FormControlLabel, IconButton, Switch, Table, TableBody, TableCell, TableHead, TableRow,
  Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { errorText } from '../../api/client';
import { dfdApi, layoutApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { CanvasHeader, DiagramGrid, LegendSwatch, NodeFlag, nodeFrame, nodeHeader } from '../../canvas/CanvasChrome';
import { edgeLook } from '../../canvas/edges';
import { ModelCanvas } from '../../canvas/ModelCanvas';
import { LOW_ZOOM, pushClear } from '../../canvas/layout';
import { useLayoutSave } from '../../canvas/useLayoutSave';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { CopyMermaidButton } from '../../components/CopyMermaidButton';
import { Card, Code, ListRow, SectionLabel, Segmented, Status, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// The DFD of one parent node — the one process diagram (D-38, D-46, D-47, D-49; slice7_schema §9.8).
// Lanes are performers; a process sits in its lane at the column of its derived rank (order comes
// from the data: B follows A when B reads what A writes). Stores, parties and triggers sit in a band
// under the lanes. Nothing is edited here except where boxes stand: a step's facts are edited on the step.
// D-51: laid out as mockup 02 — the canvas card with counts and legend, and an inspector at the right.
const STEP = { w: 210, h: 84 };
const STORE = { w: 184, h: 52 };
const PARTY = { w: 156, h: 64 };
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

/** A step's gaps (the rule elements it misses), as the one short text its header shows. */
const gapText = (kinds) => (!kinds?.length ? null : kinds.length > 1 ? t('processes.dfdGap') : t(`processes.gap.${kinds[0]}`));

// Text is hidden with `visibility`, never `display: none`, so handle positions stay valid (§14.6).
function StepBox({ data, selected }) {
  const low = useLowZoom();
  const gap = gapText(data.gap);
  return (
    <Box sx={(th) => ({ ...nodeFrame(th, 'purple', { selected, warn: Boolean(data.gap) }), width: STEP.w, height: STEP.h,
      display: 'flex', flexDirection: 'column' })}>
      <Ends />
      <Box sx={(th) => ({ ...nodeHeader(th, 'purple', { selected }), height: 26, flexShrink: 0, px: 1.25, display: 'flex',
        alignItems: 'center', justifyContent: 'space-between', gap: 1, visibility: low ? 'hidden' : 'visible' })}>
        <Code tone="purple" sx={{ fontSize: 12, fontWeight: 600 }}>{data.node.hier_code}</Code>
        {gap ? (
          <Tooltip title={t('processes.dfdGapHelp')}>
            <Typography noWrap sx={(th) => ({ fontSize: 11, fontWeight: 700, color: th.vars.palette.warning.main })}>{gap}</Typography>
          </Tooltip>
        ) : data.node.br_number && <Code tone="muted" sx={{ fontSize: 11.5 }}>{data.node.br_number}</Code>}
      </Box>
      <Box sx={{ px: 1.25, py: 0.5, minHeight: 0, overflow: 'hidden', visibility: low ? 'hidden' : 'visible' }}>
        <Typography sx={{ fontSize: 13.5, fontWeight: 700, lineHeight: 1.25, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: data.node.systems.length ? 1 : 2, WebkitBoxOrient: 'vertical' }}>
          {data.node.node_name}</Typography>
        {data.node.systems.length > 0 && (
          <Typography noWrap sx={(th) => ({ fontSize: 11.5, color: th.vars.palette.brand.muted })}>
            {data.node.systems.map((a) => a.application_code).join(' · ')}</Typography>)}
      </Box>
    </Box>
  );
}

function TriggerDot({ data, selected }) {
  const low = useLowZoom();
  return (
    <Tooltip title={data.trigger.schedule_note ? `${data.trigger.trigger_name} — ${data.trigger.schedule_note}` : data.trigger.trigger_name}>
      <Box aria-label={t('processes.dfdTrigger')} sx={(th) => ({ width: TRIG, height: TRIG, borderRadius: '50%',
        border: data.trigger.trigger_kind === 'TIME' ? 4 : 2, borderStyle: data.trigger.trigger_kind === 'TIME' ? 'double' : 'solid',
        borderColor: selected ? th.vars.palette.brand.ftcViolet : th.vars.palette.text.secondary,
        boxShadow: selected ? `0 0 0 4px ${th.vars.palette.brand.purpleTint}` : 'none',
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
      borderColor: th.vars.palette.divider, bgcolor: data.shade ? th.vars.palette.brand.purpleTint : 'transparent' })}>
      <Box sx={(th) => ({ width: LABEL_W - 16, height: '100%', px: 1.5, py: 1.25, borderRight: 1, borderColor: th.vars.palette.divider,
        visibility: low ? 'hidden' : 'visible' })}>
        <Typography sx={(th) => ({ fontSize: 10.5, fontWeight: 600, color: th.vars.palette.brand.muted, textTransform: 'uppercase',
          letterSpacing: '0.06em' })}>{data.kind}</Typography>
        <Typography sx={{ fontSize: 13, fontWeight: 700, lineHeight: 1.3 }}>{data.title}</Typography>
        {data.subtitle && <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>{data.subtitle}</Typography>}
      </Box>
    </Box>
  );
}

/** A data store as the mockup draws it: an open-ended teal box, the entity's code under its name. */
function StoreBox({ data, selected }) {
  const low = useLowZoom();
  return (
    <Box aria-label={t('processes.dfdStore')} sx={(th) => {
      const c = selected ? th.vars.palette.brand.ftcViolet : th.vars.palette.brand.teal;
      return { position: 'relative', width: STORE.w, height: STORE.h, display: 'flex', alignItems: 'stretch',
        bgcolor: th.vars.palette.background.paper, backgroundImage: `linear-gradient(${th.vars.palette.brand.tealTint}, ${th.vars.palette.brand.tealTint})`,
        borderTop: `1.5px solid ${c}`, borderBottom: `1.5px solid ${c}`, borderLeft: `1.5px solid ${c}`,
        boxShadow: selected ? `0 0 0 4px ${th.vars.palette.brand.purpleTint}` : 'none' };
    }}>
      <Ends />
      <Box aria-hidden sx={(th) => ({ width: 14, flexShrink: 0, borderRight: `1.5px solid ${th.vars.palette.brand.teal}` })} />
      <Box sx={{ px: 1.25, minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        visibility: low ? 'hidden' : 'visible' }}>
        <Typography noWrap sx={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25 }}>{data.store.de_name}</Typography>
        <Code tone="teal" sx={{ fontSize: 11.5 }}>{data.store.de_number}</Code>
      </Box>
      {data.crossArea && (
        <NodeFlag tone="teal" title={t('processes.dfdCrossAreaHelp')}>{t('processes.dfdCrossArea')}</NodeFlag>)}
    </Box>
  );
}

/** An outside party: navy, heavy-edged, its kind as a small-caps eyebrow. */
function PartyBox({ data, selected }) {
  const low = useLowZoom();
  return (
    <Box aria-label={t('processes.dfdParty')} sx={(th) => ({ ...nodeFrame(th, 'navy', { selected, radius: 6 }), borderWidth: 2.5,
      width: PARTY.w, height: PARTY.h, px: 1.25, py: 0.75, bgcolor: th.vars.palette.background.subtle })}>
      <Ends />
      <Box sx={{ visibility: low ? 'hidden' : 'visible', height: '100%', overflow: 'hidden' }}>
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
          <Typography sx={(th) => ({ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: th.vars.palette.brand.muted,
            textTransform: 'uppercase' })}>{t('processes.dfdParty')}</Typography>
          <Code tone="navy" sx={{ fontSize: 11 }}>{data.party.ext_number}</Code>
        </Box>
        <Typography sx={{ fontSize: 13.5, fontWeight: 700, lineHeight: 1.2, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{data.party.ext_name}</Typography>
      </Box>
    </Box>
  );
}

const NODE_TYPES = { step: StepBox, store: StoreBox, party: PartyBox, trigger: TriggerDot, lane: LaneBand };

/** The far end of a flow: its store, its party or its trigger. */
const farNode = (f) => ({ STORE: storeNode(f.data_entity_id), EXTERNAL: partyNode(f.external_entity_id),
  TRIGGER: trigNode(f.process_trigger_id) }[f.kind]);
const flowId = (f, i) => `f${i}-${f.kind}-${f.bfc_node_id}-${f.direction}`;

const laneTitle = (lane) => (lane.kind === 'UNASSIGNED' ? t('processes.laneUnassigned')
  : lane.code ? `${lane.code} ${lane.name ?? ''}`.trim() : lane.name);

// One list per element of the chart's DFD rule (D-70); a list whose element is off the rule is empty.
const RULE_GAPS = ['missing_input', 'missing_data_in', 'missing_output', 'missing_order'];

/** Each step's gaps: the report keys of the rule elements it misses ('missing_input', …), or absent. */
function gapsOf(g) {
  const out = new Map();
  for (const k of RULE_GAPS) {
    for (const r of g.completeness[k] ?? []) out.set(r.bfc_node_id, [...(out.get(r.bfc_node_id) ?? []), k]);
  }
  return out;
}

/** Graph → React Flow nodes and edges. Lanes are bands; a process stands at (its lane, its rank);
 * stores, parties and triggers stand in the band below, each under the steps it touches. Saved
 * positions win (D-30); every other box is pushed clear of them (§14.6). Edge colour is applied
 * later, by the page, so selecting a box restyles lines without rebuilding the layout. */
function buildLayout(g, showOrder) {
  const gap = gapsOf(g);
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
      nodes.push({ id: stepNode(p.bfc_node_id), type: 'step', data: { node: p, gap: gap.get(p.bfc_node_id),
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
  // Pack the band into rows: each box keeps its wanted column but drops to the first row where it fits, so
  // eight stores under two steps stack instead of stretching the diagram out of readable zoom (UAT 9).
  const rowEnds = [];
  const ROW_GAP = 24;
  const rowH = Math.max(STORE.h, PARTY.h, TRIG) + ROW_GAP;
  for (const d of [...data].sort((a, b) => a.x - b.x)) {
    const x = Math.max(LABEL_W, d.x);
    let row = rowEnds.findIndex((end) => end + 16 <= x);
    if (row < 0) { row = rowEnds.length; rowEnds.push(-Infinity); }
    const left = Math.max(x, rowEnds[row] + 16);
    rowEnds[row] = left + d.size.w;
    nodes.push({ id: d.id, type: d.type, data: { ...d.data, object: d.object }, size: d.size,
      position: { x: left, y: dataTop + row * rowH } });
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

  const edges = g.flows.map((f, i) => {
    const into = f.direction === 'I';
    return {
      id: flowId(f, i), type: 'labelled', data: { flow: f }, interactionWidth: 16,
      source: into ? farNode(f) : stepNode(f.bfc_node_id), sourceHandle: 's-R',
      target: into ? stepNode(f.bfc_node_id) : farNode(f), targetHandle: 't-L',
      label: f.kind === 'TRIGGER' ? undefined : f.label ?? undefined,
    };
  });
  if (showOrder) {
    // The derived order (D-38), dashed: never stored, drawn on request.
    g.order.forEach((o, i) => edges.push({ id: `o${i}`, type: 'labelled', source: stepNode(o.from_bfc_node_id), sourceHandle: 's-R',
      target: stepNode(o.to_bfc_node_id), targetHandle: 't-L', interactionWidth: 8, data: { order: true } }));
  }
  return { nodes: [...lanes, ...nodes], edges };
}

/** Lines in the mockup's look; those touching the selected box in violet. */
function styleEdges(edges, palette, sel) {
  return edges.map((e) => {
    if (e.data?.order) {
      return { ...e, markerEnd: { type: MarkerType.ArrowClosed, color: palette.primary.main },
        style: { stroke: palette.primary.main, strokeWidth: 1.25, strokeDasharray: '6 4', opacity: 0.8 } };
    }
    const hot = sel != null && (e.source === sel || e.target === sel);
    const { markerColor, ...look } = edgeLook(palette, hot);
    return { ...e, ...look, markerEnd: { type: MarkerType.ArrowClosed, color: markerColor } };
  });
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

/** A flow end as a code + name row with its direction (relative to the step). */
function FlowRow({ code, tone, name, direction, onClick }) {
  return (
    <ListRow onClick={onClick} sx={{ py: 1 }}>
      {code && <Code tone={tone} sx={{ fontSize: 12 }}>{code}</Code>}
      <Typography sx={{ fontSize: 13.5, flexGrow: 1, minWidth: 0, wordBreak: 'break-word' }}>{name}</Typography>
      <Tag tone={direction === 'I' ? 'navy' : 'purple'} sx={{ height: 22 }}>{t(`processes.dfdDir.${direction}`)}</Tag>
    </ListRow>
  );
}

/** The right-hand panel: the selected box's facts, or — with nothing selected — the diagram's summary. */
function Inspector({ g, sel, onSelect, projectId, canEdit }) {
  const navigate = useNavigate();
  const gaps = gapsOf(g);
  const close = <IconButton size="small" aria-label={t('processes.dfdCloseInspector')} onClick={() => onSelect(null)}>
    <CloseRounded fontSize="small" /></IconButton>;
  const stepOf = new Map(g.processes.map((p) => [stepNode(p.bfc_node_id), p]));
  const storeOf = new Map(g.stores.map((s) => [storeNode(s.data_entity_id), s]));
  const partyOf = new Map(g.externals.map((x) => [partyNode(x.external_entity_id), x]));
  const trigOf = new Map(g.triggers.map((x) => [trigNode(x.process_trigger_id), x]));
  const laneOf = new Map(g.lanes.map((l) => [l.lane_key, l]));

  const step = sel && stepOf.get(sel);
  if (step) {
    const lane = laneOf.get(step.lane_key);
    const flows = g.flows.filter((f) => f.bfc_node_id === step.bfc_node_id);
    const gap = gaps.get(step.bfc_node_id);
    const end = (f) => {
      const id = farNode(f);
      if (f.kind === 'STORE') { const s = storeOf.get(id); return { code: s?.de_number, tone: 'teal', name: s?.de_name ?? f.label }; }
      if (f.kind === 'EXTERNAL') {
        const x = partyOf.get(id);
        return { code: x?.ext_number, tone: 'navy', name: f.label ? `${x?.ext_name} · ${f.label}` : x?.ext_name };
      }
      return { code: null, tone: 'muted', name: `${t('processes.dfdTrigger')} · ${f.label}` };
    };
    return (
      <Card title={t('processes.dfdInspectStep', { code: step.hier_code })} action={close}>
        <Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Code tone="muted">{step.hier_code}</Code>
            {step.br_number && <Code tone="purple">{step.br_number}</Code>}
          </Box>
          <Typography sx={{ fontSize: 20, fontWeight: 700, mt: 0.5, wordBreak: 'break-word' }}>{step.node_name}</Typography>
          {step.data_processing_desc && (
            <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mt: 0.5, whiteSpace: 'pre-wrap' }}>{step.data_processing_desc}</Typography>)}
        </Box>
        <Divider />
        <SectionLabel>{t('processes.dfdDataUsed')}</SectionLabel>
        {flows.length === 0 && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('processes.dfdNoData')}</Typography>}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {flows.map((f, i) => {
            const e = end(f);
            return <FlowRow key={`${flowId(f, i)}`} {...e} direction={f.direction} onClick={() => onSelect(farNode(f))} />;
          })}
        </Box>
        <SectionLabel>{t('processes.dfdLane')}</SectionLabel>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <Tag tone="neutral">{t(`processes.performer.kind.${lane?.kind ?? 'UNASSIGNED'}`)}</Tag>
          {lane && lane.kind !== 'UNASSIGNED' && <Typography sx={{ fontSize: 14 }}>{laneTitle(lane)}</Typography>}
        </Box>
        {step.systems.length > 0 && (<>
          <SectionLabel>{t('processes.dfdSystems')}</SectionLabel>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {step.systems.map((a) => <Tag key={a.application_id} tone="navy">{`${a.application_code} ${a.application_name}`}</Tag>)}
          </Box>
        </>)}
        <SectionLabel>{t('processes.dfdChecks')}</SectionLabel>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {!gap && <Status tone="ok" size="sm">{t('processes.dfdChecksOk')}</Status>}
          {(gap ?? []).map((k) => <Status key={k} tone="caution" size="sm">{t(`processes.gap.${k}`)}</Status>)}
          {/* D-70: a recommended element outside the rule is information here, never a gap */}
          {(g.completeness.advised?.[step.bfc_node_id] ?? []).map((c) => (
            <Status key={c} tone="neutral" size="sm" sx={{ whiteSpace: 'normal', height: 'auto', py: 0.25 }}>{t('processes.dfdAdvised', { what: t(`processes.dfdLight.element.${c}`) })}</Status>))}
        </Box>
        <Button variant="contained" fullWidth sx={{ mt: 1 }}
          onClick={() => navigate(links.node(projectId, step.bfc_node_id, step.bfc_set_code))}>{t('processes.dfdOpenStep')}</Button>
      </Card>
    );
  }

  // A store, a party or a trigger: who uses it, and how.
  const far = sel && (storeOf.get(sel) ?? partyOf.get(sel) ?? trigOf.get(sel));
  if (far) {
    const store = storeOf.get(sel);
    const party = partyOf.get(sel);
    const trig = trigOf.get(sel);
    const uses = g.flows.filter((f) => farNode(f) === sel);
    const kindKey = store ? 'processes.dfdStore' : party ? 'processes.dfdParty' : 'processes.dfdTrigger';
    return (
      <Card title={t(kindKey)} action={close}>
        <Box>
          {store && <Code tone="teal">{store.de_number}</Code>}
          {party && <Code tone="navy">{party.ext_number}</Code>}
          {trig && <Tag tone="neutral">{t(`processes.trigger.kind.${trig.trigger_kind}`)}</Tag>}
          <Typography sx={{ fontSize: 20, fontWeight: 700, mt: 0.5, wordBreak: 'break-word' }}>
            {store?.de_name ?? party?.ext_name ?? trig?.trigger_name}</Typography>
          {trig?.schedule_note && <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mt: 0.5 }}>{trig.schedule_note}</Typography>}
          {store && g.cross_area.includes(store.data_entity_id) && (
            <Tooltip title={t('processes.dfdCrossAreaHelp')}><Box component="span" sx={{ display: 'inline-flex', mt: 1 }}>
              <Tag tone="teal">{t('processes.dfdCrossArea')}</Tag></Box></Tooltip>)}
        </Box>
        <Divider />
        <SectionLabel>{t('processes.dfdUsedBy')}</SectionLabel>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {uses.map((f, i) => {
            const p = stepOf.get(stepNode(f.bfc_node_id));
            return <FlowRow key={flowId(f, i)} code={p?.hier_code} tone="muted" name={p?.node_name} direction={f.direction}
              onClick={() => onSelect(stepNode(f.bfc_node_id))} />;
          })}
        </Box>
        {store && (
          <Button variant="contained" fullWidth component={RouterLink} to={links.entity(projectId, store.data_entity_id)}
            sx={{ mt: 1 }}>{t('processes.dfdOpenEntity')}</Button>)}
      </Card>
    );
  }

  // Nothing selected: the diagram's summary — its chart, its lanes and its gaps.
  const gapSteps = g.processes.filter((p) => gaps.has(p.bfc_node_id));
  return (
    <Card title={t('processes.dfdSummary')}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Tag tone="purple">{t(`processes.chart.${g.scope.bfc_set_code}`)}</Tag>
      </Box>
      <SectionLabel>{t('processes.dfdLane')}</SectionLabel>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {g.lanes.map((l) => (
          <Box key={l.lane_key} sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
            <Typography sx={{ fontSize: 13.5, flexGrow: 1, minWidth: 0, wordBreak: 'break-word' }}>{laneTitle(l)}</Typography>
            <Code tone="muted" sx={{ fontSize: 12 }}>{g.processes.filter((p) => p.lane_key === l.lane_key).length}</Code>
          </Box>))}
      </Box>
      <SectionLabel>{t('processes.dfdChecks')}</SectionLabel>
      {gapSteps.length === 0 ? <Status tone="ok" size="sm">{t('processes.gapsNone')}</Status> : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.dfdGapsAlert', { n: gapSteps.length })}</Typography>
          {gapSteps.map((p) => (
            <ListRow key={p.bfc_node_id} onClick={() => onSelect(stepNode(p.bfc_node_id))}
              sx={{ py: 1, flexDirection: 'column', alignItems: 'flex-start', gap: 0.5 }}>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline', minWidth: 0 }}>
                <Code tone="muted" sx={{ fontSize: 12 }}>{p.hier_code}</Code>
                <Typography sx={{ fontSize: 13.5, minWidth: 0 }}>{p.node_name}</Typography>
              </Box>
              <Status tone="caution" size="sm">{gapText(gaps.get(p.bfc_node_id))}</Status>
            </ListRow>))}
        </Box>)}
      <Divider />
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
        {t(canEdit ? 'processes.dfdInspectHelp' : 'processes.dfdInspectHelpReadOnly')}</Typography>
    </Card>
  );
}

/**
 * The data flow diagram of one parent node, on the shared canvas. Read-only apart from placing boxes.
 * `frame` lays out the parts — the roll-up route wraps them in a page of their own, the DFD screen
 * (D-54) puts them beside its list — so there is one diagram, drawn one way (law 8).
 */
export function DfdView({ projectId, nodeId, frame, chartLabel = t('processes.backToChart'), container = false }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const theme = useTheme();
  const canEdit = useCanEdit();
  const graphKey = keys.dfdGraph(projectId, nodeId);
  const q = useQuery({ queryKey: graphKey, queryFn: () => dfdApi.graph(nodeId) });
  const g = q.data;
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [baseEdges, setBaseEdges] = useState([]);
  const [view, setView] = useState('diagram');
  const [showOrder, setShowOrder] = useState(false);
  const [layoutError, setLayoutError] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const [sel, setSel] = useState(null);
  const selRef = useRef(sel);
  selRef.current = sel;
  const palette = theme.vars.palette;
  useEffect(() => {
    if (!g) return undefined;
    let live = true;
    Promise.resolve().then(() => buildLayout(g, showOrder))
      .then((r) => {
        if (!live) return;
        setNodes(r.nodes.map((n) => (n.id === selRef.current ? { ...n, selected: true } : n)));
        setBaseEdges(r.edges);
        setLayoutError('');
      })
      .catch((err) => { if (live) setLayoutError(err.message); });
    return () => { live = false; };
  }, [g, setNodes, showOrder]);
  const edges = useMemo(() => styleEdges(baseEdges, palette, sel), [baseEdges, palette, sel]);

  // A new node (another scope) starts with nothing selected. The inspector's selection owns the
  // ring, whether a click, the inspector or a pane click set it.
  useEffect(() => { setSel(null); }, [nodeId]);
  useEffect(() => {
    setNodes((ns) => ns.map((n) => (Boolean(n.selected) === (n.id === sel) ? n : { ...n, selected: n.id === sel })));
  }, [sel, setNodes]);

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

  // A click shows the box in the inspector; a double-click on a step opens it in the chart, where
  // its data in and out is edited (spec 3a: no editing here). The inspector has the same link.
  const onNodeClick = useCallback((_, n) => setSel(n.type === 'lane' ? null : n.id), []);
  const onPaneClick = useCallback(() => setSel(null), []);
  const onNodeDoubleClick = useCallback((_, n) => {
    if (n.type === 'step') navigate(links.node(projectId, n.data.node.bfc_node_id, n.data.node.bfc_set_code));
  }, [navigate, projectId]);

  const title = g ? t('processes.dfdHeading', { name: g.scope.node_name }) : t('processes.dfdTitle');
  const counts = g && t('processes.dfdCounts', { steps: g.processes.length, stores: g.stores.length,
    parties: g.externals.length, triggers: g.triggers.length, flows: g.flows.length });
  const eyebrow = g && (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
      <Code tone="purple">{g.scope.hier_code}</Code>
      <Tag tone="purple" sx={{ height: 22 }}>{t(`processes.chart.${g.scope.bfc_set_code}`)}</Tag>
    </Box>);
  const actions = (
    <>
      <Segmented size="sm" label={t('processes.flowView')} value={view} onChange={setView}
        options={[{ value: 'diagram', label: t('processes.viewDiagram') }, { value: 'table', label: t('processes.viewTable') }]} />
      <Button variant="outlined" component={RouterLink} to={links.node(projectId, nodeId, g?.scope.bfc_set_code)}>{chartLabel}</Button>
      <CopyMermaidButton area="processes" disabled={!g} fetchText={() => dfdApi.mermaid(nodeId, showOrder)} />
      {canEdit && (
        <Button color="warning" disabled={!g || reset.isPending}
          onClick={() => setConfirmReset(true)}>{t('processes.resetLayout')}</Button>)}
    </>);
  const content = (
    <>
      {layoutError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setLayoutError('')}>{layoutError}</Alert>}
      {g && g.processes.length === 0 && <Alert severity="info">{t('processes.dfdNoSteps')}</Alert>}
      {g && g.processes.length > 0 && g.flows.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>{t('processes.dfdNoFlows')}</Alert>)}
      {g && g.processes.length > 0 && (
        <DiagramGrid container={container}>
          <Card bodySx={{ p: 0, gap: 0 }}>
            <CanvasHeader summary={counts} legend={view === 'diagram' && (<>
              <LegendSwatch shape="process" label={t('processes.dfdLegendStep')} />
              <LegendSwatch shape="store" label={t('processes.dfdStore')} />
              <LegendSwatch shape="party" label={t('processes.dfdParty')} />
              <LegendSwatch shape="trigger" label={t('processes.dfdTrigger')} />
              {showOrder && <LegendSwatch shape="order" label={t('processes.dfdLegendOrder')} />}
            </>)}>
              {/* DR13-P4: with no order in the data, the steps stand in chart order — said, never drawn as arrows */}
              {view === 'diagram' && g.order_source === 'CHART' && (
                <Tooltip title={t('processes.dfdChartOrderHelp')}>
                  <Typography component="span" tabIndex={0} sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                    {t('processes.dfdChartOrder')}</Typography>
                </Tooltip>)}
              {view === 'diagram' && g.order_source !== 'CHART' && (
                <FormControlLabel sx={{ mr: 0, '& .MuiFormControlLabel-label': { fontSize: 12.5, color: 'text.secondary' } }}
                  label={t('processes.dfdShowOrder')}
                  control={<Switch size="small" id="dfd-order" checked={showOrder} onChange={(e) => setShowOrder(e.target.checked)} />} />)}
            </CanvasHeader>
            {view === 'diagram' ? (
              <ModelCanvas kind="dfd" bare nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} height="max(480px, 68vh)"
                draggable={canEdit} onNodesChange={handleNodesChange} onNodeClick={onNodeClick} onPaneClick={onPaneClick}
                onNodeDoubleClick={onNodeDoubleClick} ariaLabel={title} />
            ) : <Box sx={{ p: 1 }}><DfdTable g={g} /></Box>}
          </Card>
          <Inspector g={g} sel={sel} onSelect={setSel} projectId={projectId} canEdit={canEdit} />
        </DiagramGrid>
      )}
      <ConfirmDialog open={confirmReset} title={t('processes.resetLayoutTitle')} body={t('processes.resetLayoutBody')}
        confirmLabel={t('processes.resetLayout')} busy={reset.isPending}
        onClose={() => setConfirmReset(false)} onConfirm={() => reset.mutate()} />
    </>);
  return frame({ g, title, eyebrow, actions, content, error: q.error ? errorText(q.error) : '' });
}

/** The roll-up route (processes/:nodeId/dfd): any non-process node's diagram, opened from the chart. */
export default function DfdPage() {
  const { projectId, nodeId } = useParams();
  return (
    <DfdView projectId={projectId} nodeId={nodeId} frame={(f) => (
      <Page title={f.title} subtitle={t('processes.dfdPageHelp')} error={f.error} crumb={f.g?.scope.hier_code}
        eyebrow={f.eyebrow} actions={f.actions}>{f.content}</Page>)} />
  );
}
