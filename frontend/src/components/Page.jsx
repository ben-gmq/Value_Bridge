import { Alert, Box, Stack, Typography } from '@mui/material';

// Scaffold §2 page shell: bold h5 title (mb 3) → error Alert → wrapper Box → content.
export function Page({ title, subtitle, actions, error, children }) {
  return (
    <Box>
      <Stack direction="row" sx={{ alignItems: 'flex-start', justifyContent: 'space-between', mb: 3, gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1" sx={(th) => ({ fontWeight: 700, color: th.vars.palette.brand.title })}>{title}</Typography>
          {subtitle && <Typography sx={{ color: 'text.secondary', mt: 0.5 }}>{subtitle}</Typography>}
        </Box>
        {actions && <Stack direction="row" spacing={1}>{actions}</Stack>}
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {children}
    </Box>
  );
}

// The wrapper Box — list filters AND detail headers share it (scaffold §2). Fill and border
// come from theme tokens so it works in dark mode (§14.2; recorded deviation).
export function WrapperBox({ children }) {
  return (
    <Box sx={{ mb: 3, mt: 2, p: 2, bgcolor: 'background.subtle', borderRadius: 1, border: 1, borderColor: 'divider' }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
        {children}
      </Stack>
    </Box>
  );
}
