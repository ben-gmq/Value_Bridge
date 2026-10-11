import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack,
  TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { baselineApi } from '../../api/scope';
import { keys } from '../../app/links';
import { t } from '../../i18n/t';
import { fmtValue, lineLabel } from './baselineKit';

// A freeze 409 carries {message, errors, freeze_blocking}; other errors a plain string.
export function detailText(err) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return d?.message ?? 'Something went wrong.';
}

// A gap names its step and, because both charts share codes, which chart it is on (UAT 8).
export function itemText(x) {
  if (typeof x !== 'object' || x === null) return fmtValue(x);
  if (x.hier_code) return x.bfc_set_code ? `${x.hier_code} (${t(`baselines.dlg.chart.${x.bfc_set_code}`)})` : x.hier_code;
  return fmtValue(x.label ?? x.component ?? x.de_number ?? x.br_number ?? '');
}

function Lines({ title, lines, severity }) {
  const entries = Object.entries(lines ?? {});
  if (!entries.length) return null;
  return (
    <Alert severity={severity} sx={{ mt: 1 }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{title}</Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {entries.map(([k, v]) => (
          <li key={k}>
            <Typography sx={{ fontSize: 13 }}>{t('baselines.line.count', { line: lineLabel(k), n: v.length })}</Typography>
            <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
              {v.slice(0, 5).map(itemText).join(', ')}
              {v.length > 5 ? ' …' : ''}
            </Typography>
          </li>
        ))}
      </Box>
    </Alert>
  );
}

// §5.1 and DR8-P2: the dialog shows what will be frozen and what it supersedes, and sends back the preview's
// digest — if the scope moves while it is open, the server refuses and nothing is saved.
export function FreezeDialog({ projectId, open, onClose, onFrozen }) {
  const qc = useQueryClient();
  const [bump, setBump] = useState('MINOR');
  const [note, setNote] = useState('');
  const [typed, setTyped] = useState('');
  const pv = useQuery({ queryKey: keys.baselineNext(projectId, bump), queryFn: () => baselineApi.next(projectId, bump),
    enabled: open, staleTime: 0, gcTime: 0 });
  const other = useQuery({ queryKey: keys.baselineNext(projectId, bump === 'MINOR' ? 'MAJOR' : 'MINOR'),
    queryFn: () => baselineApi.next(projectId, bump === 'MINOR' ? 'MAJOR' : 'MINOR'), enabled: open, staleTime: 0, gcTime: 0 });
  const p = pv.data;
  const blocked = p && (Object.keys(p.errors).length > 0 || Object.keys(p.freeze_blocking).length > 0);
  const save = useMutation({
    mutationFn: () => baselineApi.freeze(projectId, { note: note || null, bump, confirm_text: typed,
      preview_digest: p.preview_digest }),
    onSuccess: (out) => {
      qc.invalidateQueries({ queryKey: keys.baselines(projectId) });
      qc.invalidateQueries({ queryKey: keys.brs(projectId) });
      qc.invalidateQueries({ queryKey: ['br'] });
      setNote(''); setTyped(''); setBump('MINOR');
      onFrozen(out);
    },
    onError: () => pv.refetch(),
  });
  const labels = { [bump]: p?.next_label, [bump === 'MINOR' ? 'MAJOR' : 'MINOR']: other.data?.next_label };
  const total = p ? Object.values(p.counts_by_entity).reduce((a, b) => a + b, 0) : 0;
  const areas = p ? Object.values(p.counts_by_entity).filter((n) => n > 0).length : 0;
  const close = () => { save.reset(); onClose(); };
  return (
    <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
      <DialogTitle>{t('baselines.dlg.title', { label: p?.next_label ?? '' })}</DialogTitle>
      <DialogContent>
        {pv.isLoading && <CircularProgress size={24} />}
        {p && (
          <Stack spacing={2} sx={{ pt: 1 }}>
            {p.prior_label && (
              <ToggleButtonGroup exclusive size="small" value={bump} onChange={(_, v) => v && (setBump(v), setTyped(''))}>
                <ToggleButton value="MINOR">{t('baselines.dlg.minor', { label: labels.MINOR ?? '' })}</ToggleButton>
                <ToggleButton value="MAJOR">{t('baselines.dlg.major', { label: labels.MAJOR ?? '' })}</ToggleButton>
              </ToggleButtonGroup>
            )}
            <TextField label={t('baselines.dlg.note')} helperText={t('baselines.dlg.noteHelp')} value={note}
              onChange={(e) => setNote(e.target.value)} size="small" fullWidth multiline maxRows={4}
              slotProps={{ htmlInput: { maxLength: 4000 } }} />
            <Box>
              <Typography sx={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.4 }}>{t('baselines.dlg.check').toUpperCase()}</Typography>
              {!blocked && <Alert severity="success" sx={{ mt: 1 }}>{t('baselines.dlg.ready')}</Alert>}
              <Lines title={t('baselines.dlg.errors')} lines={p.errors} severity="error" />
              <Lines title={t('baselines.dlg.blocking')} lines={p.freeze_blocking} severity="error" />
              <Lines title={t('baselines.dlg.warnings')} lines={p.warnings} severity="warning" />
            </Box>
            {p.supersedes && (
              <Alert severity={p.supersedes.awaiting_sign_off ? 'warning' : 'info'}>
                {p.supersedes.awaiting_sign_off
                  ? t('baselines.dlg.supersedesUnsigned', { label: p.supersedes.version_label })
                  : t('baselines.dlg.supersedes', { label: p.supersedes.version_label })}
              </Alert>
            )}
            {!blocked && (
              <>
                <Typography sx={{ fontSize: 13.5 }}>{t('baselines.dlg.counts', { n: total, m: areas })}</Typography>
                <TextField label={t('baselines.dlg.typeToConfirm', { text: p.confirm_text })} value={typed}
                  onChange={(e) => setTyped(e.target.value)} size="small" fullWidth autoComplete="off"
                  slotProps={{ htmlInput: { 'aria-label': t('baselines.dlg.typeToConfirm', { text: p.confirm_text }) } }} />
              </>
            )}
            {save.error && <Alert severity="error">{detailText(save.error)}</Alert>}
          </Stack>
        )}
        {pv.error && <Alert severity="error">{detailText(pv.error)}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.cancel')}</Button>
        <Button variant="contained" color="warning" disabled={!p || blocked || typed !== p.confirm_text || save.isPending}
          onClick={() => save.mutate()}>{t('baselines.dlg.confirm')}</Button>
      </DialogActions>
    </Dialog>
  );
}
