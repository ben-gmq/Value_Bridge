import { useMemo, useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, InputAdornment, Link, TextField, Tooltip, Typography } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { errorText } from '../../api/client';
import { bfcApi, chartApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useComponents } from '../../app/useComponents';
import { Card, Code, ListRow, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { DfdView } from './DfdPage';
import { LightCounts } from './DfdLight';

/**
 * One DFD per direct parent of processes (D-54): every live non-process node with a live process
 * child — in a five-level chart, the L4s. Listed flat in chart order, each with the processes its
 * diagram draws (every live process below it, as the server's generate_dfd does).
 */
function dfdsOf(rows) {
  const byId = new Map(rows.map((r) => [r.bfc_node_id, r]));
  const parents = new Set();
  const count = new Map();
  const lights = new Map();                  // D-68: ready / partly / not per diagram, over the same processes
  for (const r of rows) {
    if (!r.is_active || !r.is_process) continue;
    const parent = byId.get(r.parent_bfc_node_id);
    if (parent?.is_active && !parent.is_process) parents.add(parent.bfc_node_id);
    for (let p = parent; p; p = byId.get(p.parent_bfc_node_id)) {
      count.set(p.bfc_node_id, (count.get(p.bfc_node_id) ?? 0) + 1);
      if (r.dfd_light) {
        const n = lights.get(p.bfc_node_id) ?? { READY: 0, PARTIAL: 0, NOT_READY: 0 };
        n[r.dfd_light] += 1;
        lights.set(p.bfc_node_id, n);
      }
    }
  }
  return rows.filter((r) => parents.has(r.bfc_node_id))
    .map((r) => ({ ...r, processes: count.get(r.bfc_node_id) ?? 0, lights: lights.get(r.bfc_node_id) ?? null }));
}

function DfdRow({ projectId, dfd, bfcSet, selected, noParty }) {
  return (
    <ListRow component={RouterLink} to={links.dfds(projectId, dfd.bfc_node_id, bfcSet)} selected={selected}
      aria-current={selected ? 'page' : undefined} sx={{ py: 1, gap: 1, flexShrink: 0 }}>
      <Code tone={selected ? 'purple' : 'muted'} sx={{ fontSize: 12, flex: 'none', alignSelf: 'flex-start', mt: '2px' }}>{dfd.hier_code}</Code>
      <Box sx={{ minWidth: 0, flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
        <Typography noWrap sx={{ fontSize: 13.5, fontWeight: selected ? 700 : 500 }}>{dfd.node_name}</Typography>
        {dfd.lights && <LightCounts counts={dfd.lights} />}
        {/* Q-6 / Q-16: under a rule with EXTERNAL, each diagram needs an outside party — shown here only, never in a light */}
        {noParty && (
          <Tooltip title={t('processes.dfdList.noPartyHelp')}>
            <Box component="span" tabIndex={0} sx={{ alignSelf: 'flex-start', display: 'inline-flex', borderRadius: 999 }}>
              <Tag tone="escalate" size="lg">{t('processes.dfdList.noParty')}</Tag></Box>
          </Tooltip>)}
      </Box>
      <Box component="span" sx={(th) => ({ flex: 'none', alignSelf: 'flex-start', mt: '2px', fontSize: 12, color: th.vars.palette.brand.muted, whiteSpace: 'nowrap' })}>
        {t(dfd.processes === 1 ? 'processes.dfdList.countOne' : 'processes.dfdList.count', { n: dfd.processes })}</Box>
    </ListRow>
  );
}

/** The DFD screen (D-54): the project's diagrams as a flat, searchable list; the selected one drawn beside it. */
export default function DfdListPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  const { isOn } = useComponents(projectId);
  // The same chart rule as the function chart's DFD button (D-37, D-47): to-be needs TO_BE_DFD, as-is needs AS_IS.
  const sets = [isOn('TO_BE_DFD') && 'TO_BE', isOn('AS_IS') && 'AS_IS'].filter(Boolean);
  const bfcSet = params.get('set') === 'AS_IS' && sets.includes('AS_IS') ? 'AS_IS' : (sets[0] ?? 'TO_BE');
  const [filter, setFilter] = useState('');

  // The function chart's own query, so the two screens share one cache entry.
  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: false, set: bfcSet }],
    queryFn: () => bfcApi.tree(projectId, false, bfcSet) });
  const dfds = useMemo(() => dfdsOf(treeQ.data ?? []), [treeQ.data]);
  // The process panel's completeness read (same cache entry): which diagrams lack an outside party (D-70, Q-16).
  const gapsQ = useQuery({ queryKey: [...keys.flowGaps(projectId), bfcSet], queryFn: () => chartApi.completeness(projectId, bfcSet) });
  const noParty = useMemo(() => new Set((gapsQ.data?.diagram_missing_external ?? []).map((r) => r.bfc_node_id)), [gapsQ.data]);
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? dfds.filter((d) => d.hier_code.toLowerCase().includes(q) || d.node_name.toLowerCase().includes(q)) : dfds;
  }, [dfds, filter]);
  const selected = dfds.find((d) => String(d.bfc_node_id) === params.get('node')) ?? dfds[0] ?? null;

  const chooseSet = (v) => { const next = new URLSearchParams(); if (v === 'AS_IS') next.set('set', 'AS_IS'); setParams(next); };
  const empty = !treeQ.isLoading && !treeQ.error && dfds.length === 0;

  return (
    <Page title={t('processes.dfdList.title')} subtitle={t('processes.dfdList.subtitle')}
      crumb={selected ? `${selected.hier_code} ${selected.node_name}` : undefined}
      error={treeQ.error && errorText(treeQ.error)}
      actions={sets.length > 1 && (
        <Segmented label={t('processes.chart.label')} value={bfcSet} onChange={chooseSet}
          options={sets.map((v) => ({ value: v, label: t(`processes.chart.${v}`) }))} />)}>
      {empty ? (
        <Card>
          <Typography sx={{ color: 'text.secondary' }}>
            {t(bfcSet === 'AS_IS' ? 'processes.dfdList.emptyAsIs' : 'processes.dfdList.empty')}</Typography>
          <Link component={RouterLink} to={links.processes(projectId, bfcSet)} sx={{ alignSelf: 'flex-start' }}>
            {t('processes.dfdList.goChart')}</Link>
        </Card>
      ) : (
        <Box sx={{ display: 'grid', gap: 2, alignItems: 'start',
          gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(260px,300px) minmax(0,1fr)' } }}>
          <Card title={t(dfds.length === 1 ? 'processes.dfdList.headingOne' : 'processes.dfdList.heading', { n: dfds.length })}
            bodySx={{ gap: 1.25, px: 1.5 }} sx={{ position: { lg: 'sticky' }, top: { lg: 16 } }}>
            <Box sx={{ px: 1 }}>
              <TextField fullWidth size="small" id="dfd-filter" placeholder={t('processes.dfdList.filter')} value={filter}
                onChange={(e) => setFilter(e.target.value)}
                slotProps={{ htmlInput: { 'aria-label': t('processes.dfdList.filter') },
                  input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }} />
            </Box>
            {treeQ.isLoading && <Typography sx={{ color: 'text.secondary', px: 1 }}>{t('processes.loading')}</Typography>}
            {dfds.length > 0 && shown.length === 0 && (
              <Typography sx={{ color: 'text.secondary', px: 1, py: 1 }}>{t('processes.dfdList.noMatch')}</Typography>)}
            <Box component="nav" aria-label={t('processes.dfdList.listLabel')}
              sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, overflowY: 'auto', maxHeight: { xs: 300, lg: 'calc(100vh - 260px)' } }}>
              {shown.map((d) => (
                <DfdRow key={d.bfc_node_id} projectId={projectId} dfd={d} bfcSet={bfcSet} noParty={noParty.has(d.bfc_node_id)}
                  selected={d.bfc_node_id === selected?.bfc_node_id} />))}
            </Box>
          </Card>
          {selected && (
            <DfdView key={selected.bfc_node_id} projectId={projectId} nodeId={String(selected.bfc_node_id)} chartLabel={t('processes.dfdList.openInChart')} container
              frame={(f) => (
                <Box component="section" aria-label={f.title} sx={{ minWidth: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 1.5, flexWrap: 'wrap', mb: 2 }}>
                    <Box sx={{ flex: '1 1 260px', minWidth: 0 }}>
                      {f.eyebrow && <Box sx={{ mb: 0.5 }}>{f.eyebrow}</Box>}
                      <Typography variant="h6" component="h2" sx={{ wordBreak: 'break-word' }}>{f.title}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1.25, flexWrap: 'wrap', alignItems: 'center' }}>{f.actions}</Box>
                  </Box>
                  {f.error && <Alert severity="error" sx={{ mb: 2 }}>{f.error}</Alert>}
                  {f.content}
                </Box>)} />
          )}
        </Box>
      )}
    </Page>
  );
}
