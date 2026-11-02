import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, FormControlLabel, Link, Stack, Switch, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { decisionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';
import { GRID_SX, Toolbar } from '../frs/frKit';

// The decision log (§4.11 decision_log): newest decided-on first; a corrected decision stays, tagged (A-41).
export default function DecisionsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const canEdit = useCanEdit();
  const dim = useCodes(projectId, 'PM_DIMENSION');
  const [dimension, setDimension] = useState('');
  const [showSuperseded, setShowSuperseded] = useState(true);
  const params = { include_superseded: showSuperseded, ...(dimension ? { dimension } : {}) };
  const q = useQuery({ queryKey: [...keys.decisions(projectId), params],
    queryFn: () => decisionApi.list(projectId, params), placeholderData: (prev) => prev });
  const rows = q.data ?? [];

  const columns = [
    { field: 'decision_number', headerName: t('decisions.field.number'), width: 105,
      renderCell: ({ row, value, tabIndex }) => (
        <Link component={RouterLink} to={links.decision(projectId, row.decision_id)} tabIndex={tabIndex}
          underline="hover" onClick={(e) => e.stopPropagation()}>
          <Code tone={row.superseded_by_id ? 'muted' : 'navy'}>{value}</Code></Link>) },
    { field: 'decided_on', headerName: t('decisions.field.decided_on'), width: 115 },
    { field: 'title', headerName: t('decisions.field.title'), flex: 3, minWidth: 320,      // room for the tag (UAT)
      renderCell: ({ row, value }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.superseded_by_id ? 'text.secondary' : 'inherit' }}>{value}</Box>
          {row.superseded_by_number && (
            <Tag tone="neutral">{t('decisions.supersededBy', { number: row.superseded_by_number })}</Tag>)}
        </Stack>) },
    { field: 'dimension_code', headerName: t('decisions.field.dimension_code'), width: 150,
      valueGetter: (v) => dim.getLabel(v) },
    { field: 'analysis_code', headerName: t('decisions.field.analysis_code'), flex: 1, minWidth: 160,
      valueGetter: (v) => (v ? t(`control.analysis.${v}`) : '') },
    { field: 'decided_by_name', headerName: t('decisions.field.decided_by'), width: 160 },
  ];

  return (
    <Page title={t('decisions.title')} subtitle={t('decisions.subtitle')} error={q.error && errorText(q.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<AddRounded />} onClick={() => navigate(links.decisionNew(projectId))}>
          {t('decisions.record')}</Button>)}>
      <Card>
        <Toolbar>
          <Box sx={{ width: 220 }}>
            <SimpleSelect id="dec-f-dimension" label={t('decisions.field.dimension_code')} value={dimension} allowEmpty
              emptyLabel={t('decisions.any')} onChange={setDimension}
              options={dim.options().map((c) => ({ value: c.code, label: c.label }))} />
          </Box>
          <Box sx={{ flex: 1 }} />
          {!q.error && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
            {t('decisions.count', { n: rows.length })}</Typography>}
          <FormControlLabel control={<Switch id="dec-show-superseded" size="small" checked={showSuperseded}
            onChange={(e) => setShowSuperseded(e.target.checked)} />} label={t('decisions.showSuperseded')} />
        </Toolbar>
        {!q.error && (
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.decision_id} columns={columns} loading={q.isLoading}
            disableRowSelectionOnClick hideFooterSelectedRowCount
            onRowClick={({ row }) => navigate(links.decision(projectId, row.decision_id))}
            localeText={{ noRowsLabel: t('decisions.empty') }} sx={GRID_SX} />)}
      </Card>
    </Page>
  );
}
