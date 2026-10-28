import { Alert, Box, CircularProgress, Typography } from '@mui/material';
import { useCodes } from '../../app/useCodes';
import { t } from '../../i18n/t';

// The time a report was worked out, always in ICT (spec §3.1), whatever the browser's own zone.
export function Generated({ at }) {
  const when = new Date(at).toLocaleString('en-GB', { timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short',
    year: 'numeric', hour: '2-digit', minute: '2-digit' });
  return <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1.5 }}>{t('reports.generated', { at: when })}</Typography>;
}

// A report part whose component is off is null from the server (A1); the screen says so rather than "none". The
// component's name is its code_master label, the one the Components settings screen shows.
export function Off({ projectId, component }) {
  const { getLabel } = useCodes(projectId, 'PROJECT_COMPONENT');
  return <Alert severity="info">{t('reports.off', { component: getLabel(component) })}</Alert>;
}

export function Loading() {
  return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress size={28} /></Box>;
}
