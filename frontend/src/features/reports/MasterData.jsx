import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile, Status } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading } from './reportKit';

// Master data candidates (docs/slice_control_c_spec.md §2.2, CC-2): data entities the future state uses in three or
// more top-level areas, with the business owner noted on each. Unowned ones come first; the server decides who counts
// as owned (any note but a blank one). Notes render as text (VB law 9).
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'left', verticalAlign: 'top' };

export function MasterData({ projectId }) {
  const q = useQuery({ queryKey: keys.masterData(projectId), queryFn: () => controlApi.masterData(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const h = d.headline;
  return (
    <Stack sx={{ gap: 2 }}>
      <Generated at={d.generated_at} />
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.master.intro')}</Typography>
      {h.reason && <Alert severity="info">{t(`control.reason.${h.reason}`)}</Alert>}
      {!h.reason && (
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <PurpleTile label={t('reports.master.unowned')} value={Number(h.measured)}
            note={t('control.master', { n: h.candidates, used: h.entities_used })} />
        </Stack>)}
      {d.entities && d.entities.length === 0 && <Alert severity="success">{t('reports.master.none')}</Alert>}
      {d.entities && d.entities.length > 0 && (
        <Card title={t('reports.tab.master_data')} bodySx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                {['entity', 'owner', 'areas', 'brs'].map((k) => (
                  <Box component="th" key={k} scope="col" sx={{ ...cellSx, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
                    {t(`reports.master.${k}`)}
                  </Box>))}
              </tr>
            </thead>
            <tbody>
              {d.entities.map((e) => (
                <tr key={e.data_entity_id}>
                  <Box component="th" scope="row" sx={{ ...cellSx, fontWeight: 400 }}>
                    <Code tone="muted">{e.de_number}</Code> {e.de_name}
                  </Box>
                  <Box component="td" sx={cellSx}>
                    {e.business_owner_note ?? <Status tone="caution" size="sm">{t('reports.master.noOwner')}</Status>}
                  </Box>
                  <Box component="td" sx={cellSx}>{e.areas.map((a) => a.area_name).join(', ')}</Box>
                  <Box component="td" sx={{ ...cellSx, textAlign: 'right' }}>{e.br_count}</Box>
                </tr>))}
            </tbody>
          </Box>
        </Card>)}
    </Stack>
  );
}
