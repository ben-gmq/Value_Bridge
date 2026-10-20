import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { phaseApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code, ListRow, PurpleTile, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { fmtDate } from '../baselines/baselineKit';
import { WaveStatus, fmtDays, fmtPct } from './waveKit';

// The wave plan (spec §3, R3, R6): effort per wave + in no wave + no solution = the effort headline. The figures are the
// server's, already rounded so they add up; this screen never sums or rounds them again. Live project only (Q-66).
function Solutions({ projectId, items, showPct }) {
  return items.map((s) => (
    <Box key={s.solution_id} sx={{ display: 'flex', gap: 1, alignItems: 'center', pl: 1, minWidth: 0 }}>
      <Link component={RouterLink} to={links.solution(projectId, s.solution_id)} underline="hover"
        sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, flex: 1, color: 'inherit' }}>
        <Code>{s.solution_number}</Code>
        <Typography noWrap sx={{ fontSize: 13.5 }}>{s.solution_name}</Typography>
      </Link>
      {showPct && <Tag tone="neutral">{t('waves.plan.share', { pct: fmtPct(s.portion_pct) })}</Tag>}
      <Typography sx={{ fontSize: 13.5, minWidth: 90, textAlign: 'right' }}>
        {t('waves.plan.days', { days: fmtDays(s.days) })}</Typography>
    </Box>
  ));
}

function Line({ title, note, days, tags, children }) {
  return (
    <ListRow sx={{ flexDirection: 'column', alignItems: 'stretch', gap: 0.75 }}>
      <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
        <Box sx={{ flex: 1, minWidth: 0, display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>{title}{tags}</Box>
        <Typography sx={{ fontSize: 15, fontWeight: 700 }}>{t('waves.plan.days', { days: fmtDays(days) })}</Typography>
      </Box>
      {note && <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{note}</Typography>}
      {children}
    </ListRow>
  );
}

export function WavePlan({ projectId }) {
  const q = useQuery({ queryKey: keys.phasePlan(projectId), queryFn: () => phaseApi.plan(projectId) });
  const { getLabel } = useCodes(projectId, 'PHASE_STATUS');
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const p = q.data;
  if (!p) return null;
  const waves = p.lines.filter((l) => l.kind === 'WAVE');
  const unphased = p.lines.find((l) => l.kind === 'UNPHASED');
  const unassigned = p.lines.find((l) => l.kind === 'UNASSIGNED');
  return (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,2fr) minmax(0,1fr)' } }}>
      <Card title={t('waves.tab.plan')} bodySx={{ gap: 1 }}>
        {waves.length === 0 && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('waves.empty')}</Typography>}
        {waves.map((w) => (
          <Line key={w.phase_id} days={w.days}
            title={<><Code>{w.phase_code}</Code><Typography sx={{ fontSize: 14, fontWeight: 600 }}>{w.phase_name}</Typography></>}
            tags={<>
              {p.current_phase_id === w.phase_id && <Tag tone="purple">{t('waves.current')}</Tag>}
              <WaveStatus code={w.status_code} label={getLabel(w.status_code)} />
              {(w.start_date || w.end_date) && <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                {`${fmtDate(w.start_date) || '…'} – ${fmtDate(w.end_date) || '…'}`}</Typography>}
            </>}
            note={w.solutions.length === 0 ? t('waves.plan.noSolutions') : null}>
            <Solutions projectId={projectId} items={w.solutions} showPct />
          </Line>
        ))}
        <Line days={unphased.days} title={<Typography sx={{ fontSize: 14, fontWeight: 600 }}>
          {t('waves.plan.unphased')}</Typography>} note={t('waves.plan.unphasedNote')}>
          <Solutions projectId={projectId} items={unphased.solutions} />
        </Line>
        <Line days={unassigned.days} title={<Typography sx={{ fontSize: 14, fontWeight: 600 }}>
          {t('waves.plan.unassigned')}</Typography>} note={t('waves.plan.unassignedNote')} />
      </Card>
      <Stack spacing={2}>
        <PurpleTile label={t('waves.plan.headline')} value={fmtDays(p.total_shown)} unit={t('effort.days')}
          note={t('waves.plan.headlineNote')} />
        {p.unrated_count > 0 && <Alert severity="info">{t('waves.plan.unrated', { n: p.unrated_count })}</Alert>}
        <Card title={t('waves.plan.warnings')} bodySx={{ gap: 1 }}>
          {p.warnings.length === 0 && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('waves.plan.noWarnings')}</Typography>}
          {p.warnings.map((w) => (
            <Alert key={`${w.kind}-${w.solution_number}-${w.depends_on_solution_number}`} severity="warning">
              {t(`waves.warn.${w.kind}`, { sol: w.solution_number, pre: w.depends_on_solution_number ?? '' })}
            </Alert>
          ))}
        </Card>
      </Stack>
    </Box>
  );
}
