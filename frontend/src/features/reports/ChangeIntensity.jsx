import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading, Off } from './reportKit';

// Where change lands (docs/slice_control_c_spec.md §2.1, CC-1): per top-level area, the process steps carrying a
// change against all its steps. Every changed step weighs the same; the solution categories are context. The server
// works out every figure; the screen lays them out in chart order.
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'left' };
const numSx = { ...cellSx, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
const headSx = { fontSize: 12, fontWeight: 600, color: 'text.secondary' };

export function ChangeIntensity({ projectId }) {
  const q = useQuery({ queryKey: keys.changeIntensity(projectId), queryFn: () => controlApi.changeIntensity(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const h = d.headline;
  if (h.reason === 'SOLUTION_OFF') {
    return <><Generated at={d.generated_at} /><Off projectId={projectId} component="SOLUTION" /></>;
  }
  return (
    <Stack sx={{ gap: 2 }}>
      <Generated at={d.generated_at} />
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.intensity.intro')}</Typography>
      {h.reason && <Alert severity="info">{t(`control.reason.${h.reason}`)}</Alert>}
      {!h.reason && (
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <PurpleTile label={t('reports.intensity.busiest')} value={`${Number(h.measured)} %`}
            note={t('control.intensity', { area: h.top_area, n: h.changed_steps })} />
          {h.areas_at_top > 1 && (
            <PurpleTile label={t('reports.intensity.tied')} value={h.areas_at_top} note={t('reports.intensity.tiedNote')} />)}
        </Stack>)}
      {d.areas.length > 0 && (
        <Card title={t('reports.tab.change_intensity')} bodySx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                <Box component="th" scope="col" sx={{ ...cellSx, ...headSx }}>{t('reports.intensity.area')}</Box>
                {['changed', 'steps', 'share'].map((k) => (
                  <Box component="th" key={k} scope="col" sx={{ ...numSx, ...headSx }}>{t(`reports.intensity.${k}`)}</Box>))}
                {d.categories.map((c) => (
                  <Box component="th" key={c.code} scope="col" sx={{ ...numSx, ...headSx }}>{c.label}</Box>))}
              </tr>
            </thead>
            <tbody>
              {d.areas.map((a) => (
                <tr key={a.bfc_node_id}>
                  <Box component="th" scope="row" sx={{ ...cellSx, fontWeight: 400 }}>
                    <Code tone="muted">{a.hier_code}</Code> {a.area_name}
                  </Box>
                  <Box component="td" sx={numSx}>{a.changed_steps}</Box>
                  <Box component="td" sx={numSx}>{a.steps}</Box>
                  <Box component="td" sx={numSx}>{a.share === null ? '–' : `${Number(a.share)} %`}</Box>
                  {d.categories.map((c) => <Box component="td" key={c.code} sx={{ ...numSx, color: 'text.secondary' }}>{a.by_category[c.code] || '–'}</Box>)}
                </tr>))}
            </tbody>
          </Box>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 1, px: 1.25 }}>{t('reports.intensity.categoryNote')}</Typography>
        </Card>)}
    </Stack>
  );
}
