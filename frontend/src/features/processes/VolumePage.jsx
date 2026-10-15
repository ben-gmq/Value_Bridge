import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Link, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { volumeApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, Segmented, Status, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// D-67 (slice 13c, Q-9, Q-28): annual hours and FTE per area, as-is beside to-be — the time the change saves. The
// server sums only complete processes and pairs areas only when code and name agree; this screen shows its result
// and never adds an unmatched area into a total (C7, C9).
const h = (v) => Number(v).toLocaleString('en-GB', { maximumFractionDigits: 0 });
const f = (v) => (Math.round(Number(v) * 100 + 1e-9) / 100).toFixed(2);
const num = { fontFamily: 'monospace', fontVariantNumeric: 'tabular-nums' };

/** "1 of 2 processes" with a tooltip naming the ones still missing figures. */
function Completeness({ totals }) {
  const label = t('processes.vsum.complete', { n: totals.complete, of: totals.processes });
  if (!totals.incomplete.length) return <Typography component="span" sx={{ fontSize: 12.5, color: 'text.secondary' }}>{label}</Typography>;
  return (
    <Tooltip title={totals.incomplete.map((p) => `${p.hier_code} ${p.node_name}`).join(' · ')}>
      <Box component="span" sx={{ display: 'inline-flex' }}><Status tone="caution" size="sm">{label}</Status></Box>
    </Tooltip>
  );
}

export default function VolumePage() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: keys.volumeSummary(projectId), queryFn: () => volumeApi.summary(projectId) });
  const [level, setLevel] = useState(1);
  const s = q.data;
  const lvl = s?.levels.find((l) => l.level === level);
  const totals = lvl && lvl.matched.reduce((a, m) => ({ asis: a.asis + Number(m.as_is.annual_hours),
    tobe: a.tobe + Number(m.to_be.annual_hours), saved: a.saved + Number(m.saved_hours), fte: a.fte + Number(m.saved_fte) }),
  { asis: 0, tobe: 0, saved: 0, fte: 0 });
  return (
    <Page title={t('processes.vsum.title')} subtitle={t('processes.vsum.subtitle')} error={q.error && errorText(q.error)}
      actions={(
        <>
          <Segmented label={t('processes.vsum.level')} value={level} onChange={setLevel}
            options={[{ value: 1, label: t('processes.vsum.l1') }, { value: 2, label: t('processes.vsum.l2') }]} />
          <Button variant="outlined" component={RouterLink} to={links.processes(projectId)}>{t('nav.functions')}</Button>
        </>)}>
      {s && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
            {t('processes.vsum.basis', { days: s.working_days_per_year, hpd: Number(s.hours_per_working_day),
              per: (s.working_days_per_year * Number(s.hours_per_working_day)).toLocaleString('en-GB') })}{' '}
            <Link component={RouterLink} to={links.components(projectId)}>{t('processes.vsum.changeBasis')}</Link></Typography>
          {!s.has_as_is && <Alert severity="info">{t('processes.vsum.noAsIs')}</Alert>}
          <Card title={t('processes.vsum.matched')} bodySx={{ pt: 0 }}>
            {lvl.matched.length === 0 ? (
              <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t('processes.vsum.noneMatched')}</Typography>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small" sx={{ '& th': { fontSize: 12, fontWeight: 600, color: 'text.secondary', whiteSpace: 'nowrap' },
                  '& td': { fontSize: 13.5 } }}>
                  <TableHead><TableRow>
                    <TableCell>{t('processes.vsum.area')}</TableCell>
                    <TableCell align="right">{t('processes.vsum.asis')}</TableCell>
                    <TableCell align="right">{t('processes.vsum.tobe')}</TableCell>
                    <TableCell align="right">{t('processes.vsum.saved')}</TableCell>
                    <TableCell align="right">{t('processes.vsum.savedFte')}</TableCell>
                    <TableCell>{t('processes.vsum.coverage')}</TableCell>
                  </TableRow></TableHead>
                  <TableBody>
                    {lvl.matched.map((m) => (
                      <TableRow key={m.hier_code}>
                        <TableCell>
                          <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}>
                            <Code tone="muted" sx={{ fontSize: 12 }}>{m.hier_code}</Code>
                            <Typography component="span" sx={{ fontSize: 14, fontWeight: 600 }}>{m.to_be_name}</Typography>
                          </Box>
                        </TableCell>
                        <TableCell align="right" sx={num}>{h(m.as_is.annual_hours)}</TableCell>
                        <TableCell align="right" sx={num}>{h(m.to_be.annual_hours)}</TableCell>
                        <TableCell align="right" sx={{ ...num, fontWeight: 700 }}>{h(m.saved_hours)}</TableCell>
                        <TableCell align="right" sx={num}>{f(m.saved_fte)}</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
                            <Completeness totals={m.as_is} /><Completeness totals={m.to_be} />
                          </Box>
                        </TableCell>
                      </TableRow>))}
                    <TableRow sx={(th) => ({ '& td': { fontWeight: 700, borderTop: `1px solid ${th.vars.palette.divider}` } })}>
                      <TableCell>{t('processes.vsum.total')}</TableCell>
                      <TableCell align="right" sx={num}>{h(totals.asis)}</TableCell>
                      <TableCell align="right" sx={num}>{h(totals.tobe)}</TableCell>
                      <TableCell align="right" sx={num}>{h(totals.saved)}</TableCell>
                      <TableCell align="right" sx={num}>{f(totals.fte)}</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableBody>
                </Table>
              </Box>)}
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('processes.vsum.hint')}</Typography>
          </Card>
          {lvl.unmatched.length > 0 && (
            <Card title={t('processes.vsum.unmatched')} bodySx={{ gap: 1 }}>
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.vsum.unmatchedHelp')}</Typography>
              {lvl.unmatched.map((u) => (
                <Box key={`${u.chart}-${u.hier_code}`} sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Tag tone={u.chart === 'AS_IS' ? 'neutral' : 'purple'}>{t(`processes.chart.${u.chart}`)}</Tag>
                  <Code tone="muted" sx={{ fontSize: 12 }}>{u.hier_code}</Code>
                  <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{u.name}</Typography>
                  <Typography sx={{ fontSize: 13, color: 'text.secondary', flexGrow: 1 }}>
                    {t(`processes.vsum.reason.${u.reason}`, { code: u.other_code ?? '' })}</Typography>
                  <Typography sx={{ ...num, fontSize: 13 }}>{t('processes.vsum.hours', { h: h(u.totals.annual_hours) })}</Typography>
                </Box>))}
            </Card>)}
        </Box>
      )}
    </Page>
  );
}
