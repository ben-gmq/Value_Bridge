import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, Snackbar, Stack } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { orgApi, stakeholderApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Code, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { RecordDialog, SettingsCrumbs, ShowRetired } from './settingsKit';

// Stakeholders (§4.5, D-4): the client's people who raise issues. No login. The org unit is optional (I-2) and a name
// is unique per unit (I-16). Writes need component ISSUE (I-9); a stakeholder named by a live issue cannot be retired.
export default function StakeholdersPage() {
  const { projectId } = useParams();
  const { isOn } = useComponents(projectId);
  const canEdit = useCanEdit() && isOn('ISSUE');
  const qc = useQueryClient();
  const [showRetired, setShowRetired] = useState(false);
  const listKey = [...keys.stakeholders(projectId), { retired: showRetired }];
  const q = useQuery({ queryKey: listKey, queryFn: () => stakeholderApi.list(projectId, showRetired) });
  const units = useQuery({ queryKey: keys.units(projectId), queryFn: () => orgApi.units(projectId) });
  const unitName = Object.fromEntries((units.data ?? []).map((u) => [u.org_unit_id, `${u.org_unit_code} ${u.org_unit_name}`]));
  const [editing, setEditing] = useState(null);           // { row } — row null to add
  const [confirm, setConfirm] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const refresh = () => qc.invalidateQueries({ queryKey: keys.stakeholders(projectId) });

  const retire = useMutation({
    mutationFn: (row) => stakeholderApi.retire(row.stakeholder_id, row.row_version),
    onSuccess: () => { refresh(); setConfirm(null); setNotice(t('issues.stakeholder.retired')); },
    onError: (err) => { setConfirm(null); refresh(); setError(errorText(err, t('settings.retireFailed'))); },
  });
  const restore = useMutation({
    mutationFn: (row) => stakeholderApi.restore(row.stakeholder_id),
    onSuccess: () => { refresh(); setNotice(t('issues.stakeholder.restored')); },
    onError: (err) => { refresh(); setError(errorText(err, t('settings.restoreFailed'))); },
  });

  const rows = (q.data ?? []).filter((r) => showRetired || r.is_active);
  const liveUnits = (units.data ?? []).filter((u) => u.is_active);
  const fields = [
    { name: 'stakeholder_name', label: t('issues.stakeholder.name'), required: true },
    { name: 'job_title', label: t('issues.stakeholder.jobTitle') },
    { name: 'org_unit_id', label: t('issues.stakeholder.orgUnit'), type: 'select', emptyLabel: t('issues.stakeholder.noUnit'),
      options: liveUnits.map((u) => ({ value: u.org_unit_id, label: `${u.org_unit_code} ${u.org_unit_name}` })) },
    { name: 'bpo', label: t('issues.stakeholder.side'), type: 'select', required: true,
      options: [{ value: 'N', label: t('issues.stakeholder.client') }, { value: 'Y', label: t('issues.stakeholder.bpo') }] },
  ];
  const asBody = ({ bpo, ...body }) => ({ ...body, is_bpo: bpo === 'Y' });
  const submit = (body, rowVersion) => (editing.row
    ? stakeholderApi.update(editing.row.stakeholder_id, { ...asBody(body), row_version: rowVersion })
    : stakeholderApi.create(projectId, asBody(body)));
  const reload = async () => {
    const fresh = await qc.fetchQuery({ queryKey: listKey, queryFn: () => stakeholderApi.list(projectId, showRetired) });
    return fresh.find((r) => r.stakeholder_id === editing.row.stakeholder_id && r.is_active) ?? null;
  };

  const columns = [
    { field: 'stakeholder_name', headerName: t('issues.stakeholder.name'), flex: 1, minWidth: 180,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'text.primary' : 'text.disabled' }}>{row.stakeholder_name}</Box>
          {!row.is_active && <Tag tone="neutral">{t('settings.retiredChip')}</Tag>}
        </Stack>) },
    { field: 'job_title', headerName: t('issues.stakeholder.jobTitle'), flex: 1, minWidth: 160 },
    { field: 'org_unit_id', headerName: t('issues.stakeholder.orgUnit'), flex: 1, minWidth: 180,
      renderCell: ({ value }) => (value ? <Code sx={{ fontSize: 12.5 }}>{unitName[value] ?? value}</Code>
        : <Box component="span" sx={{ color: 'text.secondary' }}>{t('issues.stakeholder.noUnit')}</Box>) },
    { field: 'is_bpo', headerName: t('issues.stakeholder.side'), width: 130,
      valueGetter: (v) => (v ? t('issues.stakeholder.bpo') : t('issues.stakeholder.client')) },
    { field: 'actions', headerName: '', width: 180, sortable: false, filterable: false,
      renderCell: ({ row }) => canEdit && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          {row.is_active ? (
            <>
              <Button size="small" onClick={() => { setError(''); setEditing({ row }); }}>{t('settings.edit')}</Button>
              <Button size="small" color="warning" onClick={() => { setError(''); setConfirm(row); }}>{t('settings.retire')}</Button>
            </>
          ) : (
            <Button size="small" disabled={restore.isPending} onClick={() => { setError(''); restore.mutate(row); }}>
              {t('settings.restore')}</Button>
          )}
        </Stack>) },
  ];

  return (
    <Box>
      <SettingsCrumbs projectId={projectId} current={t('settings.stakeholders')} />
      <Page title={t('settings.stakeholders')} subtitle={t('settings.stakeholdersWhat')}
        error={error || (q.error && errorText(q.error))}
        actions={canEdit && <Button variant="contained" onClick={() => { setError(''); setEditing({ row: null }); }}>
          {t('issues.stakeholder.add')}</Button>}>
        <Card title={t('issues.stakeholder.count', { n: rows.length })} bodySx={{ px: 0, pb: 0 }}
          action={<ShowRetired id="stakeholders-show-retired" checked={showRetired} onChange={setShowRetired} />}>
          <DataGrid autoHeight rows={rows} getRowId={(r) => r.stakeholder_id} columns={columns}
            loading={q.isLoading} disableRowSelectionOnClick hideFooterSelectedRowCount
            localeText={{ noRowsLabel: t('issues.stakeholder.none') }}
            sx={{ bgcolor: 'background.paper', border: 0, borderRadius: 0 }} />
        </Card>
      </Page>
      {editing && (
        <RecordDialog open title={editing.row ? t('issues.stakeholder.editTitle') : t('issues.stakeholder.addTitle')}
          fields={fields} row={editing.row && { ...editing.row, bpo: editing.row.is_bpo ? 'Y' : 'N' }}
          initial={{ bpo: 'N' }} onSubmit={submit} onReload={reload} onClose={() => setEditing(null)}
          onDone={() => { refresh(); setNotice(t(editing.row ? 'settings.saved' : 'issues.stakeholder.created')); }} />
      )}
      <ConfirmDialog open={Boolean(confirm)} title={t('issues.stakeholder.retireTitle')}
        body={t('issues.stakeholder.retireBody', { name: confirm?.stakeholder_name ?? '' })}
        confirmLabel={t('settings.retire')} busy={retire.isPending}
        onClose={() => setConfirm(null)} onConfirm={() => retire.mutate(confirm)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
