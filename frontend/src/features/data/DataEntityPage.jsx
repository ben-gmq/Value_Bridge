import { Card, CardContent, Typography } from '@mui/material';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// Placeholder: replaced by the Slice 1 data session. Keep the default export name.
export default function DataEntityPage() {
  return (
    <Page title={t('data.title')}>
      <Card><CardContent><Typography sx={{ color: 'text.secondary' }}>{t('data.building')}</Typography></CardContent></Card>
    </Page>
  );
}
