import { Link as RouterLink, useParams } from 'react-router-dom';
import { Tab, Tabs } from '@mui/material';
import { links } from '../../app/links';
import { t } from '../../i18n/t';

// S6a-4: the BR–FR map section holds two registers, Solutions and Function requirements.
export function BrFrTabs({ current }) {
  const { projectId } = useParams();
  return (
    <Tabs value={current} sx={{ mb: 1, borderBottom: 1, borderColor: 'divider' }}>
      <Tab value="solutions" label={t('frs.tabSolutions')} component={RouterLink} to={links.solutions(projectId)} />
      <Tab value="frs" label={t('frs.tabFrs')} component={RouterLink} to={links.frs(projectId)} />
    </Tabs>
  );
}
