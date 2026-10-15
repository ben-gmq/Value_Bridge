import { Link as RouterLink, useParams } from 'react-router-dom';
import { Box, Typography } from '@mui/material';
import { Page } from '../../components/Page';
import { links } from '../../app/links';
import { useComponents } from '../../app/useComponents';
import { useAuth } from '../../app/AuthContext';
import { t } from '../../i18n/t';

// Settings holds configuration and master data other screens pick from (Ben, 2026-09-29, S1-9). The organisation
// and the systems are rail items under Scope since D-56.
const ITEMS = [['access', links.access, null, true], ['components', links.components],
  ['parties', links.parties], ['rateCard', links.rateCard, 'EFFORT']];

export default function SettingsPage() {
  const { projectId } = useParams();
  const { isOn } = useComponents(projectId);
  const { isAdmin } = useAuth();
  return (
    <Page title={t('settings.title')} subtitle={t('settings.subtitle')}>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))' }}>
        {ITEMS.filter(([, , need, adminOnly]) => (!need || isOn(need)) && (!adminOnly || isAdmin)).map(([key, to]) => (
          <Box key={key} component={RouterLink} to={to(projectId)} sx={(th) => ({ display: 'flex', flexDirection: 'column', gap: 0.5,
            p: 2.25, borderRadius: '24px', bgcolor: th.vars.palette.background.paper, border: `1px solid ${th.vars.palette.divider}`,
            color: 'inherit', textDecoration: 'none',
            '&:hover, &:focus-visible': { borderColor: th.vars.palette.brand.ftcViolet, bgcolor: th.vars.palette.brand.selected } })}>
            <Typography sx={{ fontWeight: 700, fontSize: 15 }}>{t(`settings.${key}`)}</Typography>
            <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t(`settings.${key}What`)}</Typography>
          </Box>
        ))}
      </Box>
    </Page>
  );
}
