import { Card, CardContent, Typography } from '@mui/material';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// Placeholder: replaced by the Slice 1 organisation session. Keep the default export name.
export default function OrganisationPage() {
  return (
    <Page title={t('settings.organisation')}>
      <Card><CardContent><Typography sx={{ color: 'text.secondary' }}>{t('settings.building')}</Typography></CardContent></Card>
    </Page>
  );
}
