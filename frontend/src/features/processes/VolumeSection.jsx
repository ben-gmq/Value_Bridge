import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, MenuItem, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { bfcApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Segmented } from '../../components/kit';
import { t } from '../../i18n/t';

// D-67 (slice 13c): a process's volume figures. The server derives hours and FTE (services/process_volume.py);
// the screen only shows them. SP-1: typed figures wait for the panel's one Save, with the unsaved counter and the
// leave guard. The period and the unit wait too: they are checked together with their numbers (a period without a
// number is refused), so saving them alone would only produce a refusal.
const PERIODS = ['DAY', 'WEEK', 'MONTH', 'QUARTER', 'YEAR'];
const blank = (v) => (v == null ? '' : String(Number(v)));

/** Seconds as stored → what the time field shows: minutes when it reads better (one minute or more). */
function timeView(seconds) {
  if (seconds == null) return { time: '', timeUnit: 'min' };
  const s = Number(seconds);
  return s >= 60 ? { time: String(Number((s / 60).toFixed(4))), timeUnit: 'min' } : { time: String(s), timeUnit: 's' };
}

function fromServer(d) {
  return {
    runs: blank(d?.runs_per_period), period: d?.volume_period_code ?? '',
    txns: blank(d?.transactions_per_run), unit: d?.transaction_unit_code ?? '',
    ...timeView(d?.seconds_per_transaction),
  };
}

/** The time field in seconds, to the millisecond (minutes × 60 is exact for up to 4 decimals of a minute). */
const toSeconds = (time, unit) => (time.trim() === '' ? null
  : (Math.round(Number(time) * (unit === 'min' ? 60 : 1) * 1000) / 1000).toFixed(3));
const num = (v) => (v.trim() === '' ? null : v.trim());

export function useVolumeEditor({ nodeId, enabled }) {
  const qc = useQueryClient();
  const key = [...keys.node(nodeId), 'volume'];
  const q = useQuery({ queryKey: key, queryFn: () => bfcApi.volume(nodeId), enabled });
  const saved = useMemo(() => fromServer(q.data), [q.data]);
  const [values, setValues] = useState(saved);
  const [error, setError] = useState('');
  useEffect(() => { setValues(saved); setError(''); }, [saved]);

  // What would be sent: only the figures whose stored value differs from what is typed.
  const sent = useMemo(() => {
    if (!q.data) return {};
    const out = {};
    const now = { runs_per_period: num(values.runs), volume_period_code: values.period || null,
      transactions_per_run: num(values.txns), transaction_unit_code: values.unit || null,
      seconds_per_transaction: toSeconds(values.time, values.timeUnit) };
    const was = { runs_per_period: num(saved.runs), volume_period_code: saved.period || null,
      transactions_per_run: num(saved.txns), transaction_unit_code: saved.unit || null,
      seconds_per_transaction: toSeconds(saved.time, saved.timeUnit) };
    for (const k of Object.keys(now)) {
      const a = now[k] == null ? null : String(now[k]);
      const b = was[k] == null ? null : String(was[k]);
      if (k.endsWith('_code') ? a !== b : (a === null) !== (b === null) || (a !== null && Number(a) !== Number(b))) out[k] = now[k];
    }
    return out;
  }, [values, saved, q.data]);
  const changedCount = Object.keys(sent).length;

  const m = useMutation({
    mutationFn: () => bfcApi.setVolume(nodeId, { row_version: q.data.row_version, ...sent }),
    onSuccess: (d) => { qc.setQueryData(key, d); setError(''); },
    onError: (err) => setError(isStale(err) ? t('processes.volume.conflict') : errorText(err)),
  });
  return {
    data: q.data, values, changedCount, busy: m.isPending, error,
    set: (k, v) => setValues((p) => ({ ...p, [k]: v })),
    setTime: (time, timeUnit) => setValues((p) => ({ ...p, time, timeUnit })),
    canSave: Boolean(q.data) && changedCount > 0,
    saveNow: () => m.mutateAsync().then(() => true, () => false),
    discard: () => { setValues(saved); setError(''); },
  };
}

const hours = (h) => Number(h).toLocaleString('en-GB', { maximumFractionDigits: 1 });
// FTE half-up to two decimals (0.325 → 0.33), as the spec's worked case reads it (C1).
const fte = (f) => (Math.round(Number(f) * 100 + 1e-9) / 100).toFixed(2);

/** "624 h a year · 0.33 FTE", or what is still missing — for the section's collapsed line. */
export function volumeSummary(d) {
  if (!d) return '';
  if (d.annual_hours != null) return t('processes.volume.summary', { h: hours(d.annual_hours), fte: fte(d.fte) });
  return d.incomplete.length === 4 ? t('processes.volume.none') : t('processes.volume.partial');
}

export function VolumeSection({ projectId, ed, disabled }) {
  const units = useCodes(projectId, 'TRANSACTION_UNIT');
  const d = ed.data;
  if (!d) return null;
  const v = ed.values;
  const field = { size: 'small', disabled, sx: { width: 140 } };
  const label = (k) => <Typography sx={{ fontSize: 13, fontWeight: 600, minWidth: 170 }}>{t(`processes.volume.${k}`)}</Typography>;
  const row = { display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap' };
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box sx={row}>
        {label('runs')}
        <TextField {...field} id="vol-runs" type="number" value={v.runs} onChange={(e) => ed.set('runs', e.target.value)}
          slotProps={{ htmlInput: { min: 0, step: 'any', 'aria-label': t('processes.volume.runs') } }} />
        <TextField {...field} id="vol-period" select value={v.period} onChange={(e) => ed.set('period', e.target.value)}
          slotProps={{ select: { displayEmpty: true }, htmlInput: { 'aria-label': t('processes.volume.period') } }}>
          <MenuItem value="">{t('processes.volume.noPeriod')}</MenuItem>
          {PERIODS.map((p) => <MenuItem key={p} value={p}>{t(`processes.volume.per.${p}`)}</MenuItem>)}
        </TextField>
      </Box>
      <Box sx={row}>
        {label('txns')}
        <TextField {...field} id="vol-txns" type="number" value={v.txns} onChange={(e) => ed.set('txns', e.target.value)}
          slotProps={{ htmlInput: { min: 0, step: 'any', 'aria-label': t('processes.volume.txns') } }} />
        <TextField {...field} id="vol-unit" select value={v.unit} onChange={(e) => ed.set('unit', e.target.value)}
          slotProps={{ select: { displayEmpty: true }, htmlInput: { 'aria-label': t('processes.volume.unit') } }}>
          <MenuItem value="">{t('processes.volume.noUnit')}</MenuItem>
          {units.codes.map((c) => <MenuItem key={c.code} value={c.code}>{c.label}</MenuItem>)}
        </TextField>
      </Box>
      <Box sx={row}>
        {label('time')}
        <TextField {...field} id="vol-time" type="number" value={v.time} onChange={(e) => ed.setTime(e.target.value, v.timeUnit)}
          slotProps={{ htmlInput: { min: 0, step: 'any', 'aria-label': t('processes.volume.time') } }} />
        <Segmented size="sm" label={t('processes.volume.timeUnit')} value={v.timeUnit}
          onChange={disabled ? undefined : (u) => ed.setTime(v.time, u)}
          options={[{ value: 'min', label: t('processes.volume.min') }, { value: 's', label: t('processes.volume.sec') }]} />
      </Box>
      {ed.error && <Alert severity="error">{ed.error}</Alert>}
      <Box sx={(th) => ({ p: 1.5, borderRadius: '12px', bgcolor: th.vars.palette.background.subtle })}>
        {d.annual_hours != null ? (
          <Typography sx={{ fontSize: 14, fontWeight: 600 }}>
            {t('processes.volume.result', { h: hours(d.annual_hours), fte: fte(d.fte) })}</Typography>
        ) : (
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('processes.volume.needs', { what: d.incomplete.map((k) => t(`processes.volume.field.${k}`)).join(', ') })}</Typography>
        )}
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 0.5 }}>
          {t('processes.volume.basis', { days: d.working_days_per_year, hpd: Number(d.hours_per_working_day),
            per: Number(d.working_days_per_year * d.hours_per_working_day).toLocaleString('en-GB') })}
          {ed.changedCount > 0 && ` · ${t('processes.volume.onSave')}`}</Typography>
      </Box>
    </Box>
  );
}
