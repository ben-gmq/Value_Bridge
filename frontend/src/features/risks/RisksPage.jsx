import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Link, Snackbar, Stack,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { riskApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired, SimpleSelect } from '../processes/chartKit';
import { GRID_SX, Toolbar } from '../frs/frKit';
import { ExposureTag, RiskFields, useRiskRefs } from './riskKit';

const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };
const EMPTY = { title: '', description: '', probability_code: '', impact_code: '', owner_org_role_id: '',
  raised_date: '', target_date: '', phase_id: '', solution_id: '', bfc_node_id: '', mitigation: '' };
const DAY = 86400000;

// Raise a risk (§4.10 raise_risk): the number and the score come from the server at save (law 6).
function RaiseDialog({ projectId, refs, onClose, onDone }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const set = (k, val) => setF((cur) => ({ ...cur, [k]: val }));
  const m = useMutation({
    mutationFn: () => riskApi.create(projectId, Object.fromEntries(Object.entries(f).map(([k, val]) => [k,
      typeof val === 'string' ? (val.trim() || null) : val]))),
    onSuccess: (r) => { onDone(r); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const ready = f.title.trim() && f.probability_code && f.impact_code && f.owner_org_role_id;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('risks.raiseTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <RiskFields projectId={projectId} refs={refs} v={f} set={set} idPrefix="rsk-new" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !ready}
          onClick={() => { setError(''); m.mutate(); }}>{t('risks.raise')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// The risk register (§4.10 risk_register): open first, highest exposure, oldest raised.
export default function RisksPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('RISK');
  const refs = useRiskRefs(projectId);
  const [filter, setFilter] = useState({ status: '', owner_org_role_id: '', phase_id: '' });
  const [showRetired, setShowRetired] = useState(false);
  const params = { include_retired: showRetired, ...Object.fromEntries(Object.entries(filter).filter(([, val]) => val !== '')) };
  const q = useQuery({ queryKey: [...keys.risks(projectId), params], queryFn: () => riskApi.list(projectId, params),
    placeholderData: (prev) => prev });
  const sts = useCodes(projectId, 'RISK_STATUS');
  const prob = useCodes(projectId, 'RISK_PROBABILITY');
  const imp = useCodes(projectId, 'RISK_IMPACT');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const rows = q.data ?? [];
  const today = new Date(new Date().toDateString()).getTime();
  const age = (row) => (row.status_behaviour === 'OPEN'
    ? Math.max(0, Math.round((today - new Date(`${row.raised_date}T00:00:00`).getTime()) / DAY)) : null);

  const columns = [
    { field: 'risk_number', headerName: t('risks.field.number'), width: 105,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.risk(projectId, row.risk_id)} tabIndex={tabIndex}
          underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code tone={row.is_active ? 'navy' : 'muted'}>{value}</Code></Link>) },
    { field: 'title', headerName: t('risks.field.title'), flex: 2, minWidth: 180,
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'inherit' : 'text.secondary' }}>{value}</Box>
          {!row.is_active && <Tag tone="neutral">{t('settings.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'exposure_score', headerName: t('risks.field.exposure'), width: 95,
      renderCell: ({ row }) => <ExposureTag score={row.exposure_score} rule={refs.rule}
        open={row.is_active && row.status_behaviour === 'OPEN'} /> },
    { field: 'probability_code', headerName: t('risks.field.probability_code'), width: 115, valueGetter: (v) => prob.getLabel(v) },
    { field: 'impact_code', headerName: t('risks.field.impact_code'), width: 105, valueGetter: (v) => imp.getLabel(v) },
    { field: 'owner_org_role_id', headerName: t('risks.field.owner_org_role_id'), flex: 1, minWidth: 130,
      valueGetter: (v) => refs.roleName(v) },
    { field: 'status_code', headerName: t('risks.field.status_code'), width: 120, valueGetter: (v) => sts.getLabel(v) },
    ...(refs.waveOn ? [{ field: 'phase_id', headerName: t('risks.field.phase_id'), width: 110,
      valueGetter: (v) => (v ? refs.waveName(v) : '') }] : []),
    { field: 'age', headerName: t('risks.field.age'), width: 80, valueGetter: (_, row) => age(row),
      renderCell: ({ value }) => (value == null ? '–' : t('risks.days', { n: value })) },
    { field: 'target_date', headerName: t('risks.field.target_date'), width: 110 },
  ];

  return (
    <Page title={t('risks.title')} subtitle={t('risks.subtitle')} error={(q.error || refs.error) && errorText(q.error || refs.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => setAdding(true)}>{t('risks.raise')}</Button>)}>
      <Card>
        <Toolbar>
          <Box sx={{ width: 170 }}>
            <SimpleSelect id="rsk-f-status" label={t('risks.field.status_code')} value={filter.status} allowEmpty
              emptyLabel={t('risks.any')} onChange={(val) => setFilter({ ...filter, status: val })}
              options={sts.options().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ width: 220 }}>
            <SimpleSelect id="rsk-f-owner" label={t('risks.field.owner_org_role_id')} value={filter.owner_org_role_id}
              allowEmpty emptyLabel={t('risks.any')} onChange={(val) => setFilter({ ...filter, owner_org_role_id: val })}
              options={refs.roleOptions()} />
          </Box>
          {refs.waveOn && <Box sx={{ width: 200 }}>
            <SimpleSelect id="rsk-f-wave" label={t('risks.field.phase_id')} value={filter.phase_id} allowEmpty
              emptyLabel={t('risks.any')} onChange={(val) => setFilter({ ...filter, phase_id: val })}
              options={refs.waveOptions()} />
          </Box>}
          <Box sx={{ flex: 1 }} />
          {!q.error && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('risks.count', { n: rows.length })}</Typography>}
          <ShowRetired id="rsk-show-retired" checked={showRetired} onChange={setShowRetired} />
        </Toolbar>
        {refs.rule && !refs.rule.is_enabled && (
          <Typography sx={{ px: 2, pb: 1, fontSize: 12.5, color: 'text.secondary' }}>{t('risks.ruleOff')}</Typography>)}
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.risk_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.risk(projectId, row.risk_id))}
            localeText={{ noRowsLabel: t('risks.empty') }} sx={GRID_SX} />)}
      </Card>
      {adding && <RaiseDialog projectId={projectId} refs={refs} onClose={() => setAdding(false)}
        onDone={(r) => { qc.invalidateQueries({ queryKey: keys.risks(projectId) });
          qc.invalidateQueries({ queryKey: ['control', String(projectId)] });
          setNotice(t('risks.raised', { number: r.risk_number })); }} />}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
