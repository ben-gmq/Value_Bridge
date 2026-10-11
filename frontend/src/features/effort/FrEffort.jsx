import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import LockOutlined from '@mui/icons-material/LockOutlined';
import { errorText, isStale } from '../../api/client';
import { effortApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { Card, PurpleTile, SectionLabel, Segmented, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';

const num = (v) => (v == null ? null : Number(v));

// The card's current cell for this FR's type and complexity, and whether the FR's days have moved off it (S6c-5).
function useCurrentRate(projectId, fr) {
  const cardQ = useQuery({ queryKey: keys.rateCard(projectId), queryFn: () => effortApi.card(projectId) });
  const cells = cardQ.data?.cells ?? [];
  const current = cells.find((c) => c.fr_type_code === fr.fr_type_code && c.complexity_code === fr.complexity_code);
  const offRate = fr.effort_days != null && current?.standard_days != null && num(current.standard_days) !== num(fr.effort_days);
  return { cardQ, cells, current, offRate };
}

/**
 * Rating an FR (§7.13): choosing a complexity copies the card's current days onto the FR — never typed
 * (law 6). Re-rating at the same complexity takes today's rate, explicitly (S6c-2). When the card has
 * moved since, the FR says so (S6c-5). Rating is its own action, apart from the form's Save.
 */
export function FrEffort({ projectId, fr, onRated }) {
  const qc = useQueryClient();
  const canEdit = useCanEdit() && fr.is_active;
  const { codes, getLabel } = useCodes(projectId, 'FR_COMPLEXITY');
  const { current, offRate } = useCurrentRate(projectId, fr);
  const [pick, setPick] = useState(fr.complexity_code ?? '');
  const [error, setError] = useState('');
  const rate = useMutation({
    mutationFn: () => effortApi.rate(fr.fr_id, { row_version: fr.row_version, complexity_code: pick || null }),
    onSuccess: (row) => {
      setError('');
      qc.invalidateQueries({ queryKey: keys.rateCard(projectId) });
      qc.invalidateQueries({ queryKey: keys.effortSummary(projectId) });
      onRated(row);
    },
    onError: (err) => setError(isStale(err) ? t('frs.staleAction') : errorText(err, t('common.saveFailed'))),
  });
  const same = (pick || null) === (fr.complexity_code ?? null);
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      <SectionLabel>{t('effort.fr.complexity')}</SectionLabel>
      {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
      {canEdit ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Segmented label={t('effort.fr.complexity')} value={pick} onChange={setPick}
            options={[...codes.map((c) => ({ value: c.code, label: c.label })), { value: '', label: t('effort.fr.notRated') }]} />
          <Button variant="outlined" size="small" disabled={rate.isPending || (same && !offRate)}
            onClick={() => { setError(''); rate.mutate(); }}>
            {same && offRate ? t('effort.fr.rerate') : t('effort.fr.rate')}</Button>
        </Box>
      ) : (
        <Box><Tag tone={fr.complexity_code ? 'purple' : 'neutral'}>
          {fr.complexity_code ? getLabel(fr.complexity_code) : t('effort.fr.notRated')}</Tag></Box>
      )}
      {canEdit && !same && <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('effort.fr.pickHint')}</Typography>}
      {offRate && <Typography sx={{ fontSize: 12.5, color: 'status.caution' }}>
        {t('effort.fr.offRate', { days: current.standard_days })}</Typography>}
    </Box>
  );
}

/**
 * The FR page's side panel (mockup 06): the stored effort as the key figure, the lock note, and the
 * rate card row for this FR's type with its complexity highlighted. Read-only.
 */
export function FrEffortSide({ projectId, fr }) {
  const { getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const { getLabel: complexityLabel } = useCodes(projectId, 'FR_COMPLEXITY');
  const { cardQ, cells } = useCurrentRate(projectId, fr);
  const complexities = cardQ.data?.complexities ?? [];
  const forType = (code) => cells.find((c) => c.fr_type_code === fr.fr_type_code && c.complexity_code === code);
  const rated = fr.effort_days != null;
  return (
    <>
      <PurpleTile label={t('effort.fr.title')} value={rated ? num(fr.effort_days) : '—'} unit={rated ? t('effort.fr.unit') : undefined}
        note={fr.complexity_code ? `${typeLabel(fr.fr_type_code)} × ${complexityLabel(fr.complexity_code)}` : t('effort.fr.notRated')} />
      <Box sx={(th) => ({ display: 'flex', gap: 1, alignItems: 'flex-start', p: 1.75, borderRadius: '16px',
        bgcolor: th.vars.palette.background.paper, border: `1px solid ${th.vars.palette.divider}` })}>
        <LockOutlined sx={{ fontSize: 18, color: 'brand.purpleText', mt: '1px' }} />
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('effort.fr.lockNote')}</Typography>
      </Box>
      <Card title={t('effort.fr.cardFor', { type: typeLabel(fr.fr_type_code) })}>
        {cardQ.error && <Alert severity="error">{errorText(cardQ.error)}</Alert>}
        {cardQ.data && (
          <Table size="small">
            <TableHead>
              <TableRow><TableCell>{t('effort.fr.complexity')}</TableCell><TableCell align="right">{t('effort.days')}</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {complexities.map((cx) => {
                const on = cx.code === fr.complexity_code;
                const cell = forType(cx.code);
                return (
                  <TableRow key={cx.code} sx={(th) => ({ bgcolor: on ? th.vars.palette.brand.purpleTint : 'transparent' })}>
                    <TableCell sx={{ fontWeight: on ? 700 : 400 }}>{cx.label}</TableCell>
                    <TableCell align="right" sx={{ fontFamily: MONO, color: on ? 'brand.purpleText' : undefined }}>
                      {cell?.standard_days != null ? num(cell.standard_days) : t('effort.card.noCell')}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', color: 'brand.muted' }}>
          <InfoOutlined sx={{ fontSize: 16 }} /><Typography sx={{ fontSize: 12.5 }}>{t('effort.fr.cardHint')}</Typography>
        </Box>
      </Card>
    </>
  );
}
