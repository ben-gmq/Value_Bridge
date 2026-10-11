import { useQuery } from '@tanstack/react-query';
import { Box, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { useAuth } from '../../app/AuthContext';
import { SectionLabel, Tag, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { CARD_GRID, EngagementCard } from './homeKit';

export default function HomePage() {
  const { isAdmin, me } = useAuth();
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const none = !projects.isLoading && (projects.data ?? []).length === 0;

  return (
    <Page title={t('home.title')}
      subtitle={isAdmin ? t('home.adminNote') : t(`home.kindNote.${me?.user_kind ?? 'VIEWER'}`)}>
      <Stack spacing={3}>
        {(projects.data || programs.data) && (
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 200px), 1fr))' }}>
            <Tile label={t('home.projects')} value={(projects.data ?? []).length} />
            <Tile label={t('home.programs')} value={(programs.data ?? []).length} />
          </Box>
        )}
        {(programs.data ?? []).length > 0 && (
          <Box>
            <SectionLabel sx={{ mb: 1.5 }}>{t('home.programs')}</SectionLabel>
            <Box sx={CARD_GRID}>
              {programs.data.map((g) => (
                <EngagementCard key={g.program_id} to={`/g/${g.program_id}`} code={g.program_code} name={g.program_name} />))}
            </Box>
          </Box>
        )}
        <Box>
          <SectionLabel sx={{ mb: 1.5 }}>{t('home.projects')}</SectionLabel>
          {none && (
            <Typography sx={{ color: 'text.secondary' }}>
              {isAdmin ? t('home.emptyAdmin') : t('home.emptyUser')}
            </Typography>
          )}
          <Box sx={CARD_GRID}>
            {(projects.data ?? []).map((p) => (
              <EngagementCard key={p.project_id} to={`/p/${p.project_id}`} code={p.project_code} name={p.project_name}
                tags={(
                  <>
                    {p.program_id && <Tag tone="navy">{t('home.inProgram')}</Tag>}
                    {p.is_restricted && <Tag tone="caution">{t('settings.acc.restricted')}</Tag>}
                  </>)} />))}
          </Box>
        </Box>
      </Stack>
    </Page>
  );
}
