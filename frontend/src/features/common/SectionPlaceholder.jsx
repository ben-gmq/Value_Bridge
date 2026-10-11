import { Typography } from '@mui/material';
import { Card } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// The shell is final from day one; each section is filled by its build slice (plan §3).
export default function SectionPlaceholder({ section, slice }) {
  const title = t(`section.${section}.title`);
  const what = t(`section.${section}.what`);
  return (
    <Page title={title}>
      <Card title={t('section.arrives', { slice })}>
        <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{what}</Typography>
      </Card>
    </Page>
  );
}
