import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Snackbar, TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { appApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, Code, ListRow, PurpleTile, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CodeTitle, SaveState, TwoCol } from '../frs/frKit';

const pickApp = (a) => ({ application_code: a.application_code, application_name: a.application_name,
  lifecycle_code: a.lifecycle_code, kind_code: a.app_kind_code ?? '', vendor: a.vendor ?? '',
  version_label: a.version_label ?? '', description: a.description ?? '' });

// What the application touches, read-only here: links are made from the Solution and step pages.
function UsedBy({ title, empty, query, render }) {
  const rows = query.data ?? [];
  return (
    <Card title={title} action={query.data && <Tag tone="neutral">{rows.length}</Tag>} bodySx={{ gap: 1 }}>
      {query.error && <Alert severity="error">{errorText(query.error)}</Alert>}
      {!query.isLoading && !query.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{empty}</Typography>)}
      {rows.map(render)}
    </Card>
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
  const { options: lifecycleOptions, getLabel: lifecycleLabel } = useCodes(projectId, 'APP_LIFECYCLE');
  const { options: kindOptions, getLabel: kindLabel } = useCodes(projectId, 'APP_KIND');
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

  if (q.error) return <Page title={t('applications.back')} error={errorText(q.error)} />;
  if (!app || !form.values) return <Page title={t('applications.loading')} />;

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

  const actions = (
    <>
      {canEdit && (live ? (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('applications.retire')}</Button>
      ) : (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('applications.restore')}</Button>
      ))}
      {editable && (
        <>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('applications.discard')}</Button>
          <Button variant="contained" disabled={!form.dirty || busy || !v.application_code.trim() || !v.application_name.trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('applications.save')}</Button>
        </>)}
    </>
  );
  const linkRow = (key, to, code, codeTone, name) => (
    <ListRow key={key} component={RouterLink} to={to}>
      <Code tone={codeTone}>{code}</Code>
      <Typography sx={{ fontSize: 13.5, fontWeight: 600, minWidth: 0 }}>{name}</Typography>
    </ListRow>
  );

  const main = (
    <Card title={t('applications.cardTitle')} action={<SaveState version={form.version} dirty={form.dirty} retired={!live} />}>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Tag tone="teal">{lifecycleLabel(app.lifecycle_code)}</Tag>
        {app.app_kind_code && <Tag tone="neutral">{kindLabel(app.app_kind_code)}</Tag>}
      </Box>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'minmax(0,1fr) minmax(0,2fr)' } }}>
        {text('application_code', 1, 30)}
        {text('application_name', 1, 200)}
      </Box>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'repeat(2, minmax(0,1fr))' } }}>
        {select('lifecycle_code', lifecycleOptions(app.lifecycle_code).map((c) => ({ value: c.code, label: c.label })))}
        {select('kind_code', kindOptions(app.app_kind_code).map((c) => ({ value: c.code, label: c.label })), { allowEmpty: true, emptyLabel: t('applications.noKind') })}
        {text('vendor', 1, 200)}
        {text('version_label', 1, 50)}
      </Box>
      {text('description', 3)}
    </Card>
  );
  const side = (
    <>
      <PurpleTile label={t('applications.tiles.delivers')} value={solsQ.data ? solsQ.data.length : '—'} />
      <UsedBy title={t('applications.deliversTitle')} empty={t('applications.noneDelivers')} query={solsQ}
        render={(r) => linkRow(r.application_solution_id, links.solution(projectId, r.solution_id), r.solution_number, 'navy', r.solution_name)} />
      <UsedBy title={t('applications.supportsTitle')} empty={t('applications.noneSupports')} query={stepsQ}
        render={(r) => linkRow(r.application_bfc_node_id, links.node(projectId, r.bfc_node_id), r.hier_code, 'muted', r.node_name)} />
    </>
  );

  return (
    <Page title={<CodeTitle code={app.application_code} name={app.application_name} />} subtitle={t('applications.detailSubtitle')}
      crumb={app.application_code} actions={actions}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      {warnings.map((w) => (
        <Alert key={w.code} severity="warning" sx={{ mb: 2 }} onClose={() => setWarnings([])}>
          {t(`applications.warn.${w.code}`, { items: w.items.join(', ') })}</Alert>))}
      <TwoCol main={main} side={side} />

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('applications.retireTitle')}
        body={t('applications.retireBody', { code: app.application_code })} confirmLabel={t('applications.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
