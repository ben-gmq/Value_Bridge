import { forwardRef, useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, IconButton, InputAdornment, Snackbar, Stack, Switch, TextField, Tooltip,
  Typography, useMediaQuery } from '@mui/material';
import ArrowBackRounded from '@mui/icons-material/ArrowBackRounded';
import AddRounded from '@mui/icons-material/AddRounded';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import SearchIcon from '@mui/icons-material/Search';
import FlowIcon from '@mui/icons-material/AccountTreeOutlined';
import { RichTreeView } from '@mui/x-tree-view/RichTreeView';
import { TreeItem } from '@mui/x-tree-view/TreeItem';
import { useTreeItemModel } from '@mui/x-tree-view/hooks';
import { errorText, isStale } from '../../api/client';
import { bfcApi, brApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { Page } from '../../components/Page';
import { Card, Code, InfoTip, LevelBadge, Segmented, Tag } from '../../components/kit';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, ShowRetired, blankToNull } from './chartKit';
import { NodePanel } from './NodePanel';
import { CopyChartButton } from './StepDfd';
import { DfdLight, useDfdRule } from './DfdLight';

// Business function chart (§7.2, mockup 01). The tree arrives flat, ordered by hier_code; it is
// built here from parent_bfc_node_id. Codes, levels and positions are derived by the server.

function buildTree(rows) {
  const byId = new Map(rows.map((r) => [r.bfc_node_id, { ...r, children: [] }]));
  const roots = [];
  for (const n of byId.values()) {
    const parent = n.parent_bfc_node_id != null ? byId.get(n.parent_bfc_node_id) : null;
    (parent ? parent.children : roots).push(n);   // a parent hidden as retired → shown at the top
  }
  return roots;
}

// Matching nodes plus every ancestor, so a hit is never shown without its chain.
function filterRows(rows, text) {
  const q = text.trim().toLowerCase();
  if (!q) return rows;
  const byId = new Map(rows.map((r) => [r.bfc_node_id, r]));
  const keep = new Set();
  for (const r of rows) {
    if (r.hier_code.toLowerCase().includes(q) || r.node_name.toLowerCase().includes(q)) {
      for (let n = r; n && !keep.has(n.bfc_node_id); n = byId.get(n.parent_bfc_node_id)) keep.add(n.bfc_node_id);
    }
  }
  return rows.filter((r) => keep.has(r.bfc_node_id));
}

// D-68 / Q-13 (S13-2): every process that is not Ready — red (a rule element missing: blocks the freeze) and yellow (a
// recommended element missing: passes it) — with its ancestors so it is never shown without its chain.
function notReadyRows(rows) {
  const byId = new Map(rows.map((r) => [r.bfc_node_id, r]));
  const keep = new Set();
  for (const r of rows) {
    if (!r.dfd_light || r.dfd_light === 'READY') continue;
    for (let n = r; n && !keep.has(n.bfc_node_id); n = byId.get(n.parent_bfc_node_id)) keep.add(n.bfc_node_id);
  }
  return rows.filter((r) => keep.has(r.bfc_node_id));
}

// How many functions sit below each node (in what is loaded) — the muted count at the row's right.
function countBelow(rows) {
  const byId = new Map(rows.map((r) => [r.bfc_node_id, r]));
  const n = new Map();
  for (const r of rows) {
    for (let p = byId.get(r.parent_bfc_node_id); p; p = byId.get(p.parent_bfc_node_id)) {
      n.set(p.bfc_node_id, (n.get(p.bfc_node_id) ?? 0) + 1);
    }
  }
  return n;
}

// A name that ellipsises in a narrow column and shows in full on hover — only when it is actually cut.
function TruncName({ name, sx }) {
  const ref = useRef(null);
  const [cut, setCut] = useState(false);
  return (
    <Tooltip title={cut ? name : ''} placement="top-start" enterDelay={400}>
      <Box component="span" ref={ref} onMouseEnter={() => setCut(ref.current ? ref.current.scrollWidth > ref.current.clientWidth : false)}
        sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, ...sx }}>{name}</Box>
    </Tooltip>
  );
}

function NodeLabel({ node }) {
  const { projectId } = useParams();
  const [params] = useSearchParams();
  const selected = params.get('node') === String(node.bfc_node_id);
  const flowable = node.is_active && !node.is_process && node.level_no >= FIRST_PROCESS_LEVEL - 1;
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', minWidth: 0, minHeight: 28 }}>
      <Box component="span" sx={{ flex: 'none', display: 'inline-flex' }}>
        <LevelBadge level={node.level_no} label={t('processes.levelN', { n: node.level_no })} /></Box>
      <Code tone={selected ? 'purple' : 'muted'} sx={{ fontSize: 12.5, flex: 'none' }}>{node.hier_code}</Code>
      <TruncName name={node.node_name} sx={{ flex: '0 1 auto', flexShrink: 1, minWidth: '10ch', fontSize: 13.5, fontWeight: node.level_no <= 2 || selected ? 700 : 500,
        color: node.is_active ? 'text.primary' : 'text.disabled' }} />
      {/* The BR chip gives way first (10e UAT): the name keeps 10ch and the light stays whole */}
      {node.is_process && <Box component="span" className="vb-row-extra" sx={{ flex: '0 1000 auto', minWidth: 0, overflow: 'hidden', display: 'inline-flex' }}>
        <Tag tone="purple" size="lg" sx={{ height: 22, display: 'inline-block', lineHeight: '22px', maxWidth: '100%',
          overflow: 'hidden', textOverflow: 'ellipsis' }}>{node.br_number ?? t('processes.processChip')}</Tag></Box>}
      {!node.is_active && <Tag tone="neutral" size="lg" sx={{ height: 22, flex: 'none' }}>{t('processes.retiredChip')}</Tag>}
      {flowable && (
        <Tooltip title={t('processes.openFlow')}>
          <IconButton size="small" className="vb-row-extra" component={RouterLink} to={links.dfd(projectId, node.bfc_node_id)}
            aria-label={t('processes.openFlowFor', { name: node.node_name })} sx={{ flex: 'none', p: 0.25 }}
            onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
            <FlowIcon sx={{ fontSize: 17 }} /></IconButton>
        </Tooltip>
      )}
      <Box sx={{ flexGrow: 1 }} />
      {/* D-68: always visible on a process row (not hover-only like the BR chip); icon-only so the name keeps the width (10e) */}
      {node.is_process && node.dfd_light && <Box component="span" sx={{ flex: 'none', display: 'inline-flex' }}>
        <DfdLight light={node.dfd_light} missing={node.dfd_missing} advised={node.dfd_advised ?? []} size="icon" /></Box>}
      {node.below > 0 && <Box component="span" sx={(th) => ({ fontFamily: MONO, fontSize: 12.5, flex: 'none',
        color: th.vars.palette.brand.muted })}>{node.below}</Box>}
    </Stack>
  );
}

// The tree rows as the mockup draws them: 36px rounded rows, the selection in purple tint with a violet hairline.
const treeSx = (th) => ({
  display: 'flex', flexDirection: 'column', gap: '2px',
  '& .MuiTreeItem-content': { minHeight: 36, borderRadius: '14px', py: 0.25, pr: 1.25 },
  '& .MuiTreeItem-content:hover': { bgcolor: th.vars.palette.brand.selected },
  '& .MuiTreeItem-content[data-selected], & .MuiTreeItem-content[data-selected]:hover, & .MuiTreeItem-content[data-selected][data-focused]': {
    bgcolor: th.vars.palette.brand.purpleTint, outline: `1px solid ${th.vars.palette.brand.ftcViolet}` },
  '& .MuiTreeItem-iconContainer': { color: th.vars.palette.brand.muted },
  // D-63: the BR chip and the flow icon show on hover, focus or selection only, so names get the width
  '& .vb-row-extra': { display: 'none' },
  '& .MuiTreeItem-content:hover .vb-row-extra, & .MuiTreeItem-content:focus-within .vb-row-extra, & .MuiTreeItem-content[data-focused] .vb-row-extra, & .MuiTreeItem-content[data-selected] .vb-row-extra':
    { display: 'inline-flex' },
  '& .MuiTreeItem-groupTransition': { display: 'flex', flexDirection: 'column', gap: '2px' },
});

const NodeItem = forwardRef(function NodeItem(props, ref) {
  const node = useTreeItemModel(props.itemId);
  return <TreeItem {...props} ref={ref} label={node ? <NodeLabel node={node} /> : props.label} />;
});

function AddNodeDialog({ projectId, parent, bfcSet, onDone, onClose }) {
  const level = parent ? parent.level_no + 1 : 1;
  const [name, setName] = useState('');
  const [purpose, setPurpose] = useState('');
  const [isProcess, setIsProcess] = useState(false);
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => bfcApi.create(projectId, { parent_bfc_node_id: parent?.bfc_node_id ?? null,
      node_name: name.trim(), purpose_desc: blankToNull(purpose), is_process: isProcess, bfc_set: bfcSet }),
    onSuccess: (row) => { onDone(row); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{parent ? t('processes.addChildTitle', { parent: `${parent.hier_code} ${parent.node_name}` })
        : t('processes.addTopTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.newLevel', { n: level })}</Typography>
          <TextField id="add-node-name" label={t('processes.name')} required autoFocus value={name}
            onChange={(e) => setName(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <TextField id="add-node-purpose" label={t('processes.purpose')} multiline minRows={2} value={purpose}
            onChange={(e) => setPurpose(e.target.value)} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          {level >= FIRST_PROCESS_LEVEL && (
            <Box>
              <FormControlLabel label={t('processes.isProcess')}
                control={<Checkbox id="add-node-process" checked={isProcess} onChange={(e) => setIsProcess(e.target.checked)} />} />
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.addProcessHelp')}</Typography>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!name.trim() || m.isPending}
          onClick={() => { setError(''); m.mutate(); }}>{t('common.create')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// Leaving with unsaved text asks first (DR 10d-1): what is unsaved, then Save / Discard / Keep editing.
function LeaveDialog({ pending, onStay, onDiscard, onSave, saving }) {
  if (!pending) return null;
  const { count, draft, name } = pending.state;
  return (
    <Dialog open onClose={onStay} maxWidth="xs" fullWidth>
      <DialogTitle>{t('processes.leave.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        {count > 0 && <Typography>{t('processes.leave.body', { name, n: count })}</Typography>}
        {draft && <Typography>{t('processes.leave.draft')}</Typography>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onStay}>{t('processes.leave.stay')}</Button>
        <Button color="warning" onClick={onDiscard}>{t('processes.leave.discard')}</Button>
        {count > 0 && <Button variant="contained" disabled={saving} onClick={onSave}>{t('processes.leave.save')}</Button>}
      </DialogActions>
    </Dialog>
  );
}

export default function ProcessesPage() {
  const canEdit = useCanEdit();
  const { projectId } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const selectedId = params.get('node');
  const { isOn } = useComponents(projectId);
  const wide = useMediaQuery('(min-width:1100px)');      // D-63: side by side from 1100px (UAT: the panel is too narrow at 900), one at a time below
  // D-47: the to-be chart always; the as-is chart only while its component is on.
  const bfcSet = params.get('set') === 'AS_IS' && isOn('AS_IS') ? 'AS_IS' : 'TO_BE';
  const [showRetired, setShowRetired] = useState(false);
  const [filter, setFilter] = useState('');
  const [notReadyOnly, setNotReadyOnly] = useState(false);
  const [expanded, setExpanded] = useState(null);          // null → everything expanded
  const [adding, setAdding] = useState(null);              // { parent }
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const guardRef = useRef(null);                           // the open panel's unsaved state (NodePanel)
  const [leave, setLeave] = useState(null);                // { state, go }
  const [leaveSaving, setLeaveSaving] = useState(false);
  const treeBoxRef = useRef(null);

  // Every way off the open panel goes through here: unsaved text or a half-filled tile form asks first.
  // A name still being typed in a tile editor saves when its field loses focus (SP-1), and every in-page way off
  // the panel (a tree click, Save & next) blurs it first — so only typed panel text asks here (10g UAT check 4).
  // Browser Back/Forward and closing the tab can leave without a blur, so those still count the typed name.
  const guarded = (go) => {
    const state = guardRef.current?.get();
    if (state && state.count > 0) setLeave({ state: { ...state, draft: false }, go });
    else go();
  };

  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: showRetired, set: bfcSet }],
    queryFn: () => bfcApi.tree(projectId, showRetired, bfcSet) });
  const brsQ = useQuery({ queryKey: [...keys.brs(projectId), { retired: true }], queryFn: () => brApi.list(projectId, true) });
  const rows = useMemo(() => treeQ.data ?? [], [treeQ.data]);
  const rowById = useMemo(() => new Map(rows.map((r) => [String(r.bfc_node_id), r])), [rows]);
  const dfdOn = bfcSet === 'AS_IS' ? isOn('AS_IS') : isOn('TO_BE_DFD');     // the chart's DFD component: the light applies
  const { ruleFor } = useDfdRule(projectId);                                // D-70: which fields carry a DFD mark
  const lightFilter = dfdOn && notReadyOnly;
  const items = useMemo(() => {
    const below = countBelow(rows);
    const shown = filterRows(lightFilter ? notReadyRows(rows) : rows, filter);
    return buildTree(shown.map((r) => ({ ...r, below: below.get(r.bfc_node_id) ?? 0 })));
  }, [rows, filter, lightFilter]);
  const selected = selectedId ? rowById.get(selectedId) ?? null : null;
  const filtering = filter.trim() !== '' || lightFilter;
  const expandedItems = filtering || expanded === null ? rows.map((r) => String(r.bfc_node_id)) : expanded;

  const selectNow = (id) => {
    setError('');
    const next = new URLSearchParams(params);
    if (id) next.set('node', id); else next.delete('node');
    setParams(next);
  };
  const select = (id) => { if (String(id ?? '') !== String(selectedId ?? '')) guarded(() => selectNow(id)); };
  const chooseSet = (v) => guarded(() => { const next = new URLSearchParams(); if (v === 'AS_IS') next.set('set', 'AS_IS'); setParams(next); });

  // A link elsewhere (the rail, a breadcrumb, a chip in the panel) is asked about too. The app uses a plain
  // BrowserRouter, so there is no route blocker: in-app links are caught at the document, before React Router.
  useEffect(() => {
    const onClick = (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest?.('a[href]');
      if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
      const url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === location.pathname && url.search === location.search) return;
      const state = guardRef.current?.get();
      if (!state || (state.count === 0 && !state.draft)) return;
      e.preventDefault(); e.stopPropagation();
      setLeave({ state, go: () => navigate(url.pathname + url.search + url.hash) });
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [location.pathname, location.search, navigate]);

  // Back / Forward too (sara L5). A capture listener on window runs before React Router's own popstate
  // listener, so it can stop the move: it puts the current entry back, asks, and on Save or Discard goes to
  // where the button was taking the user.
  const here = useRef(null);
  useEffect(() => {
    here.current = { url: location.pathname + location.search + location.hash, state: window.history.state };
  }, [location.pathname, location.search, location.hash]);
  useEffect(() => {
    const onPop = (e) => {
      const state = guardRef.current?.get();
      if (!state || (state.count === 0 && !state.draft) || !here.current) return;
      e.stopImmediatePropagation();
      const target = window.location.pathname + window.location.search + window.location.hash;
      window.history.pushState(here.current.state, '', here.current.url);
      setLeave({ state, go: () => navigate(target) });
    };
    window.addEventListener('popstate', onPop, true);
    return () => window.removeEventListener('popstate', onPop, true);
  }, [navigate]);

  // One at a time below 1100px: a newly opened panel starts at its top.
  useEffect(() => { if (!wide && selectedId) window.scrollTo({ top: 0 }); }, [wide, selectedId]);

  // The selected row stays in view in its own scrolling column.
  useEffect(() => {
    if (!wide || !selectedId) return;
    const el = treeBoxRef.current?.querySelector('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [wide, selectedId, rows.length]);

  // Up / down among the live siblings; the server re-codes every shifted subtree (S1-2).
  const siblings = selected?.is_active ? rows.filter((r) => r.is_active
    && r.parent_bfc_node_id === selected.parent_bfc_node_id).sort((a, b) => a.seq_no - b.seq_no) : [];
  const pos = selected ? siblings.findIndex((s) => s.bfc_node_id === selected.bfc_node_id) + 1 : 0;
  const reorder = useMutation({
    // The freshest version we know: the panel's copy is newer than the tree's right after a save.
    mutationFn: (to) => bfcApi.reorder(selected.bfc_node_id, { new_seq_no: to, row_version: Math.max(selected.row_version,
      qc.getQueryData(keys.node(selected.bfc_node_id))?.row_version ?? 0) }),
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: keys.tree(projectId) });
      qc.setQueryData(keys.node(row.bfc_node_id), row);
      setNotice(t('processes.reordered', { code: row.hier_code }));
    },
    onError: (err) => {
      qc.invalidateQueries({ queryKey: keys.tree(projectId) });
      setError(isStale(err) ? t('processes.staleAction') : errorText(err, t('common.saveFailed')));
    },
  });

  // The live requirement, else the latest retired one — so a retired BR can still be reached.
  const nodeBrs = selected ? (brsQ.data ?? []).filter((b) => b.bfc_node_id === selected.bfc_node_id) : [];
  const br = nodeBrs.find((b) => b.is_active) ?? nodeBrs[nodeBrs.length - 1] ?? null;
  const path = useMemo(() => {
    const out = [];
    for (let p = selected && rowById.get(String(selected.parent_bfc_node_id)); p && out.length < 10;
      p = rowById.get(String(p.parent_bfc_node_id))) out.unshift(p.node_name);
    return out;
  }, [selected, rowById]);
  const hasChildren = Boolean(selected && rows.some((r) => r.is_active && r.parent_bfc_node_id === selected.bfc_node_id));
  // D-57: the live processes anywhere below a function, in chart order, for its "Open a process below".
  const processesBelow = useMemo(() => {
    if (!selected || selected.is_process) return [];
    const under = (r) => { for (let p = rowById.get(String(r.parent_bfc_node_id)); p; p = rowById.get(String(p.parent_bfc_node_id))) {
      if (p.bfc_node_id === selected.bfc_node_id) return true; } return false; };
    return rows.filter((r) => r.is_active && r.is_process && under(r));
  }, [selected, rows, rowById]);
  // "Save & next process": the next live process in chart order (rows arrive ordered by hier_code).
  const nextProcess = selected ? rows.slice(rows.findIndex((r) => r.bfc_node_id === selected.bfc_node_id) + 1)
    .find((r) => r.is_process && r.is_active) : null;
  const canAddChild = Boolean(selected?.is_active && !selected.is_process);

  const hierarchyAction = (
    <Stack direction="row" spacing={0.5} aria-hidden>
      {[1, 2, 3, 4, 5].map((l) => <LevelBadge key={l} level={l} label={t('processes.levelN', { n: l })} />)}
    </Stack>
  );
  // Each column scrolls on its own and stays in view while the page scrolls (D-63).
  const column = wide ? { position: 'sticky', top: 12, height: 'calc(100dvh - 24px)', minHeight: 420 } : {};
  const showTree = wide || !selected;
  const showPanel = wide || Boolean(selected);

  return (
    <Page title={t('processes.title')} subtitle={t(bfcSet === 'AS_IS' ? 'processes.subtitleAsIs' : 'processes.subtitle')}
      crumb={selected ? `${selected.hier_code} ${selected.node_name}` : undefined}
      error={error || (treeQ.error && errorText(treeQ.error)) || (brsQ.error && errorText(brsQ.error))}
      actions={<>
        {isOn('AS_IS') && (
          <Segmented label={t('processes.chart.label')} value={bfcSet} onChange={chooseSet}
            options={['TO_BE', 'AS_IS'].map((v) => ({ value: v, label: t(`processes.chart.${v}`) }))} />
        )}
        {canEdit && <Button variant="contained" startIcon={<AddRounded />}
          onClick={() => { setError(''); setAdding({ parent: null }); }}>{t('processes.addTop')}</Button>}
      </>}>
      <Box sx={{ display: 'grid', gap: 2, alignItems: 'start',
        gridTemplateColumns: wide ? 'clamp(340px, 32%, 440px) minmax(0,1fr)' : 'minmax(0,1fr)' }}>
        {showTree && (
          <Card title={t('processes.hierarchy')} action={hierarchyAction} sx={column}
            bodySx={{ gap: 1.25, px: 1.5, minHeight: 0, ...(wide ? { overflow: 'hidden' } : {}) }}>
            <Box sx={{ px: 1, display: 'flex', flexDirection: 'column', gap: 1, flex: 'none' }}>
              {/* 10e (VB-005 UAT 10d-2): search and the edit actions share one line, the filters the next — nothing wraps at 1440 */}
              <Stack direction="row" spacing={0.25} sx={{ alignItems: 'center', minWidth: 0 }}>
                <TextField fullWidth size="small" id="bfc-filter" placeholder={t('processes.filter')} value={filter}
                  onChange={(e) => setFilter(e.target.value)} sx={{ minWidth: 0, mr: 0.75 }}
                  slotProps={{ htmlInput: { 'aria-label': t('processes.filter') },
                    input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }} />
                {canEdit && <>
                  <Tooltip title={t('processes.addChild')}>
                    <span>
                      <IconButton size="small" aria-label={t('processes.addChild')} disabled={!canAddChild}
                        onClick={() => { setError(''); setAdding({ parent: selected }); }}><AddRounded fontSize="small" /></IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={t('processes.moveUp')}>
                    <span>
                      <IconButton size="small" aria-label={t('processes.moveUp')} disabled={pos <= 1 || reorder.isPending}
                        onClick={() => reorder.mutate(pos - 1)}><ArrowUpwardIcon fontSize="small" /></IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={t('processes.moveDown')}>
                    <span>
                      <IconButton size="small" aria-label={t('processes.moveDown')}
                        disabled={!pos || pos >= siblings.length || reorder.isPending}
                        onClick={() => reorder.mutate(pos + 1)}><ArrowDownwardIcon fontSize="small" /></IconButton>
                    </span>
                  </Tooltip>
                  <InfoTip title={t('processes.reorderHelp')} />
                </>}
              </Stack>
              <Stack direction="row" useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap', columnGap: 1, rowGap: 0.5 }}>
                <ShowRetired id="bfc-show-retired" checked={showRetired} onChange={setShowRetired} />
                {dfdOn && (
                  <Stack direction="row" sx={{ alignItems: 'center' }}>
                    <FormControlLabel label={t('processes.dfdLight.notReadyOnly')} sx={{ mr: 0 }}
                      control={<Switch id="bfc-not-ready" checked={notReadyOnly} onChange={(e) => setNotReadyOnly(e.target.checked)} />} />
                    <InfoTip title={t('processes.dfdLight.notReadyOnlyInfo')} />
                  </Stack>)}
              </Stack>
              {canEdit && selected?.is_process && (
                <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.noChildOfProcess')}</Typography>
              )}
            </Box>
            {!treeQ.isLoading && rows.length === 0 && (
              <Box sx={{ px: 1, py: 2 }}>
                <Typography sx={{ color: 'text.secondary', mb: 1.5 }}>
                  {t(bfcSet === 'AS_IS' ? 'processes.emptyAsIs' : 'processes.empty')}</Typography>
                {canEdit && !showRetired && isOn('AS_IS') && (
                  <CopyChartButton projectId={projectId} toSet={bfcSet} fromSet={bfcSet === 'AS_IS' ? 'TO_BE' : 'AS_IS'}
                    onCopied={() => { qc.invalidateQueries({ queryKey: keys.tree(projectId) });
                      qc.invalidateQueries({ queryKey: keys.brs(projectId) }); setNotice(t('processes.chart.copied')); }} />)}
              </Box>
            )}
            {filtering && rows.length > 0 && items.length === 0 && (
              <Typography sx={{ color: 'text.secondary', px: 1, py: 2 }}>
                {t(lightFilter && filter.trim() === '' ? 'processes.dfdLight.allReady' : 'processes.noMatch')}</Typography>
            )}
            <Box ref={treeBoxRef} sx={{ minWidth: 0, minHeight: 0, flex: 1, overflowX: 'hidden', overflowY: wide ? 'auto' : 'visible' }}>
              <RichTreeView items={items} getItemId={(n) => String(n.bfc_node_id)} getItemLabel={(n) => `${n.hier_code} ${n.node_name}`}
                getItemChildren={(n) => n.children} slots={{ item: NodeItem }}
                selectedItems={selectedId} onSelectedItemsChange={(_, id) => select(id)}
                expandedItems={expandedItems} onExpandedItemsChange={(_, ids) => { if (!filtering) setExpanded(ids); }}
                expansionTrigger="iconContainer" sx={treeSx} />
            </Box>
          </Card>
        )}
        {showPanel && (
          <Box sx={{ ...column, display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
            {!wide && (
              <Button startIcon={<ArrowBackRounded />} sx={{ alignSelf: 'flex-start' }} onClick={() => select(null)}>
                {t('processes.backChart')}</Button>)}
            {selected ? (
              <Box sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                <NodePanel key={selected.bfc_node_id} projectId={projectId} nodeId={selected.bfc_node_id} wide={wide}
                  path={path} br={br} dfd={{ light: selected.dfd_light, missing: selected.dfd_missing ?? [], advised: selected.dfd_advised ?? [], rule: ruleFor(bfcSet) ?? [] }} hasChildren={hasChildren} processesBelow={processesBelow}
                  onOpenNode={(id) => select(String(id))} showRetired={showRetired} guardRef={guardRef}
                  onNext={nextProcess ? () => selectNow(String(nextProcess.bfc_node_id)) : null}
                  onNotice={setNotice} onGone={() => selectNow(null)} />
              </Box>
            ) : (
              <Card>
                <Typography sx={{ color: 'text.secondary' }}>
                  {selectedId && !treeQ.isLoading ? t('processes.notInTree') : t('processes.pickNode')}</Typography>
              </Card>
            )}
          </Box>
        )}
      </Box>
      {adding && (
        <AddNodeDialog projectId={projectId} parent={adding.parent} bfcSet={bfcSet} onClose={() => setAdding(null)}
          onDone={(row) => {
            qc.invalidateQueries({ queryKey: keys.tree(projectId) });
            qc.invalidateQueries({ queryKey: keys.brs(projectId) });
            qc.invalidateQueries({ queryKey: keys.flows(projectId) });     // UAT 7c: the gaps panel and the DFDs
            if (expanded && adding.parent) setExpanded([...expanded, String(adding.parent.bfc_node_id)]);
            select(String(row.bfc_node_id));
            setNotice(t('processes.created', { code: row.hier_code }));
          }} />
      )}
      <LeaveDialog pending={leave} saving={leaveSaving} onStay={() => setLeave(null)}
        onDiscard={() => { const go = leave.go; guardRef.current?.get().discardAll(); setLeave(null); go(); }}
        onSave={async () => {
          setLeaveSaving(true);
          const ok = await guardRef.current?.get().saveAll();
          setLeaveSaving(false);
          const go = leave.go;
          setLeave(null);
          if (ok) go();                 // a refusal keeps the panel, its edits and its message
        }} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3500} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
