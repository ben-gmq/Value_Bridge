import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Link, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import { errorText } from '../../api/client';
import { effortApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, PurpleTile, Tag, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';
import { TableFrame, TileRow } from '../frs/frKit';

const n = (v) => Number(v);

function Totals({ title, rows, label }) {
  const max = Math.max(1, ...rows.map((r) => n(r.days)));
  return (
    <Card title={title}>
      <TableFrame>
        <Table size="small" sx={{ minWidth: 360 }}>
          <TableHead>
            <TableRow><TableCell /><TableCell align="right">{t('effort.count')}</TableCell><TableCell align="right">{t('effort.days')}</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}>
                <TableCell>
                  {label(r)}
                  <Box aria-hidden sx={(th) => ({ mt: 0.75, height: 4, borderRadius: 2, width: `${(n(r.days) / max) * 100}%`,
                    bgcolor: th.vars.palette.brand.ftcViolet, opacity: 0.6 })} />
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: MONO }}>{r.count}</TableCell>
                <TableCell align="right" sx={{ fontFamily: MONO, fontWeight: 600 }}>{n(r.days)}</TableCell>
              </TableRow>))}
          </TableBody>
        </Table>
      </TableFrame>
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
    <Page title={t('effort.title')} subtitle={t('effort.subtitle')} error={q.error && errorText(q.error)}
      actions={<Button variant="outlined" component={RouterLink} to={links.rateCard(projectId)}>{t('effort.goCard')}</Button>}>
      {s && (
        <>
          <TileRow min={220}>
            <PurpleTile label={t('effort.total')} value={n(s.total_days)} unit={t('effort.fr.unit')}
              note={t('effort.rated', { n: s.rated_count })} />
            <Tile label={t('effort.tiles.unrated')} value={s.unrated_count} tone={s.unrated_count > 0 ? 'caution' : undefined}
              note={s.unrated_count > 0 ? t('effort.unrated', { n: s.unrated_count }) : undefined} />
            <Tile label={t('effort.tiles.offRate')} value={s.not_at_current_rate.count}
              tone={s.not_at_current_rate.count > 0 ? 'caution' : undefined}
              note={s.not_at_current_rate.count > 0
                ? t('effort.offRate', { n: s.not_at_current_rate.count, days: s.not_at_current_rate.days }) : undefined} />
            <Tile label={t('effort.tiles.rejected')} value={s.rejected.count}
              note={s.rejected.count > 0 ? t('effort.rejected', { n: s.rejected.count, days: s.rejected.days }) : undefined} />
          </TileRow>
          {/* D-52 (Q-18): information only — these FRs are already inside the totals, never added again */}
          {s.untraced?.count > 0 && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {t('effort.untraced', { n: s.untraced.count, days: n(s.untraced.days ?? 0) })}</Alert>)}
          {s.on_unconfirmed_default > 0 && (
            <Alert severity="info" sx={{ mb: 2 }}>{t('effort.unconfirmed', { n: s.on_unconfirmed_default })}</Alert>)}
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', md: 'repeat(2, minmax(0,1fr))' } }}>
            <Totals title={t('effort.byType')} rows={s.by_type} label={(r) => <Tag tone="navy">{r.fr_type_label}</Tag>} />
            <Totals title={t('effort.bySolution')} rows={s.by_solution}
              label={(r) => (r.solution_id ? (
                <Link component={RouterLink} to={links.solution(projectId, r.solution_id)} underline="hover" color="inherit"
                  sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'baseline' }}>
                  <Code>{r.solution_number}</Code>{r.solution_name}</Link>) : <Tag tone="neutral">{t('effort.unassigned')}</Tag>)} />
          </Box>
        </>
      )}
    </Page>
  );
}
