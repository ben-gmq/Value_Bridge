import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, Card, CardContent, Chip, Grid, Snackbar, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { RichTreeView } from '@mui/x-tree-view/RichTreeView';
import { errorText } from '../../api/client';
import { orgApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Page, WrapperBox } from '../../components/Page';
import { t } from '../../i18n/t';
import { RecordDialog, SettingsCrumbs, ShowRetired } from './settingsKit';

// Client organisation (§5.3 ORG_UNIT / ORG_ROLE, S1-7): a unit tree fixed at three levels and
// the roles in each unit. These roles are the R/A/C/I holders on the chart and requirement screens.
const MAX_LEVEL = 3;

// Build the tree from parent_org_unit_id. A unit whose parent is not in the list (a retired
// parent while retired rows are hidden) is shown at the top rather than lost.
function buildTree(units) {
  const byId = new Map(units.map((u) => [u.org_unit_id, { ...u, children: [] }]));
  const roots = [];
  for (const u of byId.values()) {
    const parent = u.parent_org_unit_id != null ? byId.get(u.parent_org_unit_id) : null;
    (parent ? parent.children : roots).push(u);
  }
  const sort = (list) => { list.sort((a, b) => a.seq_no - b.seq_no); list.forEach((n) => sort(n.children)); return list; };
  return sort(roots);
}

export default function OrganisationPage() {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const [showRetired, setShowRetired] = useState(false);
  // include_retired is requested for "Show retired"; see the hand-back note on api/scope.js.
  const unitsKey = [...keys.units(projectId), { retired: showRetired }];
  const rolesKey = [...keys.roles(projectId), { retired: showRetired }];
  const fetchUnits = () => orgApi.units(projectId, showRetired);
  const fetchRoles = () => orgApi.roles(projectId, showRetired);
  const unitsQ = useQuery({ queryKey: unitsKey, queryFn: fetchUnits });
  const rolesQ = useQuery({ queryKey: rolesKey, queryFn: fetchRoles });
  const { codes: levels, getLabel: levelLabel } = useCodes(projectId, 'ORG_UNIT_LEVEL');
  const [selectedId, setSelectedId] = useState(null);     // string item id for RichTreeView
  const [expanded, setExpanded] = useState(null);         // null → everything expanded
  const [unitDialog, setUnitDialog] = useState(null);     // { row, parent }
  const [roleDialog, setRoleDialog] = useState(null);     // { row }
  const [confirm, setConfirm] = useState(null);           // { kind: 'unit'|'role', row }
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const units = useMemo(() => (unitsQ.data ?? []).filter((u) => showRetired || u.is_active), [unitsQ.data, showRetired]);
  const tree = useMemo(() => buildTree(units), [units]);
  const unitById = useMemo(() => new Map(units.map((u) => [String(u.org_unit_id), u])), [units]);
  const selected = selectedId ? unitById.get(selectedId) ?? null : null;
  const roles = (rolesQ.data ?? []).filter((r) => (showRetired || r.is_active)
    && selected && r.org_unit_id === selected.org_unit_id);
  const expandedItems = expanded ?? units.map((u) => String(u.org_unit_id));

  const refreshUnits = () => qc.invalidateQueries({ queryKey: keys.units(projectId) });
  const refreshRoles = () => qc.invalidateQueries({ queryKey: keys.roles(projectId) });

  const retire = useMutation({
    mutationFn: ({ kind, row }) => (kind === 'unit'
      ? orgApi.retireUnit(row.org_unit_id, row.row_version)
      : orgApi.retireRole(row.org_role_id, row.row_version)),
    onSuccess: (_, { kind }) => {
      if (kind === 'unit') { refreshUnits(); if (!showRetired) setSelectedId(null); } else refreshRoles();
      setConfirm(null);
      setNotice(t(kind === 'unit' ? 'settings.org.unitRetired' : 'settings.org.roleRetired'));
    },
    onError: (err, { kind }) => {
      setConfirm(null);
      if (kind === 'unit') refreshUnits(); else refreshRoles();
      setError(errorText(err, t('settings.retireFailed')));
    },
  });
  const restore = useMutation({
    mutationFn: ({ kind, row }) => (kind === 'unit' ? orgApi.restoreUnit(row.org_unit_id) : orgApi.restoreRole(row.org_role_id)),
    onSuccess: (_, { kind }) => {
      if (kind === 'unit') refreshUnits(); else refreshRoles();
      setNotice(t(kind === 'unit' ? 'settings.org.unitRestored' : 'settings.org.roleRestored'));
    },
    onError: (err) => setError(errorText(err, t('settings.restoreFailed'))),
  });

  // ---- unit dialog ----
  const unitFields = (depth) => [
    { name: 'org_unit_code', label: t('settings.code'), required: true },
    { name: 'org_unit_name', label: t('settings.name'), required: true },
    { name: 'level_code', label: t('settings.org.level'), type: 'select',
      emptyLabel: t('settings.org.levelDefault', { level: levelLabel(levels[depth - 1]?.code) || depth }),
      options: levels.map((c) => ({ value: c.code, label: c.label })) },
    { name: 'description', label: t('settings.description'), multiline: true },
  ];
  const submitUnit = (body, rowVersion) => {
    if (unitDialog.row) return orgApi.updateUnit(unitDialog.row.org_unit_id, { ...body, row_version: rowVersion });
    return orgApi.createUnit(projectId, { ...body, parent_org_unit_id: unitDialog.parent?.org_unit_id ?? null });
  };
  const reloadUnit = async () => {
    const fresh = await qc.fetchQuery({ queryKey: unitsKey, queryFn: fetchUnits });
    return fresh.find((u) => u.org_unit_id === unitDialog.row.org_unit_id && u.is_active) ?? null;
  };

  // ---- role dialog ----
  const activeUnits = units.filter((u) => u.is_active);
  const roleFields = [
    { name: 'org_role_code', label: t('settings.code'), required: true },
    { name: 'org_role_name', label: t('settings.name'), required: true },
    { name: 'org_unit_id', label: t('settings.org.unit'), type: 'select', required: true,
      helperText: t('settings.org.moveHelp'),
      options: activeUnits.map((u) => ({ value: u.org_unit_id, label: `${u.org_unit_code} — ${u.org_unit_name}` })) },
    { name: 'responsibility_desc', label: t('settings.org.responsibility'), multiline: true },
    { name: 'headcount', label: t('settings.org.headcount'), type: 'number' },
  ];
  const submitRole = (body, rowVersion) => (roleDialog.row
    ? orgApi.updateRole(roleDialog.row.org_role_id, { ...body, row_version: rowVersion })
    : orgApi.createRole(projectId, body));
  const reloadRole = async () => {
    const fresh = await qc.fetchQuery({ queryKey: rolesKey, queryFn: fetchRoles });
    return fresh.find((r) => r.org_role_id === roleDialog.row.org_role_id && r.is_active) ?? null;
  };

  const open = (fn) => { setError(''); fn(); };
  const canAddChild = selected?.is_active && selected.level_no < MAX_LEVEL;

  const roleColumns = [
    { field: 'org_role_code', headerName: t('settings.code'), width: 130,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          <Box component="span" sx={{ color: row.is_active ? 'text.primary' : 'text.disabled' }}>{row.org_role_code}</Box>
          {!row.is_active && <Chip size="small" variant="outlined" label={t('settings.retiredChip')} />}
        </Stack>) },
    { field: 'org_role_name', headerName: t('settings.name'), flex: 1, minWidth: 150 },
    { field: 'responsibility_desc', headerName: t('settings.org.responsibility'), flex: 1.5, minWidth: 180 },
    { field: 'headcount', headerName: t('settings.org.headcount'), width: 110, type: 'number' },
    { field: 'actions', headerName: '', width: 170, sortable: false, filterable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
          {row.is_active ? (
            <>
              <Button size="small" onClick={() => open(() => setRoleDialog({ row }))}>{t('settings.edit')}</Button>
              <Button size="small" color="warning" onClick={() => open(() => setConfirm({ kind: 'role', row }))}>
                {t('settings.retire')}</Button>
            </>
          ) : (
            <Button size="small" disabled={restore.isPending}
              onClick={() => open(() => restore.mutate({ kind: 'role', row }))}>{t('settings.restore')}</Button>
          )}
        </Stack>) },
  ];

  const confirmName = confirm && (confirm.kind === 'unit'
    ? `${confirm.row.org_unit_code} ${confirm.row.org_unit_name}` : `${confirm.row.org_role_code} ${confirm.row.org_role_name}`);

  return (
    <Box>
      <SettingsCrumbs projectId={projectId} current={t('settings.organisation')} />
      <Page title={t('settings.organisation')} subtitle={t('settings.organisationWhat')}
        error={error || (unitsQ.error && errorText(unitsQ.error)) || (rolesQ.error && errorText(rolesQ.error))}>
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mb: 1 }}>{t('settings.org.raciHelp')}</Typography>
        <WrapperBox>
          <Button variant="contained" onClick={() => open(() => setUnitDialog({ row: null, parent: null }))}>
            {t('settings.org.addTop')}</Button>
          <Button variant="outlined" disabled={!canAddChild}
            onClick={() => open(() => setUnitDialog({ row: null, parent: selected }))}>{t('settings.org.addChild')}</Button>
          <Button disabled={!selected?.is_active} onClick={() => open(() => setUnitDialog({ row: selected, parent: null }))}>
            {t('settings.org.editUnit')}</Button>
          {selected && !selected.is_active ? (
            <Button disabled={restore.isPending} onClick={() => open(() => restore.mutate({ kind: 'unit', row: selected }))}>
              {t('settings.org.restoreUnit')}</Button>
          ) : (
            <Button color="warning" disabled={!selected} onClick={() => open(() => setConfirm({ kind: 'unit', row: selected }))}>
              {t('settings.org.retireUnit')}</Button>
          )}
          <ShowRetired id="org-show-retired" checked={showRetired} onChange={setShowRetired} />
          {selected?.is_active && selected.level_no >= MAX_LEVEL && (
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('settings.org.maxLevel')}</Typography>
          )}
        </WrapperBox>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 5 }}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography sx={{ fontWeight: 700, mb: 1 }}>{t('settings.org.units')}</Typography>
                {!unitsQ.isLoading && tree.length === 0 && (
                  <Typography sx={{ color: 'text.secondary' }}>{t('settings.org.noUnits')}</Typography>
                )}
                <RichTreeView items={tree} getItemId={(u) => String(u.org_unit_id)}
                  getItemLabel={(u) => `${u.org_unit_code} · ${u.org_unit_name} — ${levelLabel(u.level_code)}`
                    + (u.is_active ? '' : ` (${t('settings.retiredChip')})`)}
                  getItemChildren={(u) => u.children}
                  selectedItems={selectedId} onSelectedItemsChange={(_, id) => setSelectedId(id)}
                  expandedItems={expandedItems} onExpandedItemsChange={(_, ids) => setExpanded(ids)}
                  expansionTrigger="iconContainer" />
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                {selected ? (
                  <>
                    <Stack direction="row" sx={{ alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, mb: 1 }}>
                      <Box>
                        <Typography sx={{ fontWeight: 700 }}>
                          {t('settings.org.rolesIn', { unit: `${selected.org_unit_code} ${selected.org_unit_name}` })}
                        </Typography>
                        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{levelLabel(selected.level_code)}</Typography>
                      </Box>
                      <Button variant="contained" size="small" disabled={!selected.is_active}
                        onClick={() => open(() => setRoleDialog({ row: null }))}>{t('settings.org.addRole')}</Button>
                    </Stack>
                    {selected.description && (
                      <Typography sx={{ whiteSpace: 'pre-wrap', color: 'text.secondary', mb: 1.5 }}>{selected.description}</Typography>
                    )}
                    <DataGrid autoHeight rows={roles} getRowId={(r) => r.org_role_id} columns={roleColumns}
                      loading={rolesQ.isLoading} disableRowSelectionOnClick hideFooterSelectedRowCount
                      localeText={{ noRowsLabel: t('settings.org.noRoles') }}
                      sx={{ bgcolor: 'background.paper', borderRadius: 3 }} />
                  </>
                ) : (
                  <Typography sx={{ color: 'text.secondary' }}>{t('settings.org.pickUnit')}</Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Page>

      {unitDialog && (
        <RecordDialog open fields={unitFields(unitDialog.row ? unitDialog.row.level_no : (unitDialog.parent?.level_no ?? 0) + 1)}
          title={unitDialog.row ? t('settings.org.editUnitTitle', { code: unitDialog.row.org_unit_code })
            : unitDialog.parent ? t('settings.org.addChildTitle', { parent: unitDialog.parent.org_unit_name })
              : t('settings.org.addTopTitle')}
          row={unitDialog.row} onSubmit={submitUnit} onReload={reloadUnit} onClose={() => setUnitDialog(null)}
          onDone={(saved) => {
            refreshUnits();
            if (saved?.org_unit_id) setSelectedId(String(saved.org_unit_id));
            if (expanded && unitDialog.parent) setExpanded([...expanded, String(unitDialog.parent.org_unit_id)]);
            setNotice(t('settings.saved'));
          }} />
      )}
      {roleDialog && (
        <RecordDialog open fields={roleFields}
          title={roleDialog.row ? t('settings.org.editRoleTitle', { code: roleDialog.row.org_role_code }) : t('settings.org.addRoleTitle')}
          row={roleDialog.row} initial={{ org_unit_id: selected?.org_unit_id }}
          onSubmit={submitRole} onReload={reloadRole} onClose={() => setRoleDialog(null)}
          onDone={() => { refreshRoles(); setNotice(t('settings.saved')); }} />
      )}
      <ConfirmDialog open={Boolean(confirm)}
        title={t(confirm?.kind === 'unit' ? 'settings.org.retireUnitTitle' : 'settings.org.retireRoleTitle')}
        body={t('settings.retireBody', { name: confirmName })} confirmLabel={t('settings.retire')} busy={retire.isPending}
        onClose={() => setConfirm(null)} onConfirm={() => retire.mutate(confirm)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Box>
  );
}
