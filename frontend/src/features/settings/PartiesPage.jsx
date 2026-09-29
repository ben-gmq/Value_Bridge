import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, Chip, Snackbar, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { errorText } from '../../api/client';
import { partyApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';
import { RecordDialog, SettingsCrumbs, ShowRetired } from './settingsKit';

// External parties (D-24a): customers, banks, regulators… that exchange data with a process.
// The EXT number is minted by the server; a DELETE is a soft retire, refused while a flow uses it.
export default function PartiesPage() {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const [showRetired, setShowRetired] = useState(false);
  // include_retired is requested for "Show retired"; see the hand-back note on api/scope.js.
  const listKey = [...keys.parties(projectId), { retired: showRetired }];
  const q = useQuery({ queryKey: listKey, queryFn: () => partyApi.list(projectId, showRetired) });
  const { codes: kinds, getLabel } = useCodes(projectId, 'EXTERNAL_ENTITY_KIND');
  const [editing, setEditing] = useState(null);           // { row } — row null to add
  const [confirm, setConfirm] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const refresh = () => qc.invalidateQueries({ queryKey: keys.parties(projectId) });

  const retire = useMutation({
    mutationFn: (row) => partyApi.retire(row.external_entity_id, row.row_version),
    onSuccess: () => { refresh(); setConfirm(null); setNotice(t('settings.party.retired')); },
    onError: (err) => { setConfirm(null); refresh(); setError(errorText(err, t('settings.retireFailed'))); },
  });
  const restore = useMutation({
    mutationFn: (row) => partyApi.restore(row.external_entity_id),
    onSuccess: () => { refresh(); setNotice(t('settings.party.restored')); },
    onError: (err) => setError(errorText(err, t('settings.restoreFailed'))),
  });

  const rows = (q.data ?? []).filter((r) => showRetired || r.is_active);
  const fields = [
    { name: 'ext_name', label: t('settings.party.name'), required: true },
    { name: 'kind_code', label: t('settings.party.kind'), type: 'select', emptyLabel: t('settings.party.noKind'),
      options: kinds.map((c) => ({ value: c.code, label: c.label })) },
    { name: 'description', label: t('settings.description'), multiline: true },
  ];
  const submit = (body, rowVersion) => (editing.row
    ? partyApi.update(editing.row.external_entity_id, { ...body, row_version: rowVersion })
    : partyApi.create(projectId, body));
  const reload = async () => {
    const fresh = await qc.fetchQuery({ queryKey: listKey, queryFn: () => partyApi.list(projectId, showRetired) });
    return fresh.find((r) => r.external_entity_id === editing.row.external_entity_id && r.is_active) ?? null;
  };

  const columns = [
    { field: 'ext_number', headerName: t('settings.party.number'), width: 120 },
    { field: 'ext_name', headerName: t('settings.party.name'), flex: 1, minWidth: 180,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'text.primary' : 'text.disabled' }}>{row.ext_name}</Box>
          {!row.is_active && <Chip size="small" variant="outlined" label={t('settings.retiredChip')} />}
        </Stack>) },
    { field: 'kind_code', headerName: t('settings.party.kind'), width: 160,
      valueGetter: (v) => (v ? getLabel(v) : '') },
    { field: 'description', headerName: t('settings.description'), flex: 2, minWidth: 220 },
    { field: 'actions', headerName: '', width: 180, sortable: false, filterable: false,
      renderCell: ({ row }) => (
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
      <SettingsCrumbs projectId={projectId} current={t('settings.parties')} />
      <Page title={t('settings.parties')} subtitle={t('settings.partiesWhat')}
        error={error || (q.error && errorText(q.error))}
        actions={<Button variant="contained" onClick={() => { setError(''); setEditing({ row: null }); }}>
          {t('settings.party.add')}</Button>}>
        <WrapperBox>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('settings.party.count', { n: rows.length })}</Typography>
          <ShowRetired id="parties-show-retired" checked={showRetired} onChange={setShowRetired} />
        </WrapperBox>
        <DataGrid autoHeight rows={rows} getRowId={(r) => r.external_entity_id} columns={columns}
          loading={q.isLoading} disableRowSelectionOnClick hideFooterSelectedRowCount
          localeText={{ noRowsLabel: t('settings.party.none') }}
          sx={{ bgcolor: 'background.paper', borderRadius: 3 }} />
      </Page>
      {editing && (
        <RecordDialog open title={editing.row ? t('settings.party.editTitle', { number: editing.row.ext_number })
          : t('settings.party.addTitle')}
          fields={fields} row={editing.row} onSubmit={submit} onReload={reload} onClose={() => setEditing(null)}
          onDone={(saved) => { refresh(); setNotice(t(editing.row ? 'settings.saved' : 'settings.party.created',
            { number: saved?.ext_number })); }} />
      )}
      <ConfirmDialog open={Boolean(confirm)} title={t('settings.party.retireTitle')}
        body={t('settings.party.retireBody', { name: confirm ? `${confirm.ext_number} ${confirm.ext_name}` : '' })}
        confirmLabel={t('settings.retire')} busy={retire.isPending}
        onClose={() => setConfirm(null)} onConfirm={() => retire.mutate(confirm)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
