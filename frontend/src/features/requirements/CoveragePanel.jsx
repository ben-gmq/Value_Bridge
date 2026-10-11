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
 * The mockup's purple "Coverage" panel (D-51): the FRs this requirement reaches through its live
 * solutions — v_br_function_requirement, derived, never stored (D-7) — with each FR's effort_days
 * from the FR register (derived server-side; shown, never sent). Read-only: FRs are edited on their page.
 */
export function CoveragePanel({ projectId, brId }) {
  const q = useQuery({ queryKey: [...keys.frTrace(), 'br', String(brId)], queryFn: () => frApi.ofBr(brId) });
  // Same key and call as the FR register's default view, so the two share one cache entry.
  const frsQ = useQuery({ queryKey: [...keys.frs(projectId), { retired: false, unlinked: false }],
    queryFn: () => frApi.list(projectId, { includeRetired: false, unlinked: false }) });
  const days = useMemo(() => new Map((frsQ.data ?? []).map((f) => [f.fr_id, f.effort_days])), [frsQ.data]);
  // One row per FR; an FR reached through two solutions lists both.
  const frs = useMemo(() => {
    const by = new Map();
    for (const r of q.data ?? []) {
      const e = by.get(r.fr_id) ?? { ...r, via: [] };
      e.via.push(r.solution_number);
      by.set(r.fr_id, e);
    }
    return [...by.values()];
  }, [q.data]);

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
            title={t('frs.via', { solution: r.via.join(', ') })}
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
