import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Card, CardActionArea, CardContent, Chip, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { useAuth } from '../../app/AuthContext';
import { Page } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';

export default function HomePage() {
  const { isAdmin, me } = useAuth();
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const none = !projects.isLoading && (projects.data ?? []).length === 0;

  return (
    <Page title={t('home.title')}
      subtitle={isAdmin ? t('home.adminNote') : me?.scope === 'PROGRAM' ? t('home.programNote') : undefined}>
      {(programs.data ?? []).length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" component="h2" sx={{ mb: 1.5 }}>{t('home.programs')}</Typography>
          <Stack direction="row" useFlexGap spacing={2} sx={{ flexWrap: 'wrap' }}>
            {programs.data.map((g) => (
              <Card key={g.program_id} sx={{ width: 320 }}>
                <CardActionArea component={RouterLink} to={`/g/${g.program_id}`}>
                  <CardContent>
                    <Typography sx={{ fontFamily: MONO, fontSize: 12.5, color: 'text.secondary' }}>{g.program_code}</Typography>
                    <Typography sx={{ fontWeight: 700 }}>{g.program_name}</Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Stack>
        </Box>
      )}
      <Typography variant="h6" component="h2" sx={{ mb: 1.5 }}>{t('home.projects')}</Typography>
      {none && (
        <Typography sx={{ color: 'text.secondary' }}>
          {isAdmin ? t('home.emptyAdmin') : t('home.emptyUser')}
        </Typography>
      )}
      <Stack direction="row" useFlexGap spacing={2} sx={{ flexWrap: 'wrap' }}>
        {(projects.data ?? []).map((p) => (
          <Card key={p.project_id} sx={{ width: 320 }}>
            <CardActionArea component={RouterLink} to={`/p/${p.project_id}`}>
              <CardContent>
                <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography sx={{ fontFamily: MONO, fontSize: 12.5, color: 'text.secondary' }}>{p.project_code}</Typography>
                  {p.program_id && <Chip size="small" label={t('home.inProgram')} />}
                </Stack>
                <Typography sx={{ fontWeight: 700 }}>{p.project_name}</Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        ))}
      </Stack>
    </Page>
  );
}
