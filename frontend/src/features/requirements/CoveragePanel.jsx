import { useMemo } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { frApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';

/**
 * The mockup's purple "Coverage" panel (D-51): the FRs this requirement maps to — its stored links (D-52),
 * edited in the requirement's Function requirements section — with each FR's effort_days from the FR
 * register (derived server-side; shown, never sent). Read-only. Effort is never summed by BR: an FR
 * serving three BRs would count three times (slice10b_schema §6.4).
 */
export function CoveragePanel({ projectId, brId }) {
  const q = useQuery({ queryKey: keys.brFrs(brId), queryFn: () => frApi.ofBr(brId) });
  // Same key and call as the FR register's default view, so the two share one cache entry.
  const frsQ = useQuery({ queryKey: keys.frList(projectId), queryFn: () => frApi.list(projectId) });
  const days = useMemo(() => new Map((frsQ.data ?? []).map((f) => [f.fr_id, f.effort_days])), [frsQ.data]);
  // One row per link, so one per FR (the link grain is BR × FR).
  const frs = useMemo(() => [...new Map((q.data ?? []).map((r) => [r.fr_id, r])).values()], [q.data]);

  return (
    <Box component="section" aria-labelledby="br-coverage" sx={(th) => ({ borderRadius: '24px', bgcolor: th.vars.palette.brand.ftc,
      p: 2.5, display: 'flex', flexDirection: 'column', gap: 1.25, minWidth: 0 })}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography component="h2" id="br-coverage" sx={(th) => ({ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em',
          textTransform: 'uppercase', color: th.vars.palette.brand.onFtcTile, flexGrow: 1 })}>{t('requirements.coverage')}</Typography>
        <Link component={RouterLink} to={links.frs(projectId)} underline="hover"
          sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.onFtcTile })}>{t('requirements.coverageRegister')}</Link>
      </Box>
      {(q.error || frsQ.error) && <Alert severity="error">{errorText(q.error || frsQ.error)}</Alert>}
      {!q.isLoading && !q.error && (
        <Typography sx={(th) => ({ fontSize: 17, fontWeight: 700, color: th.vars.palette.brand.onFtc })}>
          {frs.length === 0 ? t('requirements.coverageNone')
            : t(frs.length === 1 ? 'requirements.coverageOne' : 'requirements.coverageMany', { n: frs.length })}
        </Typography>)}
      {frs.length === 0 && !q.isLoading && !q.error && (
        <Typography sx={(th) => ({ fontSize: 13, color: th.vars.palette.brand.onFtcTile })}>{t('requirements.coverageHint')}</Typography>)}
      {frs.map((r) => {
        const d = days.get(r.fr_id);
        return (
          <Box key={r.fr_id} component={RouterLink} to={links.fr(projectId, r.fr_id)}
            title={r.solution_number ? t('frs.via', { solution: `${r.solution_number} ${r.solution_name ?? ''}` }) : undefined}
            sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, minHeight: 38, py: 0.5, borderRadius: '14px',
              textDecoration: 'none', bgcolor: th.vars.palette.brand.onFtcFill,
              '&:hover': { bgcolor: th.vars.palette.brand.onFtcHover } })}>
            <Box component="span" sx={(th) => ({ fontFamily: MONO, fontSize: 12, color: th.vars.palette.brand.purpleLight, whiteSpace: 'nowrap' })}>
              {r.fr_number}</Box>
            <Typography noWrap sx={(th) => ({ fontSize: 13.5, color: th.vars.palette.brand.onFtc, flexGrow: 1, minWidth: 0 })}>{r.fr_name}</Typography>
            {d != null && (
              <Box component="span" sx={(th) => ({ fontFamily: MONO, fontSize: 12, color: th.vars.palette.brand.onFtcTile, whiteSpace: 'nowrap' })}>
                {t('requirements.days', { n: Number(d) })}</Box>)}
          </Box>
        );
      })}
    </Box>
  );
}
