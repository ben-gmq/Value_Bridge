import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile, Status } from '../../components/kit';
import { t } from '../../i18n/t';
import { ShareBar } from './OrgImpact';
import { Generated, Loading, Off } from './reportKit';

// Stakeholder engagement (docs/slice_control_b_spec.md §2.3, CB-3): each org unit on a change, its share, and whether
// it has a voice — a stakeholder in it, or in its direct parent, raised an issue. Silence is the signal. The server
// decides the voice; the screen only lays it out. Names render as text (VB law 9).
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'left' };
const TONE = { OWN: 'ok', PARENT: 'ok' };

export function Engagement({ projectId }) {
  const q = useQuery({ queryKey: keys.engagement(projectId), queryFn: () => controlApi.engagement(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const h = d.headline;
  if (h.reason === 'ISSUE_OFF' || h.reason === 'SOLUTION_OFF') {
    return <><Generated at={d.generated_at} /><Off projectId={projectId} component={h.reason.replace('_OFF', '')} /></>;
  }
  return (
    <Stack sx={{ gap: 2 }}>
      <Generated at={d.generated_at} />
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.engagement.intro')}</Typography>
      {h.reason ? <Alert severity="info">{t(`control.reason.${h.reason}`)}</Alert> : (
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <PurpleTile label={t('reports.engagement.top')} value={Number(h.measured)} unit="%"
            note={h.top_unit ?? t('reports.engagement.allHeard')} />
          <PurpleTile label={t('reports.engagement.silent')} value={h.silent_units}
            note={t('reports.engagement.ofAffected', { n: h.affected_units })} />
        </Stack>)}
      {d.units?.length > 0 && (
        <Card title={t('reports.tab.engagement')} bodySx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                {['unit', 'share', 'voice', 'raised', 'speakers'].map((k) => (
                  <Box component="th" key={k} scope="col" sx={{ ...cellSx, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
                    {t(`reports.engagement.${k}`)}
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
                  <Box component="td" sx={cellSx}>
                    <Status tone={TONE[u.voice] ?? 'caution'} size="sm">{t(`reports.engagement.voice.${u.voice ?? 'NONE'}`)}</Status>
                  </Box>
                  <Box component="td" sx={cellSx}>
                    {t('reports.engagement.raisedCell', { own: u.issues_raised, parent: u.parent_issues_raised })}
                  </Box>
                  <Box component="td" sx={{ ...cellSx, color: 'text.secondary' }}>
                    {u.speakers.length ? u.speakers.map((s) => `${s.stakeholder_name} (${s.issues})`).join(', ') : '–'}
                  </Box>
                </tr>))}
            </tbody>
          </Box>
        </Card>)}
    </Stack>
  );
}
