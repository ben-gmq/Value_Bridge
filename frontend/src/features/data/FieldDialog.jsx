import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControl,
  FormControlLabel, FormLabel, InputLabel, MenuItem, Select, Stack, TextField, ToggleButton,
  ToggleButtonGroup, Typography } from '@mui/material';
import { dataApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConflictDialog } from '../../components/ConflictDialog';
import { t } from '../../i18n/t';
import { explainError } from './conflict';
import { entityLabel, groupsTo, normName, toInt } from './fieldRules';

const KEEP = 'keep';
const NEW = 'new';
const tri = (v) => (v === true ? 'yes' : v === false ? 'no' : 'unknown');
const untri = (v) => (v === 'yes' ? true : v === 'no' ? false : null);
const str = (v) => (v == null ? '' : String(v));

function initial(field, fields) {
  if (field) {
    return {
      field_name: field.field_name, data_type_code: field.data_type_code ?? '',
      length_val: str(field.length_val), precision_val: str(field.precision_val), scale_val: str(field.scale_val),
      required: tri(field.is_mandatory), is_primary_key: field.is_primary_key, pk_ordinal: str(field.pk_ordinal),
      ref_data_entity_id: field.ref_data_entity_id ?? '', ref_data_field_id: field.ref_data_field_id ?? '',
      fk_group: field.is_foreign_key ? KEEP : NEW, description: field.description ?? '',
    };
  }
  const nextPk = Math.max(0, ...fields.filter((f) => f.is_primary_key).map((f) => f.pk_ordinal ?? 0)) + 1;
  return { field_name: '', data_type_code: '', length_val: '', precision_val: '', scale_val: '', required: 'unknown',
    is_primary_key: false, pk_ordinal: String(nextPk), ref_data_entity_id: '', ref_data_field_id: '', fk_group: NEW,
    description: '' };
}

// Add or edit one logical field (D-26). The relationship number is never typed: the request
// names "new" or an existing relationship to the same entity, and the server assigns it (S1-7).
export function FieldDialog({ projectId, entity, field, fields, onClose, onSaved }) {
  const qc = useQueryClient();
  const { codes: types } = useCodes(projectId, 'FIELD_DATA_TYPE');
  const entities = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const [f, setF] = useState(() => initial(field, fields));
  const [base, setBase] = useState(field);        // the server version the form is editing
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [conflict, setConflict] = useState(false);
  const orig = base ? initial(base, fields) : null;
  const touched = (...ks) => !orig || ks.some((k) => f[k] !== orig[k]);
  const targetId = f.ref_data_entity_id === '' ? null : Number(f.ref_data_entity_id);
  const targetFields = useQuery({ queryKey: [...keys.entity(targetId), 'fields'],
    queryFn: () => dataApi.fields(targetId), enabled: targetId != null });
  const sameTarget = base?.is_foreign_key && base.ref_data_entity_id === targetId;
  const groups = targetId != null ? groupsTo(fields, targetId, base?.data_field_id) : [];

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const setTarget = (e) => {
    const v = e.target.value;
    const keep = base?.is_foreign_key && base.ref_data_entity_id === (v === '' ? null : Number(v));
    setF({ ...f, ref_data_entity_id: v, ref_data_field_id: keep ? base.ref_data_field_id ?? '' : '',
      fk_group: keep ? KEEP : NEW });
  };

  const dup = fields.some((o) => o.data_field_id !== field?.data_field_id && normName(o.field_name) === normName(f.field_name));
  const pkBad = f.is_primary_key && !(toInt(f.pk_ordinal) >= 1 && toInt(f.pk_ordinal) <= 32);

  // An edit sends only what this user changed, so it never rewrites another user's value.
  function body() {
    const b = {};
    if (touched('field_name')) b.field_name = f.field_name.trim();
    if (touched('data_type_code')) b.data_type_code = f.data_type_code || null;
    ['length', 'precision', 'scale'].forEach((k) => { if (touched(`${k}_val`)) b[`${k}_val`] = toInt(f[`${k}_val`]); });
    if (touched('required')) b.is_mandatory = untri(f.required);
    if (touched('is_primary_key', 'pk_ordinal')) {
      b.is_primary_key = f.is_primary_key;
      b.pk_ordinal = f.is_primary_key ? toInt(f.pk_ordinal) : null;
    }
    if (touched('description')) b.description = f.description.trim() || null;
    const refField = f.ref_data_field_id === '' ? null : Number(f.ref_data_field_id);
    if (targetId == null) {
      if (base?.is_foreign_key) b.ref_data_entity_id = null;            // drop the foreign key
    } else if (!(sameTarget && f.fk_group === KEEP && refField === (base.ref_data_field_id ?? null))) {
      // Keeping the relationship while changing its field: name it if another field shares it.
      const group = f.fk_group === KEEP ? (groups.includes(base.fk_group_no) ? base.fk_group_no : NEW) : f.fk_group;
      Object.assign(b, { ref_data_entity_id: targetId, ref_data_field_id: refField, fk_group: group });
    }
    return base ? { ...b, row_version: base.row_version } : b;
  }

  const m = useMutation({
    mutationFn: () => (field ? dataApi.updateField(field.data_field_id, body())
      : dataApi.createField(entity.data_entity_id, body())),
    onSuccess: (saved) => { onSaved(saved); onClose(); },
    onError: async (err) => {
      const r = await explainError(err, base?.row_version, field && (async () =>
        (await dataApi.fields(entity.data_entity_id)).find((x) => x.data_field_id === field.data_field_id)));
      if (r.stale) setConflict(true); else setError(r.text);
    },
  });

  async function reload() {
    // Their version becomes the base. What this user changed is reapplied on top; everything
    // they did not touch takes the other user's value, never the stale one.
    await qc.invalidateQueries({ queryKey: keys.entity(entity.data_entity_id) });
    const fresh = (await dataApi.fields(entity.data_entity_id)).find((x) => x.data_field_id === field.data_field_id);
    setConflict(false);
    if (!fresh) { setError(t('data.field.gone')); return; }
    const next = initial(fresh, fields);
    setF((cur) => Object.fromEntries(Object.keys(next).map((k) => [k, cur[k] !== orig[k] ? cur[k] : next[k]])));
    setBase(fresh);
    setInfo(t('data.field.reloaded'));
  }

  const typeValue = types.some((c) => c.code === f.data_type_code) ? f.data_type_code : '';
  const targets = (entities.data ?? []);
  const refFieldValue = (targetFields.data ?? []).some((x) => x.data_field_id === Number(f.ref_data_field_id))
    ? f.ref_data_field_id : '';
  const groupValue = f.fk_group === KEEP && !sameTarget ? NEW : f.fk_group;
  const unsaved = Object.fromEntries([
    ['field_name', t('data.field.name'), f.field_name], ['data_type_code', t('data.field.type'), f.data_type_code],
    ['length_val', t('data.field.length'), f.length_val], ['precision_val', t('data.field.precision'), f.precision_val],
    ['scale_val', t('data.field.scale'), f.scale_val], ['required', t('data.field.required'), t(`data.req.${f.required}`)],
    ['pk_ordinal', t('data.field.pk'), f.is_primary_key ? f.pk_ordinal : '—'],
    ['ref_data_entity_id', t('data.field.fk'), entityLabel(targets.find((e) => e.data_entity_id === targetId)) || '—'],
    ['description', t('data.description'), f.description],
  ].filter(([k]) => touched(k) || (k === 'pk_ordinal' && touched('is_primary_key'))
    || (k === 'ref_data_entity_id' && touched('ref_data_field_id', 'fk_group'))).map(([, label, v]) => [label, v]));

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{field ? t('data.field.editTitle', { name: field.field_name }) : t('data.field.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        {info && <Alert severity="info" sx={{ mb: 2 }}>{info}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="df-name" label={t('data.field.name')} required autoFocus value={f.field_name}
            onChange={set('field_name')} error={dup} helperText={dup ? t('data.field.duplicate') : ' '}
            slotProps={{ htmlInput: { maxLength: 200 } }} />
          <FormControl size="small">
            <InputLabel id="df-type-label">{t('data.field.type')}</InputLabel>
            <Select labelId="df-type-label" id="df-type" label={t('data.field.type')} value={typeValue}
              onChange={set('data_type_code')}>
              <MenuItem value="">{t('data.field.typeNone')}</MenuItem>
              {types.map((c) => <MenuItem key={c.code} value={c.code}>{c.label}</MenuItem>)}
            </Select>
          </FormControl>
          <Stack direction="row" spacing={2}>
            {['length', 'precision', 'scale'].map((k) => (
              <TextField key={k} id={`df-${k}`} type="number" label={t(`data.field.${k}`)} value={f[`${k}_val`]}
                onChange={set(`${k}_val`)} slotProps={{ htmlInput: { min: k === 'scale' ? 0 : 1 } }} sx={{ flex: 1 }} />
            ))}
          </Stack>
          <FormControl>
            <FormLabel id="df-req-label" sx={{ fontSize: 13, mb: 0.5 }}>{t('data.field.required')}</FormLabel>
            <ToggleButtonGroup exclusive size="small" aria-labelledby="df-req-label" value={f.required}
              onChange={(_, v) => v && setF({ ...f, required: v })}>
              {['yes', 'no', 'unknown'].map((v) => <ToggleButton key={v} value={v}>{t(`data.req.${v}`)}</ToggleButton>)}
            </ToggleButtonGroup>
          </FormControl>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
            <FormControlLabel label={t('data.field.pk')} control={<Checkbox id="df-pk" checked={f.is_primary_key}
              onChange={(e) => setF({ ...f, is_primary_key: e.target.checked })} />} />
            {f.is_primary_key && (
              <TextField id="df-pk-ord" type="number" label={t('data.field.pkOrdinal')} value={f.pk_ordinal}
                onChange={set('pk_ordinal')} error={pkBad} slotProps={{ htmlInput: { min: 1, max: 32 } }} sx={{ width: 160 }} />
            )}
          </Stack>
          <Typography variant="h6" component="h3" sx={{ pt: 1 }}>{t('data.field.fk')}</Typography>
          <FormControl size="small">
            <InputLabel id="df-target-label">{t('data.field.target')}</InputLabel>
            <Select labelId="df-target-label" id="df-target" label={t('data.field.target')}
              value={targets.some((e) => e.data_entity_id === targetId) ? String(targetId) : ''} onChange={setTarget}>
              <MenuItem value="">{t('data.field.noFk')}</MenuItem>
              {targets.map((e) => <MenuItem key={e.data_entity_id} value={String(e.data_entity_id)}>{entityLabel(e)}</MenuItem>)}
            </Select>
          </FormControl>
          {targetId != null && (
            <>
              <FormControl size="small">
                <InputLabel id="df-reffield-label">{t('data.field.targetField')}</InputLabel>
                <Select labelId="df-reffield-label" id="df-reffield" label={t('data.field.targetField')}
                  value={refFieldValue === '' ? '' : String(refFieldValue)} onChange={set('ref_data_field_id')}>
                  <MenuItem value="">{t('data.field.targetFieldNone')}</MenuItem>
                  {(targetFields.data ?? []).map((x) => (
                    <MenuItem key={x.data_field_id} value={String(x.data_field_id)}>{x.field_name}</MenuItem>))}
                </Select>
              </FormControl>
              <FormControl size="small">
                <InputLabel id="df-group-label">{t('data.field.group')}</InputLabel>
                <Select labelId="df-group-label" id="df-group" label={t('data.field.group')} value={String(groupValue)}
                  onChange={(e) => setF({ ...f, fk_group: [KEEP, NEW].includes(e.target.value) ? e.target.value : Number(e.target.value) })}>
                  {sameTarget && <MenuItem value={KEEP}>{t('data.field.groupKeep', { n: base.fk_group_no })}</MenuItem>}
                  <MenuItem value={NEW}>{t('data.field.groupNew')}</MenuItem>
                  {groups.filter((g) => !(sameTarget && g === base.fk_group_no)).map((g) => (
                    <MenuItem key={g} value={String(g)}>{t('data.field.groupExtend', { n: g })}</MenuItem>))}
                </Select>
              </FormControl>
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.field.groupHelp')}</Typography>
            </>
          )}
          <TextField id="df-desc" label={t('data.description')} multiline minRows={2} value={f.description}
            onChange={set('description')} slotProps={{ htmlInput: { maxLength: 4000 } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !f.field_name.trim() || dup || pkBad || (field && Object.keys(body()).length === 1)}
          onClick={() => { setError(''); setInfo(''); m.mutate(); }}>{field ? t('common.save') : t('data.field.add')}</Button>
      </DialogActions>
      <ConflictDialog open={conflict} unsaved={unsaved} onReload={reload} onClose={() => setConflict(false)} />
    </Dialog>
  );
}
