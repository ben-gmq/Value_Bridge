import { useEffect, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack, TextField,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { changeApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { GRID_SX, Toolbar } from '../frs/frKit';
import { StatusTag, changeLink, days, useTargets } from './changeKit';

const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };

// Raise a change request (§4.11 raise_change_request): the number, status and raiser are the server's (law 6). The
// target defaults to the agreed baseline and is fixed once raised.
function RaiseDialog({ projectId, targets, onClose, onDone }) {
  const origin = useCodes(projectId, 'CR_ORIGIN');
  const [f, setF] = useState({ title: '', rationale: '', origin_code: '', against_baseline_id: targets.preferred });
  const [error, setError] = useState('');
  useEffect(() => {
    if (f.against_baseline_id === '' && targets.preferred !== '') setF((cur) => ({ ...cur, against_baseline_id: targets.preferred }));
  }, [targets.preferred, f.against_baseline_id]);
  const set = (k, val) => setF((cur) => ({ ...cur, [k]: val }));
  const m = useMutation({
    mutationFn: () => changeApi.create(projectId, { ...f, title: f.title.trim(), rationale: f.rationale.trim() }),
    onSuccess: (r) => { onDone(r); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const ready = f.title.trim() && f.rationale.trim() && f.origin_code && f.against_baseline_id !== '';
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('changes.raiseTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        {!targets.loading && targets.options.length === 0 && <Alert severity="info" sx={ERR_SX}>{t('changes.noTarget')}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="cr-new-title" size="small" fullWidth required label={t('changes.field.title')} value={f.title}
            onChange={(e) => set('title', e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <TextField id="cr-new-rationale" size="small" fullWidth required multiline minRows={3}
            label={t('changes.field.rationale')} value={f.rationale} onChange={(e) => set('rationale', e.target.value)} />
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
            <SimpleSelect id="cr-new-origin" label={t('changes.field.origin_code')} value={f.origin_code}
              onChange={(v) => set('origin_code', v)}
              options={origin.options().map((c) => ({ value: c.code, label: c.label }))} />
            <SimpleSelect id="cr-new-target" label={t('changes.field.against')} value={f.against_baseline_id}
              onChange={(v) => set('against_baseline_id', v)} options={targets.options} />
          </Box>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('changes.targetHelp')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !ready}
          onClick={() => { setError(''); m.mutate(); }}>{t('changes.raise')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// CR-1: seeds of an undecided, rejected or retired change whose live row still differs from the target. The team
// undoes these edits; the app never does.
function UnagreedEdits({ projectId }) {
  const q = useQuery({ queryKey: keys.unagreedEdits(projectId), queryFn: () => changeApi.unagreed(projectId) });
  const rows = q.data ?? [];
  if (q.error) return <Alert severity="error" sx={{ mb: 2 }}>{errorText(q.error)}</Alert>;
  if (!rows.length) return null;
  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{t('changes.unagreedTitle', { n: rows.length })}</Typography>
      <Typography sx={{ fontSize: 12.5, mb: 0.5 }}>{t('changes.unagreedHelp')}</Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {rows.map((e) => (
          <li key={`${e.change_request_id}-${e.number}`}>
            <Typography sx={{ fontSize: 13 }}>
              {changeLink(projectId, e.change_request_id, e.cr_number)}{' '}
              {t(e.retired ? 'changes.unagreedLineRetired' : 'changes.unagreedLine',
                { status: e.status_code.toLowerCase(), number: e.number, label: e.against_label })}
            </Typography>
          </li>))}
      </Box>
    </Alert>
  );
}

// The change register (§4.11 cr_register): newest first, with the price and the decision read through its DEC.
export default function ChangesPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('CHANGE_REQUEST');
  const targets = useTargets(projectId);
  const sts = useCodes(projectId, 'CR_STATUS');
  const origin = useCodes(projectId, 'CR_ORIGIN');
  const [filter, setFilter] = useState({ status: '', origin: '', against: '' });
  const [showRetired, setShowRetired] = useState(false);
  const params = { include_retired: showRetired, ...Object.fromEntries(Object.entries(filter).filter(([, val]) => val !== '')) };
  const q = useQuery({ queryKey: [...keys.changes(projectId), params], queryFn: () => changeApi.list(projectId, params),
    placeholderData: (prev) => prev });
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const rows = q.data ?? [];

  const columns = [
    { field: 'cr_number', headerName: t('changes.field.number'), width: 105,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.change(projectId, row.change_request_id)} tabIndex={tabIndex}
          underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code tone={row.is_active ? 'navy' : 'muted'}>{value}</Code></Link>) },
    { field: 'title', headerName: t('changes.field.title'), flex: 2, minWidth: 180,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary' }}>{value}</Box>
          {!row.is_active && <Tag tone="neutral">{t('settings.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'status_code', headerName: t('changes.field.status_code'), width: 115,
      renderCell: ({ row }) => <StatusTag cr={row} getLabel={sts.getLabel} /> },
    { field: 'origin_code', headerName: t('changes.field.origin_code'), width: 110, valueGetter: (v) => origin.getLabel(v) },
    { field: 'against_label', headerName: t('changes.field.against'), width: 90 },
    { field: 'effort_delta_days', headerName: t('changes.field.delta'), width: 105, valueGetter: (v) => days(v) },
    { field: 'effort_exposed_days', headerName: t('changes.field.exposure'), width: 105,
      valueGetter: (v) => (v == null ? '–' : t('changes.days', { n: v })) },
    { field: 'decision_number', headerName: t('changes.field.decision'), width: 100,
      renderCell: ({ row, value }) => (value
        ? <Link component={RouterLink} to={links.decision(projectId, row.decision_id)} underline="hover"
          onClick={(e) => e.stopPropagation()}><Code>{value}</Code></Link> : '–') },
    { field: 'decided_by_name', headerName: t('changes.field.decided_by'), flex: 1, minWidth: 120,
      valueGetter: (v, row) => (v ? `${v} · ${row.decided_on}` : '') },
  ];

  return (
    <Page title={t('changes.title')} subtitle={t('changes.subtitle')} error={(q.error || targets.error) && errorText(q.error || targets.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('changes.raise')}</Button>)}>
      <UnagreedEdits projectId={projectId} />
      <Card>
        <Toolbar>
          <Box sx={{ width: 160 }}>
            <SimpleSelect id="cr-f-status" label={t('changes.field.status_code')} value={filter.status} allowEmpty
              emptyLabel={t('changes.any')} onChange={(val) => setFilter({ ...filter, status: val })}
              options={sts.options().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ width: 160 }}>
            <SimpleSelect id="cr-f-origin" label={t('changes.field.origin_code')} value={filter.origin} allowEmpty
              emptyLabel={t('changes.any')} onChange={(val) => setFilter({ ...filter, origin: val })}
              options={origin.options().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ width: 170 }}>
            <SimpleSelect id="cr-f-against" label={t('changes.field.against')} value={filter.against} allowEmpty
              emptyLabel={t('changes.any')} onChange={(val) => setFilter({ ...filter, against: val })}
              options={targets.options} />
          </Box>
          <Box sx={{ flex: 1 }} />
          {!q.error && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('changes.count', { n: rows.length })}</Typography>}
          <ShowRetired id="cr-show-retired" checked={showRetired} onChange={setShowRetired} />
        </Toolbar>
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.change_request_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.change(projectId, row.change_request_id))}
            localeText={{ noRowsLabel: t('changes.empty') }} sx={GRID_SX} />)}
      </Card>
      {adding && <RaiseDialog projectId={projectId} targets={targets} onClose={() => setAdding(false)}
        onDone={(r) => { qc.invalidateQueries({ queryKey: keys.changes(projectId) });
          setNotice(t('changes.raised', { number: r.cr_number }));
          navigate(links.change(projectId, r.change_request_id)); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
