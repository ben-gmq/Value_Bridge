import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputLabel, List,
  ListItemButton, ListItemText, MenuItem, Select, Snackbar, Stack, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Tooltip, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { codeListApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanAdmin } from '../../app/useCanEdit';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SettingsCrumbs } from './settingsKit';

// The behaviour vocabularies (code_master CHECKs, D-27, I-1): a new FR or RACI type or issue status needs one.
const BEHAVIOURS = { FR_TYPE: ['FORM', 'INTERFACE', 'REPORT', 'BATCH', 'OTHER'],
  RACI_TYPE: ['RESPONSIBLE', 'ACCOUNTABLE', 'CONSULTED', 'INFORMED', 'SUPPORT', 'OTHER'],
  ISSUE_STATUS: ['OPEN', 'CLOSED'] };

// One add / rename dialog: a new code (with behaviour for FR and RACI types), or a new wording for an existing one.
function CodeDialog({ open, title, hint, category, withCode, initial, onSubmit, onClose }) {
  const [code, setCode] = useState('');
  const [label, setLabel] = useState(initial ?? '');
  const [behaviour, setBehaviour] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const needsBehaviour = withCode && BEHAVIOURS[category];
  const submit = () => {
    setBusy(true);
    onSubmit({ code: code.trim(), label: label.trim(), behaviour_code: needsBehaviour ? behaviour || null : null })
      .then(onClose).catch((err) => setError(errorText(err, t('codes.failed')))).finally(() => setBusy(false));
  };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          {hint && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{hint}</Typography>}
          {withCode && (
            <TextField id="code-code" label={t('codes.code')} value={code} helperText={t('codes.codeHelp')}
              onChange={(e) => setCode(e.target.value.toUpperCase())} />)}
          <TextField id="code-label" label={t('codes.label')} value={label} onChange={(e) => setLabel(e.target.value)} />
          {needsBehaviour && (
            <FormControl size="small">
              <InputLabel id="code-behaviour-label">{t('codes.behaviour')}</InputLabel>
              <Select labelId="code-behaviour-label" id="code-behaviour" label={t('codes.behaviour')} value={behaviour}
                onChange={(e) => setBehaviour(e.target.value)}>
                {BEHAVIOURS[category].map((b) => <MenuItem key={b} value={b}>{t(`codes.behaviour.${b}`)}</MenuItem>)}
              </Select>
            </FormControl>)}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={busy || !label.trim() || (withCode && !code.trim()) || (needsBehaviour && !behaviour)}
          onClick={submit}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function Flags({ item }) {
  return (
    <Stack direction="row" useFlexGap sx={{ gap: 0.5, flexWrap: 'wrap' }}>
      {item.pinned && <Tooltip title={t('codes.pinnedHint')}><span><Tag tone="navy">{t('codes.pinned')}</Tag></span></Tooltip>}
      {item.hidden && <Tag tone="caution">{t('codes.hidden')}</Tag>}
      {!item.company && <Tag tone="teal">{t('codes.own')}</Tag>}
      {(item.company ? !item.company.is_active && !item.project?.is_active : !item.project?.is_active) && (
        <Tag tone="neutral">{t('codes.retired')}</Tag>)}
    </Stack>
  );
}

/**
 * The code-list screen (wave 1g; slice1g_spec §4, §7). With a projectId: that project's lists — its admins rename,
 * add, retire, hide (G-1, G-5). Without: the company library, for platform admins. Every rule is the server's; the
 * screen only hides controls a person could not use.
 */
export function CodeListsView({ projectId }) {
  const company = !projectId;
  const canAdmin = useCanAdmin();
  const canWrite = company || canAdmin;
  const qc = useQueryClient();
  const key = keys.codeLists(projectId);
  const q = useQuery({ queryKey: key, queryFn: () => (company ? codeListApi.company() : codeListApi.project(projectId)) });
  const [category, setCategory] = useState(null);
  const [dialog, setDialog] = useState(null);           // { kind: 'add' | 'rename' | 'edit', item }
  const [confirm, setConfirm] = useState(null);         // { kind: 'retire' | 'useCompany', row, item }
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ['codes'] }); };
  const done = () => { setError(''); setNotice(t('codes.saved')); refresh(); };
  const act = useMutation({ mutationFn: (fn) => fn(), onSuccess: () => { setConfirm(null); done(); },
    onError: (err) => { setConfirm(null); setError(errorText(err, t('codes.failed'))); } });

  const lists = q.data ?? [];
  const current = lists.find((l) => l.category === category) ?? lists[0];
  const locked = !current || current.is_system || (!company && current.company_only);
  const editable = canWrite && !locked;

  const add = (body) => (company ? codeListApi.addCompany(current.category, body)
    : codeListApi.addProject(projectId, current.category, body)).then(done);
  const rename = (item, body) => {
    const own = company ? item.company : item.project;
    if (own?.is_active) return codeListApi.update(own.code_id, { row_version: own.row_version, label: body.label }).then(done);
    return codeListApi.addProject(projectId, current.category, { code: item.code, label: body.label }).then(done);
  };

  return (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: '280px minmax(0, 1fr)' }, alignItems: 'start' }}>
      <Card title={t('codes.lists')} bodySx={{ px: 0, py: 0.5 }}>
        <List dense aria-label={t('codes.lists')}>
          {lists.map((l) => (
            <ListItemButton key={l.category} selected={current?.category === l.category} onClick={() => setCategory(l.category)}>
              <ListItemText primary={<Code tone="neutral">{l.category}</Code>}
                secondary={t('codes.count', { n: l.codes.length })} />
            </ListItemButton>))}
        </List>
      </Card>
      <Stack spacing={2} sx={{ minWidth: 0 }}>
        {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
        {current && (
          <Card title={<Code tone="neutral">{current.category}</Code>} bodySx={{ px: 0, gap: 1.5 }}
            action={editable && <Button variant="contained" size="small" onClick={() => setDialog({ kind: 'add' })}>{t('codes.add')}</Button>}>
            {current.is_system && <Alert severity="info" sx={{ mx: 2.5 }}>{t('codes.system')}</Alert>}
            {!company && current.company_only && !current.is_system && <Alert severity="info" sx={{ mx: 2.5 }}>{t('codes.companyOnly')}</Alert>}
            {!company && !canWrite && !locked && <Alert severity="info" sx={{ mx: 2.5 }}>{t('codes.readOnly')}</Alert>}
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ pl: 2.5 }}>{t('codes.code')}</TableCell>
                    <TableCell>{t('codes.company')}</TableCell>
                    {!company && <TableCell>{t('codes.project')}</TableCell>}
                    {BEHAVIOURS[current.category] && <TableCell>{t('codes.behaviour')}</TableCell>}
                    <TableCell align="right">{t('codes.inUse')}</TableCell>
                    <TableCell />
                    <TableCell sx={{ pr: 2.5 }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {current.codes.map((item) => {
                    const ref = item.company ?? item.project;
                    const override = item.company && item.project?.is_active;
                    return (
                      <TableRow key={item.code}>
                        <TableCell sx={{ pl: 2.5 }}><Code tone="neutral">{item.code}</Code></TableCell>
                        <TableCell sx={{ minWidth: 140 }}>{item.company?.label ?? '—'}</TableCell>
                        {!company && <TableCell sx={{ minWidth: 140, fontWeight: override || !item.company ? 600 : 400 }}>
                          {item.project?.is_active ? item.project.label : ''}</TableCell>}
                        {BEHAVIOURS[current.category] && <TableCell>{ref.behaviour_code && t(`codes.behaviour.${ref.behaviour_code}`)}</TableCell>}
                        <TableCell align="right">{item.in_use}</TableCell>
                        <TableCell><Flags item={item} /></TableCell>
                        <TableCell align="right" sx={{ pr: 2.5, whiteSpace: 'nowrap' }}>
                          {editable && <Actions item={item} company={company} projectId={projectId} act={act}
                            onRename={() => setDialog({ kind: 'rename', item })} onConfirm={setConfirm} />}
                        </TableCell>
                      </TableRow>);
                  })}
                </TableBody>
              </Table>
            </Box>
          </Card>)}
      </Stack>
      {dialog && (
        <CodeDialog open category={current.category} withCode={dialog.kind === 'add'}
          title={dialog.kind === 'add' ? t('codes.addTitle', { list: current.category }) : t('codes.renameTitle', { code: dialog.item.code })}
          hint={dialog.kind === 'rename' && !company ? t('codes.renameHint', { code: dialog.item.code }) : null}
          initial={dialog.kind === 'rename' ? ((company ? dialog.item.company : dialog.item.project)?.is_active
            ? (company ? dialog.item.company : dialog.item.project).label : dialog.item.company?.label) : ''}
          onSubmit={(body) => (dialog.kind === 'add' ? add(body) : rename(dialog.item, body))}
          onClose={() => setDialog(null)} />)}
      <ConfirmDialog open={Boolean(confirm)}
        title={confirm?.kind === 'useCompany' ? t('codes.useCompany') : t('codes.retire')}
        body={confirm?.kind === 'useCompany'
          ? t('codes.useCompanyBody', { code: confirm.item.code, label: confirm.item.company?.label })
          : t('codes.retireBody', { code: confirm?.item.code })}
        confirmLabel={confirm?.kind === 'useCompany' ? t('codes.useCompany') : t('codes.retire')} busy={act.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => act.mutate(() => codeListApi.retire(confirm.row.code_id, confirm.row.row_version))} />
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}

function Actions({ item, company, projectId, act, onRename, onConfirm }) {
  const own = company ? item.company : item.project;
  const override = !company && item.company && item.project?.is_active;
  return (
    <Stack direction="row" useFlexGap sx={{ gap: 0.5, justifyContent: 'flex-end' }}>
      {(own?.is_active || (!company && item.company?.is_active)) && (
        <Button size="small" onClick={onRename}>{t('codes.rename')}</Button>)}
      {override && <Button size="small" color="warning" onClick={() => onConfirm({ kind: 'useCompany', row: item.project, item })}>
        {t('codes.useCompany')}</Button>}
      {!company && item.company && !item.pinned && !item.hidden && (
        <Button size="small" onClick={() => act.mutate(() => codeListApi.hide(projectId, item.company.code_id))}>{t('codes.hide')}</Button>)}
      {!company && item.hidden && (
        <Button size="small" onClick={() => act.mutate(() => codeListApi.unhide(projectId, item.company.code_id))}>{t('codes.unhide')}</Button>)}
      {(company || !item.company) && own?.is_active && !item.pinned && (
        <Button size="small" color="warning" onClick={() => onConfirm({ kind: 'retire', row: own, item })}>{t('codes.retire')}</Button>)}
      {(company || !item.company) && own && !own.is_active && (
        <Button size="small" onClick={() => act.mutate(() => codeListApi.restore(own.code_id, own.row_version))}>{t('codes.restore')}</Button>)}
    </Stack>
  );
}

export default function CodeListsPage() {
  const { projectId } = useParams();
  return (
    <>
      <SettingsCrumbs projectId={projectId} current={t('codes.title')} />
      <Page title={t('codes.title')} subtitle={t('codes.subtitle')}>
        <CodeListsView projectId={projectId} />
      </Page>
    </>
  );
}
