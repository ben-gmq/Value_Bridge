import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Box, Button, Card, CardContent, Chip, Grid, IconButton, Stack, TextField, Tooltip,
  Typography } from '@mui/material';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { errorText, isStale } from '../../api/client';
import { appApi, dataApi, ifaceApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { t } from '../../i18n/t';
import { Mono, SectionTitle, SimpleSelect, blankToNull } from '../processes/chartKit';

const toForm = (d) => ({
  source: d.source_application_id ?? '', target: d.target_application_id ?? '',
  pattern: d.pattern_code ?? '', method: d.method_code ?? '', frequency: d.frequency_code ?? '',
  volume: d.volume_note ?? '',
  carried: (d.carried ?? []).map((c) => ({ data_entity_id: c.data_entity_id, label: `${c.de_number} ${c.de_name}`, note: c.note ?? '' })),
});

/**
 * Interface detail of one FR (D-27). Shown only when the FR's type *behaves* as INTERFACE
 * (fr_type_behaviour — never the code, DR6b2-S2). One PUT saves the whole detail and the carried
 * set, with the detail's row_version (DR6b2-P1/P2).
 */
export function InterfaceCard({ projectId, fr, onNotice }) {
  const qc = useQueryClient();
  const canEdit = useCanEdit() && fr.is_active;
  const q = useQuery({ queryKey: keys.iface(fr.fr_id), queryFn: () => ifaceApi.get(fr.fr_id) });
  const d = q.data;
  const [form, setForm] = useState(null);                 // non-null while editing
  const [error, setError] = useState('');
  const [confirmRemove, setConfirmRemove] = useState(false);
  const editing = form !== null;
  const appsQ = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId), enabled: editing });
  const desQ = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId), enabled: editing });
  const { codes: patterns, getLabel: patternLabel } = useCodes(projectId, 'INTERFACE_PATTERN');
  const { codes: methods, getLabel: methodLabel } = useCodes(projectId, 'INTERFACE_METHOD');
  const { codes: freqs, getLabel: freqLabel } = useCodes(projectId, 'INTERFACE_FREQUENCY');

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.iface(fr.fr_id) });
    qc.invalidateQueries({ queryKey: keys.interfaces(projectId) });
  };
  const fail = (err) => {
    if (isStale(err)) { refresh(); setForm(null); setError(t('interfaces.card.stale')); }
    else setError(errorText(err, t('common.saveFailed')));
  };
  const save = useMutation({
    mutationFn: () => ifaceApi.put(fr.fr_id, {
      row_version: d?.row_version ?? null,
      source_application_id: form.source, target_application_id: form.target,
      pattern_code: form.pattern || null, method_code: form.method || null, frequency_code: form.frequency || null,
      volume_note: blankToNull(form.volume),
      carried: form.carried.map((c) => ({ data_entity_id: c.data_entity_id, note: blankToNull(c.note) })),
    }),
    onSuccess: (row) => { qc.setQueryData(keys.iface(fr.fr_id), row); refresh(); setForm(null); setError('');
      onNotice?.(t('interfaces.card.saved')); },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: () => ifaceApi.remove(fr.fr_id, d.row_version),
    onSuccess: () => { setConfirmRemove(false); refresh(); setError(''); onNotice?.(t('interfaces.card.removed')); },
    onError: (err) => { setConfirmRemove(false); fail(err); },
  });

  const opts = (codes) => codes.map((c) => ({ value: c.code, label: c.label }));
  const apps = (appsQ.data ?? []).filter((a) => a.is_active).map((a) => ({ value: a.application_id, label: `${a.application_code} ${a.application_name}` }));
  const chosen = new Set(form?.carried.map((c) => c.data_entity_id) ?? []);
  const deOptions = (desQ.data ?? []).filter((e) => e.is_active !== false && !chosen.has(e.data_entity_id));
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setNote = (id, note) => setForm((f) => ({ ...f, carried: f.carried.map((c) => (c.data_entity_id === id ? { ...c, note } : c)) }));

  const view = d?.described ? (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('interfaces.route')}</Typography>
        <Typography><Mono>{d.source_application_code}</Mono> → <Mono>{d.target_application_code}</Mono></Typography>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
          {d.pattern_code && <Chip size="small" variant="outlined" label={patternLabel(d.pattern_code)} />}
          {d.method_code && <Chip size="small" variant="outlined" label={methodLabel(d.method_code)} />}
          {d.frequency_code && <Chip size="small" variant="outlined" label={freqLabel(d.frequency_code)} />}
        </Stack>
      </Grid>
      {d.volume_note && <Grid size={12}><Typography sx={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{d.volume_note}</Typography></Grid>}
      <Grid size={12}>
        <Typography sx={{ fontSize: 12, color: 'text.secondary', mb: 0.5 }}>{t('interfaces.card.carried')}</Typography>
        {d.carried.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('interfaces.card.noCarried')}</Typography>}
        <Stack spacing={0.5}>
          {d.carried.map((c) => (
            <Typography key={c.data_entity_id} sx={{ fontSize: 13.5 }}>
              <Mono>{c.de_number}</Mono> {c.de_name}{c.note ? ` — ${c.note}` : ''}</Typography>))}
        </Stack>
      </Grid>
    </Grid>
  ) : <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('interfaces.card.notDescribed')}</Typography>;

  const editor = editing && (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 6 }}>
        <SimpleSelect id="iface-source" label={t('interfaces.card.source')} value={form.source} onChange={(v) => set('source', v)} options={apps} /></Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <SimpleSelect id="iface-target" label={t('interfaces.card.target')} value={form.target} onChange={(v) => set('target', v)} options={apps} /></Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <SimpleSelect id="iface-pattern" label={t('interfaces.pattern')} value={form.pattern} allowEmpty emptyLabel={t('interfaces.card.none')}
          onChange={(v) => set('pattern', v)} options={opts(patterns)} /></Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <SimpleSelect id="iface-method" label={t('interfaces.method')} value={form.method} allowEmpty emptyLabel={t('interfaces.card.none')}
          onChange={(v) => set('method', v)} options={opts(methods)} /></Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <SimpleSelect id="iface-frequency" label={t('interfaces.frequency')} value={form.frequency} allowEmpty emptyLabel={t('interfaces.card.none')}
          onChange={(v) => set('frequency', v)} options={opts(freqs)} /></Grid>
      <Grid size={12}>
        <TextField id="iface-volume" fullWidth multiline minRows={2} label={t('interfaces.card.volume')} value={form.volume}
          onChange={(e) => set('volume', e.target.value)} slotProps={{ htmlInput: { maxLength: 4000 } }} /></Grid>
      <Grid size={12}>
        <Typography sx={{ fontSize: 12, color: 'text.secondary', mb: 1 }}>{t('interfaces.card.carried')}</Typography>
        <Stack spacing={1}>
          {form.carried.map((c) => (
            <Stack key={c.data_entity_id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography sx={{ minWidth: 200, fontSize: 13.5 }}>{c.label}</Typography>
              <TextField size="small" fullWidth label={t('interfaces.card.noteFor', { de: c.label })} value={c.note}
                onChange={(e) => setNote(c.data_entity_id, e.target.value)} slotProps={{ htmlInput: { maxLength: 4000 } }} />
              <Tooltip title={t('interfaces.card.removeEntity', { de: c.label })}>
                <IconButton size="small" aria-label={t('interfaces.card.removeEntity', { de: c.label })}
                  onClick={() => set('carried', form.carried.filter((x) => x.data_entity_id !== c.data_entity_id))}>
                  <CloseRounded fontSize="small" /></IconButton>
              </Tooltip>
            </Stack>))}
          <Autocomplete key={form.carried.length} size="small" options={deOptions} value={null} getOptionLabel={(e) => `${e.de_number} ${e.de_name}`}
            onChange={(_, e) => e && set('carried', [...form.carried, { data_entity_id: e.data_entity_id, label: `${e.de_number} ${e.de_name}`, note: '' }])}
            renderInput={(params) => <TextField {...params} label={t('interfaces.card.addEntity')} />} />
        </Stack>
      </Grid>
    </Grid>
  );

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <SectionTitle action={canEdit && !editing && (
          <Stack direction="row" spacing={1}>
            {d?.described && <Button size="small" color="warning" onClick={() => { setError(''); setConfirmRemove(true); }}>
              {t('interfaces.card.remove')}</Button>}
            <Button size="small" variant="outlined" disabled={!d} onClick={() => { setError(''); setForm(toForm(d?.described ? d : {})); }}>
              {d?.described ? t('interfaces.card.edit') : t('interfaces.card.describe')}</Button>
          </Stack>)}>
          {t('interfaces.card.title')}
        </SectionTitle>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
        {q.error && <Alert severity="error" sx={{ mb: 2 }}>{errorText(q.error)}</Alert>}
        {editing ? editor : (d && view)}
        {editing && (
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1, mt: 2 }}>
            <Button onClick={() => { setForm(null); setError(''); }}>{t('interfaces.card.cancel')}</Button>
            <Button variant="contained" disabled={save.isPending || !form.source || !form.target}
              onClick={() => { setError(''); save.mutate(); }}>{t('interfaces.card.save')}</Button>
          </Box>)}
      </CardContent>
      <ConfirmDialog open={confirmRemove} title={t('interfaces.card.removeTitle')}
        body={t('interfaces.card.removeBody', { number: fr.fr_number })} confirmLabel={t('interfaces.card.remove')}
        busy={remove.isPending} onClose={() => setConfirmRemove(false)} onConfirm={() => remove.mutate()} />
    </Card>
  );
}
