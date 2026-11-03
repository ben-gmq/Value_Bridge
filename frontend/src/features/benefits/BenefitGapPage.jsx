import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { benefitApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { BenefitTabs } from './benefitKit';

const NOTE = { fontSize: 13, color: 'text.secondary' };

// The benefit gap (spec §8.2): solutions carrying work with no benefit behind them, and fragile benefits. The control
// panel's benefit_gap row reads the same computation and links here.
export default function BenefitGapPage() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: keys.benefitGap(projectId), queryFn: () => benefitApi.gap(projectId) });
  const cat = useCodes(projectId, 'SOLUTION_CATEGORY');
  const d = q.data;
  const h = d?.headline;
  return (
    <Page title={t('benefits.gap.title')} subtitle={t('benefits.gap.subtitle')} error={q.error && errorText(q.error)}>
      <BenefitTabs projectId={projectId} value="gap" />
      {d && (
        <Stack spacing={2}>
          {h.measured != null
            ? <Alert severity={h.gap_count ? 'warning' : 'success'} icon={false}>
                {t('benefits.gap.headline', { gap: h.gap_count, n: h.carrying_count, pct: h.measured })}</Alert>
            : <Alert severity="info">{t('benefits.gap.notMeasured', { reason: t(`benefits.gap.reason.${h.reason}`) })}</Alert>}
          <Card>
            {d.gap.length === 0
              ? <Typography sx={NOTE}>{t('benefits.gap.empty')}</Typography>
              : (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('benefits.links.solution')}</TableCell>
                      <TableCell>{t('benefits.gap.category')}</TableCell>
                      <TableCell align="right">{t('benefits.gap.frs')}</TableCell>
                      <TableCell align="right">{t('benefits.gap.effort')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {d.gap.map((r) => (
                      <TableRow key={r.solution_id}>
                        <TableCell>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            <Link component={RouterLink} to={links.solution(projectId, r.solution_id)} underline="hover">
                              <Code>{r.solution_number}</Code></Link>
                            <Box component="span">{r.solution_name}</Box>
                          </Stack>
                        </TableCell>
                        <TableCell>{cat.getLabel(r.category_code)}</TableCell>
                        <TableCell align="right">{r.fr_count}</TableCell>
                        <TableCell align="right">{r.rated_effort_days}</TableCell>
                      </TableRow>))}
                  </TableBody>
                </Table>)}
          </Card>
          <Card title={t('benefits.gap.fragile')} bodySx={{ gap: 0.5 }}>
            {d.fragile.length === 0 && <Typography sx={NOTE}>{t('benefits.gap.fragileEmpty')}</Typography>}
            {d.fragile.map((b) => (
              <Stack key={b.benefit_id} direction="row" spacing={1} sx={{ alignItems: 'center', fontSize: 13.5 }}>
                <Link component={RouterLink} to={links.benefit(projectId, b.benefit_id)} underline="hover">
                  <Code>{b.benefit_number}</Code></Link>
                <Box component="span" sx={{ flex: 1 }}>{b.benefit_name}</Box>
                <Box component="span" sx={NOTE}>{b.solutions.join(', ')}</Box>
              </Stack>))}
          </Card>
        </Stack>)}
    </Page>
  );
}
