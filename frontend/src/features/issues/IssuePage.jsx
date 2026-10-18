import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { issueApi, stakeholderApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CodeTitle, SaveState, TwoCol } from '../frs/frKit';
import { IssueStatus, SeverityTag } from './issueKit';
import { IssueBrLinks } from './IssueBrLinks';

const pick = (i) => ({ title: i.title, description: i.description ?? '', severity_code: i.severity_code,
  issue_type_code: i.issue_type_code, status_code: i.status_code, raised_by_stakeholder_id: i.raised_by_stakeholder_id,
  raised_date: i.raised_date, target_date: i.target_date ?? '' });

// Resolve (§4.5): a closed status and a resolution, both required; the server stamps who and when.
function ResolveDialog({ issue, closedOptions, onClose, onDone, onStale }) {
  const [status, setStatus] = useState(closedOptions[0]?.value ?? '');
  const [text, setText] = useState(issue.resolution ?? '');
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => issueApi.resolve(issue.issue_id, { row_version: issue.row_version, status_code: status,
      resolution: text.trim() }),
    onSuccess: (row) => { onDone(row); onClose(); },
    onError: (err) => (isStale(err) ? onStale() : setError(errorText(err, t('common.saveFailed')))),
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('issues.resolveTitle', { number: issue.issue_number })}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <SimpleSelect id="iss-resolve-status" label={t('issues.field.status')} value={status} onChange={setStatus}
            options={closedOptions} />
          <TextField id="iss-resolve-text" label={t('issues.field.resolution')} required multiline minRows={3} value={text}
            onChange={(e) => setText(e.target.value)} helperText={t('issues.problemNotPerson')} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !status || !text.trim()}
          onClick={() => { setError(''); m.mutate(); }}>{t('issues.resolve')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function IssuePage() {
  const { projectId, issueId } = useParams();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('ISSUE');
  const q = useQuery({ queryKey: keys.issue(issueId), queryFn: () => issueApi.get(issueId) });
  const issue = q.data;
  const stk = useQuery({ queryKey: keys.stakeholders(projectId), queryFn: () => stakeholderApi.list(projectId, true) });
  const sev = useCodes(projectId, 'ISSUE_SEVERITY');
  const typ = useCodes(projectId, 'ISSUE_TYPE');
  const sts = useCodes(projectId, 'ISSUE_STATUS');
  const form = useEditForm(issue, pick);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [resolving, setResolving] = useState(false);
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.issue(issueId) });
    qc.invalidateQueries({ queryKey: keys.issues(projectId) }); qc.invalidateQueries({ queryKey: keys.scopeSummary(projectId) });
  };
  const landed = (row, msg) => { form.saved(row); qc.setQueryData(keys.issue(issueId), row); refreshAll(); setNotice(msg); };
  const save = useFormSave({
    save: () => {
      const body = { row_version: form.version };
      for (const k of form.changed) body[k] = k === 'title' ? form.values.title.trim() : blankToNull(form.values[k]);
      return issueApi.update(issue.issue_id, body);
    },
    onSaved: (row) => landed(row, t('issues.saved')),
  });
  const reload = async () => {
    try {
      form.rebase(await qc.fetchQuery({ queryKey: keys.issue(issueId), queryFn: () => issueApi.get(issueId) }));
      save.setError('');
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };
  const actionFail = (err) => { refreshAll(); setActionError(isStale(err) ? t('issues.stale') : errorText(err, t('common.saveFailed'))); };
  const reopen = useMutation({
    mutationFn: () => issueApi.reopen(issue.issue_id, { row_version: issue.row_version }),
    onSuccess: (row) => { setActionError(''); landed(row, t('issues.reopened')); },
    onError: actionFail,
  });
  const retire = useMutation({
    mutationFn: () => issueApi.retire(issue.issue_id, issue.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('issues.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => issueApi.restore(issue.issue_id),
    onSuccess: (row) => { setActionError(''); landed(row, t('issues.restored')); },
    onError: actionFail,
  });

  if (q.error) return <Page title={t('issues.title')} error={errorText(q.error)} />;
  if (!issue || !form.values) return <Page title={t('issues.loading')} />;

  const v = form.values;
  const live = issue.is_active;
  const closed = issue.status_behaviour === 'CLOSED';
  const editable = live && canEdit;
  const busy = save.m.isPending || reopen.isPending || retire.isPending || restore.isPending;
  const people = stk.data ?? [];
  const pickOf = (codes, current, keep = () => true) => codes.options(current).filter(keep)
    .map((c) => ({ value: c.code, label: c.label }));
  const labels = { title: t('issues.field.title'), description: t('issues.field.description'),
    severity_code: t('issues.field.severity'), issue_type_code: t('issues.field.type'), status_code: t('issues.field.status'),
    raised_by_stakeholder_id: t('issues.field.raiser'), raised_date: t('issues.field.raisedDate'),
    target_date: t('issues.field.targetDate') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], v[k]]));
  const field = (name, extra = {}) => (
    <TextField fullWidth id={`iss-${name}`} label={labels[name]} disabled={!editable} value={v[name]}
      onChange={(e) => form.set(name, e.target.value)} {...extra} />
  );
  const select = (name, options, disabled = false) => (
    <SimpleSelect id={`iss-${name}`} label={labels[name]} value={v[name]} disabled={!editable || disabled}
      onChange={(c) => form.set(name, c)} options={options} />
  );

  const actions = canEdit && (
    <>
      {live && !closed && (
        <Button variant="outlined" disabled={busy || form.dirty} onClick={() => { setActionError(''); setResolving(true); }}>
          {t('issues.resolve')}</Button>)}
      {live && closed && (
        <Button variant="outlined" disabled={busy || form.dirty} onClick={() => { setActionError(''); reopen.mutate(); }}>
          {t('issues.reopen')}</Button>)}
      {live ? (
        <Button variant="outlined" color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>
          {t('issues.retire')}</Button>
      ) : (
        <Button variant="outlined" disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('issues.restore')}</Button>
      )}
      {editable && (
        <>
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('issues.discard')}</Button>
          <Button variant="contained" disabled={!form.dirty || busy || !v.title.trim()}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('issues.save')}</Button>
        </>)}
    </>
  );

  const main = (
    <Card title={t('issues.cardTitle')} action={<SaveState version={form.version} dirty={form.dirty} retired={!live} />}>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <IssueStatus issue={issue} label={sts.getLabel(issue.status_code)} />
        <SeverityTag code={issue.severity_code} label={sev.getLabel(issue.severity_code)} />
      </Box>
      {field('title', { required: true, slotProps: { htmlInput: { maxLength: 200 } } })}
      {field('description', { multiline: true, minRows: 3, helperText: t('issues.problemNotPerson') })}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'repeat(2, minmax(0,1fr))' } }}>
        {select('severity_code', pickOf(sev, issue.severity_code))}
        {select('issue_type_code', pickOf(typ, issue.issue_type_code))}
        {/* R2: edit moves only among open statuses; a closed issue changes status by reopen */}
        {select('status_code', closed ? pickOf(sts, issue.status_code, (c) => c.code === issue.status_code)
          : pickOf(sts, issue.status_code, (c) => c.behaviour_code === 'OPEN'), closed)}
        <SimpleSelect id="iss-raiser" label={labels.raised_by_stakeholder_id} value={v.raised_by_stakeholder_id}
          disabled={!editable} onChange={(c) => form.set('raised_by_stakeholder_id', c)}
          options={people.filter((s) => s.is_active || s.stakeholder_id === issue.raised_by_stakeholder_id)
            .map((s) => ({ value: s.stakeholder_id, label: s.stakeholder_name }))} />
        {field('raised_date', { type: 'date', slotProps: { inputLabel: { shrink: true } } })}
        {field('target_date', { type: 'date', slotProps: { inputLabel: { shrink: true } } })}
      </Box>
    </Card>
  );
  const side = (
    <>
    <IssueBrLinks projectId={projectId} issue={issue} canEdit={canEdit} />
    <Card title={t('issues.resolutionTitle')} bodySx={{ gap: 1 }}>
      {issue.resolution ? (
        <Typography sx={{ fontSize: 13.5, whiteSpace: 'pre-wrap' }}>{issue.resolution}</Typography>
      ) : <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('issues.noResolution')}</Typography>}
      {issue.resolved_at && (
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
          {t('issues.resolvedAt', { when: new Date(issue.resolved_at).toLocaleString() })}</Typography>)}
      {issue.resolution && !closed && (
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('issues.reopenedNote')}</Typography>)}
    </Card>
    </>
  );
  const closedOptions = pickOf(sts, '', (c) => c.behaviour_code === 'CLOSED');

  return (
    <Page title={<CodeTitle code={issue.issue_number} name={issue.title} />} subtitle={t('issues.detailSubtitle')}
      crumb={issue.issue_number} actions={actions}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      <TwoCol main={main} side={side} />
      {resolving && <ResolveDialog issue={issue} closedOptions={closedOptions} onClose={() => setResolving(false)}
        onDone={(row) => landed(row, t('issues.resolved', { number: row.issue_number }))}
        onStale={() => { setResolving(false); refreshAll(); setActionError(t('issues.stale')); }} />}
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('issues.retireTitle')}
        body={t('issues.retireBody', { number: issue.issue_number })} confirmLabel={t('issues.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
