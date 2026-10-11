import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Breadcrumbs, Button, Card, CardContent, Chip, Divider, Grid, Link, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { appApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { t } from '../../i18n/t';
import { Mono, SectionTitle, SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';

const pickApp = (a) => ({ application_code: a.application_code, application_name: a.application_name,
  lifecycle_code: a.lifecycle_code, kind_code: a.app_kind_code ?? '', vendor: a.vendor ?? '',
  version_label: a.version_label ?? '', description: a.description ?? '' });

// What the application touches, read-only here: links are made from the Solution and step pages.
function UsedBy({ title, empty, query, render }) {
  const rows = query.data ?? [];
  return (
    <Box>
      <SectionTitle>{title}</SectionTitle>
      {query.error && <Alert severity="error" sx={{ mb: 1 }}>{errorText(query.error)}</Alert>}
      {!query.isLoading && !query.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{empty}</Typography>)}
      <Stack spacing={1}>{rows.map(render)}</Stack>
    </Box>
  );
}

export default function ApplicationPage() {
  const { projectId, appId } = useParams();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const q = useQuery({ queryKey: keys.application(appId), queryFn: () => appApi.get(appId) });
  const app = q.data;
  const solsQ = useQuery({ queryKey: keys.appLinksOf('app-solutions', appId), queryFn: () => appApi.solutions(appId) });
  const stepsQ = useQuery({ queryKey: keys.appLinksOf('app-steps', appId), queryFn: () => appApi.steps(appId) });
  const { codes: lifecycles, getLabel: lifecycleLabel } = useCodes(projectId, 'APP_LIFECYCLE');
  const { codes: kinds, getLabel: kindLabel } = useCodes(projectId, 'APP_KIND');
  const form = useEditForm(app, pickApp);
  const [notice, setNotice] = useState('');
  const [warnings, setWarnings] = useState([]);
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.application(appId) });
    qc.invalidateQueries({ queryKey: keys.applications(projectId) });
    qc.invalidateQueries({ queryKey: keys.appLinks() });
  };
  const save = useFormSave({
    save: () => {
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'kind_code') body.kind_code = form.values.kind_code || null;     // '' clears (DR6b-P3)
        else if (k === 'lifecycle_code') body.lifecycle_code = form.values.lifecycle_code;
        else body[k] = blankToNull(form.values[k]);
      }
      if ('application_code' in body) body.application_code = form.values.application_code.trim();
      if ('application_name' in body) body.application_name = form.values.application_name.trim();
      return appApi.update(app.application_id, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.application(appId), row); refreshAll();
      setWarnings(row.warnings ?? []); setNotice(t('applications.saved')); },
  });
  const reload = async () => {
    try {
      form.rebase(await qc.fetchQuery({ queryKey: keys.application(appId), queryFn: () => appApi.get(appId) }));
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => { refreshAll(); setActionError(isStale(err) ? t('applications.staleAction') : errorText(err, t('common.saveFailed'))); };
  const retire = useMutation({
    mutationFn: () => appApi.retire(app.application_id, app.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('applications.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => appApi.restore(app.application_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.application(appId), row); refreshAll();
      setNotice(t('applications.restored', { code: row.application_code })); },
    onError: actionFail,
  });

  const crumbs = (
    <Breadcrumbs sx={{ mb: 1.5 }}>
      <Link component={RouterLink} to={links.settings(projectId)} underline="hover" color="inherit">{t('settings.title')}</Link>
      <Link component={RouterLink} to={links.applications(projectId)} underline="hover" color="inherit">{t('applications.back')}</Link>
      <Typography sx={{ color: 'text.primary' }}>{app?.application_code ?? '…'}</Typography>
    </Breadcrumbs>
  );
  if (q.error) return <Box>{crumbs}<Alert severity="error">{errorText(q.error)}</Alert></Box>;
  if (!app || !form.values) return <Box>{crumbs}<Typography sx={{ color: 'text.secondary' }}>{t('applications.loading')}</Typography></Box>;

  const v = form.values;
  const live = app.is_active;
  const editable = live && canEdit;
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const labels = { application_code: t('applications.code'), application_name: t('applications.name'),
    lifecycle_code: t('applications.lifecycle'), kind_code: t('applications.kind'), vendor: t('applications.vendor'),
    version_label: t('applications.version'), description: t('applications.description') };
  const shown = (k) => (k === 'lifecycle_code' ? lifecycleLabel(v[k]) : k === 'kind_code' ? (v[k] ? kindLabel(v[k]) : t('applications.noKind')) : v[k]);
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], shown(k)]));
  const text = (name, rows = 1, max = 4000) => (
    <TextField fullWidth multiline={rows > 1} minRows={rows > 1 ? rows : undefined} id={`app-${name}`} label={labels[name]}
      disabled={!editable} value={v[name]} required={name === 'application_code' || name === 'application_name'}
      onChange={(e) => form.set(name, name === 'application_code' ? e.target.value.toUpperCase() : e.target.value)}
      slotProps={{ htmlInput: { maxLength: max } }} />
  );
  const select = (name, options, extra = {}) => (editable ? (
    <SimpleSelect id={`app-${name}`} label={labels[name]} value={v[name]} onChange={(c) => form.set(name, c)} options={options} {...extra} />
  ) : <TextField fullWidth size="small" disabled label={labels[name]} value={shown(name)} />);

  return (
    <Box>
      {crumbs}
      <Stack direction="row" sx={{ alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5" component="h1" sx={(th) => ({ fontWeight: 700, color: th.vars.palette.brand.title })}>
            <Mono sx={(th) => ({ color: th.vars.palette.brand.link, mr: 1.5 })}>{app.application_code}</Mono>{app.application_name}
          </Typography>
          <Typography sx={{ color: 'text.secondary', mt: 0.5 }}>{t('applications.detailSubtitle')}</Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          {!live && <Chip variant="outlined" label={t('applications.retiredChip')} />}
          {canEdit && (live ? (
            <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('applications.retire')}</Button>
          ) : (
            <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('applications.restore')}</Button>
          ))}
          {editable && (
            <>
              <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('applications.discard')}</Button>
              <Button variant="contained" disabled={!form.dirty || busy || !v.application_code.trim() || !v.application_name.trim()}
                onClick={() => { save.setError(''); save.m.mutate(); }}>{t('applications.save')}</Button>
            </>)}
        </Stack>
      </Stack>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      {warnings.map((w) => (
        <Alert key={w.code} severity="warning" sx={{ mb: 2 }} onClose={() => setWarnings([])}>
          {t(`applications.warn.${w.code}`, { items: w.items.join(', ') })}</Alert>))}

      <Card>
        <CardContent>
          <Stack direction="row" sx={{ justifyContent: 'flex-end', mb: 2 }}>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('applications.version_', { v: form.version })}</Typography>
          </Stack>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 4, md: 3 }}>{text('application_code', 1, 30)}</Grid>
            <Grid size={{ xs: 12, sm: 8, md: 5 }}>{text('application_name', 1, 200)}</Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2 }}>{select('lifecycle_code', lifecycles.map((c) => ({ value: c.code, label: c.label })))}</Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2 }}>
              {select('kind_code', kinds.map((c) => ({ value: c.code, label: c.label })), { allowEmpty: true, emptyLabel: t('applications.noKind') })}</Grid>
            <Grid size={{ xs: 12, md: 6 }}>{text('vendor', 1, 200)}</Grid>
            <Grid size={{ xs: 12, md: 6 }}>{text('version_label', 1, 50)}</Grid>
            <Grid size={12}>{text('description', 3)}</Grid>
          </Grid>
          <Divider sx={{ my: 3 }} />
          <Grid container spacing={4}>
            <Grid size={{ xs: 12, md: 6 }}>
              <UsedBy title={t('applications.deliversTitle')} empty={t('applications.noneDelivers')} query={solsQ}
                render={(r) => (
                  <Link key={r.application_solution_id} component={RouterLink} to={links.solution(projectId, r.solution_id)} underline="hover">
                    <Mono>{r.solution_number}</Mono> {r.solution_name}</Link>)} />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <UsedBy title={t('applications.supportsTitle')} empty={t('applications.noneSupports')} query={stepsQ}
                render={(r) => (
                  <Link key={r.application_bfc_node_id} component={RouterLink} to={links.node(projectId, r.bfc_node_id)} underline="hover">
                    <Mono>{r.hier_code}</Mono> {r.node_name}</Link>)} />
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('applications.retireTitle')}
        body={t('applications.retireBody', { code: app.application_code })} confirmLabel={t('applications.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
