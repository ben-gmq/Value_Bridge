import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { Page, WrapperBox } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';

export default function ProjectHome() {
  const { projectId } = useParams();
  const q = useQuery({ queryKey: ['project', projectId], queryFn: () => api.project(projectId) });
  const p = q.data;
  return (
    <Page title={p ? p.project_name : t('project.fallbackTitle')} error={q.error && errorText(q.error)}>
      {p && (
        <WrapperBox>
          <Stack><Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('project.code')}</Typography>
            <Typography sx={{ fontFamily: MONO }}>{p.project_code}</Typography></Stack>
          <Stack><Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('project.start')}</Typography>
            <Typography>{p.start_date ?? '—'}</Typography></Stack>
          <Stack><Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('project.end')}</Typography>
            <Typography>{p.end_date ?? '—'}</Typography></Stack>
        </WrapperBox>
      )}
      <Card><CardContent>
        <Typography variant="h6" component="h2" sx={{ mb: 1 }}>{t('project.dashboardTitle')}</Typography>
        <Typography sx={{ color: 'text.secondary' }}>
          {t('project.dashboardBody')}
        </Typography>
      </CardContent></Card>
    </Page>
  );
}
