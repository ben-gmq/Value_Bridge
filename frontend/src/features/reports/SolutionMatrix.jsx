import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { reportApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading, Off, Printable } from './reportKit';

// Solution matrix (spec §3.3, function 66, criterion 10b): to-be L1 areas down, the five solution categories across.
// Every category is a column even when empty, so a missing Organization & rules answer is visible. The server counts;
// the screen only lays the counts out. A cell reads "solutions · BRs".
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'center' };

function Count({ c }) {
  if (!c || c.solutions === 0) return <Typography component="span" sx={{ color: 'text.disabled' }}>–</Typography>;
  return (
    <Box component="span" sx={{ fontWeight: 600 }}>{c.solutions}
      <Typography component="span" sx={{ fontSize: 12, color: 'text.secondary', ml: 0.5 }}>{t('reports.matrix.brs', { n: c.brs })}</Typography>
    </Box>
  );
}

export function SolutionMatrix({ projectId }) {
  const q = useQuery({ queryKey: keys.solutionMatrix(projectId), queryFn: () => reportApi.solutionMatrix(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  if (d.rows === null) return <><Generated at={d.generated_at} /><Off projectId={projectId} component="SOLUTION" /></>;
  const head = (label, key) => (
    <Box component="th" key={key} scope="col" sx={{ ...cellSx, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>{label}</Box>
  );
  return (
    <Printable projectId={projectId} report="solution_matrix" query={q} data={d}>
      <Stack sx={{ gap: 2 }}>
        <Box>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.matrix.intro')}</Typography>
        </Box>
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <PurpleTile label={t('reports.matrix.share')} value={d.technology_share ?? '–'}
            unit={d.technology_share === null ? undefined : '%'} note={t('reports.matrix.shareNote')} />
          {d.rejected_count > 0 && <Tag tone="neutral">{t('reports.matrix.rejected', { n: d.rejected_count })}</Tag>}
        </Stack>
        <Card title={t('reports.tab.solution_matrix')} bodySx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                {head(t('reports.matrix.area'), 'area')}
                {d.categories.map((c) => head(c.label, c.code))}
                {head(t('reports.matrix.total'), 'total')}
              </tr>
            </thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.bfc_node_id}>
                  <Box component="th" scope="row" sx={{ ...cellSx, textAlign: 'left', fontWeight: 400 }}>
                    <Code tone="muted">{r.hier_code}</Code> {r.area_name}
                  </Box>
                  {d.categories.map((c) => <Box component="td" key={c.code} sx={cellSx}><Count c={r.cells[c.code]} /></Box>)}
                  <Box component="td" sx={cellSx}><Count c={r.total} /></Box>
                </tr>
              ))}
              <tr>
                <Box component="th" scope="row" sx={{ ...cellSx, textAlign: 'left', fontWeight: 400, color: 'text.secondary' }}>
                  {t('reports.matrix.unlinked')}
                </Box>
                {d.categories.map((c) => (
                  <Box component="td" key={c.code} sx={cellSx}>{d.unlinked[c.code].solutions || '–'}</Box>
                ))}
                <Box component="td" sx={cellSx} />
              </tr>
              <tr>
                <Box component="th" scope="row" sx={{ ...cellSx, textAlign: 'left' }}>{t('reports.matrix.totals')}</Box>
                {d.categories.map((c) => <Box component="td" key={c.code} sx={{ ...cellSx, fontWeight: 600 }}>{d.totals[c.code]}</Box>)}
                <Box component="td" sx={{ ...cellSx, fontWeight: 600 }}>{d.live_count}</Box>
              </tr>
            </tbody>
          </Box>
        </Card>
      </Stack>
    </Printable>
  );
}
