import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { baselineApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, KV, ListRow, PurpleTile, SectionLabel, Status, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { AgreedChip, StatusChip, entityLabel, fmtDate } from '../baselines/baselineKit';

// The working-set figures shown as tiles, from the freeze preview's live counts (only what is in use).
const FIGURES = ['bfc_node', 'data_entity', 'solution', 'function_requirement'];

// The project dashboard (no mockup; D-51 kit): the key figure in purple, live counts as tiles, the project
// card and the baselines card. Every number is the server's.
export default function ProjectHome() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const counts = useQuery({ queryKey: keys.baselineNext(projectId, 'MINOR'), queryFn: () => baselineApi.next(projectId, 'MINOR'),
    staleTime: 60_000 });
  const bl = useQuery({ queryKey: keys.baselines(projectId), queryFn: () => baselineApi.list(projectId) });
  const p = q.data;
  const n = counts.data?.counts_by_entity;
  const latest = bl.data?.[0];
  return (
    <Page title={p ? p.project_name : t('project.fallbackTitle')} error={q.error && errorText(q.error)}
      eyebrow={p && <Code tone="muted">{p.project_code}</Code>}>
      <Stack spacing={2}>
        {n && (
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'minmax(0, 1.35fr) repeat(4, minmax(0, 1fr))' } }}>
            <PurpleTile label={entityLabel('business_requirement')} value={n.business_requirement ?? 0}
              note={t('settings.home.working')} sx={{ gridColumn: { xs: '1 / -1', md: 'auto' } }} />
            {FIGURES.map((e) => <Tile key={e} label={entityLabel(e)} value={n[e] ?? 0} />)}
          </Box>
        )}
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' }, alignItems: 'start' }}>
          {p && (
            <Card title={t('settings.acc.project')} bodySx={{ gap: 1 }}>
              <KV k={t('project.code')} v={<Code>{p.project_code}</Code>} />
              <KV k={t('project.start')} v={p.start_date ?? '—'} mono />
              <KV k={t('project.end')} v={p.end_date ?? '—'} mono />
              <KV k={t('admin.restricted')} v={(
                <Status tone={p.is_restricted ? 'caution' : 'ok'} size="sm">
                  {p.is_restricted ? t('settings.acc.restricted') : t('settings.acc.open')}</Status>)} />
            </Card>
          )}
          <Card title={t('baselines.title')}
            action={<Button size="small" variant="outlined" component={RouterLink} to={links.baselines(projectId)}>{t('settings.home.open')}</Button>}
            bodySx={{ gap: 1 }}>
            <SectionLabel>{t('settings.home.latest')}</SectionLabel>
            {latest ? (
              <ListRow component={RouterLink} to={links.baseline(projectId, latest.baseline_id)}>
                <Code sx={{ fontSize: 14, fontWeight: 600 }}>{latest.version_label}</Code>
                <Typography sx={{ fontSize: 12.5, color: 'text.secondary', flexGrow: 1, minWidth: 0 }}>{fmtDate(latest.frozen_at)}</Typography>
                <StatusChip code={latest.status_code} label={latest.status_label} />
                {latest.is_agreed && <AgreedChip />}
              </ListRow>
            ) : bl.isSuccess && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('baselines.none')}</Typography>}
          </Card>
        </Box>
        <Card title={t('project.dashboardTitle')}>
          <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t('project.dashboardBody')}</Typography>
        </Card>
      </Stack>
    </Page>
  );
}
