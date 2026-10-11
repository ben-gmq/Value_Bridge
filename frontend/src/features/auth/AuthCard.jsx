import { Box, Typography } from '@mui/material';
import { Card } from '../../components/kit';
import { t } from '../../i18n/t';

// Sign-in and first-run setup share one centred card (D-51, no mockup): the VB logo tile and name, a title,
// an optional intro, then the form.
export function AuthCard({ title, intro, width = 420, children }) {
  return (
    <Card sx={{ width, maxWidth: '100%' }} bodySx={{ p: { xs: 3, sm: 4 }, gap: 2.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
        <Box aria-hidden sx={(th) => ({ width: 40, height: 40, borderRadius: '12px', bgcolor: th.vars.palette.brand.ftc,
          color: th.vars.palette.brand.onFtc, display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 14 })}>VB</Box>
        <Typography sx={{ fontWeight: 700, fontSize: 16 }}>{t('app.name')}</Typography>
      </Box>
      <Box>
        <Typography variant="h5" component="h1" sx={{ color: 'brand.title' }}>{title}</Typography>
        {intro && <Typography sx={{ color: 'text.secondary', fontSize: 13.5, mt: 0.75 }}>{intro}</Typography>}
      </Box>
      {children}
    </Card>
  );
}
