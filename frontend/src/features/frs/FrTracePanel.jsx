import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Chip, Link, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { frApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { t } from '../../i18n/t';
import { Mono, SectionTitle } from '../processes/chartKit';

/**
 * The FRs a page's object leads to (read-only; FRs are edited on their own page). On a solution
 * page: the FRs under it. On a BR page: the FRs reached through its live solutions — derived
 * through v_br_function_requirement, never stored (D-7).
 */
export function FrTracePanel({ projectId, side, id }) {
  const onBr = side === 'br';
  const { getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const q = useQuery({ queryKey: [...keys.frTrace(), side, String(id)],
    queryFn: () => (onBr ? frApi.ofBr(id) : solutionApi.frs(id)) });
  const rows = q.data ?? [];
  return (
    <Box>
      <SectionTitle action={(
        <Link component={RouterLink} to={links.frs(projectId)} sx={{ fontSize: 13 }}>{t('frs.goRegister')}</Link>)}>
        {t(onBr ? 'frs.panelBr' : 'frs.panelSolution')}
      </SectionTitle>
      {q.error && <Alert severity="error" sx={{ mb: 1 }}>{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
          {t(onBr ? 'frs.panelNoneBr' : 'frs.panelNoneSolution')}</Typography>)}
      <Stack spacing={1}>
        {rows.map((r) => (
          <Stack key={`${r.fr_id}-${r.solution_id}`} direction="row" spacing={1} useFlexGap
            sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Link component={RouterLink} to={links.fr(projectId, r.fr_id)} underline="hover" sx={{ fontWeight: 600 }}>
              <Mono>{r.fr_number}</Mono> {r.fr_name}</Link>
            {r.fr_type_code && <Chip size="small" variant="outlined" label={typeLabel(r.fr_type_code)} />}
            {onBr && (
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
                {t('frs.via', { solution: `${r.solution_number} ${r.solution_name}` })}</Typography>)}
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}
