import { useMemo, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Link, Tooltip, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { appApi, ifaceApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';
import { Mono, SimpleSelect } from '../processes/chartKit';

// The generated interface list (D-27): one row per interface-behaviour FR, never typed. Incomplete
// interfaces are marked with what they lack (criterion 103, S6b2-1); a pair filter says how many
// interfaces it cannot match because they have no endpoints yet (S6b2-2).
export default function InterfacesPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [status, setStatus] = useState('');
  const params = Object.fromEntries(Object.entries({ source, target, status }).filter(([, v]) => v !== ''));
  const q = useQuery({ queryKey: [...keys.interfaces(projectId), params], queryFn: () => ifaceApi.list(projectId, params),
    placeholderData: (prev) => prev });
  const appsQ = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId) });
  const { codes: statuses } = useCodes(projectId, 'FR_FULFILMENT_STATUS');
  const apps = useMemo(() => (appsQ.data ?? []).map((a) => ({ value: a.application_id, label: `${a.application_code} ${a.application_name}` })),
    [appsQ.data]);
  const rows = q.data?.rows ?? [];
  const hidden = q.data?.unfilterable_incomplete ?? 0;
  const missingText = (m) => m.map((x) => t(`interfaces.missing.${x}`)).join(', ');

  const columns = [
    { field: 'interface_number', headerName: t('interfaces.number'), width: 110,
      renderCell: ({ row, value }) => (
        <Link component={RouterLink} to={links.fr(projectId, row.fr_id)} underline="hover" onClick={(e) => e.stopPropagation()}>
          <Mono>{value}</Mono></Link>) },
    { field: 'interface_name', headerName: t('interfaces.name'), flex: 1, minWidth: 200 },
    { field: 'is_complete', headerName: '', width: 120, sortable: false,
      renderCell: ({ row }) => (row.is_complete ? <Chip size="small" label={t('interfaces.completeChip')} /> : (
        <Tooltip title={t('interfaces.missingTip', { items: missingText(row.missing) })}>
          <Chip size="small" variant="outlined" label={t('interfaces.incompleteChip')}
            sx={{ color: 'status.caution', borderColor: 'status.caution' }} />
        </Tooltip>)) },
    { field: 'route', headerName: t('interfaces.route'), width: 220,
      valueGetter: (_, row) => (row.is_described ? `${row.source_application_code} → ${row.target_application_code}` : '') },
    { field: 'pattern_label', headerName: t('interfaces.pattern'), width: 120 },
    { field: 'method_label', headerName: t('interfaces.method'), width: 110 },
    { field: 'frequency_label', headerName: t('interfaces.frequency'), width: 130 },
    { field: 'carried', headerName: t('interfaces.carried'), flex: 1, minWidth: 220, sortable: false,
      valueGetter: (v) => (v ?? []).map((c) => (c.note ? `${c.de_number} (${c.note})` : c.de_number)).join(', ') },
    { field: 'solution_number', headerName: t('interfaces.solution'), width: 110 },
    { field: 'br_numbers', headerName: t('interfaces.brs'), width: 160, valueGetter: (v) => (v ?? []).join(', ') },
    { field: 'fulfilment_status_label', headerName: t('interfaces.status'), width: 140 },
  ];

  return (
    <Page title={t('interfaces.title')} subtitle={t('interfaces.subtitle')} error={q.error && errorText(q.error)}>
      <WrapperBox>
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('interfaces.count', { n: rows.length })}</Typography>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ width: 220 }}><SimpleSelect id="if-source" label={t('interfaces.filterSource')} value={source} allowEmpty
          emptyLabel={t('interfaces.filterAny')} onChange={setSource} options={apps} /></Box>
        <Box sx={{ width: 220 }}><SimpleSelect id="if-target" label={t('interfaces.filterTarget')} value={target} allowEmpty
          emptyLabel={t('interfaces.filterAny')} onChange={setTarget} options={apps} /></Box>
        <Box sx={{ width: 180 }}><SimpleSelect id="if-status" label={t('interfaces.filterStatus')} value={status} allowEmpty
          emptyLabel={t('interfaces.filterAny')} onChange={setStatus} options={statuses.map((c) => ({ value: c.code, label: c.label }))} /></Box>
      </WrapperBox>
      {hidden > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }} action={(
          <Button size="small" onClick={() => { setSource(''); setTarget(''); }}>{t('interfaces.showUnfilterable')}</Button>)}>
          {t('interfaces.unfilterable', { n: hidden })}</Alert>)}
      {!q.error && (
        <DataGrid autoHeight rows={rows} getRowId={(r) => r.fr_id} columns={columns} loading={q.isLoading}
          disableRowSelectionOnClick hideFooterSelectedRowCount onRowClick={({ row }) => navigate(links.fr(projectId, row.fr_id))}
          localeText={{ noRowsLabel: t('interfaces.empty') }}
          sx={{ bgcolor: 'background.paper', borderRadius: 3, '& .MuiDataGrid-row': { cursor: 'pointer' } }} />)}
    </Page>
  );
}
