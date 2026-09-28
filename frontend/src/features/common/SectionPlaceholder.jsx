import { Card, CardContent, Typography } from '@mui/material';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// The shell is final from day one; each section is filled by its build slice (plan §3).
export default function SectionPlaceholder({ section, slice }) {
  const title = t(`section.${section}.title`);
  const what = t(`section.${section}.what`);
  return (
    <Page title={title}>
      <Card><CardContent>
        <Typography sx={{ fontWeight: 600, mb: 0.5 }}>{t('section.arrives', { slice })}</Typography>
        <Typography sx={{ color: 'text.secondary' }}>{what}</Typography>
      </CardContent></Card>
    </Page>
  );
}
