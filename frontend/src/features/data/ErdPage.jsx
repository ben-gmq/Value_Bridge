// The logical ERD of the project or one subject area (spec §7 3b, design §7.4 / §7.14 / §14.6),
// at /p/:projectId/data/diagram?area={nodeId}. Read-only (A-S3-6): positions and collapse are
// the only things saved, through the Slice 2 diagram-layout routes with type ERD.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNodesState, useReactFlow } from '@xyflow/react';
import { Alert, Autocomplete, Box, Button, Link, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TextField,
  Tooltip } from '@mui/material';
import { errorText } from '../../api/client';
import { bfcApi, erdApi, layoutApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { CanvasHeader, DiagramGrid, LegendSwatch } from '../../canvas/CanvasChrome';
import { ModelCanvas } from '../../canvas/ModelCanvas';
import { useLayoutSave } from '../../canvas/useLayoutSave';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { CopyMermaidButton } from '../../components/CopyMermaidButton';
import { SavePictureButton } from '../../components/SavePictureButton';
import { Card, Code, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { ErdInspector } from './ErdInspector';
import { ERD_EDGE_TYPES, ERD_NODE_TYPES, ErdContext, ErdMarkers, cardinalityText } from './ErdParts';
import { arrange, buildEdges, buildNodes, entityNodeId, ghostNodeId, initialCollapsed, neighbours } from './erdModel';
import { entityLabel } from './fieldRules';

const DIM = 'erd-dim';
const WHOLE = 'project';                     // the picker's "Whole project" (the layout scope key)
const NOWRAP = { whiteSpace: 'nowrap' };

/** Search-to-focus: it needs the React Flow instance, so it renders inside the canvas. */
function FocusOn({ request }) {
  const rf = useReactFlow();
  useEffect(() => {
    if (request) rf.fitView({ nodes: [{ id: request.id }], duration: 400, maxZoom: 1.1, padding: 0.5 });
  }, [request, rf]);
  return null;
}

/** Fit the view once per subject area, after that area's own cards are laid out (UAT finding
 * A: switching area kept the previous zoom, which could leave the new diagram off screen).
 * `laid` names the scope the canvas currently holds, so the old area's cards never trigger it. */
function FitOnArea({ laid }) {
  const rf = useReactFlow();
  const fitted = useRef(null);
  useEffect(() => {
    if (!laid || fitted.current === laid) return;
    fitted.current = laid;
    requestAnimationFrame(() => rf.fitView({ padding: 0.1 }));
  }, [laid, rf]);
  return null;
}

function ErdTable({ g, projectId }) {
  const byId = new Map(g.entities.map((e) => [e.data_entity_id, e]));
  const rows = [...g.relationships.map((r) => ({ r, stub: false })), ...g.outside_refs.map((r) => ({ r, stub: true }))];
  if (!rows.length) return <Alert severity="info">{t('data.erd.table.none')}</Alert>;
  const parentText = (r, stub) => {
    const label = `${r.parent_de_number} ${r.parent_de_name}`;
    if (!stub) return label;
    return t(r.retired ? 'data.erd.table.retired' : 'data.erd.table.outside', { label });
  };
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small" aria-label={t('data.erd.viewTable')}>
        <TableHead><TableRow>
          <TableCell>{t('data.erd.table.child')}</TableCell><TableCell>{t('data.erd.table.fields')}</TableCell>
          <TableCell>{t('data.erd.table.parent')}</TableCell><TableCell>{t('data.erd.table.cardinality')}</TableCell>
          <TableCell>{t('data.erd.table.kind')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {rows.map(({ r, stub }) => (
            <TableRow key={`${r.child_data_entity_id}-${r.parent_data_entity_id}-${r.fk_group_no}`}>
              <TableCell><Link component={RouterLink} to={links.entity(projectId, r.child_data_entity_id)} sx={{ color: 'brand.link' }}>
                {entityLabel(byId.get(r.child_data_entity_id))}</Link></TableCell>
              <TableCell sx={{ fontFamily: MONO, fontSize: 12.5 }}>{r.label}</TableCell>
              <TableCell><Link component={RouterLink} to={links.entity(projectId, r.parent_data_entity_id)} sx={{ color: 'brand.link' }}>
                {parentText(r, stub)}</Link></TableCell>
              <TableCell>{cardinalityText(r)}</TableCell>
              <TableCell>{t(r.identifying ? 'data.erd.table.identifying' : 'data.erd.table.nonIdentifying')}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

export default function ErdPage() {
  const { projectId } = useParams();
  const [params] = useSearchParams();
  const area = params.get('area') || null;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.erd(projectId, area), queryFn: () => erdApi.graph(projectId, area) });
  const g = q.data;
  const treeQ = useQuery({ queryKey: keys.tree(projectId), queryFn: () => bfcApi.tree(projectId) });
  const { getLabel } = useCodes(projectId, 'FIELD_DATA_TYPE');
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [view, setView] = useState('diagram');
  const [focusId, setFocusId] = useState(null);
  const [focusRequest, setFocusRequest] = useState(null);
  const [layoutError, setLayoutError] = useState('');
  const pictureRef = useRef(null);                     // function 41: the canvas and its marker defs, saved as shown
  const [confirmReset, setConfirmReset] = useState(false);
  const [arrangeTick, setArrangeTick] = useState(0);
  const [resetTick, setResetTick] = useState(0);
  const [laidScope, setLaidScope] = useState(null);

  // The graph's parts keep their identity across a layout-only cache update (structural
  // sharing), so saving a position never re-arranges the canvas.
  const entities = g?.entities;
  const relationships = g?.relationships;
  const outsideRefs = g?.outside_refs;
  const scopeKey = g?.scope_key;
  const gRef = useRef(g);
  gRef.current = g;
  const collapsedRef = useRef(new Map());
  const collapseFor = useRef({});
  const focusRef = useRef(null);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  const baseEdges = useMemo(() => (relationships ? buildEdges({ relationships, outside_refs: outsideRefs }) : []),
    [relationships, outsideRefs]);
  const near = useMemo(() => (focusId ? neighbours(baseEdges, focusId) : null), [baseEdges, focusId]);
  focusRef.current = near;
  const focusIdRef = useRef(focusId);
  focusIdRef.current = focusId;
  // Dimmed outside the focus; the focused card's own lines in violet (the shared line look).
  const edges = useMemo(() => (near ? baseEdges.map((e) => (near.has(e.source) && near.has(e.target)
    ? (e.source === focusId || e.target === focusId ? { ...e, data: { ...e.data, hot: true } } : e)
    : { ...e, className: DIM })) : baseEdges), [baseEdges, near, focusId]);

  useEffect(() => { setFocusId(null); }, [area]);

  // Build: on new data, Reset or Auto-arrange only. Collapse is (re)read from the saved rows
  // when the entities or a Reset change, and kept across an Auto-arrange.
  useEffect(() => {
    const cur = gRef.current;
    if (!cur || !entities) return undefined;
    if (collapseFor.current.entities !== entities || collapseFor.current.reset !== resetTick) {
      collapsedRef.current = initialCollapsed(cur);
      collapseFor.current = { entities, reset: resetTick };
    }
    let live = true;
    arrange(cur, collapsedRef.current, baseEdges).then((positions) => {
      if (!live) return;
      const hot = focusRef.current;         // a highlight survives a re-arrange
      setNodes(buildNodes(cur, collapsedRef.current, positions)
        .map((n) => ({ ...n, className: hot && !hot.has(n.id) ? DIM : undefined, selected: n.id === focusIdRef.current })));
      setLaidScope(cur.scope_key);
      setLayoutError('');
    }).catch((err) => { if (live) setLayoutError(t('data.erd.layoutFailed', { message: err.message })); });
    return () => { live = false; };
  }, [entities, baseEdges, resetTick, arrangeTick, setNodes]);

  // Highlight: only the class and the focused card's selection change, so other cards' rows do
  // not re-render (criterion 17). The focus owns the selection ring, whoever set it.
  useEffect(() => {
    setNodes((ns) => ns.map((n) => {
      const c = near && !near.has(n.id) ? DIM : undefined;
      const s = n.id === focusId;
      return n.className === c && Boolean(n.selected) === s ? n : { ...n, className: c, selected: s };
    }));
  }, [near, focusId, setNodes]);

  // Positions save through the one shared hook (§14.6). The ONLY ERD-specific extra is
  // `collapsed`: every item carries its card's current flag (R2-NEW-1), so a drag never
  // un-collapses a card. The saved scope's positions go back into the cache, so a return visit
  // (and Auto-arrange) pins what was placed; the entities keep their identity.
  const layout = useLayoutSave({
    projectId, diagramType: 'ERD', scopeKey, canEdit,
    getNode: (id) => nodesRef.current.find((n) => n.id === id),
    toItem: (n) => (n.type === 'entity' && n.position ? {
      object_type: 'ENTITY', object_id: n.data.entity.data_entity_id,
      x: Math.round(n.position.x), y: Math.round(n.position.y),
      collapsed: Boolean(collapsedRef.current.get(n.data.entity.data_entity_id)) } : null),
    onSaved: (saved, sk) => qc.setQueryData(keys.erd(projectId, sk === WHOLE ? null : sk),
      (old) => (old ? { ...old, layout: saved } : old)),
    onError: (err) => setLayoutError(errorText(err, t('common.saveFailed'))),
  });
  const queue = layout.queue;
  const handleNodesChange = useCallback((changes) => {
    onNodesChange(changes);
    layout.onChanges(changes);
  }, [onNodesChange, layout]);

  const reset = useMutation({
    mutationFn: () => layoutApi.reset(projectId, 'ERD', scopeKey),
    onMutate: () => layout.discard(),           // a queued move must not re-pin after the reset (sara L3)
    onSuccess: async () => {
      setConfirmReset(false);
      await qc.refetchQueries({ queryKey: keys.erd(projectId, area), exact: true });
      setResetTick((n) => n + 1);
    },
    onError: (err) => { setConfirmReset(false); setLayoutError(errorText(err, t('common.saveFailed'))); },
  });

  // Collapsing a card that was never dragged saves its current place, which pins it (the
  // tooltip says so). A read-only user may fold a card on their own screen; nothing is saved.
  const onToggle = useCallback((deId) => {
    const next = !collapsedRef.current.get(deId);
    collapsedRef.current = new Map(collapsedRef.current).set(deId, next);
    const id = entityNodeId(deId);
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, collapsed: next } } : n)));
    if (canEdit) queue(id);
  }, [setNodes, canEdit, queue]);
  const ctx = useMemo(() => ({ getLabel, onToggle, canEdit }), [getLabel, onToggle, canEdit]);

  const onNodeClick = useCallback((_, n) => setFocusId((cur) => (cur === n.id ? null : n.id)), []);
  // The inspector focuses a card by its relationships, and pans to it, as the search does.
  const focusFromPanel = useCallback((id) => {
    setFocusId(id);
    if (id) setFocusRequest({ id, at: Date.now() });
  }, []);
  const onPaneClick = useCallback(() => setFocusId(null), []);
  const onNodeDoubleClick = useCallback((_, n) => {
    const deId = n.type === 'entity' ? n.data.entity.data_entity_id : n.data.ghost.data_entity_id;
    navigate(links.entity(projectId, deId));
  }, [navigate, projectId]);

  const areaNodes = (treeQ.data ?? []).filter((n) => n.is_active);
  const areaNode = areaNodes.find((n) => String(n.bfc_node_id) === area);
  const scopeName = areaNode ? `${areaNode.hier_code} ${areaNode.node_name}` : t('data.erd.areaAll');
  const options = useMemo(() => [...(entities ?? []).map((e) => ({ id: entityNodeId(e.data_entity_id), e })),
    ...(outsideRefs ?? []).filter((r, i, all) => all.findIndex((x) => x.parent_data_entity_id === r.parent_data_entity_id) === i)
      .map((r) => ({ id: ghostNodeId(r.parent_data_entity_id),
        e: { de_number: r.parent_de_number, de_name: r.parent_de_name } }))], [entities, outsideRefs]);
  const empty = g && g.entities.length === 0;

  return (
    <Page title={t('data.erd.title')} subtitle={t('data.erd.subtitle')} error={q.error ? errorText(q.error, t('data.loadFailed')) : ''}
      crumb={areaNode?.hier_code}
      eyebrow={(
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          {areaNode && <Code tone="muted">{areaNode.hier_code}</Code>}
          <Tag tone="teal" sx={{ height: 22 }}>{areaNode ? areaNode.node_name : t('data.erd.areaAll')}</Tag>
        </Box>)}
      actions={(<>
        <Segmented size="sm" label={t('data.erd.view')} value={view} onChange={setView}
          options={[{ value: 'diagram', label: t('data.erd.viewDiagram') }, { value: 'table', label: t('data.erd.viewTable') }]} />
        <Button variant="outlined" component={RouterLink} to={links.data(projectId)} sx={NOWRAP}>{t('data.erd.back')}</Button>
        <Tooltip title={t('data.erd.arrangeHelp')}>
          <span><Button sx={NOWRAP} disabled={!g || empty} onClick={() => setArrangeTick((n) => n + 1)}>{t('data.erd.arrange')}</Button></span>
        </Tooltip>
        <CopyMermaidButton area="data.erd" disabled={!g} fetchText={() => erdApi.mermaid(projectId, area)} />
        <SavePictureButton target={pictureRef} fileName={`vb-erd-${projectId}-${area ?? WHOLE}`}
          disabled={!g || empty || view !== 'diagram'} />
        {canEdit && (
          <Button color="warning" sx={NOWRAP} disabled={!g || reset.isPending} onClick={() => setConfirmReset(true)}>
            {t('data.erd.reset')}</Button>)}
      </>)}>
      {layoutError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setLayoutError('')}>{layoutError}</Alert>}
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center', mb: 2 }}>
        <TextField select size="small" id="erd-area" label={t('data.erd.area')} value={area ?? WHOLE} sx={{ minWidth: 260, maxWidth: '100%' }}
          onChange={(e) => navigate(links.erd(projectId, e.target.value === WHOLE ? null : e.target.value))}>
          <MenuItem value={WHOLE}>{t('data.erd.areaAll')}</MenuItem>
          {/* Until the chart has loaded (or for a node no longer live), the address still names a valid value. */}
          {area && !areaNode && <MenuItem value={area} sx={{ display: 'none' }}>{area}</MenuItem>}
          {areaNodes.map((n) => (
            <MenuItem key={n.bfc_node_id} value={String(n.bfc_node_id)} sx={{ pl: 1 + n.level_no * 1.5 }}>
              <Box component="span" sx={{ fontFamily: MONO, fontSize: 12.5, mr: 1, color: 'text.secondary' }}>{n.hier_code}</Box>
              {n.node_name}</MenuItem>))}
        </TextField>
        <Autocomplete id="erd-search" size="small" sx={{ minWidth: 260, maxWidth: '100%' }} options={options} value={null}
          disabled={!g || empty || view !== 'diagram'} blurOnSelect clearOnBlur
          getOptionLabel={(o) => `${o.e.de_number} ${o.e.de_name}`} isOptionEqualToValue={(a, b) => a.id === b.id}
          noOptionsText={t('data.erd.searchNone')}
          onChange={(_, o) => { if (o) { setFocusId(o.id); setFocusRequest({ id: o.id, at: Date.now() }); } }}
          renderInput={(p) => <TextField {...p} label={t('data.erd.search')} />} />
      </Box>
      {empty && <Alert severity="info">{t(area ? 'data.erd.emptyArea' : 'data.erd.empty')}</Alert>}
      {g && !empty && (
        <DiagramGrid>
          <Card bodySx={{ p: 0, gap: 0 }}>
            <CanvasHeader
              summary={t('data.erd.counts', { entities: g.entities.length, relationships: g.relationships.length, stubs: g.outside_refs.length })}
              legend={view === 'diagram' && (<>
                <LegendSwatch shape="entity" label={t('data.erd.legendEntity')} />
                <LegendSwatch shape="ghost" label={t('data.erd.outside')} />
                <LegendSwatch shape="line" label={t('data.erd.table.identifying')} />
                <LegendSwatch shape="dashed" label={t('data.erd.table.nonIdentifying')} />
              </>)} />
            {view === 'diagram' ? (
              <ErdContext.Provider value={ctx}>
                <Box ref={pictureRef}
                  sx={{ [`& .react-flow__node.${DIM}`]: { opacity: 0.2 }, [`& .react-flow__edge.${DIM}`]: { opacity: 0.1 } }}>
                  <ErdMarkers />
                  <ModelCanvas kind="erd" bare nodes={nodes} edges={edges} nodeTypes={ERD_NODE_TYPES} edgeTypes={ERD_EDGE_TYPES}
                    onNodesChange={handleNodesChange} draggable={canEdit} onNodeClick={onNodeClick} onPaneClick={onPaneClick}
                    onNodeDoubleClick={onNodeDoubleClick} minimap height="max(480px, 70vh)"
                    ariaLabel={t('data.erd.canvasLabel', { scope: scopeName })}>
                    <FocusOn request={focusRequest} />
                    <FitOnArea laid={laidScope} />
                  </ModelCanvas>
                </Box>
              </ErdContext.Provider>
            ) : <Box sx={{ p: 1 }}><ErdTable g={g} projectId={projectId} /></Box>}
          </Card>
          <ErdInspector g={g} focusId={view === 'diagram' ? focusId : null} onFocus={focusFromPanel} projectId={projectId}
            scopeName={scopeName} canEdit={canEdit} />
        </DiagramGrid>
      )}
      <ConfirmDialog open={confirmReset} title={t('data.erd.resetTitle')} body={t('data.erd.resetBody')}
        confirmLabel={t('data.erd.reset')} busy={reset.isPending}
        onClose={() => setConfirmReset(false)} onConfirm={() => reset.mutate()} />
    </Page>
  );
}
