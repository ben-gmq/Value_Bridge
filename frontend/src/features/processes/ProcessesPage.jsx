import { forwardRef, useMemo, useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, IconButton, InputAdornment, Snackbar, Stack, TextField, Tooltip,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import SwapVertRounded from '@mui/icons-material/SwapVertRounded';
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
import { Card, Code, LevelBadge, Segmented, Tag } from '../../components/kit';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, ShowRetired, blankToNull } from './chartKit';
import { NodePanel } from './NodePanel';
import { CopyChartButton } from './StepDfd';

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

function NodeLabel({ node }) {
  const { projectId } = useParams();
  const [params] = useSearchParams();
  const selected = params.get('node') === String(node.bfc_node_id);
  const flowable = node.is_active && !node.is_process && node.level_no >= FIRST_PROCESS_LEVEL - 1;
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0, minHeight: 28 }}>
      <LevelBadge level={node.level_no} label={t('processes.levelN', { n: node.level_no })} />
      <Code tone={selected ? 'purple' : 'muted'} sx={{ fontSize: 12, flex: 'none' }}>{node.hier_code}</Code>
      <Box component="span" sx={{ fontSize: 13.5, fontWeight: node.level_no <= 2 || selected ? 700 : 500,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0,
        color: node.is_active ? 'text.primary' : 'text.disabled' }}>{node.node_name}</Box>
      {node.is_process && <Tag tone="purple" sx={{ height: 20, flex: 'none', fontSize: 11.5 }}>
        {node.br_number ?? t('processes.processChip')}</Tag>}
      {!node.is_active && <Tag tone="neutral" sx={{ height: 20, flex: 'none', fontSize: 11.5 }}>{t('processes.retiredChip')}</Tag>}
      {flowable && (
        <Tooltip title={t('processes.openFlow')}>
          <IconButton size="small" component={RouterLink} to={links.dfd(projectId, node.bfc_node_id)}
            aria-label={t('processes.openFlowFor', { name: node.node_name })} sx={{ flex: 'none', p: 0.25 }}
            onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
            <FlowIcon sx={{ fontSize: 17 }} /></IconButton>
        </Tooltip>
      )}
      <Box sx={{ flexGrow: 1 }} />
      {node.below > 0 && <Box component="span" sx={(th) => ({ fontFamily: MONO, fontSize: 12, flex: 'none',
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

export default function ProcessesPage() {
  const canEdit = useCanEdit();
  const { projectId } = useParams();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selectedId = params.get('node');
  const { isOn } = useComponents(projectId);
  // D-47: the to-be chart always; the as-is chart only while its component is on.
  const bfcSet = params.get('set') === 'AS_IS' && isOn('AS_IS') ? 'AS_IS' : 'TO_BE';
  const chooseSet = (v) => { const next = new URLSearchParams(); if (v === 'AS_IS') next.set('set', 'AS_IS'); setParams(next); };
  const [showRetired, setShowRetired] = useState(false);
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState(null);          // null → everything expanded
  const [adding, setAdding] = useState(null);              // { parent }
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: showRetired, set: bfcSet }],
    queryFn: () => bfcApi.tree(projectId, showRetired, bfcSet) });
  const brsQ = useQuery({ queryKey: [...keys.brs(projectId), { retired: true }], queryFn: () => brApi.list(projectId, true) });
  const rows = useMemo(() => treeQ.data ?? [], [treeQ.data]);
  const rowById = useMemo(() => new Map(rows.map((r) => [String(r.bfc_node_id), r])), [rows]);
  const items = useMemo(() => {
    const below = countBelow(rows);
    return buildTree(filterRows(rows, filter).map((r) => ({ ...r, below: below.get(r.bfc_node_id) ?? 0 })));
  }, [rows, filter]);
  const selected = selectedId ? rowById.get(selectedId) ?? null : null;
  const filtering = filter.trim() !== '';
  const expandedItems = filtering || expanded === null ? rows.map((r) => String(r.bfc_node_id)) : expanded;

  const select = (id) => {
    setError('');
    const next = new URLSearchParams(params);
    if (id) next.set('node', id); else next.delete('node');
    setParams(next);
  };

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
  const parent = selected?.parent_bfc_node_id != null ? rowById.get(String(selected.parent_bfc_node_id)) : null;
  const canAddChild = Boolean(selected?.is_active && !selected.is_process);

  const hierarchyAction = (
    <Stack direction="row" spacing={0.5} aria-hidden>
      {[1, 2, 3, 4, 5].map((l) => <LevelBadge key={l} level={l} label={t('processes.levelN', { n: l })} />)}
    </Stack>
  );

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
      {params.get('pick') === 'dfd' && (
        <Alert severity="info" sx={{ mb: 2 }} onClose={() => { const next = new URLSearchParams(params); next.delete('pick'); setParams(next); }}>
          {t('processes.pickDfd')}</Alert>
      )}
      <Box sx={{ display: 'grid', gap: 2, alignItems: 'stretch',
        gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(300px,400px) minmax(0,1fr)' } }}>
        <Card title={t('processes.hierarchy')} action={hierarchyAction} bodySx={{ gap: 1.25, px: 1.5 }}>
          <Box sx={{ px: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
            <TextField fullWidth size="small" id="bfc-filter" placeholder={t('processes.filter')} value={filter}
              onChange={(e) => setFilter(e.target.value)}
              slotProps={{ htmlInput: { 'aria-label': t('processes.filter') },
                input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }} />
            <Stack direction="row" useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 0.5 }}>
              <ShowRetired id="bfc-show-retired" checked={showRetired} onChange={setShowRetired} />
              <Box sx={{ flexGrow: 1 }} />
              {canEdit && <>
                <Button size="small" variant="outlined" startIcon={<AddRounded />} disabled={!canAddChild}
                  onClick={() => { setError(''); setAdding({ parent: selected }); }}>{t('processes.addChild')}</Button>
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
              </>}
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
            <Typography sx={{ color: 'text.secondary', px: 1, py: 2 }}>{t('processes.noMatch')}</Typography>
          )}
          <Box sx={{ minWidth: 0, overflowX: 'auto' }}>
            <RichTreeView items={items} getItemId={(n) => String(n.bfc_node_id)} getItemLabel={(n) => `${n.hier_code} ${n.node_name}`}
              getItemChildren={(n) => n.children} slots={{ item: NodeItem }}
              selectedItems={selectedId} onSelectedItemsChange={(_, id) => select(id)}
              expandedItems={expandedItems} onExpandedItemsChange={(_, ids) => { if (!filtering) setExpanded(ids); }}
              expansionTrigger="iconContainer" sx={treeSx} />
          </Box>
          {canEdit && (
            <Box sx={(th) => ({ mt: 'auto', mx: 1, pt: 1, display: 'flex', alignItems: 'flex-start', gap: 1,
              color: th.vars.palette.brand.muted, fontSize: 12.5 })}>
              <SwapVertRounded sx={{ fontSize: 16, mt: '1px' }} />{t('processes.reorderHelp')}
            </Box>
          )}
        </Card>
        {selected ? (
          <NodePanel key={selected.bfc_node_id} projectId={projectId} nodeId={selected.bfc_node_id}
            parent={parent} br={br} showRetired={showRetired} onNotice={setNotice} onGone={() => select(null)} />
        ) : (
          <Card>
            <Typography sx={{ color: 'text.secondary' }}>
              {selectedId && !treeQ.isLoading ? t('processes.notInTree') : t('processes.pickNode')}</Typography>
          </Card>
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
      <Snackbar open={Boolean(notice)} autoHideDuration={3500} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
