import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Breadcrumbs, Button, Card, CardContent, Chip, Divider, Grid, Link, Snackbar, Stack,
  TextField, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { bfcApi, brApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { t } from '../../i18n/t';
import { LevelBadge, Mono, RaciPanel, SimpleSelect, blankToNull, useEditForm, useFormSave } from '../processes/chartKit';
import { CrudGrid } from './CrudGrid';
import { SolutionLinkPanel } from '../solutions/SolutionLinkPanel';

// S1-8: a person sets Draft or Confirmed. Baselined / Superseded are set by the freeze and are
// shown read-only (the server refuses them too: business_requirement.SYSTEM_SET_STATUSES).
const SETTABLE_STATUSES = ['DRAFT', 'CONFIRMED'];
const BR_SINGLE = ['ACCOUNTABLE'];                      // services/raci.py SINGLE[BrOrgRole]

const pickBr = (b) => ({ br_statement: b.br_statement ?? '', business_logic: b.business_logic ?? '',
  output_expectation: b.output_expectation ?? '', status_code: b.status_code });

export default function RequirementPage() {
  const { projectId, brId } = useParams();
  const qc = useQueryClient();
  const brQ = useQuery({ queryKey: keys.br(brId), queryFn: () => brApi.get(brId) });
  const br = brQ.data;
  const nodeQ = useQuery({ queryKey: keys.node(br?.bfc_node_id), queryFn: () => bfcApi.get(br.bfc_node_id),
    enabled: Boolean(br) });
  const node = nodeQ.data;
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

  const crumbs = (
    <Breadcrumbs sx={{ mb: 1.5 }}>
      <Link component={RouterLink} to={links.requirements(projectId)} underline="hover" color="inherit">{t('requirements.title')}</Link>
      <Typography sx={{ color: 'text.primary' }}>{br?.br_number ?? '…'}</Typography>
    </Breadcrumbs>
  );
  if (brQ.error) return <Box>{crumbs}<Alert severity="error">{errorText(brQ.error)}</Alert></Box>;
  if (!br || !form.values) return <Box>{crumbs}<Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography></Box>;

  const v = form.values;
  const live = br.is_active;
  const statusSettable = SETTABLE_STATUSES.includes(form.base.status_code);
  const busy = save.m.isPending || retire.isPending || restore.isPending;
  const statusOptions = statuses.filter((c) => SETTABLE_STATUSES.includes(c.code)).map((c) => ({ value: c.code, label: c.label }));
  const labels = { br_statement: t('requirements.statement'), business_logic: t('requirements.logic'),
    output_expectation: t('requirements.output'), status_code: t('requirements.status') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], k === 'status_code' ? getLabel(v[k]) : v[k]]));
  const text = (name, label, rows = 2) => (
    <TextField fullWidth multiline minRows={rows} id={`br-${name}`} label={label} disabled={!live} value={v[name]}
      onChange={(e) => form.set(name, e.target.value)} slotProps={{ htmlInput: { maxLength: 8000 } }} />
  );

  return (
    <Box>
      {crumbs}
      <Stack direction="row" sx={{ alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0 }}>
          {node && (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
              <LevelBadge level={node.level_no} process={node.is_process} />
              <Link component={RouterLink} to={links.node(projectId, node.bfc_node_id)} underline="hover">
                <Mono>{node.hier_code}</Mono></Link>
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.backToNode')}</Typography>
            </Stack>
          )}
          <Typography variant="h5" component="h1" sx={(th) => ({ fontWeight: 700, color: th.vars.palette.brand.title })}>
            <Mono sx={(th) => ({ color: th.vars.palette.brand.link, mr: 1.5 })}>{br.br_number}</Mono>{node?.node_name}
          </Typography>
          <Typography sx={{ color: 'text.secondary', mt: 0.5 }}>{t('requirements.detailSubtitle')}</Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          {!live && <Chip variant="outlined" label={t('processes.retiredChip')} />}
          {live ? (
            <Button color="warning" disabled={busy} onClick={() => { setActionError(''); setConfirmRetire(true); }}>{t('requirements.retire')}</Button>
          ) : (
            <Button disabled={busy} onClick={() => { setActionError(''); restore.mutate(); }}>{t('requirements.restore')}</Button>
          )}
          <Button variant="outlined" disabled={!form.dirty || busy} onClick={form.discard}>{t('processes.discard')}</Button>
          <Button variant="contained" disabled={!live || !form.dirty || busy}
            onClick={() => { save.setError(''); save.m.mutate(); }}>{t('requirements.save')}</Button>
        </Stack>
      </Stack>
      {actionError && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
      {save.error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
      {nodeQ.error && <Alert severity="error" sx={{ mb: 2 }}>{errorText(nodeQ.error)}</Alert>}

      <Card>
        <CardContent>
          <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Typography component="h2" variant="h6">{t('requirements.requirement')}</Typography>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('requirements.version', { v: form.version })}</Typography>
          </Stack>
          <Grid container spacing={2}>
            <Grid size={12}>{text('br_statement', t('requirements.statement'))}</Grid>
            <Grid size={12}>{text('business_logic', t('requirements.logic'), 3)}</Grid>
            <Grid size={{ xs: 12, md: 8 }}>{text('output_expectation', t('requirements.output'))}</Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              {statusSettable ? (
                <SimpleSelect id="br-status" label={t('requirements.status')} value={v.status_code}
                  onChange={(s) => form.set('status_code', s)} options={statusOptions} />
              ) : (
                <Box>
                  <Typography sx={{ fontSize: 12, color: 'text.secondary', mb: 0.5 }}>{t('requirements.status')}</Typography>
                  <Chip label={getLabel(br.status_code)} />
                  <Typography sx={{ fontSize: 12, color: 'text.secondary', mt: 0.5 }}>{t('requirements.statusByFreeze')}</Typography>
                </Box>
              )}
            </Grid>
          </Grid>
          <Divider sx={{ my: 3 }} />
          <Grid container spacing={4}>
            <Grid size={{ xs: 12, lg: 7 }}>
              <CrudGrid projectId={projectId} br={br} disabled={!live} />
            </Grid>
            <Grid size={{ xs: 12, lg: 5 }}>
              <RaciPanel projectId={projectId} queryKey={[...keys.br(brId), 'roles']} disabled={!live}
                list={() => brApi.roles(br.br_id)} link={(body) => brApi.linkRole(br.br_id, body)}
                unlink={(id, rv) => brApi.unlinkRole(br.br_id, id, rv)} linkId="br_org_role_id" single={BR_SINGLE} />
            </Grid>
          </Grid>
          <Divider sx={{ my: 3 }} />
          <SolutionLinkPanel projectId={projectId} side="br" br={br} disabled={!live} />
        </CardContent>
      </Card>

      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      <ConfirmDialog open={confirmRetire} title={t('requirements.retireTitle')}
        body={t('requirements.retireBody', { number: br.br_number })} confirmLabel={t('requirements.retire')}
        busy={retire.isPending} onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
