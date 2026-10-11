import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { effortApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { t } from '../../i18n/t';
import { SectionTitle, SimpleSelect } from '../processes/chartKit';

/**
 * Rating an FR (§7.13): choosing a complexity copies the card's current days onto the FR — never typed
 * (law 6). Re-rating at the same complexity takes today's rate, explicitly (S6c-2). When the card has
 * moved since, the FR says so (S6c-5).
 */
export function FrEffort({ projectId, fr, onRated }) {
  const qc = useQueryClient();
  const canEdit = useCanEdit() && fr.is_active;
  const { codes } = useCodes(projectId, 'FR_COMPLEXITY');
  const cardQ = useQuery({ queryKey: keys.rateCard(projectId), queryFn: () => effortApi.card(projectId) });
  const [pick, setPick] = useState(fr.complexity_code ?? '');
  const [error, setError] = useState('');
  const current = (cardQ.data?.cells ?? []).find((c) => c.fr_type_code === fr.fr_type_code && c.complexity_code === fr.complexity_code);
  const offRate = fr.effort_days != null && current?.standard_days != null && Number(current.standard_days) !== Number(fr.effort_days);
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
    <Box>
      <SectionTitle>{t('effort.fr.title')}</SectionTitle>
      {error && <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>{error}</Alert>}
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
        <Box sx={{ width: 220 }}>
          {canEdit ? (
            <SimpleSelect id="fr-complexity" label={t('effort.fr.complexity')} value={pick} allowEmpty emptyLabel={t('effort.fr.notRated')}
              onChange={setPick} options={codes.map((c) => ({ value: c.code, label: c.label }))} />
          ) : <Typography>{codes.find((c) => c.code === fr.complexity_code)?.label ?? t('effort.fr.notRated')}</Typography>}
        </Box>
        <Typography sx={{ fontWeight: 700 }}>
          {fr.effort_days != null ? t('effort.fr.days', { days: fr.effort_days }) : t('effort.fr.notRated')}</Typography>
        {canEdit && (
          <Button variant="outlined" size="small" disabled={rate.isPending || (same && !offRate)}
            onClick={() => { setError(''); rate.mutate(); }}>
            {same && offRate ? t('effort.fr.rerate') : t('effort.fr.rate')}</Button>)}
      </Stack>
      {offRate && <Typography sx={{ fontSize: 12.5, color: 'status.caution', mt: 1 }}>
        {t('effort.fr.offRate', { days: current.standard_days })}</Typography>}
    </Box>
  );
}
