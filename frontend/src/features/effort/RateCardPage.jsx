import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, FormControlLabel, Snackbar, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { effortApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { Card, Tag, Tile } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { MONO } from '../../theme/theme';
import { TableFrame, TileRow } from '../frs/frKit';

const HIGH = 60;
const key = (c) => `${c.fr_type_code}|${c.complexity_code}`;

// The project's rate card (D-13, §4.8). any User (EDIT level) changes it with a reason (S6c-3, D-40); nothing is
// repriced (A-38) — each cell shows how many rated FRs are not at its current value (S6c-5).
export default function RateCardPage() {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.rateCard(projectId), queryFn: () => effortApi.card(projectId) });
  const [edits, setEdits] = useState(null);               // { key: value } while editing
  const [reason, setReason] = useState('');
  const [confirmHigh, setConfirmHigh] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const data = q.data;
  const cells = Object.fromEntries((data?.cells ?? []).map((c) => [key(c), c]));
  const changed = edits ? (data?.cells ?? []).filter((c) => edits[key(c)] !== undefined && edits[key(c)] !== ''
    && Number(edits[key(c)]) !== Number(c.standard_days ?? NaN)) : [];
  const needsConfirm = changed.some((c) => Number(edits[key(c)]) > HIGH);

  const save = useMutation({
    mutationFn: () => effortApi.saveCard(projectId, {
      change_rationale: reason, confirm_high: confirmHigh,
      cells: changed.map((c) => ({ fr_type_code: c.fr_type_code, complexity_code: c.complexity_code,
        standard_days: String(edits[key(c)]), row_version: c.row_version })),
    }),
    onSuccess: (res) => {
      const off = res.changes.reduce((n, l) => n + l.not_at_current_rate, 0);
      setNotice(off ? t('effort.card.savedOffRate', { n: off }) : t('effort.card.saved'));
      setEdits(null); setReason(''); setConfirmHigh(false); setError('');
      qc.invalidateQueries({ queryKey: keys.rateCard(projectId) });
      qc.invalidateQueries({ queryKey: keys.effortSummary(projectId) });
    },
    onError: (err) => {
      if (isStale(err)) { qc.invalidateQueries({ queryKey: keys.rateCard(projectId) }); setError(t('effort.card.stale')); }   // edits kept (sara L-4)
      else setError(errorText(err, t('common.saveFailed')));
    },
  });

  const allCells = data?.cells ?? [];
  const unconfirmedCount = allCells.filter((c) => c.unconfirmed_default).length;
  const offRateCount = allCells.reduce((m, c) => m + c.not_at_current_rate, 0);

  return (
    <Page title={t('effort.card.title')} subtitle={t('effort.card.subtitle')} crumb={t('effort.card.title')}
      error={q.error && errorText(q.error)}
      actions={canEdit && !edits && data && (
        <Button variant="outlined" onClick={() => { setError(''); setEdits({}); }}>{t('effort.card.edit')}</Button>)}>
      {data && (
        <TileRow min={220}>
          <Tile label={t('effort.card.tileUnconfirmed')} value={unconfirmedCount} tone={unconfirmedCount ? 'caution' : undefined} />
          <Tile label={t('effort.card.tileOffRate')} value={offRateCount} tone={offRateCount ? 'caution' : undefined}
            note={t('effort.card.legend')} />
        </TileRow>)}
      {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      {data && (
        <Card title={t('effort.card.gridTitle')}>
          <TableFrame>
            <Table size="small" aria-label={t('effort.card.title')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('effort.card.type')}</TableCell>
                  {data.complexities.map((c) => <TableCell key={c.code} align="right">{c.label}</TableCell>)}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.types.map((ty) => (
                  <TableRow key={ty.code}>
                    <TableCell sx={{ verticalAlign: 'top' }}><Tag tone="navy">{ty.label}</Tag></TableCell>
                    {data.complexities.map((cx) => {
                      const c = cells[`${ty.code}|${cx.code}`];
                      return (
                        <TableCell key={cx.code} align="right" sx={{ verticalAlign: 'top', minWidth: 150 }}>
                          {edits ? (
                            <TextField size="small" type="number" sx={{ width: 110 }}
                              slotProps={{ htmlInput: { step: '0.25', min: '0.01', 'aria-label': `${ty.label} × ${cx.label}` } }}
                              value={edits[key(c)] ?? (c.standard_days ?? '')}
                              onChange={(e) => setEdits({ ...edits, [key(c)]: e.target.value })} />
                          ) : (
                            <Typography sx={{ fontFamily: MONO, fontSize: 15, fontWeight: 600 }}>
                              {c.standard_days ?? <Box component="span" sx={{ color: 'text.disabled', fontFamily: 'inherit' }}>{t('effort.card.noCell')}</Box>}</Typography>
                          )}
                          <Stack spacing={0.5} sx={{ alignItems: 'flex-end', mt: 0.5 }}>
                            {c.unconfirmed_default && <Tag tone="neutral">{t('effort.card.unconfirmed')}</Tag>}
                            {c.high && <Tag tone="caution">{t('effort.card.high')}</Tag>}
                            {c.not_at_current_rate > 0 && (
                              <Typography sx={{ fontSize: 12, color: 'status.caution' }}>
                                {t('effort.card.offRate', { n: c.not_at_current_rate, days: c.not_at_current_rate_days })}</Typography>)}
                          </Stack>
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          {edits && (
            <Stack spacing={2}>
              <TextField id="rate-reason" label={t('effort.card.reason')} helperText={t('effort.card.reasonHelp')}
                required multiline minRows={2} value={reason} onChange={(e) => setReason(e.target.value)}
                slotProps={{ htmlInput: { maxLength: 4000 } }} />
              {needsConfirm && (
                <FormControlLabel control={<Checkbox checked={confirmHigh} onChange={(e) => setConfirmHigh(e.target.checked)} />}
                  label={t('effort.card.confirmHigh')} />)}
              <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                <Button onClick={() => { setEdits(null); setReason(''); setConfirmHigh(false); setError(''); }}>{t('effort.card.cancel')}</Button>
                <Button variant="contained" disabled={save.isPending || !changed.length || !reason.trim() || (needsConfirm && !confirmHigh)}
                  onClick={() => { setError(''); save.mutate(); }}>{t('effort.card.save')}</Button>
              </Stack>
            </Stack>
          )}
        </Card>
      )}
      <Snackbar open={Boolean(notice)} autoHideDuration={5000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
