import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Card, CardContent, Grid, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow,
  Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { effortApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { Mono } from '../processes/chartKit';
import { BrFrTabs } from '../frs/BrFrTabs';

function Totals({ title, rows, label }) {
  return (
    <Card>
      <CardContent>
        <Typography component="h2" sx={{ fontWeight: 700, mb: 1 }}>{title}</Typography>
        <Table size="small">
          <TableHead>
            <TableRow><TableCell /><TableCell align="right">{t('effort.count')}</TableCell><TableCell align="right">{t('effort.days')}</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}><TableCell>{label(r)}</TableCell><TableCell align="right">{r.count}</TableCell>
                <TableCell align="right">{r.days}</TableCell></TableRow>))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// The effort summary (§7.9): by type and by solution, Unassigned and unrated never hidden; FRs under
// rejected solutions apart from the total (S6c-8); off-rate and unconfirmed-default counts (S6c-5).
export default function EffortPage() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: keys.effortSummary(projectId), queryFn: () => effortApi.summary(projectId) });
  const s = q.data;
  return (
    <Page title={t('effort.title')} subtitle={t('effort.subtitle')} error={q.error && errorText(q.error)}>
      <BrFrTabs current="effort" />
      {s && (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <Card>
            <CardContent>
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('effort.total')}</Typography>
              <Typography sx={{ fontSize: 32, fontWeight: 700 }}>{s.total_days}</Typography>
              <Typography sx={{ fontSize: 13 }}>{t('effort.rated', { n: s.rated_count })}</Typography>
              {s.unrated_count > 0 && <Typography sx={{ fontSize: 13, color: 'status.caution' }}>{t('effort.unrated', { n: s.unrated_count })}</Typography>}
              <Box sx={{ mt: 1 }}>
                <Link component={RouterLink} to={links.rateCard(projectId)} sx={{ fontSize: 13 }}>{t('effort.goCard')}</Link>
              </Box>
            </CardContent>
          </Card>
          {s.not_at_current_rate.count > 0 && <Alert severity="warning">{t('effort.offRate', { n: s.not_at_current_rate.count, days: s.not_at_current_rate.days })}</Alert>}
          {s.on_unconfirmed_default > 0 && <Alert severity="info">{t('effort.unconfirmed', { n: s.on_unconfirmed_default })}</Alert>}
          {s.rejected.count > 0 && <Alert severity="info">{t('effort.rejected', { n: s.rejected.count, days: s.rejected.days })}</Alert>}
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}><Totals title={t('effort.byType')} rows={s.by_type} label={(r) => r.fr_type_label} /></Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Totals title={t('effort.bySolution')} rows={s.by_solution}
                label={(r) => (r.solution_id ? (
                  <Link component={RouterLink} to={links.solution(projectId, r.solution_id)} underline="hover">
                    <Mono>{r.solution_number}</Mono> {r.solution_name}</Link>) : t('effort.unassigned'))} />
            </Grid>
          </Grid>
        </Stack>
      )}
    </Page>
  );
}
