import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Breadcrumbs, Button, Card, CardContent, Chip, Grid, Link, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { frApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { t } from '../../i18n/t';
import { Mono, SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { FrWarnings, solutionOptions } from './frKit';
import { InterfaceCard } from './InterfaceCard';
import { FrEffort } from '../effort/FrEffort';

const pickFr = (f) => ({ fr_name: f.fr_name ?? '', fr_type_code: f.fr_type_code,
  fulfilment_status_code: f.fulfilment_status_code, solution_id: f.solution_id ?? '',
  description: f.description ?? '', acceptance_note: f.acceptance_note ?? '' });
const CODES = new Set(['fr_type_code', 'fulfilment_status_code']);

export default function FrPage() {
  const { projectId, frId } = useParams();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.fr(frId), queryFn: () => frApi.get(frId) });
  const fr = q.data;
  const solsQ = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId) });
  const { codes: types, getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const { codes: statuses, getLabel: statusLabel } = useCodes(projectId, 'FR_FULFILMENT_STATUS');
  const form = useEditForm(fr, pickFr);
  const [notice, setNotice] = useState('');
  const [warnings, setWarnings] = useState([]);
  const [effortChange, setEffortChange] = useState(null);     // DR6c-P2: a type change re-priced the FR
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.fr(frId) });
    qc.invalidateQueries({ queryKey: keys.frs(projectId) });
    qc.invalidateQueries({ queryKey: keys.frTrace() });
  };
  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'solution_id') body.solution_id = form.values.solution_id === '' ? null : form.values.solution_id;
        else body[k] = CODES.has(k) ? form.values[k] : blankToNull(form.values[k]);
      }
      if ('fr_name' in body) body.fr_name = form.values.fr_name.trim();
      return frApi.update(fr.fr_id, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.fr(frId), row); refreshAll();
      setWarnings((row.warnings ?? []).filter((w) => w !== 'effort_changed')); setEffortChange(row.effort_change ?? null);
      setNotice(t('frs.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.fr(frId), queryFn: () => frApi.get(frId) });
      form.rebase(fresh);
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => {
    refreshAll();
    setActionError(isStale(err) ? t('frs.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const retire = useMutation({
    mutationFn: () => frApi.retire(fr.fr_id, fr.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('frs.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => frApi.restore(fr.fr_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.fr(frId), row); refreshAll();
      setNotice(t('frs.restored', { number: row.fr_number })); },
    onError: actionFail,
  });

  const crumbs = (
    <Breadcrumbs sx={{ mb: 1.5 }}>
      <Link component={RouterLink} to={links.frs(projectId)} underline="hover" color="inherit">{t('frs.back')}</Link>
      <Typography sx={{ color: 'text.primary' }}>{fr?.fr_number ?? '…'}</Typography>
    </Breadcrumbs>
  );
  if (q.error) return <Box>{crumbs}<Alert severity="error">{errorText(q.error)}</Alert></Box>;
  if (!fr || !form.values) return <Box>{crumbs}<Typography sx={{ color: 'text.secondary' }}>{t('frs.loading')}</Typography></Box>;

  const v = form.values;
  const live = fr.is_active;
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  // The current solution stays selectable even if the list has not loaded it yet.
  const solOpts = solutionOptions(solsQ.data);
  if (fr.solution_id && !solOpts.some((o) => o.value === fr.solution_id)) {
    solOpts.unshift({ value: fr.solution_id, label: t('frs.loading') });
  }
  const sol = (solsQ.data ?? []).find((s) => s.solution_id === fr.solution_id);
  const labels = { fr_name: t('frs.name'), fr_type_code: t('frs.type'), fulfilment_status_code: t('frs.status'),
    solution_id: t('frs.solution'), description: t('frs.description'), acceptance_note: t('frs.acceptanceNote') };
  const shown = (k) => (k === 'fr_type_code' ? typeLabel(v[k]) : k === 'fulfilment_status_code' ? statusLabel(v[k])
    : k === 'solution_id' ? (solOpts.find((o) => o.value === v[k])?.label ?? t('frs.noSolution')) : v[k]);
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], shown(k)]));
  const text = (name, rows = 2, max = 4000) => (
    <TextField fullWidth multiline={rows > 1} minRows={rows > 1 ? rows : undefined} id={`fr-${name}`}
      label={labels[name]} disabled={!editable} value={v[name]} required={name === 'fr_name'}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: max } }} />
  );
  const select = (name, options, extra = {}) => (editable ? (
    <SimpleSelect id={`fr-${name}`} label={labels[name]} value={v[name]} onChange={(c) => form.set(name, c)}
      options={options} {...extra} />
  ) : <TextField fullWidth size="small" disabled label={labels[name]} value={shown(name)} />);

  return (
    <Box>
      {crumbs}
      <Stack direction="row" sx={{ alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5" component="h1" sx={(th) => ({ fontWeight: 700, color: th.vars.palette.brand.title })}>
            <Mono sx={(th) => ({ color: th.vars.palette.brand.link, mr: 1.5 })}>{fr.fr_number}</Mono>{fr.fr_name}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 0.5, flexWrap: 'wrap' }}>
            <Typography sx={{ color: 'text.secondary' }}>{t('frs.detailSubtitle')}</Typography>
            {sol && (
              <Link component={RouterLink} to={links.solution(projectId, sol.solution_id)} underline="hover">
                <Mono>{sol.solution_number}</Mono> {sol.solution_name}</Link>)}
          </Stack>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          {!live && <Chip variant="outlined" label={t('frs.retiredChip')} />}
          {canEdit && (live ? (
            <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('frs.retire')}</Button>
          ) : (
            <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('frs.restore')}</Button>
          ))}
          {editable && (
            <>
              <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('frs.discard')}</Button>
              <Button variant="contained" disabled={!form.dirty || busy || !v.fr_name.trim()}
                onClick={() => { save.setError(''); save.m.mutate(); }}>{t('frs.save')}</Button>
            </>)}
        </Stack>
      </Stack>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      <FrWarnings warnings={warnings} onClose={() => setWarnings([])} />
      {effortChange && (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setEffortChange(null)}>
          {t('effort.fr.changed', { from: effortChange.previous_days ?? t('effort.fr.notRated'), to: effortChange.new_days })}</Alert>)}

      <Card>
        <CardContent>
          <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'flex-end', mb: 2 }}>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('frs.version', { v: form.version })}</Typography>
          </Stack>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>{text('fr_name', 1, 200)}</Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>{select('fr_type_code', types.map((c) => ({ value: c.code, label: c.label })))}</Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {select('fulfilment_status_code', statuses.map((c) => ({ value: c.code, label: c.label })))}</Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              {select('solution_id', solOpts, { allowEmpty: true, emptyLabel: t('frs.noSolution') })}</Grid>
            <Grid size={{ xs: 12, md: 6 }} />
            <Grid size={12}>{text('description', 3)}</Grid>
            <Grid size={12}>{text('acceptance_note')}</Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card sx={{ mt: 3 }}>
        <CardContent>
          <FrEffort key={`${fr.row_version}-${fr.complexity_code}`} projectId={projectId} fr={fr}
            onRated={(row) => { qc.setQueryData(keys.fr(frId), row); form.rebase(row); refreshAll();   // keeps typed edits (sara M-1)
              setNotice(row.effort_days != null ? t('effort.fr.rated', { days: row.effort_days }) : t('frs.saved')); }} />
        </CardContent>
      </Card>
      {/* D-27: only an FR whose type behaves as an interface carries interface detail (never a code test) */}
      {fr.fr_type_behaviour === 'INTERFACE' && <InterfaceCard projectId={projectId} fr={fr} onNotice={setNotice} />}

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('frs.retireTitle')}
        body={t('frs.retireBody', { number: fr.fr_number })} confirmLabel={t('frs.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
