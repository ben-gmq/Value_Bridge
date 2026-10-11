import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';

function Line({ k, children }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
      <Typography sx={{ width: 76, flexShrink: 0, fontSize: 13, color: 'brand.muted', pt: '3px' }}>{k}</Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}

const none = <Typography sx={{ fontSize: 13, color: 'text.secondary', pt: '3px' }}>—</Typography>;

/**
 * Where an FR traces to (mockup 06's Traceability card): its solution, the BRs that solution answers,
 * their business functions, and the to-be applications that deliver the solution. All derived through
 * the solution (D-7) — read with the same queries the solution page uses, so its edits refresh this.
 */
export function FrTraceCard({ projectId, solutionId, solution }) {
  const sid = solutionId;
  const brsQ = useQuery({ queryKey: [...keys.solutionLinks(), 'solution', String(sid)], queryFn: () => solutionApi.brs(sid),
    enabled: Boolean(sid) });
  const appsQ = useQuery({ queryKey: keys.appLinksOf('solution', sid), queryFn: () => solutionApi.apps(sid), enabled: Boolean(sid) });
  const brs = brsQ.data ?? [];
  const steps = [...new Map(brs.map((b) => [b.hier_code, b])).values()];
  const tagLink = (to, tone, label, key) => (
    <Link key={key} component={RouterLink} to={to} underline="none"><Tag tone={tone} sx={{ cursor: 'pointer' }}>{label}</Tag></Link>
  );
  return (
    <Card title={t('frs.trace.title')} bodySx={{ gap: 1 }}>
      {!sid && <Typography sx={{ fontSize: 13, color: 'status.caution' }}>{t('frs.unlinkedTip')}</Typography>}
      {(brsQ.error || appsQ.error) && <Alert severity="error">{errorText(brsQ.error || appsQ.error)}</Alert>}
      {sid && (
        <>
          <Line k={t('frs.trace.bfc')}>
            {steps.length ? steps.map((b) => <Tag key={b.hier_code} tone="purple" sx={{ fontFamily: MONO }}>{b.hier_code}</Tag>) : none}
          </Line>
          <Line k={t('frs.trace.br')}>
            {brs.length ? brs.map((b) => tagLink(links.requirement(projectId, b.br_id), 'purple', b.br_number, b.br_solution_id)) : none}
          </Line>
          <Line k={t('frs.solution')}>
            {tagLink(links.solution(projectId, sid), 'navy', solution?.solution_number ?? t('frs.loading'), 'sol')}
          </Line>
          <Line k={t('frs.trace.system')}>
            {(appsQ.data ?? []).length ? appsQ.data.map((a) => tagLink(links.application(projectId, a.application_id), 'teal',
              a.application_name, a.application_solution_id)) : none}
          </Line>
        </>
      )}
    </Card>
  );
}
