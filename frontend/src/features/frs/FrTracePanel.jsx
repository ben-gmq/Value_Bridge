import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Link, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Code, SectionLabel, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';
import { TableFrame } from './frKit';

const days = (v) => (v == null ? null : Number(v));

/**
 * The FRs tagged with a solution (read-only; FRs are edited on their own page): type, complexity, rated
 * effort and the solution's total. A BR's FRs are its stored links (D-52), shown and edited in the
 * requirement's own Function requirements section (requirements/BrFrLinks.jsx), not here.
 */
export function FrTracePanel({ projectId, id }) {
  const { getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const { getLabel: complexityLabel } = useCodes(projectId, 'FR_COMPLEXITY');
  const q = useQuery({ queryKey: [...keys.frTrace(), 'solution', String(id)], queryFn: () => solutionApi.frs(id) });
  const rows = q.data ?? [];
  const rated = rows.filter((r) => days(r.effort_days) != null);
  const total = rated.reduce((n, r) => n + days(r.effort_days), 0);
  const unrated = rows.length - rated.length;
  const frLink = (r) => (
    <Link component={RouterLink} to={links.fr(projectId, r.fr_id)} underline="hover"><Code>{r.fr_number}</Code></Link>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      <SectionLabel action={(
        <Button size="small" variant="outlined" component={RouterLink} to={links.frs(projectId)}>{t('frs.goRegister')}</Button>)}>
        {t('frs.panelSolution')}
      </SectionLabel>
      {q.error && <Alert severity="error">{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
          {t('frs.panelNoneSolution')}</Typography>)}
      {rows.length > 0 && (
        <TableFrame>
          <Table size="small" sx={{ minWidth: 520 }}>
            <TableHead>
              <TableRow>
                <TableCell>{t('frs.number')}</TableCell><TableCell>{t('frs.name')}</TableCell>
                <TableCell>{t('frs.type')}</TableCell><TableCell>{t('frs.trace.complexity')}</TableCell>
                <TableCell align="right">{t('frs.trace.effort')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.fr_id}>
                  <TableCell>{frLink(r)}</TableCell>
                  <TableCell>{r.fr_name}</TableCell>
                  <TableCell>{r.fr_type_code && <Tag tone="navy">{typeLabel(r.fr_type_code)}</Tag>}</TableCell>
                  <TableCell sx={{ color: r.complexity_code ? undefined : 'text.secondary' }}>
                    {r.complexity_code ? complexityLabel(r.complexity_code) : t('effort.fr.notRated')}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: MONO, whiteSpace: 'nowrap' }}>
                    {days(r.effort_days) != null ? t('frs.trace.days', { d: days(r.effort_days) }) : '—'}</TableCell>
                </TableRow>
              ))}
              <TableRow sx={{ '& td': { fontWeight: 700, borderBottom: 0 } }}>
                <TableCell colSpan={4}>
                  {t('frs.trace.total')}
                  {unrated > 0 && (
                    <Typography component="span" sx={{ ml: 1, fontSize: 12.5, fontWeight: 400, color: 'status.caution' }}>
                      {t('frs.trace.unrated', { n: unrated })}</Typography>)}
                </TableCell>
                <TableCell align="right" sx={{ fontFamily: MONO, whiteSpace: 'nowrap', color: 'brand.purpleText' }}>
                  {t('frs.trace.days', { d: total })}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableFrame>
      )}
    </Box>
  );
}
