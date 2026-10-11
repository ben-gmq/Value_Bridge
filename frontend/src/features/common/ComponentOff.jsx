import { Alert } from '@mui/material';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// The screen of a component this project does not use (D-37).
export default function ComponentOff({ name }) {
  return (
    <Page title={t('components.off', { name })}>
      <Alert severity="info">{t('components.offBody')}</Alert>
    </Page>
  );
}
