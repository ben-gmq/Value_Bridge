import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { issueApi, stakeholderApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { ListImportActions } from '../../components/ImportWizard';
import { Card, Code, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { GRID_SX, Toolbar } from '../frs/frKit';
import { IssueStatus, SeverityTag } from './issueKit';
import { IssueDashboard } from './IssueDashboard';

const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };

// Raise an issue (§4.5): the number is minted by the server at save; the recorder is the signed-in consultant.
function RaiseDialog({ projectId, stakeholders, onClose, onDone }) {
  const [f, setF] = useState({ title: '', description: '', severity_code: '', issue_type_code: '',
    raised_by_stakeholder_id: '', raised_date: '', target_date: '' });
  const [error, setError] = useState('');
  const { options: severityOptions } = useCodes(projectId, 'ISSUE_SEVERITY');
  const { options: typeOptions } = useCodes(projectId, 'ISSUE_TYPE');
  const m = useMutation({
    mutationFn: () => issueApi.create(projectId, { title: f.title.trim(), description: f.description.trim() || null,
      severity_code: f.severity_code, issue_type_code: f.issue_type_code,
      raised_by_stakeholder_id: f.raised_by_stakeholder_id, raised_date: f.raised_date || null,
      target_date: f.target_date || null }),
    onSuccess: (i) => { onDone(i); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const ready = f.title.trim() && f.severity_code && f.issue_type_code && f.raised_by_stakeholder_id;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('issues.raiseTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        {stakeholders.length === 0 && <Alert severity="info" sx={ERR_SX}>{t('issues.needStakeholder')}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="iss-new-title" label={t('issues.field.title')} required autoFocus value={f.title}
            onChange={set('title')} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <TextField id="iss-new-description" label={t('issues.field.description')} multiline minRows={3}
            value={f.description} onChange={set('description')} helperText={t('issues.problemNotPerson')} />
          <SimpleSelect id="iss-new-raiser" label={t('issues.field.raiser')} value={f.raised_by_stakeholder_id}
            onChange={(v) => setF({ ...f, raised_by_stakeholder_id: v })}
            options={stakeholders.map((s) => ({ value: s.stakeholder_id, label: s.stakeholder_name }))} />
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
            <SimpleSelect id="iss-new-severity" label={t('issues.field.severity')} value={f.severity_code}
              onChange={(v) => setF({ ...f, severity_code: v })}
              options={severityOptions().map((c) => ({ value: c.code, label: c.label }))} />
            <SimpleSelect id="iss-new-type" label={t('issues.field.type')} value={f.issue_type_code}
              onChange={(v) => setF({ ...f, issue_type_code: v })}
              options={typeOptions().map((c) => ({ value: c.code, label: c.label }))} />
            <TextField id="iss-new-raised" type="date" label={t('issues.field.raisedDate')} value={f.raised_date}
              onChange={set('raised_date')} helperText={t('issues.raisedDateHelp')} slotProps={{ inputLabel: { shrink: true } }} />
            <TextField id="iss-new-target" type="date" label={t('issues.field.targetDate')} value={f.target_date}
              onChange={set('target_date')} slotProps={{ inputLabel: { shrink: true } }} />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !ready}
          onClick={() => { setError(''); m.mutate(); }}>{t('issues.raise')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// The issue register (§4.5, slice 14): every issue of the project, filtered by status, severity, type and raiser.
export default function IssuesPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('ISSUE');
  const [tab, setTab] = useState('register');
  const [view, setView] = useState('open');
  const [filter, setFilter] = useState({ severity: '', issue_type: '', raiser: '', area: '' });
  const dash = useQuery({ queryKey: keys.issueDashboard(projectId), queryFn: () => issueApi.dashboard(projectId) });
  const areaOptions = [...(dash.data?.by_area ?? []).map((a) => ({ value: String(a.area_id), label: `${a.hier_code} ${a.name}` })),
    { value: 'none', label: t('issues.dash.noArea') }];
  const openFiltered = (f) => { setFilter({ severity: '', issue_type: '', raiser: '', area: '', ...f }); setView('open'); setTab('register'); };
  const [showRetired, setShowRetired] = useState(false);
  const params = { open_only: view === 'open', include_retired: showRetired,
    ...Object.fromEntries(Object.entries(filter).filter(([, v]) => v !== '')) };
  const q = useQuery({ queryKey: [...keys.issues(projectId), params], queryFn: () => issueApi.list(projectId, params),
    placeholderData: (prev) => prev });
  const stk = useQuery({ queryKey: keys.stakeholders(projectId), queryFn: () => stakeholderApi.list(projectId, true) });
  const { options: severityOptions, getLabel: severityLabel } = useCodes(projectId, 'ISSUE_SEVERITY');
  const { options: typeOptions, getLabel: typeLabel } = useCodes(projectId, 'ISSUE_TYPE');
  const { getLabel: statusLabel } = useCodes(projectId, 'ISSUE_STATUS');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const [fileError, setFileError] = useState('');
  const people = stk.data ?? [];
  const name = Object.fromEntries(people.map((s) => [s.stakeholder_id, s.stakeholder_name]));
  const rows = q.data ?? [];

  // Fits a 1280-px screen beside the rail (browser check 2026-10-20): the title and raiser flex, the rest are fixed.
  const columns = [
    { field: 'issue_number', headerName: t('issues.field.number'), width: 105,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.issue(projectId, row.issue_id)} tabIndex={tabIndex}
          underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code tone={row.is_active ? 'navy' : 'muted'}>{value}</Code></Link>) },
    { field: 'title', headerName: t('issues.field.title'), flex: 2, minWidth: 180,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary' }}>{value}</Box>
          {!row.is_active && <Tag tone="neutral">{t('settings.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'severity_code', headerName: t('issues.field.severity'), width: 105,
      renderCell: ({ value }) => <SeverityTag code={value} label={severityLabel(value)} /> },
    { field: 'issue_type_code', headerName: t('issues.field.type'), width: 110, valueGetter: (v) => typeLabel(v) },
    { field: 'status_code', headerName: t('issues.field.status'), width: 120,
      renderCell: ({ row }) => <IssueStatus issue={row} label={statusLabel(row.status_code)} size="sm" /> },
    { field: 'raised_by_stakeholder_id', headerName: t('issues.field.raiser'), flex: 1, minWidth: 120,
      valueGetter: (v) => name[v] ?? '' },
    { field: 'raised_date', headerName: t('issues.field.raisedDate'), width: 110 },
    { field: 'target_date', headerName: t('issues.field.targetDate'), width: 110 },
  ];

  return (
    <Page title={t('issues.title')} subtitle={t('issues.subtitle')}
      error={fileError || ((q.error || stk.error) && errorText(q.error || stk.error))}
      actions={(<>
        {isOn('ISSUE') && <ListImportActions projectId={projectId} target="issues" canEdit={canEdit}
          onNotice={setNotice} onError={setFileError} />}
        {canEdit && (
          <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('issues.raise')}</Button>)}
      </>)}>
      <Segmented label={t('issues.title')} value={tab} onChange={setTab} sx={{ mb: 2 }}
        options={[{ value: 'register', label: t('issues.tab.register') }, { value: 'dashboard', label: t('issues.tab.dashboard') }]} />
      {tab === 'dashboard' && <IssueDashboard projectId={projectId} onFilter={openFiltered} />}
      {tab === 'register' && <Card>
        <Toolbar>
          <Segmented size="sm" label={t('issues.field.status')} value={view} onChange={setView}
            options={[{ value: 'open', label: t('issues.view.open') }, { value: 'all', label: t('issues.view.all') }]} />
          <Box sx={{ width: 170 }}>
            <SimpleSelect id="iss-f-severity" label={t('issues.field.severity')} value={filter.severity} allowEmpty
              emptyLabel={t('issues.any')} onChange={(v) => setFilter({ ...filter, severity: v })}
              options={severityOptions().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ width: 170 }}>
            <SimpleSelect id="iss-f-type" label={t('issues.field.type')} value={filter.issue_type} allowEmpty
              emptyLabel={t('issues.any')} onChange={(v) => setFilter({ ...filter, issue_type: v })}
              options={typeOptions().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ width: 200 }}>
            <SimpleSelect id="iss-f-raiser" label={t('issues.field.raiser')} value={filter.raiser} allowEmpty
              emptyLabel={t('issues.any')} onChange={(v) => setFilter({ ...filter, raiser: v })}
              options={people.map((s) => ({ value: s.stakeholder_id, label: s.stakeholder_name }))} />
          </Box>
          <Box sx={{ width: 200 }}>
            <SimpleSelect id="iss-f-area" label={t('issues.field.area')} value={filter.area} allowEmpty
              emptyLabel={t('issues.any')} onChange={(v) => setFilter({ ...filter, area: v })} options={areaOptions} />
          </Box>
          <Box sx={{ flex: 1 }} />
          {!q.error && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('issues.count', { n: rows.length })}</Typography>}
          <ShowRetired id="iss-show-retired" checked={showRetired} onChange={setShowRetired} />
        </Toolbar>
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.issue_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.issue(projectId, row.issue_id))}
            localeText={{ noRowsLabel: t('issues.empty') }} sx={GRID_SX} />)}
      </Card>}
      {adding && <RaiseDialog projectId={projectId} stakeholders={people.filter((s) => s.is_active)}
        onClose={() => setAdding(false)}
        onDone={(i) => { qc.invalidateQueries({ queryKey: keys.issues(projectId) }); qc.invalidateQueries({ queryKey: keys.scopeSummary(projectId) });
          setNotice(t('issues.raised', { number: i.issue_number })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
