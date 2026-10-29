import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { reportApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useComponents } from '../../app/useComponents';
import { Card, Code, ListRow, Segmented, Tag, Tile } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading, Off, Printable } from './reportKit';

// System gap (spec §3.4, function 67; D-8, RP-1): the migration backlog, per system inside each matched area. The
// server pairs the areas and finds the gaps; the screen lays them out. The input counts always show, so an empty
// project reads "nothing recorded", never "no gap" (D3).
const NEEDS = ['APPLICATION', 'AS_IS', 'SOLUTION'];

function AppTag({ projectId, a }) {
  return (
    <Link component={RouterLink} to={links.application(projectId, a.application_id)} underline="hover"
      sx={{ color: 'inherit', display: 'inline-flex', gap: 0.75, alignItems: 'center', minWidth: 0 }}>
      <Tag tone="navy">{a.application_code}</Tag><Typography sx={{ fontSize: 13 }}>{a.application_name}</Typography>
    </Link>
  );
}

function StepRow({ projectId, r, set }) {
  return (
    <ListRow sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
      {r.area_code && <Typography sx={{ fontSize: 12.5, color: 'text.secondary', minWidth: 120 }}>{r.area_name}</Typography>}
      <Link component={RouterLink} to={links.node(projectId, r.step.bfc_node_id, set)} underline="hover"
        sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, color: 'inherit', flex: '1 1 220px' }}>
        <Code>{r.step.hier_code}</Code><Typography noWrap sx={{ fontSize: 13.5 }}>{r.step.node_name}</Typography>
      </Link>
      <AppTag projectId={projectId} a={r.application} />
    </ListRow>
  );
}

function Part({ title, note, rows, warn, children }) {
  return (
    <Card title={title} bodySx={{ gap: 0.5 }}
      action={<Tag tone={rows.length && warn ? 'caution' : 'neutral'}>{t('reports.trace.rows', { n: rows.length })}</Tag>}>
      {note && <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 0.5 }}>{note}</Typography>}
      {rows.length === 0 ? <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('reports.cov.none')}</Typography> : children}
    </Card>
  );
}

export function ApplicationGap({ projectId }) {
  const [level, setLevel] = useState(1);
  const q = useQuery({ queryKey: keys.applicationGap(projectId, level), queryFn: () => reportApi.applicationGap(projectId, level) });
  const { isOn } = useComponents(projectId);
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  if (d.counts === null) {
    return <><Generated at={d.generated_at} /><Off projectId={projectId} component={NEEDS.find((c) => !isOn(c)) ?? NEEDS[0]} /></>;
  }
  const c = d.counts;
  const nothing = c.as_is_processes === 0 || c.support_links === 0;
  return (
    <Printable projectId={projectId} report="application_gap" query={q} data={d}
      filters={t('reports.gap.levelFilter', { n: level })}>
      <Stack sx={{ gap: 2 }}>
        <Box>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mb: 1.5 }}>{t('reports.gap.intro')}</Typography>
          <Segmented label={t('reports.gap.level')} value={String(level)} onChange={(v) => setLevel(Number(v))}
            options={[1, 2].map((n) => ({ value: String(n), label: t('reports.gap.levelOption', { n }) }))} />
        </Box>
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <Tile label={t('reports.gap.asIsProcesses')} value={c.as_is_processes} />
          <Tile label={t('reports.gap.supportLinks')} value={c.support_links} />
          <Tile label={t('reports.gap.allocations')} value={c.to_be_allocations} />
        </Stack>
        {nothing && <Alert severity="info">{t('reports.gap.nothingRecorded')}</Alert>}
        <Part title={t('reports.gap.unallocated')} note={t('reports.gap.unallocatedNote')} rows={d.unallocated} warn>
          {d.unallocated.map((r) => <StepRow key={`${r.step.bfc_node_id}-${r.application.application_id}`} projectId={projectId} r={r} set="AS_IS" />)}
        </Part>
        <Part title={t('reports.gap.unsupported')} note={t('reports.gap.unsupportedNote')} rows={d.unsupported}>
          {d.unsupported.map((r) => <StepRow key={`${r.step.bfc_node_id}-${r.application.application_id}`} projectId={projectId} r={r} set="TO_BE" />)}
        </Part>
        <Part title={t('reports.gap.retiring')} note={t('reports.gap.retiringNote')} rows={d.retiring}>
          {d.retiring.map((a) => <ListRow key={a.application_id}><AppTag projectId={projectId} a={a} /></ListRow>)}
        </Part>
        <Part title={t('reports.gap.byToBe')} note={t('reports.gap.byToBeNote')} rows={d.as_is_support_by_to_be}>
          {d.as_is_support_by_to_be.map((r) => <StepRow key={`${r.step.bfc_node_id}-${r.application.application_id}`} projectId={projectId} r={r} set="AS_IS" />)}
        </Part>
        <Part title={t('reports.gap.unmatched')} note={t('reports.gap.unmatchedNote')} rows={d.unmatched} warn>
          {d.unmatched.map((u) => (
            <ListRow key={`${u.chart}-${u.hier_code}`} sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
              <Tag tone="neutral">{t(`reports.gap.chart.${u.chart}`)}</Tag>
              <Code>{u.hier_code}</Code><Typography sx={{ fontSize: 13.5, flex: '1 1 200px' }}>{u.name}</Typography>
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                {t(`processes.vsum.reason.${u.reason}`, { code: u.other_code })}</Typography>
            </ListRow>))}
        </Part>
      </Stack>
    </Printable>
  );
}
