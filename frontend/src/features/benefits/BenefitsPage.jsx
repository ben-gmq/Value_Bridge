import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { benefitApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { GRID_SX, Toolbar } from '../frs/frKit';
import { BenefitFields, BenefitTabs, useBenefitRefs } from './benefitKit';

const EMPTY = { benefit_name: '', description: '', benefit_type_code: '', measure_name: '', measure_unit: '',
  baseline_value: '', target_value: '', realisation_date: '', accountable_org_role_id: '' };

// New benefit (spec §3 create_benefit): the number and the FORECAST status come from the server at save (law 6).
function NewDialog({ projectId, refs, onClose, onDone }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const set = (k, val) => setF((cur) => ({ ...cur, [k]: val }));
  const m = useMutation({
    mutationFn: () => benefitApi.create(projectId, Object.fromEntries(Object.entries(f).map(([k, val]) => [k,
      typeof val === 'string' ? (val.trim() || null) : val]))),
    onSuccess: (b) => { onDone(b); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const ready = f.benefit_name.trim() && f.benefit_type_code && f.measure_name.trim() && f.measure_unit.trim()
    && f.baseline_value !== '' && f.target_value !== '' && f.accountable_org_role_id;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('benefits.addTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <BenefitFields projectId={projectId} refs={refs} v={f} set={set} idPrefix="ben-new" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !ready}
          onClick={() => { setError(''); m.mutate(); }}>{t('benefits.add')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// The benefit register (spec §9): number order; filters status and unit; retired on request.
export default function BenefitsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('BENEFIT');
  const refs = useBenefitRefs(projectId);
  const [filter, setFilter] = useState({ status: '', unit: '' });
  const [showRetired, setShowRetired] = useState(false);
  const params = { include_retired: showRetired, ...Object.fromEntries(Object.entries(filter).filter(([, val]) => val !== '')) };
  const q = useQuery({ queryKey: [...keys.benefits(projectId), params], queryFn: () => benefitApi.list(projectId, params),
    placeholderData: (prev) => prev });
  const sts = useCodes(projectId, 'BENEFIT_STATUS');
  const typ = useCodes(projectId, 'BENEFIT_TYPE');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const rows = q.data ?? [];

  const columns = [
    { field: 'benefit_number', headerName: t('benefits.field.number'), width: 105,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.benefit(projectId, row.benefit_id)} tabIndex={tabIndex}
          underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code tone={row.is_active ? 'navy' : 'muted'}>{value}</Code></Link>) },
    { field: 'benefit_name', headerName: t('benefits.field.benefit_name'), flex: 2, minWidth: 180,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary' }}>{value}</Box>
          {!row.is_active && <Tag tone="neutral">{t('settings.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'benefit_type_code', headerName: t('benefits.field.benefit_type_code'), width: 130, valueGetter: (v) => typ.getLabel(v) },
    { field: 'measure_unit', headerName: t('benefits.field.measure_unit'), width: 90 },
    { field: 'change', headerName: t('benefits.field.change'), width: 150,
      valueGetter: (_, row) => `${row.baseline_value} → ${row.target_value}` },
    { field: 'accountable_org_role_id', headerName: t('benefits.field.accountable_org_role_id'), flex: 1, minWidth: 130,
      valueGetter: (v) => refs.roleName(v) },
    { field: 'status_code', headerName: t('benefits.field.status_code'), width: 120, valueGetter: (v) => sts.getLabel(v) },
    { field: 'realisation_date', headerName: t('benefits.field.realisation_date'), width: 120 },
    { field: 'link_total_pct', headerName: t('benefits.field.linked'), width: 90,
      renderCell: ({ value }) => `${value} %` },
  ];

  return (
    <Page title={t('benefits.title')} subtitle={t('benefits.subtitle')} error={(q.error || refs.error) && errorText(q.error || refs.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('benefits.add')}</Button>)}>
      <BenefitTabs projectId={projectId} value="register" />
      <Card>
        <Toolbar>
          <Box sx={{ width: 170 }}>
            <SimpleSelect id="ben-f-status" label={t('benefits.field.status_code')} value={filter.status} allowEmpty
              emptyLabel={t('benefits.any')} onChange={(val) => setFilter({ ...filter, status: val })}
              options={sts.options().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ width: 170 }}>
            <SimpleSelect id="ben-f-unit" label={t('benefits.field.measure_unit')} value={filter.unit} allowEmpty
              emptyLabel={t('benefits.any')} onChange={(val) => setFilter({ ...filter, unit: val })}
              options={refs.units.map((u) => ({ value: u, label: u }))} />
          </Box>
          <Box sx={{ flex: 1 }} />
          {!q.error && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('benefits.count', { n: rows.length })}</Typography>}
          <ShowRetired id="ben-show-retired" checked={showRetired} onChange={setShowRetired} />
        </Toolbar>
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.benefit_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.benefit(projectId, row.benefit_id))}
            localeText={{ noRowsLabel: t('benefits.empty') }} sx={GRID_SX} />)}
      </Card>
      {adding && <NewDialog projectId={projectId} refs={refs} onClose={() => setAdding(false)}
        onDone={(b) => { qc.invalidateQueries({ queryKey: keys.benefits(projectId) });
          qc.invalidateQueries({ queryKey: ['control', String(projectId)] });
          setNotice(t('benefits.created', { number: b.benefit_number })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
