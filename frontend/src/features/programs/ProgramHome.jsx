import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Snackbar, Stack } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { Code, SectionLabel, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { CARD_GRID, EngagementCard } from '../projects/homeKit';
import ProgramEditDialog from './ProgramEditDialog';
import ProgramMembers from './ProgramMembers';

// D-32: a program is a roll-up, never a data layer. Every figure here is one per-project
// result; drill-downs open the project's own screens (§14.3).
export default function ProgramHome() {
  const { programId } = useParams();
  const prog = useQuery({ queryKey: keys.program(programId), queryFn: () => api.program(programId) });
  const projects = useQuery({ queryKey: ['program-projects', programId], queryFn: () => api.programProjects(programId) });
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  // Slice 1f §3.7: Edit shows to platform admins only (presentation; the guard refuses everyone else).
  const canEdit = prog.data?.my_access_level === 'PLATFORM';
  return (
    <Page title={prog.data?.program_name ?? t('program.fallbackTitle')} subtitle={prog.data?.description || t('program.subtitle')}
      eyebrow={prog.data?.program_code && <Code tone="muted">{prog.data.program_code}</Code>}
      actions={canEdit && <Button variant="outlined" onClick={() => setEditing(true)}>{t('program.edit.button')}</Button>}
      error={(prog.error || projects.error) && errorText(prog.error || projects.error)}>
      {editing && prog.data && (
        <ProgramEditDialog program={prog.data} projectCount={projects.data?.length ?? 0} onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); setSaved(true); }} />)}
      <Snackbar open={saved} autoHideDuration={4000} onClose={() => setSaved(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {saved ? <Alert severity="success" variant="filled" onClose={() => setSaved(false)}>{t('program.edit.saved')}</Alert> : undefined}
      </Snackbar>
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
