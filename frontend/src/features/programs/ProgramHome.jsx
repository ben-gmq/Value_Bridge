import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card, CardActionArea, CardContent, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { Page } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';

// D-32: a program is a roll-up, never a data layer. Every figure here is one per-project
// result; drill-downs open the project's own screens (§14.3).
export default function ProgramHome() {
  const { programId } = useParams();
  const prog = useQuery({ queryKey: ['program', programId], queryFn: () => api.program(programId) });
  const projects = useQuery({ queryKey: ['program-projects', programId], queryFn: () => api.programProjects(programId) });
  return (
    <Page title={prog.data?.program_name ?? t('program.fallbackTitle')} subtitle={t('program.subtitle')}
      error={(prog.error || projects.error) && errorText(prog.error || projects.error)}>
      <Stack direction="row" useFlexGap spacing={2} sx={{ flexWrap: 'wrap' }}>
        {(projects.data ?? []).map((p) => (
          <Card key={p.project_id} sx={{ width: 320 }}>
            <CardActionArea component={RouterLink} to={`/p/${p.project_id}`}>
              <CardContent>
                <Typography sx={{ fontFamily: MONO, fontSize: 12.5, color: 'text.secondary' }}>{p.project_code}</Typography>
                <Typography sx={{ fontWeight: 700 }}>{p.project_name}</Typography>
                <Typography sx={{ fontSize: 13, color: 'text.secondary', mt: 1 }}>{t('program.rollupSoon')}</Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        ))}
      </Stack>
    </Page>
  );
}
