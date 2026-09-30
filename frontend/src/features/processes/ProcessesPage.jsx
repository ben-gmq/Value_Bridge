import { forwardRef, useMemo, useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, Grid, IconButton, InputAdornment, Snackbar, Stack, TextField, Tooltip,
  Typography } from '@mui/material';
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
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, LevelBadge, Mono, ShowRetired, blankToNull } from './chartKit';
import { NodePanel } from './NodePanel';

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

function NodeLabel({ node }) {
  const { projectId } = useParams();
  const flowable = node.is_active && !node.is_process && node.level_no >= FIRST_PROCESS_LEVEL - 1;
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0, py: 0.25 }}>
      <LevelBadge level={node.level_no} process={node.is_process} />
      <Mono sx={{ color: 'text.secondary', flex: 'none' }}>{node.hier_code}</Mono>
      <Box component="span" sx={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        color: node.is_active ? 'text.primary' : 'text.disabled' }}>{node.node_name}</Box>
      {node.is_process && (
        <Chip size="small" variant="outlined" color="primary" sx={{ height: 20, flex: 'none' }}
          label={node.br_number ?? t('processes.processChip')} />
      )}
      {!node.is_active && <Chip size="small" variant="outlined" sx={{ height: 20, flex: 'none' }} label={t('processes.retiredChip')} />}
      {flowable && (
        <Tooltip title={t('processes.openFlow')}>
          <IconButton size="small" component={RouterLink} to={links.flow(projectId, node.bfc_node_id)}
            aria-label={t('processes.openFlowFor', { name: node.node_name })} sx={{ flex: 'none', p: 0.25 }}
            onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
            <FlowIcon fontSize="small" /></IconButton>
        </Tooltip>
      )}
    </Stack>
  );
}

const NodeItem = forwardRef(function NodeItem(props, ref) {
  const node = useTreeItemModel(props.itemId);
  return <TreeItem {...props} ref={ref} label={node ? <NodeLabel node={node} /> : props.label} />;
});

function AddNodeDialog({ projectId, parent, onDone, onClose }) {
  const level = parent ? parent.level_no + 1 : 1;
  const [name, setName] = useState('');
  const [purpose, setPurpose] = useState('');
  const [isProcess, setIsProcess] = useState(false);
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => bfcApi.create(projectId, { parent_bfc_node_id: parent?.bfc_node_id ?? null,
      node_name: name.trim(), purpose_desc: blankToNull(purpose), is_process: isProcess }),
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
  const [showRetired, setShowRetired] = useState(false);
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState(null);          // null → everything expanded
  const [adding, setAdding] = useState(null);              // { parent }
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: showRetired }],
    queryFn: () => bfcApi.tree(projectId, showRetired) });
  const brsQ = useQuery({ queryKey: [...keys.brs(projectId), { retired: true }], queryFn: () => brApi.list(projectId, true) });
  const rows = useMemo(() => treeQ.data ?? [], [treeQ.data]);
  const rowById = useMemo(() => new Map(rows.map((r) => [String(r.bfc_node_id), r])), [rows]);
  const items = useMemo(() => buildTree(filterRows(rows, filter)), [rows, filter]);
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

  return (
    <Page title={t('processes.title')} subtitle={t('processes.subtitle')}
      error={error || (treeQ.error && errorText(treeQ.error)) || (brsQ.error && errorText(brsQ.error))}
      actions={canEdit && <Button variant="contained" onClick={() => { setError(''); setAdding({ parent: null }); }}>{t('processes.addTop')}</Button>}>
      {params.get('pick') === 'dfd' && (
        <Alert severity="info" sx={{ mb: 2 }} onClose={() => { const next = new URLSearchParams(params); next.delete('pick'); setParams(next); }}>
          {t('processes.pickDfd')}</Alert>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                <Typography component="h2" variant="h6">{t('processes.hierarchy')}</Typography>
                <ShowRetired id="bfc-show-retired" checked={showRetired} onChange={setShowRetired} />
              </Stack>
              <TextField fullWidth id="bfc-filter" placeholder={t('processes.filter')} value={filter}
                onChange={(e) => setFilter(e.target.value)}
                slotProps={{ htmlInput: { 'aria-label': t('processes.filter') },
                  input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }} />
              {canEdit && <Stack direction="row" spacing={1} sx={{ my: 1.5, alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
                <Button size="small" variant="outlined" disabled={!canAddChild}
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
                {selected?.is_process && (
                  <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.noChildOfProcess')}</Typography>
                )}
              </Stack>}
              {!treeQ.isLoading && rows.length === 0 && (
                <Typography sx={{ color: 'text.secondary', py: 2 }}>{t('processes.empty')}</Typography>
              )}
              {filtering && rows.length > 0 && items.length === 0 && (
                <Typography sx={{ color: 'text.secondary', py: 2 }}>{t('processes.noMatch')}</Typography>
              )}
              <RichTreeView items={items} getItemId={(n) => String(n.bfc_node_id)} getItemLabel={(n) => `${n.hier_code} ${n.node_name}`}
                getItemChildren={(n) => n.children} slots={{ item: NodeItem }}
                selectedItems={selectedId} onSelectedItemsChange={(_, id) => select(id)}
                expandedItems={expandedItems} onExpandedItemsChange={(_, ids) => { if (!filtering) setExpanded(ids); }}
                expansionTrigger="iconContainer" />
              {canEdit && <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 2 }}>{t('processes.reorderHelp')}</Typography>}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          {selected ? (
            <NodePanel key={selected.bfc_node_id} projectId={projectId} nodeId={selected.bfc_node_id}
              parent={parent} br={br} showRetired={showRetired} onNotice={setNotice} onGone={() => select(null)} />
          ) : (
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography sx={{ color: 'text.secondary' }}>
                  {selectedId && !treeQ.isLoading ? t('processes.notInTree') : t('processes.pickNode')}</Typography>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>
      {adding && (
        <AddNodeDialog projectId={projectId} parent={adding.parent} onClose={() => setAdding(null)}
          onDone={(row) => {
            qc.invalidateQueries({ queryKey: keys.tree(projectId) });
            qc.invalidateQueries({ queryKey: keys.brs(projectId) });
            if (expanded && adding.parent) setExpanded([...expanded, String(adding.parent.bfc_node_id)]);
            select(String(row.bfc_node_id));
            setNotice(t('processes.created', { code: row.hier_code }));
          }} />
      )}
      <Snackbar open={Boolean(notice)} autoHideDuration={3500} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
