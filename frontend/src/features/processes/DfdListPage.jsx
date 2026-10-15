import { useMemo } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Autocomplete, Box, Link, TextField, Tooltip, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { bfcApi, chartApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useComponents } from '../../app/useComponents';
import { Card, Code, Segmented, Tag } from '../../components/kit';
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

/** Q-6 / Q-16: under a rule with EXTERNAL, each diagram needs an outside party — shown on the diagram, never in a light. */
function NoPartyTag() {
  return (
    <Tooltip title={t('processes.dfdList.noPartyHelp')}>
      <Box component="span" tabIndex={0} sx={{ alignSelf: 'flex-start', display: 'inline-flex', borderRadius: 999 }}>
        <Tag tone="escalate" size="lg">{t('processes.dfdList.noParty')}</Tag></Box>
    </Tooltip>
  );
}

/** One diagram in the picker: its code and name, how many processes, their readiness lights, a missing party. */
function DfdOption({ dfd, noParty }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', width: '100%', minWidth: 0 }}>
      <Code tone="muted" sx={{ fontSize: 12, flex: 'none', mt: '2px' }}>{dfd.hier_code}</Code>
      <Box sx={{ minWidth: 0, flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
        <Typography noWrap sx={{ fontSize: 13.5, fontWeight: 600 }}>{dfd.node_name}</Typography>
        {dfd.lights && <LightCounts counts={dfd.lights} />}
        {noParty && <NoPartyTag />}
      </Box>
      <Box component="span" sx={(th) => ({ flex: 'none', mt: '2px', fontSize: 12, color: th.vars.palette.brand.muted, whiteSpace: 'nowrap' })}>
        {t(dfd.processes === 1 ? 'processes.dfdList.countOne' : 'processes.dfdList.count', { n: dfd.processes })}</Box>
    </Box>
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

  // The function chart's own query, so the two screens share one cache entry.
  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: false, set: bfcSet }],
    queryFn: () => bfcApi.tree(projectId, false, bfcSet) });
  const dfds = useMemo(() => dfdsOf(treeQ.data ?? []), [treeQ.data]);
  // The process panel's completeness read (same cache entry): which diagrams lack an outside party (D-70, Q-16).
  const gapsQ = useQuery({ queryKey: [...keys.flowGaps(projectId), bfcSet], queryFn: () => chartApi.completeness(projectId, bfcSet) });
  const noParty = useMemo(() => new Set((gapsQ.data?.diagram_missing_external ?? []).map((r) => r.bfc_node_id)), [gapsQ.data]);
  const selected = dfds.find((d) => String(d.bfc_node_id) === params.get('node')) ?? dfds[0] ?? null;

  const chooseSet = (v) => { const next = new URLSearchParams(); if (v === 'AS_IS') next.set('set', 'AS_IS'); setParams(next); };
  const empty = !treeQ.isLoading && !treeQ.error && dfds.length === 0;

  const pick = (d) => {
    if (!d) return;
    const next = new URLSearchParams();
    if (bfcSet === 'AS_IS') next.set('set', 'AS_IS');
    next.set('node', String(d.bfc_node_id));
    setParams(next);
  };
  // Mockup 02: the diagram is the page — its title, a picker in the header, the canvas full width.
  const header = (
    <>
      {dfds.length > 0 && (
        <Autocomplete id="dfd-pick" size="small" disableClearable options={dfds} value={selected ?? undefined}
          onChange={(_, d) => pick(d)} sx={{ width: 340 }}
          isOptionEqualToValue={(a, b) => a.bfc_node_id === b.bfc_node_id}
          getOptionLabel={(d) => `${d.hier_code}  ${d.node_name}`}
          renderOption={({ key, ...props }, d) => <Box component="li" key={key} {...props}><DfdOption dfd={d} noParty={noParty.has(d.bfc_node_id)} /></Box>}
          renderInput={(params) => <TextField {...params} label={t('processes.dfdList.pick')} />} />)}
      {sets.length > 1 && (
        <Segmented label={t('processes.chart.label')} value={bfcSet} onChange={chooseSet}
          options={sets.map((v) => ({ value: v, label: t(`processes.chart.${v}`) }))} />)}
    </>);

  if (!selected) {
    return (
      <Page title={t('processes.dfdList.title')} subtitle={t('processes.dfdList.subtitle')}
        error={treeQ.error && errorText(treeQ.error)} actions={header}>
        {treeQ.isLoading && <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>}
        {empty && (
          <Card>
            <Typography sx={{ color: 'text.secondary' }}>
              {t(bfcSet === 'AS_IS' ? 'processes.dfdList.emptyAsIs' : 'processes.dfdList.empty')}</Typography>
            <Link component={RouterLink} to={links.processes(projectId, bfcSet)} sx={{ alignSelf: 'flex-start' }}>
              {t('processes.dfdList.goChart')}</Link>
          </Card>)}
      </Page>
    );
  }
  return (
    <DfdView key={selected.bfc_node_id} projectId={projectId} nodeId={String(selected.bfc_node_id)}
      chartLabel={t('processes.dfdList.openInChart')} container
      frame={(f) => (
        <Page title={f.title} subtitle={t('processes.dfdList.subtitle')}
          eyebrow={noParty.has(selected.bfc_node_id)
            ? <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>{f.eyebrow}<NoPartyTag /></Box>
            : f.eyebrow}
          crumb={`${selected.hier_code} ${selected.node_name}`} error={f.error || (treeQ.error && errorText(treeQ.error))}
          actions={header}>
          <Box sx={{ display: 'flex', gap: 1.25, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end', mb: 2 }}>
            {f.actions}</Box>
          {f.content}
        </Page>)} />
  );
}
