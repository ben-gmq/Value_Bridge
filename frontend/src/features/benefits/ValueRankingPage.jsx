import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { benefitApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, SectionLabel, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { BenefitTabs } from './benefitKit';

const NOTE = { fontSize: 13, color: 'text.secondary' };

function Sol({ projectId, row }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <Link component={RouterLink} to={links.solution(projectId, row.solution_id)} underline="hover">
        <Code>{row.solution_number}</Code></Link>
      <Box component="span">{row.solution_name}</Box>
    </Stack>
  );
}

function SideList({ projectId, title, rows, extra }) {
  if (!rows.length) return null;
  return (
    <Box>
      <SectionLabel>{title}</SectionLabel>
      <Stack spacing={0.5} sx={{ mt: 0.5 }}>
        {rows.map((r) => (
          <Stack key={r.solution_id} direction="row" spacing={2} sx={{ alignItems: 'center', fontSize: 13.5 }}>
            <Box sx={{ flex: 1 }}><Sol projectId={projectId} row={r} /></Box>
            {extra && <Box component="span" sx={NOTE}>{extra(r)}</Box>}
            <Box component="span">{r.value}</Box>
          </Stack>))}
      </Stack>
    </Box>
  );
}

function UnitCard({ projectId, u }) {
  return (
    <Card title={u.unit} bodySx={{ gap: 2 }}>
      {u.ranked.length > 0 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: 40 }}>{t('benefits.ranking.rank')}</TableCell>
              <TableCell>{t('benefits.links.solution')}</TableCell>
              <TableCell align="right">{t('benefits.ranking.value')}</TableCell>
              <TableCell align="right">{t('benefits.ranking.effort')}</TableCell>
              <TableCell align="right">{t('benefits.ranking.ratio')}</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {u.ranked.map((r) => (
              <TableRow key={r.solution_id}>
                <TableCell>{r.rank}</TableCell>
                <TableCell><Sol projectId={projectId} row={r} /></TableCell>
                <TableCell align="right">{r.value}</TableCell>
                <TableCell align="right">{r.effort_days}</TableCell>
                <TableCell align="right">{r.ratio}</TableCell>
                <TableCell>
                  {r.displacement_candidate && <Tag tone="caution" size="sm">{t('benefits.ranking.candidate')}</Tag>}
                  {r.bottom_quartile && !r.displacement_candidate && (
                    <Typography component="span" sx={NOTE}>
                      {t('benefits.ranking.alsoDelivers', { units: r.also_delivers.map((a) => `${a.value} ${a.unit}`).join(', ') })}
                    </Typography>)}
                </TableCell>
              </TableRow>))}
          </TableBody>
        </Table>)}
      <SideList projectId={projectId} title={t('benefits.ranking.values')} rows={u.values} />
      <SideList projectId={projectId} title={t('benefits.ranking.partly')} rows={u.partly_rated}
        extra={(r) => t('benefits.ranking.partlyRow', { n: r.rated_count, m: r.fr_count })} />
      <SideList projectId={projectId} title={t('benefits.ranking.noWork')} rows={u.no_work} />
      {u.benefits.map((b) => (
        <Stack key={b.benefit_id} spacing={0.25}>
          {Number(b.unassigned_pct) > 0 && (
            <Typography sx={NOTE}>
              <Link component={RouterLink} to={links.benefit(projectId, b.benefit_id)} underline="hover">
                {t('benefits.ranking.unassigned', { pct: b.unassigned_pct, number: b.benefit_number })}</Link>
            </Typography>)}
          {Number(b.on_rejected_pct) > 0 && (
            <Typography sx={NOTE}>{t('benefits.ranking.onRejected', { pct: b.on_rejected_pct, number: b.benefit_number })}</Typography>)}
        </Stack>))}
    </Card>
  );
}

// The value ranking (spec §8.1, criteria 60, 128): one card per unit, never a mixed ratio.
export default function ValueRankingPage() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: keys.valueRanking(projectId), queryFn: () => benefitApi.ranking(projectId) });
  const d = q.data;
  const rec = d?.reconciliation;
  return (
    <Page title={t('benefits.ranking.title')} subtitle={t('benefits.ranking.subtitle')} error={q.error && errorText(q.error)}>
      <BenefitTabs projectId={projectId} value="ranking" />
      {d && (
        <Stack spacing={2}>
          {!d.measured && <Alert severity="info">{t('benefits.ranking.notMeasured')}</Alert>}
          {d.units.length === 0 && <Typography sx={NOTE}>{t('benefits.ranking.empty')}</Typography>}
          {d.units.map((u) => <UnitCard key={u.unit_key} projectId={projectId} u={u} />)}
          {d.untagged_effort_days != null && (
            <Typography sx={NOTE}>{t('benefits.ranking.untagged', { days: d.untagged_effort_days })}</Typography>)}
          {rec && (
            <Typography sx={NOTE} data-testid="ben-reconciliation">
              {t('benefits.ranking.reconciliation', { with: rec.with_value, none: rec.no_benefit, rejected: rec.rejected,
                untagged: rec.untagged, total: rec.total_days, theirs: rec.effort_summary_days, diff: rec.difference })}
            </Typography>)}
        </Stack>)}
    </Page>
  );
}
