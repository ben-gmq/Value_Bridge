import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Stack } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { Code, SectionLabel, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { CARD_GRID, EngagementCard } from '../projects/homeKit';
import ProgramMembers from './ProgramMembers';

// D-32: a program is a roll-up, never a data layer. Every figure here is one per-project
// result; drill-downs open the project's own screens (§14.3).
export default function ProgramHome() {
  const { programId } = useParams();
  const prog = useQuery({ queryKey: ['program', programId], queryFn: () => api.program(programId) });
  const projects = useQuery({ queryKey: ['program-projects', programId], queryFn: () => api.programProjects(programId) });
  return (
    <Page title={prog.data?.program_name ?? t('program.fallbackTitle')} subtitle={t('program.subtitle')}
      eyebrow={prog.data?.program_code && <Code tone="muted">{prog.data.program_code}</Code>}
      error={(prog.error || projects.error) && errorText(prog.error || projects.error)}>
      <Stack spacing={3}>
        {projects.data && (
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 200px), 1fr))' }}>
            <Tile label={t('home.projects')} value={projects.data.length} />
          </Box>
        )}
        <Box>
          <SectionLabel sx={{ mb: 1.5 }}>{t('home.projects')}</SectionLabel>
          <Box sx={CARD_GRID}>
            {(projects.data ?? []).map((p) => (
              <EngagementCard key={p.project_id} to={`/p/${p.project_id}`} code={p.project_code} name={p.project_name}
                note={t('program.rollupSoon')} />))}
          </Box>
        </Box>
        {['ADMIN', 'PLATFORM'].includes(prog.data?.my_access_level) && <ProgramMembers programId={programId} />}
      </Stack>
    </Page>
  );
}
