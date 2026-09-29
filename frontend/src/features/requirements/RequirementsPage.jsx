import { Card, CardContent, Typography } from '@mui/material';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// Placeholder: replaced by the Slice 1 chart session. Keep the default export name.
export default function RequirementsPage() {
  return (
    <Page title={t('requirements.title')}>
      <Card><CardContent><Typography sx={{ color: 'text.secondary' }}>{t('requirements.building')}</Typography></CardContent></Card>
    </Page>
  );
}
