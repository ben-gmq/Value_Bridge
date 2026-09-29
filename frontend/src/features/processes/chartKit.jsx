import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControl, FormControlLabel, InputLabel, Link, MenuItem, Select, Stack, Switch, TextField,
  ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { orgApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';

// Shared pieces of the chart area: the process screen and the requirement screens.

export function ShowRetired({ id, checked, onChange }) {
  return (
    <FormControlLabel label={t('processes.showRetired')}
      control={<Switch id={id} checked={checked} onChange={(e) => onChange(e.target.checked)} />} />
  );
}

export function SectionTitle({ children, action }) {
  return (
    <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1, gap: 1 }}>
      <Typography component="h3" sx={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.8,
        textTransform: 'uppercase', color: 'text.secondary' }}>{children}</Typography>
      {action}
    </Stack>
  );
}

export function LevelBadge({ level, process }) {
  return (
    <Box component="span" role="img" aria-label={t('processes.levelN', { n: level })} sx={(th) => ({
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flex: 'none',
      width: 20, height: 20, borderRadius: '6px', fontSize: 11, fontWeight: 700,
      border: 1, borderColor: process ? 'primary.main' : th.vars.palette.brand.lineStrong,
      bgcolor: process ? 'primary.main' : 'transparent',
      color: process ? 'primary.contrastText' : 'text.primary' })}>{level}</Box>
  );
}

export const Mono = ({ children, sx }) => (
  <Box component="span" sx={{ fontFamily: MONO, fontSize: '0.92em', ...sx }}>{children}</Box>
);

// A process sits at level 3, 4 or 5 (A-47). The server enforces it; this only decides what is
// offered. The process TEST is is_process (VB law 4).
export const FIRST_PROCESS_LEVEL = 3;

export const entityLabel = (de) => (de ? `${de.de_number} ${de.de_name}` : '');
export const dirLabel = (d) => t(d === 'I' ? 'processes.dirIn' : 'processes.dirOut');

// Optional text → null, so an emptied box clears the field instead of saving ''.
export const blankToNull = (v) => (typeof v === 'string' && v.trim() === '' ? null : v);

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/**
 * An edit form pinned to the row_version it was loaded from. While the user has unsaved
 * changes a refetch moves the version only if none of the editable fields changed on the
 * server (e.g. the user's own reorder or process switch); otherwise it stays pinned, so a save
 * after someone else's edit becomes a stale 409 (→ ConflictDialog) instead of overwriting it.
 * Saves send only `changed` fields, so an untouched field never reverts another person's edit.
 * `pick(record)` → the editable values; it must be a stable (module-level) function.
 */
export function useEditForm(record, pick) {
  const [form, setForm] = useState(null);
  useEffect(() => {
    if (!record) return;
    setForm((f) => {
      const fresh = pick(record);
      if (!f || same(f.values, f.base)) return { base: fresh, values: fresh, version: record.row_version };
      return same(fresh, f.base) ? { ...f, version: record.row_version } : f;
    });
  }, [record, pick]);
  const changed = form ? Object.keys(form.values).filter((k) => !same(form.values[k], form.base[k])) : [];
  return {
    values: form?.values ?? null,
    base: form?.base ?? null,
    version: form?.version ?? null,
    changed,
    dirty: changed.length > 0,
    set: (name, v) => setForm((f) => ({ ...f, values: { ...f.values, [name]: v } })),
    discard: () => setForm((f) => ({ ...f, values: f.base })),
    saved: (row) => setForm({ base: pick(row), values: pick(row), version: row.row_version }),
    // "Reload and reapply": keep what was typed; every untouched field takes the fresh value.
    rebase: (row) => setForm((f) => {
      const fresh = pick(row);
      const values = Object.fromEntries(Object.keys(fresh).map((k) =>
        [k, same(f.values[k], f.base[k]) ? fresh[k] : f.values[k]]));
      return { base: fresh, values, version: row.row_version };
    }),
  };
}

// One mutation shape for a pinned-form save: stale → conflict, anything else → its detail.
export function useFormSave({ save, onSaved }) {
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const m = useMutation({
    mutationFn: save,
    onSuccess: (row) => { setError(''); onSaved(row); },
    onError: (err) => { if (isStale(err)) setConflict(true); else setError(errorText(err, t('common.saveFailed'))); },
  });
  return { m, error, setError, conflict, setConflict };
}

/** Pick one option (with a label) and optional extras, then submit. */
export function PickDialog({ open, title, options, getOptionLabel, optionLabel, extra, canSubmit = true,
  submitLabel, onSubmit, onDone, onClose, emptyHint }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => onSubmit(value),
    onSuccess: (r) => { onDone?.(r); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          {options.length === 0 && emptyHint}
          <Autocomplete options={options} getOptionLabel={getOptionLabel} value={value}
            onChange={(_, v) => setValue(v)} disabled={options.length === 0}
            renderInput={(params) => <TextField {...params} label={optionLabel} />} />
          {extra}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!value || !canSubmit || m.isPending}
          onClick={() => { setError(''); m.mutate(); }}>{submitLabel}</Button>
      </DialogActions>
    </Dialog>
  );
}

export function SimpleSelect({ id, label, value, onChange, options, allowEmpty, emptyLabel }) {
  const v = options.some((o) => o.value === value) ? value : '';
  return (
    <FormControl size="small" fullWidth>
      <InputLabel id={`${id}-label`}>{label}</InputLabel>
      <Select labelId={`${id}-label`} id={id} label={label} value={v} onChange={(e) => onChange(e.target.value)}>
        {allowEmpty && <MenuItem value=""><em>{emptyLabel ?? t('common.none')}</em></MenuItem>}
        {options.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
      </Select>
    </FormControl>
  );
}

/**
 * RACI for a step or a requirement. Rows are the org roles holding at least one code; each has
 * a toggle per RACI_TYPE code (labels from code_master). Which behaviours are "one only" is the
 * server's rule (services/raci.py SINGLE); `single` lists behaviour codes, never letters.
 */
export function RaciPanel({ projectId, queryKey, list, link, unlink, linkId, single, disabled, onChanged }) {
  const qc = useQueryClient();
  const { codes } = useCodes(projectId, 'RACI_TYPE');
  const q = useQuery({ queryKey, queryFn: list });
  const rolesQ = useQuery({ queryKey: keys.roles(projectId), queryFn: () => orgApi.roles(projectId) });
  const unitsQ = useQuery({ queryKey: keys.units(projectId), queryFn: () => orgApi.units(projectId) });
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [addCode, setAddCode] = useState('');
  const roleById = useMemo(() => new Map((rolesQ.data ?? []).map((r) => [r.org_role_id, r])), [rolesQ.data]);
  const unitById = useMemo(() => new Map((unitsQ.data ?? []).map((u) => [u.org_unit_id, u])), [unitsQ.data]);
  const linksList = useMemo(() => q.data ?? [], [q.data]);
  const roleIds = [...new Set(linksList.map((l) => l.org_role_id))];
  const refresh = () => { qc.invalidateQueries({ queryKey }); onChanged?.(); };
  const toggle = useMutation({
    mutationFn: ({ roleId, code, on }) => {
      if (on) return link({ org_role_id: roleId, raci_code: code });
      const row = linksList.find((l) => l.org_role_id === roleId && l.raci_code === code);
      return unlink(row[linkId], row.row_version);
    },
    onSuccess: () => { setError(''); refresh(); },
    onError: (err) => {
      refresh();
      setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed')));
    },
  });
  const rule = codes.filter((c) => single.includes(c.behaviour_code))
    .map((c) => t('processes.raciOne', { label: c.label })).join(', ');
  const activeRoles = (rolesQ.data ?? []).filter((r) => r.is_active);
  const roleName = (r) => (r ? `${r.org_role_code} — ${r.org_role_name}` : '');

  return (
    <Box>
      <SectionTitle action={!disabled && (
        <Button size="small" onClick={() => { setError(''); setAddCode(''); setAdding(true); }}>
          {t('processes.addRole')}</Button>)}>
        {rule ? t('processes.raciTitleRule', { rule }) : t('processes.raciTitle')}
      </SectionTitle>
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      {[q.error, rolesQ.error, unitsQ.error].some(Boolean) && (
        <Alert severity="error" sx={{ mb: 1 }}>{errorText(q.error || rolesQ.error || unitsQ.error)}</Alert>)}
      {!q.isLoading && !q.error && roleIds.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.noRoles')}</Typography>
      )}
      <Stack spacing={1.25}>
        {roleIds.map((roleId) => {
          const role = roleById.get(roleId);
          const held = linksList.filter((l) => l.org_role_id === roleId).map((l) => l.raci_code);
          return (
            <Stack key={roleId} direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontWeight: 600 }}>{role ? role.org_role_name : `#${roleId}`}</Typography>
                <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                  {role && [role.org_role_code, unitById.get(role.org_unit_id)?.org_unit_name].filter(Boolean).join(' · ')}
                </Typography>
              </Box>
              <ToggleButtonGroup size="small" value={held} aria-label={t('processes.raciFor', { role: roleName(role) })}>
                {codes.map((c) => (
                  <ToggleButton key={c.code} value={c.code} aria-label={c.label} disabled={disabled || toggle.isPending}
                    sx={{ px: 1.25, py: 0.25, fontSize: 12 }}
                    onClick={() => toggle.mutate({ roleId, code: c.code, on: !held.includes(c.code) })}>
                    {c.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </Stack>
          );
        })}
      </Stack>
      {adding && (
        <PickDialog open title={t('processes.addRoleTitle')} optionLabel={t('processes.orgRole')}
          options={activeRoles} getOptionLabel={roleName} submitLabel={t('processes.add')}
          canSubmit={Boolean(addCode)}
          emptyHint={(
            <Alert severity="info">
              {t('processes.noOrgRoles')}{' '}
              <Link component={RouterLink} to={links.organisation(projectId)}>{t('processes.goOrganisation')}</Link>
            </Alert>)}
          extra={(
            <SimpleSelect id="raci-add-code" label={t('processes.raciCode')} value={addCode} onChange={setAddCode}
              options={codes.map((c) => ({ value: c.code, label: c.label }))} />)}
          onSubmit={(role) => link({ org_role_id: role.org_role_id, raci_code: addCode })}
          onDone={refresh} onClose={() => setAdding(false)} />
      )}
    </Box>
  );
}
