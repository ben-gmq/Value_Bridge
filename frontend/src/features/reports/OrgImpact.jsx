import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading, Off } from './reportKit';

// Organisation impact (docs/slice_control_b_spec.md §2.2, CB-2): each org unit and the share of the changes one of its
// roles is responsible or accountable for, on the future-state RACI. Consulted / informed and the as-is RACI are
// context, never counted. The server works out every share; the screen only lays it out.
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'left' };
const pct = (v) => t('reports.impact.pct', { v: Number(v) });

export function ShareBar({ value }) {
  return (
    <Stack direction="row" sx={{ alignItems: 'center', gap: 1 }}>
      <Box sx={{ width: 120, height: 8, borderRadius: 4, bgcolor: 'action.hover', overflow: 'hidden' }}>
        <Box sx={{ width: `${Math.min(Number(value), 100)}%`, height: '100%', bgcolor: 'primary.main' }} />
      </Box>
      <Typography component="span" sx={{ fontSize: 13.5, fontWeight: 600 }}>{pct(value)}</Typography>
    </Stack>
  );
}

export function OrgImpact({ projectId }) {
  const q = useQuery({ queryKey: keys.orgImpact(projectId), queryFn: () => controlApi.orgImpact(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const h = d.headline;
  if (h.reason === 'SOLUTION_OFF') return <><Generated at={d.generated_at} /><Off projectId={projectId} component="SOLUTION" /></>;
  const asIs = (d.units ?? []).some((u) => u.as_is_steps !== null);
  const cols = ['unit', 'share', 'changes', 'heard', 'roles', ...(asIs ? ['asIs'] : [])];
  return (
    <Stack sx={{ gap: 2 }}>
      <Generated at={d.generated_at} />
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.impact.intro')}</Typography>
      {h.reason ? <Alert severity="info">{t(`control.reason.${h.reason}`)}</Alert> : (
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <PurpleTile label={t('reports.impact.top')} value={Number(h.measured)} unit="%" note={h.top_unit} />
          <PurpleTile label={t('reports.impact.changes')} value={h.changes}
            note={t('reports.impact.withoutRa', { n: h.changes_without_ra })} />
        </Stack>)}
      {d.units?.length > 0 && (
        <Card title={t('reports.tab.org_impact')} bodySx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                {cols.map((k) => (
                  <Box component="th" key={k} scope="col" sx={{ ...cellSx, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
                    {t(`reports.impact.${k}`)}
                  </Box>))}
              </tr>
            </thead>
            <tbody>
              {d.units.map((u) => (
                <tr key={u.org_unit_id}>
                  <Box component="th" scope="row" sx={{ ...cellSx, fontWeight: 400 }}>
                    <Code tone="muted">{u.org_unit_code}</Code> {u.org_unit_name}
                  </Box>
                  <Box component="td" sx={cellSx}><ShareBar value={u.share} /></Box>
                  <Box component="td" sx={cellSx}>{u.changes}</Box>
                  <Box component="td" sx={{ ...cellSx, color: 'text.secondary' }}>{u.heard_only}</Box>
                  <Box component="td" sx={cellSx}>{u.ra_roles.join(', ') || '–'}</Box>
                  {asIs && <Box component="td" sx={{ ...cellSx, color: 'text.secondary' }}>{u.as_is_steps ?? '–'}</Box>}
                </tr>))}
            </tbody>
          </Box>
        </Card>)}
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('reports.impact.note')}</Typography>
    </Stack>
  );
}
