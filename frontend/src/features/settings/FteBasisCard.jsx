import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, TextField, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { volumeApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card } from '../../components/kit';
import { t } from '../../i18n/t';

// D-67 (slice 13c, Q-7): the project's FTE basis — hours in one FTE = working days × hours per day. Everyone sees it;
// a platform admin changes it. A change moves every process's FTE on its next read and touches no process (C4); each
// baseline keeps the basis it was frozen with (C6).
export function FteBasisCard({ projectId, isAdmin, onNotice }) {
  const qc = useQueryClient();
  const project = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const p = project.data;
  const [days, setDays] = useState('');
  const [hours, setHours] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { if (p) { setDays(String(p.working_days_per_year)); setHours(String(p.hours_per_working_day)); } }, [p]);
  const dirty = p && (Number(days) !== p.working_days_per_year || Number(hours) !== Number(p.hours_per_working_day));
  const save = useMutation({
    mutationFn: () => volumeApi.setBasis(projectId, { row_version: p.row_version, working_days_per_year: Number(days),
      hours_per_working_day: hours }),
    onSuccess: () => { setError(''); onNotice(t('components.fte.saved'));
      qc.invalidateQueries({ queryKey: keys.project(projectId) });
      qc.invalidateQueries({ queryKey: ['bfc-node'] });              // every process's volume re-derives
      qc.invalidateQueries({ queryKey: keys.volumeSummary(projectId) }); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  if (!p) return null;
  const per = Number(days) * Number(hours);
  return (
    <Card title={t('components.fte.title')} bodySx={{ gap: 1.25 }}>
      <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t('components.fte.what')}</Typography>
      {error && <Alert severity="error">{error}</Alert>}
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField size="small" id="fte-days" type="number" label={t('components.fte.days')} value={days} disabled={!isAdmin}
          onChange={(e) => setDays(e.target.value)} sx={{ width: 190 }} slotProps={{ htmlInput: { min: 1, max: 366 } }} />
        <TextField size="small" id="fte-hours" type="number" label={t('components.fte.hours')} value={hours} disabled={!isAdmin}
          onChange={(e) => setHours(e.target.value)} sx={{ width: 190 }} slotProps={{ htmlInput: { min: 0.25, max: 24, step: 0.25 } }} />
        <Typography sx={{ fontSize: 13.5 }}>
          {Number.isFinite(per) && per > 0 ? t('components.fte.per', { h: per.toLocaleString('en-GB') }) : ''}</Typography>
      </Box>
      {isAdmin && (
        <Box>
          <Button variant="contained" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {t('components.fte.save')}</Button>
        </Box>)}
    </Card>
  );
}
