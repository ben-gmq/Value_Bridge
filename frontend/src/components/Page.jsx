import { Alert, Box, Stack, Typography } from '@mui/material';
import { usePageCrumb } from './AppShell';

// The mockups' page header (D-51): optional eyebrow (e.g. a level badge and hierarchy code), a 24/700 title,
// a muted subtitle, actions aligned to the bottom right. `crumb` names the item in the header breadcrumb
// (e.g. "BR-0043"); the section crumbs come from the route.
export function Page({ title, subtitle, eyebrow, crumb, actions, error, children }) {
  usePageCrumb(crumb);
  return (
    <Box>
      <Stack direction="row" useFlexGap sx={{ alignItems: 'flex-end', justifyContent: 'space-between', mb: 2.5, gap: 2, flexWrap: 'wrap' }}>
        <Box sx={{ flex: '1 1 320px', minWidth: 0 }}>
          {eyebrow && <Box sx={{ mb: 0.5 }}>{eyebrow}</Box>}
          <Typography variant="h5" component="h1" sx={{ color: 'brand.title', wordBreak: 'break-word' }}>{title}</Typography>
          {subtitle && <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mt: 0.5 }}>{subtitle}</Typography>}
        </Box>
        {actions && <Stack direction="row" useFlexGap sx={{ gap: 1.25, flexWrap: 'wrap', alignItems: 'center' }}>{actions}</Stack>}
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {children}
    </Box>
  );
}

// The wrapper Box — list filters AND detail headers share it (scaffold §2). Fill and border
// come from theme tokens so it works in both schemes (§14.2; recorded deviation).
export function WrapperBox({ children }) {
  return (
    <Box sx={{ mb: 3, mt: 2, p: 2, bgcolor: 'background.subtle', borderRadius: '14px', border: 1, borderColor: 'divider' }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
        {children}
      </Stack>
    </Box>
  );
}
