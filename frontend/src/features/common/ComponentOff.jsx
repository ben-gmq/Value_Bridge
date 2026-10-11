import { Typography } from '@mui/material';
import { Card, Status } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// The screen of a component this project does not use (D-37).
export default function ComponentOff({ name }) {
  return (
    <Page title={t('components.off', { name })}>
      <Card bodySx={{ gap: 1.25 }}>
        <Status tone="neutral" size="sm">{name}</Status>
        <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t('components.offBody')}</Typography>
      </Card>
    </Page>
  );
}
