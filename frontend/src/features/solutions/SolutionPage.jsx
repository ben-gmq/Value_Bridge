import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Breadcrumbs, Button, Card, CardContent, Chip, Divider, Grid, Link, Snackbar, Stack,
  TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { t } from '../../i18n/t';
import { Mono, SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { SolutionLinkPanel } from './SolutionLinkPanel';

const pickSolution = (s) => ({ solution_name: s.solution_name ?? '', category_code: s.category_code,
  status_code: s.status_code, description: s.description ?? '', benefit_note: s.benefit_note ?? '',
  effort_note: s.effort_note ?? '' });
const CODES = new Set(['category_code', 'status_code']);

export default function SolutionPage() {
  const { projectId, solutionId } = useParams();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.solution(solutionId), queryFn: () => solutionApi.get(solutionId) });
  const sol = q.data;
  const { codes: categories, getLabel: categoryLabel } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const { codes: statuses, getLabel: statusLabel } = useCodes(projectId, 'SOLUTION_STATUS');
  const form = useEditForm(sol, pickSolution);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.solution(solutionId) });
    qc.invalidateQueries({ queryKey: keys.solutions(projectId) });
    qc.invalidateQueries({ queryKey: keys.solutionLinks() });
  };
  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) body[k] = CODES.has(k) ? form.values[k] : blankToNull(form.values[k]);
      if ('solution_name' in body) body.solution_name = form.values.solution_name.trim();
      return solutionApi.update(sol.solution_id, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.solution(solutionId), row); refreshAll(); setNotice(t('solutions.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.solution(solutionId), queryFn: () => solutionApi.get(solutionId) });
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
    setActionError(isStale(err) ? t('solutions.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const retire = useMutation({
    mutationFn: () => solutionApi.retire(sol.solution_id, sol.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('solutions.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => solutionApi.restore(sol.solution_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.solution(solutionId), row); refreshAll();
      setNotice(t('solutions.restored', { label: row.solution_number })); },
    onError: actionFail,
  });

  const crumbs = (
    <Breadcrumbs sx={{ mb: 1.5 }}>
      <Link component={RouterLink} to={links.solutions(projectId)} underline="hover" color="inherit">{t('solutions.back')}</Link>
      <Typography sx={{ color: 'text.primary' }}>{sol?.solution_number ?? '…'}</Typography>
    </Breadcrumbs>
  );
  if (q.error) return <Box>{crumbs}<Alert severity="error">{errorText(q.error)}</Alert></Box>;
  if (!sol || !form.values) return <Box>{crumbs}<Typography sx={{ color: 'text.secondary' }}>{t('solutions.loading')}</Typography></Box>;

  const v = form.values;
  const live = sol.is_active;
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const labels = { solution_name: t('solutions.name'), category_code: t('solutions.category'),
    status_code: t('solutions.status'), description: t('solutions.description'),
    benefit_note: t('solutions.benefitNote'), effort_note: t('solutions.effortNote') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k],
    k === 'category_code' ? categoryLabel(v[k]) : k === 'status_code' ? statusLabel(v[k]) : v[k]]));
  const text = (name, rows = 2, max = 4000) => (
    <TextField fullWidth multiline={rows > 1} minRows={rows > 1 ? rows : undefined} id={`sol-${name}`}
      label={labels[name]} disabled={!editable} value={v[name]} required={name === 'solution_name'}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: max } }} />
  );

  return (
    <Box>
      {crumbs}
      <Stack direction="row" sx={{ alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5" component="h1" sx={(th) => ({ fontWeight: 700, color: th.vars.palette.brand.title })}>
            <Mono sx={(th) => ({ color: th.vars.palette.brand.link, mr: 1.5 })}>{sol.solution_number}</Mono>{sol.solution_name}
          </Typography>
          <Typography sx={{ color: 'text.secondary', mt: 0.5 }}>{t('solutions.detailSubtitle')}</Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          {!live && <Chip variant="outlined" label={t('solutions.retiredChip')} />}
          {canEdit && (live ? (
            <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('solutions.retire')}</Button>
          ) : (
            <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('solutions.restore')}</Button>
          ))}
          {editable && (
            <>
              <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('solutions.discard')}</Button>
              <Button variant="contained" disabled={!form.dirty || busy || !v.solution_name.trim()}
                onClick={() => { save.setError(''); save.m.mutate(); }}>{t('solutions.save')}</Button>
            </>)}
        </Stack>
      </Stack>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}

      <Card>
        <CardContent>
          <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'flex-end', mb: 2 }}>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('solutions.version', { v: form.version })}</Typography>
          </Stack>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>{text('solution_name', 1, 200)}</Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {editable ? (
                <SimpleSelect id="sol-category" label={labels.category_code} value={v.category_code}
                  onChange={(c) => form.set('category_code', c)} options={categories.map((c) => ({ value: c.code, label: c.label }))} />
              ) : <TextField fullWidth size="small" disabled label={labels.category_code} value={categoryLabel(v.category_code)} />}
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {editable ? (
                <SimpleSelect id="sol-status" label={labels.status_code} value={v.status_code}
                  onChange={(c) => form.set('status_code', c)} options={statuses.map((c) => ({ value: c.code, label: c.label }))} />
              ) : <TextField fullWidth size="small" disabled label={labels.status_code} value={statusLabel(v.status_code)} />}
            </Grid>
            <Grid size={12}>{text('description', 3)}</Grid>
            <Grid size={{ xs: 12, md: 6 }}>{text('benefit_note')}</Grid>
            <Grid size={{ xs: 12, md: 6 }}>{text('effort_note')}</Grid>
          </Grid>
          <Divider sx={{ my: 3 }} />
          <SolutionLinkPanel projectId={projectId} side="solution" solution={sol} disabled={!live} />
        </CardContent>
      </Card>

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('solutions.retireTitle')}
        body={t('solutions.retireBody', { number: sol.solution_number })} confirmLabel={t('solutions.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
