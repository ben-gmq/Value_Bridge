import { Link as RouterLink } from 'react-router-dom';
import { Box, Stack, Typography } from '@mui/material';
import { Code } from '../../components/kit';

// A clickable engagement card (a project or a program) on the home and program screens, kit look.
export function EngagementCard({ to, code, name, tags, note }) {
  return (
    <Box component={RouterLink} to={to} sx={(th) => ({ display: 'flex', flexDirection: 'column', gap: 0.75, p: 2.25, minWidth: 0,
      borderRadius: '24px', bgcolor: th.vars.palette.background.paper, border: `1px solid ${th.vars.palette.divider}`,
      color: 'inherit', textDecoration: 'none', transition: 'border-color 120ms',
      '&:hover, &:focus-visible': { borderColor: th.vars.palette.brand.ftcViolet, bgcolor: th.vars.palette.brand.selected } })}>
      <Stack direction="row" useFlexGap sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
        <Code tone="muted" sx={{ fontSize: 12.5 }}>{code}</Code>
        <Box sx={{ flexGrow: 1 }} />
        {tags}
      </Stack>
      <Typography sx={{ fontWeight: 700, fontSize: 15, wordBreak: 'break-word' }}>{name}</Typography>
      {note && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{note}</Typography>}
    </Box>
  );
}

export const CARD_GRID = { display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))' };
