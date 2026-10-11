import { Box, Typography } from '@mui/material';
import CheckRounded from '@mui/icons-material/CheckRounded';

/**
 * The mockups' step progress (docs/mockups/src/kit.jsx `Steps`, mockup 08), on theme tokens. Not in
 * components/kit.jsx (frozen for slice 9); lives here until the kit takes it.
 * `steps` = [{ key, label, done?, note? }]; `current` is the index of the step in progress.
 */
export function Steps({ steps, current, label }) {
  return (
    <Box component="ol" aria-label={label} sx={{ display: 'flex', alignItems: 'center', gap: 1, m: 0, p: 0, listStyle: 'none',
      flexWrap: 'wrap', rowGap: 1 }}>
      {steps.map((st, i) => {
        const done = st.done ?? i < current;
        const on = i === current;
        return (
          <Box component="li" key={st.key} aria-current={on ? 'step' : undefined} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {i > 0 && <Box aria-hidden sx={(th) => ({ width: 28, height: 2, borderRadius: 1,
              bgcolor: done || on ? th.vars.palette.brand.ftcViolet : th.vars.palette.brand.lineStrong })} />}
            <Box sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 1, minHeight: 32, pl: 0.5, pr: 1.5, borderRadius: 999,
              bgcolor: on ? th.vars.palette.brand.purpleTint : 'transparent',
              border: `1px solid ${on ? th.vars.palette.brand.ftcViolet : 'transparent'}` })}>
              <Box sx={(th) => ({ width: 24, height: 24, borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 700,
                flexShrink: 0, bgcolor: done ? th.vars.palette.brand.ftcViolet : on ? th.vars.palette.text.primary : 'transparent',
                color: done ? th.vars.palette.brand.onFtc : on ? th.vars.palette.background.paper : th.vars.palette.brand.muted,
                border: done || on ? 0 : `1.5px solid ${th.vars.palette.brand.lineStrong}` })}>
                {done ? <CheckRounded sx={{ fontSize: 15 }} aria-hidden /> : i + 1}
              </Box>
              <Box>
                <Typography sx={(th) => ({ fontSize: 13.5, fontWeight: on ? 700 : 500, whiteSpace: 'nowrap',
                  color: on ? th.vars.palette.text.primary : done ? th.vars.palette.text.secondary : th.vars.palette.brand.muted })}>
                  {st.label}</Typography>
                {st.note && <Typography sx={{ fontSize: 11.5, color: 'brand.muted', lineHeight: 1.2 }}>{st.note}</Typography>}
              </Box>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
