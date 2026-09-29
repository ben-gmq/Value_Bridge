import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Alert, Breadcrumbs, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl,
  FormControlLabel, InputLabel, Link, MenuItem, Select, Stack, Switch, TextField, Typography } from '@mui/material';
import { errorText, isConflict } from '../../api/client';
import { links } from '../../app/links';
import { ConflictDialog } from '../../components/ConflictDialog';
import { t } from '../../i18n/t';

// Shared pieces of the two settings screens (client organisation, external parties).

// A 409 is a stale row_version only when the backend says so (services/errors.py CONFLICT,
// lifecycle.check_version). Every other 409 names its blocker and is shown as text.
const STALE_DETAIL = 'Updated by another user';
export const isStale = (err) =>
  isConflict(err) && String(err?.response?.data?.detail ?? '').startsWith(STALE_DETAIL);

export function SettingsCrumbs({ projectId, current }) {
  return (
    <Breadcrumbs sx={{ mb: 1.5 }}>
      <Link component={RouterLink} to={links.settings(projectId)} underline="hover" color="inherit">
        {t('settings.title')}
      </Link>
      <Typography sx={{ color: 'text.primary' }}>{current}</Typography>
    </Breadcrumbs>
  );
}

export function ShowRetired({ checked, onChange, id }) {
  return (
    <FormControlLabel label={t('settings.showRetired')}
      control={<Switch id={id} checked={checked} onChange={(e) => onChange(e.target.checked)} />} />
  );
}

// Optional text → null, so an emptied description is cleared rather than saved as ''.
const clean = (field, v) => {
  if (field.type === 'number') return v === '' || v == null ? null : Number(v);
  if (typeof v === 'string') return v.trim() === '' ? null : v.trim();
  return v ?? null;
};

/**
 * One add/edit dialog. `fields`: [{ name, label, required, multiline, type: 'number'|'select',
 * options: [{ value, label }], emptyLabel, helperText }]. `row` is the record being edited
 * (null to add). onSubmit(body, rowVersion) returns a promise; the body holds every field,
 * trimmed, optional blanks as null (row_version is added by the caller for an edit).
 * A stale save opens the ConflictDialog; "Reload and reapply" calls onReload() for the
 * fresh row and keeps what was typed, with the fresh row_version, ready to save again.
 */
export function RecordDialog({ open, title, fields, row, initial, onSubmit, onReload, onDone, onClose }) {
  const [values, setValues] = useState(() => Object.fromEntries(
    fields.map((f) => [f.name, (row ? row[f.name] : initial?.[f.name]) ?? ''])));
  const [rowVersion, setRowVersion] = useState(row?.row_version ?? null);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const m = useMutation({
    mutationFn: () => onSubmit(Object.fromEntries(fields.map((f) => [f.name, clean(f, values[f.name])])), rowVersion),
    onSuccess: (saved) => { onDone?.(saved); onClose(); },
    onError: (err) => {
      if (row && isStale(err)) setConflict(true);
      else setError(errorText(err, t('common.saveFailed')));
    },
  });
  const [reloading, setReloading] = useState(false);
  const reload = async () => {
    setReloading(true);
    try {
      const fresh = await onReload();
      if (fresh) { setRowVersion(fresh.row_version); setError(''); }
      else setError(t('settings.goneOnReload'));
    } catch (err) {
      setError(errorText(err, t('common.error')));
    } finally {
      setReloading(false);
      setConflict(false);
    }
  };
  const missing = fields.some((f) => f.required && String(values[f.name] ?? '').trim() === '');
  const set = (name, v) => setValues((s) => ({ ...s, [name]: v }));
  const unsaved = Object.fromEntries(fields.map((f) => {
    const v = values[f.name];
    const opt = f.options?.find((o) => o.value === v);
    return [f.label, opt ? opt.label : v];
  }));

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            {fields.map((f) => (f.type === 'select' ? (
              <FormControl key={f.name} size="small" required={f.required}>
                <InputLabel id={`rec-${f.name}-label`}>{f.label}</InputLabel>
                <Select labelId={`rec-${f.name}-label`} id={`rec-${f.name}`} label={f.label}
                  value={f.options.some((o) => o.value === values[f.name]) ? values[f.name] : ''}
                  onChange={(e) => set(f.name, e.target.value)}>
                  {!f.required && <MenuItem value=""><em>{f.emptyLabel ?? t('common.none')}</em></MenuItem>}
                  {f.options.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                </Select>
                {f.helperText && <Typography sx={{ fontSize: 12, color: 'text.secondary', mt: 0.5, ml: 1.75 }}>{f.helperText}</Typography>}
              </FormControl>
            ) : (
              <TextField key={f.name} id={`rec-${f.name}`} label={f.label} required={f.required}
                type={f.type === 'number' ? 'number' : 'text'} multiline={f.multiline} minRows={f.multiline ? 3 : undefined}
                slotProps={f.type === 'number' ? { htmlInput: { min: 0, step: 1 } } : undefined}
                helperText={f.helperText} value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)} />
            )))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={m.isPending || reloading || missing}
            onClick={() => { setError(''); m.mutate(); }}>{row ? t('common.save') : t('common.create')}</Button>
        </DialogActions>
      </Dialog>
      <ConflictDialog open={conflict} unsaved={unsaved} onReload={reload} onClose={() => setConflict(false)} />
    </>
  );
}
