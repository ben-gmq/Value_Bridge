import { Link as RouterLink, useParams } from 'react-router-dom';
import { Card, CardActionArea, CardContent, Grid, Typography } from '@mui/material';
import { Page } from '../../components/Page';
import { links } from '../../app/links';
import { t } from '../../i18n/t';

// Settings holds configuration and master data other screens pick from (Ben, 2026-09-29, S1-9).
const ITEMS = [['access', links.access], ['organisation', links.organisation], ['parties', links.parties]];

export default function SettingsPage() {
  const { projectId } = useParams();
  return (
    <Page title={t('settings.title')} subtitle={t('settings.subtitle')}>
      <Grid container spacing={2}>
        {ITEMS.map(([key, to]) => (
          <Grid key={key} size={{ xs: 12, md: 4 }}>
            <Card sx={{ height: '100%' }}>
              <CardActionArea component={RouterLink} to={to(projectId)} sx={{ height: '100%' }}>
                <CardContent>
                  <Typography sx={{ fontWeight: 700, mb: 0.5 }}>{t(`settings.${key}`)}</Typography>
                  <Typography sx={{ color: 'text.secondary' }}>{t(`settings.${key}What`)}</Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Page>
  );
}
