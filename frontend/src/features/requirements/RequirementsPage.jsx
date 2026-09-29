import { useMemo, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Chip, Link, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { bfcApi, brApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';
import { Mono, ShowRetired } from '../processes/chartKit';

// Business requirements (§7.3). There is no "add requirement": a BR appears with its process
// step (D-2), so the empty state points at the chart.
function EmptyState({ projectId }) {
  return (
    <Stack sx={{ height: '100%', alignItems: 'center', justifyContent: 'center', p: 3, textAlign: 'center' }} spacing={1}>
      <Typography sx={{ color: 'text.secondary' }}>{t('requirements.empty')}</Typography>
      <Link component={RouterLink} to={links.processes(projectId)}>{t('requirements.goProcesses')}</Link>
    </Stack>
  );
}

export default function RequirementsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [showRetired, setShowRetired] = useState(false);
  const brsQ = useQuery({ queryKey: [...keys.brs(projectId), { retired: showRetired }],
    queryFn: () => brApi.list(projectId, showRetired) });
  // Retired nodes too, so a retired requirement still shows where it sat.
  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: true }], queryFn: () => bfcApi.tree(projectId, true) });
  const { getLabel } = useCodes(projectId, 'BR_STATUS');
  const nodeById = useMemo(() => new Map((treeQ.data ?? []).map((n) => [n.bfc_node_id, n])), [treeQ.data]);
  const rows = brsQ.data ?? [];

  const columns = [
    { field: 'br_number', headerName: t('requirements.number'), width: 150,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Link component={RouterLink} to={links.requirement(projectId, row.br_id)} underline="hover"
            onClick={(e) => e.stopPropagation()} sx={{ color: row.is_active ? undefined : 'text.disabled' }}>
            <Mono>{row.br_number}</Mono></Link>
          {!row.is_active && <Chip size="small" variant="outlined" label={t('processes.retiredChip')} />}
        </Stack>) },
    { field: 'hier_code', headerName: t('requirements.code'), width: 140,
      valueGetter: (_, row) => nodeById.get(row.bfc_node_id)?.hier_code ?? '',
      renderCell: ({ value }) => <Mono>{value}</Mono> },
    { field: 'node_name', headerName: t('requirements.function'), flex: 1, minWidth: 180,
      valueGetter: (_, row) => nodeById.get(row.bfc_node_id)?.node_name ?? '' },
    { field: 'br_statement', headerName: t('requirements.statement'), flex: 2, minWidth: 240,
      valueGetter: (v) => (v ?? '').split('\n')[0] },
    { field: 'status_code', headerName: t('requirements.status'), width: 140,
      renderCell: ({ value }) => <Chip size="small" label={getLabel(value)} /> },
  ];

  return (
    <Page title={t('requirements.title')} subtitle={t('requirements.subtitle')}
      error={(brsQ.error && errorText(brsQ.error)) || (treeQ.error && errorText(treeQ.error))}>
      <WrapperBox>
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('requirements.count', { n: rows.length })}</Typography>
        <Box sx={{ flex: 1 }} />
        <ShowRetired id="br-show-retired" checked={showRetired} onChange={setShowRetired} />
      </WrapperBox>
      <DataGrid autoHeight rows={rows} getRowId={(r) => r.br_id} columns={columns} loading={brsQ.isLoading}
        disableRowSelectionOnClick hideFooterSelectedRowCount
        onRowClick={({ row }) => navigate(links.requirement(projectId, row.br_id))}
        slots={{ noRowsOverlay: () => <EmptyState projectId={projectId} /> }}
        initialState={{ sorting: { sortModel: [{ field: 'br_number', sort: 'asc' }] } }}
        sx={{ bgcolor: 'background.paper', borderRadius: 3, '& .MuiDataGrid-row': { cursor: 'pointer' },
          '--DataGrid-overlayHeight': '160px' }} />
    </Page>
  );
}
