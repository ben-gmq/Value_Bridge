import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile, Status, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading } from './reportKit';

// Requirement volatility (docs/slice_control_b_spec.md §2.1, CB-1): to-be L1 areas down, each pair of consecutive
// baselines across; a cell is marked where the area changed. The server decides what churn is and works out the run;
// the screen only lays it out.
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'center' };

export function Volatility({ projectId }) {
  const q = useQuery({ queryKey: keys.volatility(projectId), queryFn: () => controlApi.volatility(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const h = d.headline;
  const head = (label, key) => (
    <Box component="th" key={key} scope="col" sx={{ ...cellSx, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>{label}</Box>
  );
  return (
    <Stack sx={{ gap: 2 }}>
      <Generated at={d.generated_at} />
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.volatility.intro')}</Typography>
      {h.reason ? <Alert severity="info">{t(`control.reason.${h.reason}`, { label: h.baseline_label })}</Alert> : (
        <>
          <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
            <PurpleTile label={t('reports.volatility.run')} value={Number(h.measured)} note={t('reports.volatility.runNote')} />
          </Stack>
          <Card title={t('reports.tab.volatility')} bodySx={{ overflowX: 'auto' }}>
            <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 480 }}>
              <thead>
                <tr>
                  {head(t('reports.volatility.area'), 'area')}
                  {d.generations.map((g) => head(`${g.from_label} → ${g.to_label}`, `${g.from_label}-${g.to_label}`))}
                  {head(t('reports.volatility.current'), 'run')}
                </tr>
              </thead>
              <tbody>
                {d.areas.map((a) => (
                  <tr key={a.bfc_node_id}>
                    <Box component="th" scope="row" sx={{ ...cellSx, textAlign: 'left', fontWeight: 400 }}>
                      <Code tone="muted">{a.hier_code}</Code> {a.area_name}
                      {!a.in_latest && <Tag tone="neutral" size="sm" sx={{ ml: 1 }}>{t('reports.volatility.gone')}</Tag>}
                    </Box>
                    {a.churned.map((c, i) => (
                      <Box component="td" key={i} sx={cellSx}>
                        {c ? <Status tone="caution" size="sm">{t('reports.volatility.changed')}</Status>
                          : <Typography component="span" sx={{ color: 'text.disabled' }}>–</Typography>}
                      </Box>))}
                    <Box component="td" sx={{ ...cellSx, fontWeight: 600 }}>{a.current_run}</Box>
                  </tr>))}
              </tbody>
            </Box>
          </Card>
        </>)}
    </Stack>
  );
}
