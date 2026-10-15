import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { baselineApi, effortApi, scopeSummaryApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, ListRow, PurpleTile, Tag, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { AgreedChip, StatusChip, fmtDate } from '../baselines/baselineKit';

const pct = (n, of) => (of ? Math.round((n / of) * 100) : 0);
const days = (d) => (Number.isInteger(d) ? String(d) : d.toFixed(1));
const CHANGES = ['ADDED', 'CHANGED', 'REMOVED', 'MOVED'];

/** A thin bar for a share, in the semantic "ok" colour (mockup's reach column). */
function Bar({ value }) {
  return (
    <Box aria-hidden sx={(th) => ({ height: 6, borderRadius: 3, bgcolor: th.vars.palette.background.subtle, overflow: 'hidden', minWidth: 48 })}>
      <Box sx={(th) => ({ height: '100%', width: `${value}%`, bgcolor: th.vars.palette.status.ok })} />
    </Box>
  );
}

/** Requirement coverage per level-1 area — the mockup's "Requirements by workstream", from live rows. */
function AreaTable({ s }) {
  const num = { fontFamily: 'monospace', fontVariantNumeric: 'tabular-nums' };
  const row = (r, total) => {
    const reach = pct(r.with_fr, r.brs);
    return (
      <TableRow key={r.hier_code ?? 'total'} sx={total ? (th) => ({ '& td': { fontWeight: 700, borderTop: `1px solid ${th.vars.palette.divider}` } }) : undefined}>
        <TableCell>
          {total ? t('home.total') : (
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}>
              <Code tone="muted" sx={{ fontSize: 12 }}>{r.hier_code}</Code>
              <Typography component="span" sx={{ fontSize: 14, fontWeight: 600 }}>{r.name}</Typography>
            </Box>)}
        </TableCell>
        <TableCell align="right" sx={num}>{r.processes}</TableCell>
        <TableCell align="right" sx={num}>{r.brs}</TableCell>
        <TableCell align="right" sx={num}>{r.confirmed}</TableCell>
        <TableCell align="right" sx={num}>{r.frs}</TableCell>
        <TableCell sx={{ width: 130 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ flexGrow: 1 }}><Bar value={reach} /></Box>
            <Box component="span" sx={{ ...num, fontSize: 13, minWidth: 36, textAlign: 'right' }}>{reach}%</Box>
          </Box>
        </TableCell>
        <TableCell align="right" sx={num}>{days(r.effort_days)}</TableCell>
      </TableRow>
    );
  };
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small" sx={{ '& th': { fontSize: 12, fontWeight: 600, color: 'text.secondary', whiteSpace: 'nowrap' },
        '& td': { fontSize: 13.5, borderBottom: 0, py: 1.1 }, '& td, & th': { px: 1 }, '& td:first-of-type, & th:first-of-type': { pl: 0 },
        '& td:last-of-type, & th:last-of-type': { pr: 0 } }}>
        <TableHead><TableRow>
          <TableCell>{t('home.col.area')}</TableCell>
          <TableCell align="right">{t('home.col.processes')}</TableCell>
          <TableCell align="right">{t('home.col.brs')}</TableCell>
          <TableCell align="right">{t('home.col.confirmed')}</TableCell>
          <TableCell align="right">{t('home.col.frs')}</TableCell>
          <TableCell>{t('home.col.reach')}</TableCell>
          <TableCell align="right">{t('home.col.effort')}</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {s.areas.map((r) => row(r, false))}
          {s.areas.length > 1 && row({ ...s.totals, frs: s.totals.frs - s.totals.frs_without_br }, true)}
        </TableBody>
      </Table>
    </Box>
  );
}

// The project dashboard, laid out as the mockup's "Program dashboard": the requirement tiles, coverage by
// business area, and the baselines with what changed since the latest. Every number is the server's; the
// mockup's schedule parts (WBS plan vs actual, late tasks) wait for the WBS import (D-33, D-51: no data, no tile).
export default function ProjectHome() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const sq = useQuery({ queryKey: keys.scopeSummary(projectId), queryFn: () => scopeSummaryApi.get(projectId) });
  const eq = useQuery({ queryKey: keys.effortSummary(projectId), queryFn: () => effortApi.summary(projectId) });
  const bl = useQuery({ queryKey: keys.baselines(projectId), queryFn: () => baselineApi.list(projectId) });
  const latest = bl.data?.[0];
  const lq = useQuery({ queryKey: keys.baseline(latest?.baseline_id), queryFn: () => baselineApi.get(latest.baseline_id),
    enabled: Boolean(latest) });
  const dq = useQuery({ queryKey: ['baseline-diff', String(projectId), String(latest?.baseline_id), 'live'],
    queryFn: () => baselineApi.diff(projectId, latest.baseline_id, 'live'), enabled: Boolean(latest), staleTime: 60_000 });
  const p = q.data;
  const s = sq.data;
  const e = eq.data;
  const brRows = dq.data?.entities?.business_requirement?.rows ?? [];
  const brChange = (c) => brRows.filter((r) => r.change === c).length;
  const today = fmtDate(new Date().toISOString());
  const error = (q.error || sq.error) && errorText(q.error || sq.error);

  return (
    <Page title={p ? p.project_name : t('project.fallbackTitle')} error={error}
      eyebrow={p && <Code tone="muted">{p.project_code}</Code>}
      subtitle={s && t(s.areas.length === 1 ? 'home.subtitleOne' : 'home.subtitle', { n: s.areas.length, date: today })}
      actions={(
        <>
          <Button variant="outlined" component={RouterLink} to={links.processes(projectId)}>{t('nav.processes')}</Button>
          <Button variant="contained" component={RouterLink} to={links.baselines(projectId)}>{t('settings.home.open')}</Button>
        </>)}>
      {s && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'repeat(2, minmax(0,1fr))', lg: 'minmax(0,1.3fr) repeat(3, minmax(0,1fr))' } }}>
            {latest && lq.data ? (
              <PurpleTile label={t('home.inBaseline', { label: latest.version_label })} value={lq.data.counts.business_requirement ?? 0}
                unit={t('home.ofToday', { n: s.totals.brs })}
                note={dq.data && t('home.sinceBaseline', { added: brChange('ADDED'), changed: brChange('CHANGED'), label: latest.version_label })} />
            ) : (
              <PurpleTile label={t('home.inBaselineNone')} value={s.totals.brs} note={bl.isSuccess && !latest ? t('home.noBaselineYet') : null} />
            )}
            <Tile label={t('home.reach')} value={`${pct(s.totals.with_fr, s.totals.brs)}%`}
              note={t('home.reachNote', { n: s.totals.with_fr, total: s.totals.brs, frs: s.totals.frs })} />
            <Tile label={t('home.noSolution')} value={s.totals.brs - s.totals.with_solution}
              tone={s.totals.brs - s.totals.with_solution > 0 ? 'caution' : undefined}
              note={t('home.noSolutionNote', { n: s.totals.frs_without_br })} />
            <Tile label={t('home.effort')} value={`${days(s.totals.effort_days)} ${t('home.effortUnit')}`}
              note={e && t('home.effortNote', { rated: e.rated_count, unrated: e.unrated_count })} />
          </Box>

          <Box sx={{ display: 'grid', gap: 2, alignItems: 'start', gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1.7fr) minmax(300px,1fr)' } }}>
            <Card title={t('home.byArea')} action={<Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('home.byAreaHint')}</Typography>}
              bodySx={{ pt: 0 }}>
              {s.areas.length ? <AreaTable s={s} /> : <Typography sx={{ color: 'text.secondary' }}>{t('home.empty')}</Typography>}
            </Card>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
              <Card title={t('home.baselines')} action={<Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('home.baselinesHint')}</Typography>}
                bodySx={{ gap: 1 }}>
                {bl.isSuccess && !latest && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('baselines.none')}</Typography>}
                {(bl.data ?? []).slice(0, 5).map((b) => (
                  <ListRow key={b.baseline_id} component={RouterLink} to={links.baseline(projectId, b.baseline_id)}
                    sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                    <Code sx={{ fontSize: 14, fontWeight: 600 }}>{b.version_label}</Code>
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{fmtDate(b.frozen_at)}</Typography>
                      <Typography noWrap sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                        {b.client_approver_name ? t('home.approvedBy', { who: b.client_approver_name })
                          : b.status_code === 'FROZEN' ? t('home.awaiting') : ''}</Typography>
                    </Box>
                    <StatusChip code={b.status_code} label={b.status_label} />
                    {b.is_agreed && <AgreedChip />}
                  </ListRow>))}
              </Card>

              {latest && dq.data && (
                <Card title={t('home.changes', { label: latest.version_label })}
                  action={<Button size="small" variant="outlined" component={RouterLink}
                    to={links.baselines(projectId, latest.baseline_id, 'live')}>{t('home.openDiff')}</Button>}>
                  {CHANGES.every((c) => !dq.data.summary[c]) ? (
                    <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('home.changesNone', { label: latest.version_label })}</Typography>
                  ) : (
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      {CHANGES.filter((c) => dq.data.summary[c]).map((c) => (
                        <Tag key={c} tone={c === 'REMOVED' ? 'caution' : c === 'ADDED' ? 'ok' : 'purple'} size="lg">
                          {`${t(`home.change.${c}`)} · ${dq.data.summary[c]}`}</Tag>))}
                    </Box>)}
                </Card>)}
            </Box>
          </Box>
        </Box>
      )}
    </Page>
  );
}
