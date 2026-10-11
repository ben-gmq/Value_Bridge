import { useMemo, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Divider, Link, Snackbar, TextField, Typography } from '@mui/material';
import LockOutlined from '@mui/icons-material/LockOutlined';
import { errorText, isStale } from '../../api/client';
import { bfcApi, brApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, Code, KV, LevelBadge, Status, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { useComponents } from '../../app/useComponents';
import { useCanEdit } from '../../app/useCanEdit';
import { t } from '../../i18n/t';
import { SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CrudGrid } from './CrudGrid';
import { BrRaci } from './BrRaci';
import { BrSolutionTags } from './BrSolutionTags';
import { CoveragePanel } from './CoveragePanel';
import { BrStatusTag } from './reqKit';

// S1-8: a person sets Draft or Confirmed. Baselined / Superseded are set by the freeze and are
// shown read-only (the server refuses them too: business_requirement.SYSTEM_SET_STATUSES).
const SETTABLE_STATUSES = ['DRAFT', 'CONFIRMED'];

const pickBr = (b) => ({ br_statement: b.br_statement ?? '', business_logic: b.business_logic ?? '',
  output_expectation: b.output_expectation ?? '', status_code: b.status_code });

// The two-column split inside the Requirement card follows the card's own width, not the window's.
const WIDE = '@container (min-width: 700px)';

// Business requirement page — mockup 03 (D-51). Left: the Requirement card (fields, CRUD, RACI,
// solutions); right: Coverage (FRs reached through solutions) and the Record card.
export default function RequirementPage() {
  const { projectId, brId } = useParams();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit();             // UAT 7b: a viewer sees the page, not its controls
  const qc = useQueryClient();
  const brQ = useQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId) });
  const br = brQ.data;
  const nodeQ = useQuery({ queryKey: keys.node(br?.bfc_node_id), queryFn: () => bfcApi.get(br.bfc_node_id),
    enabled: Boolean(br) });
  const node = nodeQ.data;
  // The parent path in the eyebrow; retired nodes too, as on the list, so a retired step still shows where it sat.
  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: true }], queryFn: () => bfcApi.tree(projectId, true) });
  const path = useMemo(() => {
    const byId = new Map((treeQ.data ?? []).map((n) => [n.bfc_node_id, n]));
    const out = [];
    for (let p = byId.get(node?.parent_bfc_node_id); p && out.length < 10; p = byId.get(p.parent_bfc_node_id)) out.unshift(p.node_name);
    return out;
  }, [treeQ.data, node]);
  const { codes: statuses, getLabel } = useCodes(projectId, 'BR_STATUS');
  const form = useEditForm(br, pickBr);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.br(brId) });
    qc.invalidateQueries({ queryKey: keys.brs(projectId) });
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });
  };

  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'status_code') { if (SETTABLE_STATUSES.includes(form.base.status_code)) body.status_code = form.values.status_code; }
        else body[k] = blankToNull(form.values[k]);
      }
      return brApi.update(br.br_id, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.br(brId), row); refreshAll(); setNotice(t('requirements.saved')); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId) });
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
    setActionError(isStale(err) ? t('processes.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const retire = useMutation({
    mutationFn: () => brApi.retire(br.br_id, br.row_version),
    onSuccess: () => { setConfirmRetire(false); setActionError(''); refreshAll(); setNotice(t('requirements.retired')); },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: () => brApi.restore(br.br_id),
    onSuccess: (row) => { setActionError(''); qc.setQueryData(keys.br(brId), row); refreshAll(); setNotice(t('requirements.restored')); },
    onError: actionFail,
  });

  if (brQ.error) return <Page title={t('requirements.title')} error={errorText(brQ.error)} />;
  if (!br || !form.values) {
    return (
      <Page title={t('requirements.title')}>
        <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>
      </Page>
    );
  }

  const v = form.values;
  const live = br.is_active;
  const editable = live && canEdit;
  const statusSettable = SETTABLE_STATUSES.includes(form.base.status_code);
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const statusOptions = statuses.filter((c) => SETTABLE_STATUSES.includes(c.code)).map((c) => ({ value: c.code, label: c.label }));
  const labels = { br_statement: t('requirements.statement'), business_logic: t('requirements.logic'),
    output_expectation: t('requirements.output'), status_code: t('requirements.status') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], k === 'status_code' ? getLabel(v[k]) : v[k]]));
  const text = (name, label, rows = 1, extra = {}) => (
    <TextField fullWidth multiline minRows={rows} id={`br-${name}`} label={label} disabled={!editable} value={v[name]}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: 8000 } }} {...extra} />
  );

  const eyebrow = node && (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
      <LevelBadge level={node.level_no} label={t('processes.levelN', { n: node.level_no })} />
      <Link component={RouterLink} to={links.node(projectId, node.bfc_node_id)} underline="hover"
        title={t('requirements.backToNode')}>
        <Code tone="purple">{node.hier_code}</Code></Link>
      {path.length > 0 && (
        <Typography noWrap sx={{ fontSize: 13, color: 'text.secondary', minWidth: 0 }}>{path.join(' › ')}</Typography>)}
    </Box>
  );
  const actions = (
    <>
      {!live && <Tag tone="neutral">{t('processes.retiredChip')}</Tag>}
      {canEdit && (live ? (
        <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('requirements.retire')}</Button>
      ) : (
        <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('requirements.restore')}</Button>
      ))}
      {canEdit && <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('processes.discard')}</Button>}
      {canEdit && <Button variant="contained" disabled={!editable || !form.dirty || busy}
        onClick={() => { save.setError(''); save.m.mutate(); }}>{t('requirements.save')}</Button>}
    </>
  );
  const saveState = form.dirty
    ? <Status tone="caution" size="sm">{t('requirements.unsaved')}</Status>
    : <Status tone="ok" size="sm">{t('requirements.savedVersion', { v: form.version })}</Status>;

  return (
    <Page eyebrow={eyebrow} crumb={br.br_number} subtitle={t('requirements.detailSubtitle')} actions={actions}
      title={<><Code tone="purple" sx={{ fontSize: 22, mr: 1.5 }}>{br.br_number}</Code>{node?.node_name}</>}>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      {nodeQ.error && <Alert severity="error" sx={{ mb: 2 }}>{errorText(nodeQ.error)}</Alert>}

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1fr) 340px' }, alignItems: 'start' }}>
        <Card title={t('requirements.requirement')} action={saveState} bodySx={{ containerType: 'inline-size', gap: 2.5 }}>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'minmax(0,1fr)',
            [WIDE]: { gridTemplateColumns: 'minmax(0,3fr) minmax(0,1fr)' } }}>
            <Box sx={{ gridColumn: '1 / -1' }}>{text('br_statement', t('requirements.statement'))}</Box>
            <Box sx={{ gridColumn: '1 / -1' }}>{text('business_logic', t('requirements.logic'), 2)}</Box>
            {text('output_expectation', t('requirements.output'))}
            {statusSettable && editable ? (
              <SimpleSelect id="br-status" label={t('requirements.status')} value={v.status_code}
                onChange={(s) => form.set('status_code', s)} options={statusOptions} />
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, alignItems: 'flex-start' }}>
                <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('requirements.status')}</Typography>
                <BrStatusTag code={br.status_code} label={getLabel(br.status_code)} />
                {!statusSettable && (
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('requirements.statusByFreeze')}</Typography>)}
              </Box>
            )}
          </Box>
          <Divider />
          <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: 'minmax(0,1fr)',
            [WIDE]: { gridTemplateColumns: 'minmax(0,1.25fr) minmax(0,1fr)' } }}>
            <CrudGrid projectId={projectId} br={br} disabled={!editable} />
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, minWidth: 0 }}>
              <BrRaci projectId={projectId} br={br} disabled={!editable} />
              {isOn('SOLUTION') && <BrSolutionTags projectId={projectId} br={br} disabled={!editable} />}
            </Box>
          </Box>
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          {isOn('FUNCTION_REQUIREMENT') && <CoveragePanel projectId={projectId} brId={br.br_id} />}
          <Card title={t('requirements.record')}>
            <KV k={t('requirements.recordVersion')} v={<Code tone="muted" sx={{ color: 'text.primary' }}>{br.row_version}</Code>} />
            <KV k={t('requirements.recordStatus')} v={<BrStatusTag code={br.status_code} label={getLabel(br.status_code)} />} />
            {!live && <KV k={t('requirements.recordState')} v={<Tag tone="neutral">{t('processes.retiredChip')}</Tag>} />}
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', p: 1.5, borderRadius: '14px', bgcolor: 'background.subtle' }}>
              <LockOutlined sx={{ fontSize: 18, color: 'brand.muted', mt: '1px' }} />
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('requirements.recordLock')}</Typography>
            </Box>
          </Card>
        </Box>
      </Box>

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('requirements.retireTitle')}
        body={t('requirements.retireBody', { number: br.br_number })} confirmLabel={t('requirements.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
