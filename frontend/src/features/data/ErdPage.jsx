// The logical ERD of the project or one subject area (spec §7 3b, design §7.4 / §7.14 / §14.6),
// at /p/:projectId/data/diagram?area={nodeId}. Read-only (A-S3-6): positions and collapse are
// the only things saved, through the Slice 2 diagram-layout routes with type ERD.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNodesState, useReactFlow } from '@xyflow/react';
import { Alert, Autocomplete, Box, Button, Link, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TextField,
  ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { bfcApi, erdApi, layoutApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ModelCanvas } from '../../canvas/ModelCanvas';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page, WrapperBox } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { ERD_EDGE_TYPES, ERD_NODE_TYPES, ErdContext, ErdMarkers, cardinalityText } from './ErdParts';
import { arrange, buildEdges, buildNodes, entityNodeId, ghostNodeId, initialCollapsed, neighbours } from './erdModel';
import { entityLabel } from './fieldRules';

const SAVE_DELAY = 600;
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
  const edges = useMemo(() => (near ? baseEdges.map((e) => (near.has(e.source) && near.has(e.target) ? e
    : { ...e, className: DIM })) : baseEdges), [baseEdges, near]);

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
        .map((n) => ({ ...n, className: hot && !hot.has(n.id) ? DIM : undefined })));
      setLaidScope(cur.scope_key);
      setLayoutError('');
    }).catch((err) => { if (live) setLayoutError(t('data.erd.layoutFailed', { message: err.message })); });
    return () => { live = false; };
  }, [entities, baseEdges, resetTick, arrangeTick, setNodes]);

  // Highlight: only the class changes, so a card's rows do not re-render (criterion 17).
  useEffect(() => {
    setNodes((ns) => ns.map((n) => {
      const c = near && !near.has(n.id) ? DIM : undefined;
      return n.className === c ? n : { ...n, className: c };
    }));
  }, [near, setNodes]);

  // ==== LAYOUT SAVE (the same shape as FlowPage's; to move into one shared canvas hook) ====
  // Drag end and collapse queue a card; one debounced PUT sends them; a pending save is sent on
  // leaving; Reset clears the scope. The ONLY ERD-specific extra is `collapsed`: every item
  // carries its card's current flag (R2-NEW-1), so a drag never un-collapses a card.
  const pending = useRef(new Set());
  const timer = useRef(null);
  const items = useCallback((ids) => ids.map((id) => nodesRef.current.find((n) => n.id === id))
    .filter((n) => n?.type === 'entity').map((n) => ({ object_type: 'ENTITY', object_id: n.data.entity.data_entity_id,
      x: Math.round(n.position.x), y: Math.round(n.position.y),
      collapsed: Boolean(collapsedRef.current.get(n.data.entity.data_entity_id)) })), []);
  const save = useMutation({
    mutationFn: ({ sk, list }) => layoutApi.save(projectId, 'ERD', sk, list),
    // The response is every saved position of this scope: keep the cache's copy current so a
    // return visit (and Auto-arrange) pins what was placed. entities keep their identity.
    onSuccess: (layout, { forArea }) => qc.setQueryData(keys.erd(projectId, forArea), (old) => (old ? { ...old, layout } : old)),
    onError: (err) => setLayoutError(errorText(err, t('common.saveFailed'))),
  });
  const take = useCallback(() => {
    clearTimeout(timer.current);
    const list = items([...pending.current]);
    pending.current.clear();
    return list;
  }, [items]);
  const queue = useCallback((id) => {
    pending.current.add(id);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const list = take();
      if (list.length && scopeKey) save.mutate({ sk: scopeKey, list, forArea: area });
    }, SAVE_DELAY);
  }, [take, save, scopeKey, area]);
  // A move still pending when the page or the area changes is sent, not dropped.
  useEffect(() => () => {
    const list = take();
    if (list.length && scopeKey) {
      layoutApi.save(projectId, 'ERD', scopeKey, list)
        .catch((err) => console.error('Diagram positions not saved on leaving the diagram', err));
    }
  }, [take, projectId, scopeKey]);

  const handleNodesChange = useCallback((changes) => {
    onNodesChange(changes);
    if (!canEdit) return;
    for (const c of changes) {
      if (c.type === 'position' && !c.dragging && c.id.startsWith('e')) queue(c.id);
    }
  }, [onNodesChange, canEdit, queue]);

  const reset = useMutation({
    mutationFn: () => layoutApi.reset(projectId, 'ERD', scopeKey),
    onSuccess: async () => {
      pending.current.clear();
      clearTimeout(timer.current);
      setConfirmReset(false);
      await qc.refetchQueries({ queryKey: keys.erd(projectId, area), exact: true });
      setResetTick((n) => n + 1);
    },
    onError: (err) => { setConfirmReset(false); setLayoutError(errorText(err, t('common.saveFailed'))); },
  });
  // ==== END LAYOUT SAVE ====

  // Collapsing a card that was never dragged saves its current place, which pins it (the
  // tooltip says so). A REVIEWER may fold a card on their own screen; nothing is saved.
  const onToggle = useCallback((deId) => {
    const next = !collapsedRef.current.get(deId);
    collapsedRef.current = new Map(collapsedRef.current).set(deId, next);
    const id = entityNodeId(deId);
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, collapsed: next } } : n)));
    if (canEdit) queue(id);
  }, [setNodes, canEdit, queue]);
  const ctx = useMemo(() => ({ getLabel, onToggle, canEdit }), [getLabel, onToggle, canEdit]);

  const onNodeClick = useCallback((_, n) => setFocusId((cur) => (cur === n.id ? null : n.id)), []);
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
      actions={(<>
        <Button component={RouterLink} to={links.data(projectId)} sx={NOWRAP}>{t('data.erd.back')}</Button>
        <Tooltip title={t('data.erd.arrangeHelp')}>
          <span><Button sx={NOWRAP} disabled={!g || empty} onClick={() => setArrangeTick((n) => n + 1)}>{t('data.erd.arrange')}</Button></span>
        </Tooltip>
        {canEdit && (
          <Button color="warning" sx={NOWRAP} disabled={!g || reset.isPending} onClick={() => setConfirmReset(true)}>
            {t('data.erd.reset')}</Button>)}
      </>)}>
      {layoutError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setLayoutError('')}>{layoutError}</Alert>}
      <WrapperBox>
        <TextField select id="erd-area" label={t('data.erd.area')} value={area ?? WHOLE} sx={{ minWidth: 260 }}
          onChange={(e) => navigate(links.erd(projectId, e.target.value === WHOLE ? null : e.target.value))}>
          <MenuItem value={WHOLE}>{t('data.erd.areaAll')}</MenuItem>
          {/* Until the chart has loaded (or for a node no longer live), the address still names a valid value. */}
          {area && !areaNode && <MenuItem value={area} sx={{ display: 'none' }}>{area}</MenuItem>}
          {areaNodes.map((n) => (
            <MenuItem key={n.bfc_node_id} value={String(n.bfc_node_id)} sx={{ pl: 1 + n.level_no * 1.5 }}>
              <Box component="span" sx={{ fontFamily: MONO, fontSize: 12.5, mr: 1, color: 'text.secondary' }}>{n.hier_code}</Box>
              {n.node_name}</MenuItem>))}
        </TextField>
        <Autocomplete id="erd-search" size="small" sx={{ minWidth: 260 }} options={options} value={null}
          disabled={!g || empty || view !== 'diagram'} blurOnSelect clearOnBlur
          getOptionLabel={(o) => `${o.e.de_number} ${o.e.de_name}`} isOptionEqualToValue={(a, b) => a.id === b.id}
          noOptionsText={t('data.erd.searchNone')}
          onChange={(_, o) => { if (o) { setFocusId(o.id); setFocusRequest({ id: o.id, at: Date.now() }); } }}
          renderInput={(p) => <TextField {...p} label={t('data.erd.search')} />} />
        <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)} aria-label={t('data.erd.view')}>
          <ToggleButton value="diagram">{t('data.erd.viewDiagram')}</ToggleButton>
          <ToggleButton value="table">{t('data.erd.viewTable')}</ToggleButton>
        </ToggleButtonGroup>
        {g && (
          <Typography sx={{ fontSize: 13, color: 'text.secondary', ml: 'auto' }}>
            {t('data.erd.counts', { entities: g.entities.length, relationships: g.relationships.length, stubs: g.outside_refs.length })}
          </Typography>)}
      </WrapperBox>
      {empty && <Alert severity="info">{t(area ? 'data.erd.emptyArea' : 'data.erd.empty')}</Alert>}
      {g && !empty && view === 'diagram' && (
        <ErdContext.Provider value={ctx}>
          <ErdMarkers />
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1 }}>
            {t(canEdit ? 'data.erd.help' : 'data.erd.helpReadOnly')}</Typography>
          <Box sx={{ [`& .react-flow__node.${DIM}`]: { opacity: 0.2 }, [`& .react-flow__edge.${DIM}`]: { opacity: 0.1 } }}>
            <ModelCanvas kind="erd" nodes={nodes} edges={edges} nodeTypes={ERD_NODE_TYPES} edgeTypes={ERD_EDGE_TYPES}
              onNodesChange={handleNodesChange} draggable={canEdit} onNodeClick={onNodeClick} onPaneClick={onPaneClick}
              onNodeDoubleClick={onNodeDoubleClick} minimap height="72vh"
              ariaLabel={t('data.erd.canvasLabel', { scope: scopeName })}>
              <FocusOn request={focusRequest} />
              <FitOnArea laid={laidScope} />
            </ModelCanvas>
          </Box>
        </ErdContext.Provider>
      )}
      {g && !empty && view === 'table' && <ErdTable g={g} projectId={projectId} />}
      <ConfirmDialog open={confirmReset} title={t('data.erd.resetTitle')} body={t('data.erd.resetBody')}
        confirmLabel={t('data.erd.reset')} busy={reset.isPending}
        onClose={() => setConfirmReset(false)} onConfirm={() => reset.mutate()} />
    </Page>
  );
}
