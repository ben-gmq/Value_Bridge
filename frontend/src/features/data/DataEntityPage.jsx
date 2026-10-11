import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, FormControlLabel, IconButton, Link, Snackbar, Stack, Switch, TextField, Tooltip,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import KeyRounded from '@mui/icons-material/KeyRounded';
import EditOutlined from '@mui/icons-material/EditOutlined';
import ArchiveOutlined from '@mui/icons-material/ArchiveOutlined';
import UploadFileRounded from '@mui/icons-material/UploadFileRounded';
import CheckBoxRounded from '@mui/icons-material/CheckBoxRounded';
import CheckBoxOutlineBlankRounded from '@mui/icons-material/CheckBoxOutlineBlankRounded';
import HelpOutlineRounded from '@mui/icons-material/HelpOutlineRounded';
import { DataGrid } from '@mui/x-data-grid';
import { dataApi } from '../../api/scope';
import { errorText, isStale } from '../../api/client';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { ImportWizard } from '../../components/ImportWizard';
import { Card, Code, ListRow, MonoChip, Status, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { FieldDialog } from './FieldDialog';
import { entityLabel, modelChecks, requiredText, sizeText } from './fieldRules';

const TEXT_KEYS = ['de_name', 'description', 'business_owner_note'];
const pick = (de) => Object.fromEntries(TEXT_KEYS.map((k) => [k, de[k] ?? '']));
const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };
const loadText = (err) => errorText(err, t('data.loadFailed'));

// Name, description and owner note, saved together with the entity's row_version (D-6).
function EntityForm({ entity, disabled, onSaved }) {
  const qc = useQueryClient();
  const [f, setF] = useState(() => pick(entity));
  const [base, setBase] = useState(entity);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [conflict, setConflict] = useState(false);
  const changed = TEXT_KEYS.filter((k) => (f[k] ?? '') !== (base[k] ?? ''));
  const dirty = changed.length > 0;
  const m = useMutation({
    // Only what the user changed is sent, so a save never rewrites another user's field.
    mutationFn: () => dataApi.update(entity.data_entity_id, { row_version: base.row_version,
      ...Object.fromEntries(changed.map((k) => [k, k === 'de_name' ? f[k].trim() : f[k].trim() || null])) }),
    onSuccess: (de) => { setBase(de); setF(pick(de)); onSaved(de); },
    onError: (err) => { if (isStale(err)) setConflict(true); else setError(errorText(err, t('common.saveFailed'))); },
  });
  async function reload() {
    let fresh;
    try {
      fresh = await qc.fetchQuery({ queryKey: keys.entity(entity.data_entity_id),
        queryFn: () => dataApi.get(entity.data_entity_id), staleTime: 0 });
    } catch (err) {
      setConflict(false);
      setError(loadText(err));
      return;
    }
    // Their version is the new base. What this user changed is reapplied on top; everything
    // they did not touch takes the other user's value (never the stale one).
    const old = pick(base);
    setF((cur) => Object.fromEntries(TEXT_KEYS.map((k) => [k, cur[k] !== old[k] ? cur[k] : fresh[k] ?? ''])));
    setBase(fresh);
    setConflict(false);
    setInfo(t('data.reloaded'));
  }
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const labels = { de_name: t('data.name'), description: t('data.description'), business_owner_note: t('data.ownerNote') };
  return (
    <Card sx={{ mb: 2 }} bodySx={{ py: 2.25, gap: 0 }}>
      {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
      {info && <Alert severity="info" sx={{ mb: 2 }}>{info}</Alert>}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'flex-start' } }}>
        <TextField id="de-name" label={t('data.name')} required value={f.de_name} onChange={set('de_name')}
          disabled={disabled} sx={{ width: { md: 220 }, flexShrink: 0 }} slotProps={{ htmlInput: { maxLength: 200 } }} />
        <TextField id="de-desc" label={t('data.description')} value={f.description} onChange={set('description')}
          disabled={disabled} multiline maxRows={6} sx={{ flex: 2 }} slotProps={{ htmlInput: { maxLength: 4000 } }} />
        <TextField id="de-owner" label={t('data.ownerNote')} value={f.business_owner_note}
          onChange={set('business_owner_note')} disabled={disabled} multiline maxRows={6} sx={{ flex: 1 }}
          slotProps={{ htmlInput: { maxLength: 4000 } }} />
        <Button variant="contained" disabled={disabled || !dirty || !f.de_name.trim() || m.isPending}
          onClick={() => { setError(''); setInfo(''); m.mutate(); }} sx={{ flexShrink: 0, alignSelf: { md: 'center' } }}>
          {t('data.save')}</Button>
      </Stack>
      <ConflictDialog open={conflict} onReload={reload} onClose={() => setConflict(false)}
        unsaved={Object.fromEntries(changed.map((k) => [labels[k], f[k]]))} />
    </Card>
  );
}

// Computed from the loaded fields only; while they load or after a failed load there is
// nothing to check, so no "No primary key" is claimed.
function ModelChecks({ fields, ready }) {
  return (
    <Card title={t('data.checks')} bodySx={{ gap: 1.25 }}>
      {!ready && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.check.unavailable')}</Typography>}
      {ready && modelChecks(fields).map((c) => (
        <Status key={c.text} tone={c.tone} size="sm"
          sx={{ whiteSpace: 'normal', height: 'auto', minHeight: 24, py: 0.375, wordBreak: 'break-word' }}>{c.text}</Status>
      ))}
    </Card>
  );
}

function UsedBy({ projectId, rows, loading, error }) {
  return (
    <Card title={t('data.usedBy')} bodySx={{ gap: 1 }}
      action={!loading && !error && <Code tone="muted">{rows.length}</Code>}>
      {error ? <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{loadText(error)}</Alert>
        : loading ? null : rows.length === 0 ? (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.usedByNone')}</Typography>
      ) : rows.map((r) => (
        <ListRow key={r.br_id} component={RouterLink} to={links.requirement(projectId, r.br_id)} sx={{ py: 1 }}>
          <Code tone="purple" sx={{ fontSize: 12 }}>{r.br_number}</Code>
          <Typography component="span" sx={{ fontSize: 13.5, flexGrow: 1, minWidth: 0 }}>
            <Code tone="muted" sx={{ fontSize: 12, mr: 1 }}>{r.hier_code}</Code>
            {r.node_name}
          </Typography>
          <Typography component="span" aria-label={t('data.crud')}
            sx={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, letterSpacing: 2, color: 'brand.purpleText' }}>{r.crud}</Typography>
        </ListRow>
      ))}
    </Card>
  );
}

// Required is three-valued (D-26): a tick, an empty box, or "not yet known".
function RequiredMark({ value }) {
  const label = requiredText(value);
  const Icon = value === true ? CheckBoxRounded : value === false ? CheckBoxOutlineBlankRounded : HelpOutlineRounded;
  return (
    <Tooltip title={label}>
      <Icon role="img" aria-label={label} sx={{ fontSize: 20,
        color: value === true ? 'secondary.main' : value === false ? 'text.secondary' : 'brand.muted' }} />
    </Tooltip>
  );
}

// Names of the target fields this entity's foreign keys point at, read from each target's
// field list (the same query the target's own page uses, so a save there refreshes this).
function useRefFieldNames(fields) {
  const targets = [...new Set(fields.filter((f) => f.ref_data_field_id != null).map((f) => f.ref_data_entity_id))];
  const results = useQueries({ queries: targets.map((id) => ({
    queryKey: [...keys.entity(id), 'fields'], queryFn: () => dataApi.fields(id) })) });
  const names = {};
  results.forEach((r) => (r.data ?? []).forEach((x) => { names[x.data_field_id] = x.field_name; }));
  return { names, error: results.find((r) => r.error)?.error ?? null };
}

export default function DataEntityPage() {
  const { projectId, deId } = useParams();
  const canEdit = useCanEdit();             // UAT 7b / VB-008: viewers see no edit controls
  const qc = useQueryClient();
  const de = useQuery({ queryKey: keys.entity(deId), queryFn: () => dataApi.get(deId) });
  const [showRetired, setShowRetired] = useState(false);
  // Retired fields come from a separate query under the same prefix, so the active list other
  // screens read (and refresh) stays active-only.
  const fieldsQ = useQuery({ queryKey: showRetired ? [...keys.entity(deId), 'fields', 'with-retired'] : [...keys.entity(deId), 'fields'],
    queryFn: () => dataApi.fields(deId, showRetired), placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === String(deId) ? prev : undefined) });
  const usedQ = useQuery({ queryKey: [...keys.entity(deId), 'used-by'], queryFn: () => dataApi.usedBy(deId) });
  const entities = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const { getLabel } = useCodes(projectId, 'FIELD_DATA_TYPE');
  const [editing, setEditing] = useState(null);           // null | 'new' | a field
  const [confirm, setConfirm] = useState(null);           // null | 'entity' | a field
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);             // { text, restore?: field }
  const [importing, setImporting] = useState(false);       // the fields import wizard (data-fields target)
  const entity = de.data;
  const allFields = fieldsQ.data ?? [];
  const fields = allFields.filter((f) => f.is_active !== false);     // checks, duplicates, keys: live only
  const used = usedQ.data ?? [];
  const retired = entity && !entity.is_active;
  const { names: refNames, error: refError } = useRefFieldNames(fields);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.entity(deId) });      // the entity, its fields and used-by
    qc.invalidateQueries({ queryKey: keys.entities(projectId) });
  };
  const fail = (err) => setError(errorText(err, t('common.saveFailed')));

  const retireEntity = useMutation({
    mutationFn: () => dataApi.retire(entity.data_entity_id, entity.row_version),
    onSuccess: () => { setConfirm(null); refresh(); setNotice({ text: t('data.retired', { label: entityLabel(entity) }) }); },
    onError: (err) => { setConfirm(null); fail(err); refresh(); },   // a retry uses the current row_version
  });
  const restoreEntity = useMutation({
    mutationFn: () => dataApi.restore(entity.data_entity_id),
    onSuccess: () => { refresh(); setNotice({ text: t('data.restored', { label: entityLabel(entity) }) }); },
    onError: fail,
  });
  const retireField = useMutation({
    mutationFn: (fld) => dataApi.retireField(fld.data_field_id, fld.row_version),
    onSuccess: (_, fld) => { setConfirm(null); refresh();
      setNotice({ text: t('data.field.retired', { name: fld.field_name }), restore: fld }); },
    onError: (err) => { setConfirm(null); fail(err); refresh(); },   // a retry uses the current row_version
  });
  const restoreField = useMutation({
    mutationFn: (fld) => dataApi.restoreField(fld.data_field_id),
    onSuccess: (fld) => { refresh(); setNotice({ text: t('data.field.restored', { name: fld.field_name }) }); },
    onError: fail,
  });

  const targetLabel = (id) => entityLabel((entities.data ?? []).find((e) => e.data_entity_id === id))
    || t('data.field.unknownEntity', { id });
  const fkText = (row) => (row.ref_data_field_id != null
    ? t('data.field.fkToField', { target: targetLabel(row.ref_data_entity_id), field: refNames[row.ref_data_field_id] ?? '' })
    : t('data.field.fkTo', { target: targetLabel(row.ref_data_entity_id) }));
  const none = <Box component="span" sx={{ color: 'text.secondary' }}>{t('data.none')}</Box>;
  const mono = { fontFamily: MONO, fontSize: 13 };
  const columns = [
    { field: 'seq_no', headerName: t('data.field.seqShort'), width: 48,
      renderCell: ({ value }) => <Typography component="span" sx={{ fontFamily: MONO, fontSize: 12.5, color: 'text.secondary' }}>{value}</Typography> },
    { field: 'field_name', headerName: t('data.field.name'), flex: 1, minWidth: 140,
      renderCell: ({ row }) => (
        <Box component="span" sx={{ fontWeight: row.is_primary_key ? 700 : 400,
          color: row.is_active === false ? 'text.secondary' : 'inherit' }}>{row.field_name}</Box>) },
    { field: 'data_type_code', headerName: t('data.field.type'), width: 120,
      valueGetter: (v) => (v ? getLabel(v) : ''),
      renderCell: ({ value }) => (value ? <Box component="span" sx={mono}>{value}</Box> : none) },
    { field: 'size', headerName: t('data.field.size'), width: 76, sortable: false, valueGetter: (_, row) => sizeText(row),
      renderCell: ({ value }) => <Box component="span" sx={mono}>{value}</Box> },
    { field: 'is_mandatory', headerName: t('data.field.required'), width: 88, align: 'center', headerAlign: 'center',
      valueGetter: (v) => requiredText(v),
      renderCell: ({ row }) => (
        <Stack sx={{ alignItems: 'center', justifyContent: 'center', height: '100%' }}><RequiredMark value={row.is_mandatory} /></Stack>) },
    { field: 'pk_ordinal', headerName: t('data.field.pkShort'), width: 60, align: 'center', headerAlign: 'center',
      renderCell: ({ row }) => row.is_primary_key && (
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'center', height: '100%' }}
          role="img" aria-label={t('data.field.pkAt', { n: row.pk_ordinal })}>
          <KeyRounded sx={{ fontSize: 17, color: 'brand.amber' }} />
          <Box component="span" sx={{ fontFamily: MONO, fontSize: 12 }}>{row.pk_ordinal}</Box>
        </Stack>) },
    { field: 'fk', headerName: t('data.field.fk'), flex: 1, minWidth: 190, sortable: false,
      valueGetter: (_, row) => (row.is_foreign_key ? fkText(row) : ''),
      renderCell: ({ row, tabIndex }) => (row.is_foreign_key ? (
        <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', height: '100%', minWidth: 0 }}>
          <Link component={RouterLink} to={links.entity(projectId, row.ref_data_entity_id)} underline="none"
            tabIndex={tabIndex} onClick={(e) => e.stopPropagation()} sx={{ minWidth: 0, display: 'inline-flex' }}>
            <Tag tone="teal" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', display: 'inline-block', lineHeight: '24px',
              '&:hover': { textDecoration: 'underline' } }}>{fkText(row)}</Tag>
          </Link>
          <MonoChip>{t('data.field.groupNo', { n: row.fk_group_no })}</MonoChip>
        </Stack>
      ) : none) },
    { field: 'actions', headerName: '', width: showRetired ? 176 : 96, sortable: false, align: 'right', renderCell: ({ row, tabIndex }) => !retired && canEdit && (
      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
        {row.is_active === false ? (<>
          <Tag tone="neutral">{t('data.retiredChip')}</Tag>
          <Button size="small" tabIndex={tabIndex} disabled={restoreField.isPending}
            onClick={() => { setError(''); restoreField.mutate(row); }}>{t('data.restore')}</Button>
        </>) : (<>
          <Tooltip title={t('data.edit')}>
            <IconButton size="small" tabIndex={tabIndex} aria-label={`${t('data.edit')} ${row.field_name}`}
              onClick={() => { setError(''); setEditing(row); }}><EditOutlined fontSize="small" /></IconButton>
          </Tooltip>
          <Tooltip title={t('data.retire')}>
            <IconButton size="small" tabIndex={tabIndex} color="warning" aria-label={`${t('data.retire')} ${row.field_name}`}
              onClick={() => { setError(''); setConfirm(row); }}><ArchiveOutlined fontSize="small" /></IconButton>
          </Tooltip>
        </>)}
      </Stack>) },
  ];

  const title = entity ? (
    <><Code tone="teal" sx={{ fontSize: 'inherit', fontWeight: 500, mr: 1.5 }}>{entity.de_number}</Code>{entity.de_name}</>
  ) : t('data.title');

  const pageError = error || (de.error && loadText(de.error)) || (entities.error && loadText(entities.error))
    || (refError && loadText(refError));
  return (
    <Page title={title} crumb={entity ? entityLabel(entity) : undefined}
      subtitle={entity && fieldsQ.isSuccess && usedQ.isSuccess
        && t('data.detailSubtitle', { fields: fields.length, used: used.length })}
      actions={entity && canEdit && (retired
        ? <Button variant="contained" disabled={restoreEntity.isPending} onClick={() => { setError(''); restoreEntity.mutate(); }}>{t('data.restore')}</Button>
        : (<>
          <Button id="de-import-fields" variant="outlined" startIcon={<UploadFileRounded />}
            onClick={() => setImporting(true)}>{t('data.importFields')}</Button>
          <Button variant="outlined" color="warning" onClick={() => { setError(''); setConfirm('entity'); }}>{t('data.retireEntity')}</Button>
        </>))}>
      {pageError && <Alert severity="error" sx={ERR_SX}>{pageError}</Alert>}
      {retired && <Alert severity="warning" sx={{ mb: 2 }}>{t('data.retiredBanner')}</Alert>}
      {entity && <EntityForm key={`${entity.data_entity_id}-${entity.is_active}`} entity={entity} disabled={retired || !canEdit}
        onSaved={(saved) => { qc.setQueryData(keys.entity(deId), saved); qc.invalidateQueries({ queryKey: keys.entities(projectId) });
          setNotice({ text: t('data.saved') }); }} />}
      {entity && (
        <Box sx={{ display: 'grid', gap: 2, alignItems: 'start',
          gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1fr) 320px' } }}>
          <Card title={t('data.fields')} bodySx={{ px: 1.5 }}
            action={(
              <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <FormControlLabel label={t('data.showRetired')} slotProps={{ typography: { sx: { fontSize: 13 } } }}
                  control={<Switch id="df-show-retired" size="small" checked={showRetired}
                    onChange={(e) => setShowRetired(e.target.checked)} />} />
                {!retired && canEdit && <Button size="small" variant="outlined" startIcon={<AddRounded />}
                  disabled={!fieldsQ.isSuccess}
                  onClick={() => { setError(''); setEditing('new'); }}>{t('data.field.add')}</Button>}
              </Stack>)}>
            {fieldsQ.error ? <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{loadText(fieldsQ.error)}</Alert> : (
              <DataGrid autoHeight rows={allFields} getRowId={(r) => r.data_field_id} columns={columns}
                loading={fieldsQ.isLoading} disableRowSelectionOnClick hideFooterSelectedRowCount hideFooter={allFields.length <= 100}
                initialState={{ sorting: { sortModel: [{ field: 'seq_no', sort: 'asc' }] } }}
                localeText={{ noRowsLabel: t('data.field.empty') }} rowHeight={48}
                sx={{ border: 0, borderRadius: 0, bgcolor: 'transparent' }} />
            )}
          </Card>
          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <ModelChecks fields={fields} ready={fieldsQ.isSuccess} />
            <UsedBy projectId={projectId} rows={used} loading={usedQ.isLoading} error={usedQ.error} />
          </Stack>
        </Box>
      )}
      {importing && <ImportWizard projectId={projectId} initialTarget="data-fields" onClose={() => setImporting(false)} />}
      {editing && entity && (
        <FieldDialog projectId={projectId} entity={entity} fields={fields} field={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => { refresh(); if (saved.ref_data_entity_id) qc.invalidateQueries({ queryKey: keys.entity(saved.ref_data_entity_id) });
            setNotice({ text: t(editing === 'new' ? 'data.field.added' : 'data.field.saved', { name: saved.field_name }) }); }} />
      )}
      <ConfirmDialog open={confirm === 'entity'} title={t('data.retireEntityTitle')}
        body={t('data.retireEntityBody', { label: entityLabel(entity) })} confirmLabel={t('data.retire')}
        busy={retireEntity.isPending} onClose={() => setConfirm(null)} onConfirm={() => retireEntity.mutate()} />
      <ConfirmDialog open={Boolean(confirm) && confirm !== 'entity'} title={t('data.field.retireTitle')}
        body={t('data.field.retireBody', { name: confirm?.field_name })} confirmLabel={t('data.retire')}
        busy={retireField.isPending} onClose={() => setConfirm(null)} onConfirm={() => retireField.mutate(confirm)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={notice?.restore ? 8000 : 3000} onClose={() => setNotice(null)}
        message={notice?.text}
        action={notice?.restore && canEdit && (
          <Button size="small" color="inherit" disabled={restoreField.isPending}
            onClick={() => { setError(''); restoreField.mutate(notice.restore); }}>{t('data.restore')}</Button>)} />
    </Page>
  );
}
