import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  Radio, RadioGroup, Stack, Step, StepLabel, Stepper, Table, TableBody, TableCell, TableHead, TablePagination,
  TableRow, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import UploadFileRounded from '@mui/icons-material/UploadFileRounded';
import { errorText, isStale } from '../api/client';
import { importApi } from '../api/scope';
import { keys } from '../app/links';
import { MONO } from '../theme/theme';
import { t, tOr } from '../i18n/t';

/**
 * The one import wizard (VB law 8, docs/slice4a_spec.md §4 "review (manual)"): choose a target →
 * template or export → pick the .xlsx (read ONCE into memory, 4a-R16) → upload → read the preview
 * → fix in Excel and re-upload as often as needed (each upload is a new batch) → type the insert
 * count → commit. Everything a target changes lives in IMPORT_TARGETS. Every server text (messages,
 * params, names, cell values) is untrusted and renders as text.
 *
 * A BOOK (`data-model`, S4-12) is one workbook run as two batches in sequence: the entities sheet
 * (validate → preview → commit), then the fields sheet, validated against the now-live entities.
 * The same in-memory buffer is posted at every step. Before step 1 commits, the fields sheet's
 * file-level checks run (`check`, nothing staged); a file with no entities sheet skips step 1.
 * Once step 1 has committed, the wizard is left only by "Do fields later" (4a-R10), and a failed
 * fields step takes a corrected file to the fields step alone.
 */
const FIELD_COLUMNS = { de_number: 'data.number', de_name: 'data.import.col.deName',
  field_name: 'data.field.name', data_type: 'data.field.type', length: 'data.field.length',
  precision: 'data.field.precision', scale: 'data.field.scale', mandatory: 'data.field.required',
  pk_position: 'data.field.pkOrdinal', ref_de_number: 'data.import.col.refDeNumber',
  ref_de_name: 'data.import.col.refDeName', ref_field_name: 'data.import.col.refFieldName',
  fk_group: 'data.import.col.fkGroup', description: 'data.description', row_token: 'data.import.col.rowToken' };

export const IMPORT_TARGETS = {
  'data-entities': {
    label: 'data.import.target.entities',
    help: 'data.import.target.entitiesHelp',
    // Column codes the server's messages and changes name → the labels the screens already use.
    columns: { de_number: 'data.number', de_name: 'data.name', description: 'data.description',
      business_owner_note: 'data.ownerNote', row_token: 'data.import.col.rowToken' },
    refresh: (p) => [keys.entities(p)],          // what a commit makes stale
  },
  'data-fields': {
    label: 'data.import.target.fields',
    help: 'data.import.target.fieldsHelp',
    columns: FIELD_COLUMNS,
    refresh: (p) => [keys.entities(p), keys.everyEntity()],
  },
  'data-model': {
    label: 'data.import.target.model',
    help: 'data.import.target.modelHelp',
    book: ['data-entities', 'data-fields'],      // template and export only; each step validates one
    columns: FIELD_COLUMNS,
    refresh: (p) => [keys.entities(p), keys.everyEntity()],
  },
};

const MAX_BYTES = 10 * 1024 * 1024;              // the server's ingress cap (§4 validate, step 2)
const PAGE = 100;
const STEPS = ['target', 'file', 'review', 'done'];
const BOOK_STEPS = ['target', 'file', 'entities', 'fields', 'done'];
const VERDICT_COLOR = { INSERT: 'success', UPDATE: 'primary', MATCH: 'default' };
const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };

function fmtSize(n) {
  if (n < 1024) return t('data.import.sizeB', { n });
  if (n < 1024 * 1024) return t('data.import.sizeKb', { n: (n / 1024).toFixed(1) });
  return t('data.import.sizeMb', { n: (n / (1024 * 1024)).toFixed(1) });
}

const colLabel = (cfg, code) => (cfg.columns[code] ? t(cfg.columns[code]) : code);

// One server Msg: translated by code when every placeholder is present, else the English message.
function msgText(m) {
  const vars = { column: m.column, ...(m.params ?? {}) };
  for (const k of Object.keys(vars)) if (vars[k] === null) vars[k] = t('data.import.blank');
  return tOr(`data.import.msg.${m.code}`, vars, m.message);
}

function MsgList({ msgs, cfg, color, prefix = true }) {
  if (!msgs?.length) return null;
  return (
    <Box component="ul" sx={{ m: 0, pl: 2 }}>
      {msgs.map((m, i) => (
        <Typography component="li" key={`${m.code}:${m.column}:${i}`} sx={{ fontSize: 13, color }}>
          {prefix && m.column && <Box component="span" sx={{ fontWeight: 600 }}>{t('data.import.colPrefix', { column: colLabel(cfg, m.column) })}</Box>}
          {msgText(m)}
        </Typography>
      ))}
    </Box>
  );
}

function Value({ v }) {
  if (v === null || v === undefined || v === '') {
    return <Box component="span" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>{t('data.import.blank')}</Box>;
  }
  if (typeof v === 'boolean') return <Box component="span">{t(v ? 'data.import.yes' : 'data.import.no')}</Box>;
  return <Box component="span" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{String(v)}</Box>;
}

function Changes({ row, cfg }) {
  if (!row.changes?.length) {
    return row.verdict === 'MATCH'
      ? <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.import.noChange')}</Typography> : null;
  }
  return row.changes.map((c) => (
    <Box key={c.column} sx={{ fontSize: 13, mb: 0.5 }}>
      <Box component="span" sx={{ fontWeight: 600 }}>{t('data.import.colPrefix', { column: colLabel(cfg, c.column) })}</Box>
      {row.verdict === 'INSERT' ? <Value v={c.after} /> : (
        <>
          <Value v={c.before} />
          <Box component="span" sx={{ color: 'text.secondary', mx: 0.75 }}>{t('data.import.arrow')}</Box>
          {c.cleared
            ? <Chip size="small" variant="outlined" color="error" label={t('data.import.cleared')} />
            : <Value v={c.after} />}
        </>
      )}
    </Box>
  ));
}

// What a row resolved to (4a-R13: the number and name of a parent or target named by name) and
// the relationship a foreign-key row joins (4a-R1). Server values, rendered as text.
function Resolved({ res }) {
  if (!res) return null;
  const lines = [];
  if (res.parent?.by_name) lines.push(t('data.import.resolvedParent', { number: res.parent.de_number, name: res.parent.de_name }));
  if (res.ref?.by_name) lines.push(t('data.import.resolvedRef', { number: res.ref.de_number, name: res.ref.de_name }));
  const rel = res.relationship;
  if (rel) {
    const base = rel.kind === 'existing' ? t('data.import.relExisting', { group: rel.group, to: rel.to })
      : rel.label ? t('data.import.relNewLabel', { label: rel.label, to: rel.to }) : t('data.import.relNew', { to: rel.to });
    lines.push(rel.with?.length ? `${base} ${t('data.import.relWith', { names: rel.with.join(', ') })}` : base);
  }
  return lines.map((l) => <Typography key={l} sx={{ fontSize: 12, color: 'text.secondary', mt: 0.5 }}>{l}</Typography>);
}

function FileInfo({ file }) {
  if (!file) return null;
  return (
    <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
      {t('data.import.fileInfo', { name: file.name, size: fmtSize(file.size),
        modified: new Date(file.lastModified).toLocaleString() })}
    </Typography>
  );
}

function Count({ label, n, color }) {
  return (
    <Box sx={{ px: 1.5, py: 1, border: 1, borderColor: 'divider', borderRadius: 1, minWidth: 96 }}>
      <Typography sx={{ fontSize: 20, fontWeight: 700, color }}>{n}</Typography>
      <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{label}</Typography>
    </Box>
  );
}

function Preview({ pv, cfg }) {
  const b = pv.batch;
  const [filter, setFilter] = useState(b.error_count || b.warning_count ? 'issues' : 'all');
  const [page, setPage] = useState(0);
  const rows = pv.rows.filter((r) => (filter === 'issues' ? r.errors?.length || r.warnings?.length
    : filter === 'changes' ? r.verdict !== 'MATCH' : true));
  const shown = rows.slice(page * PAGE, (page + 1) * PAGE);
  return (
    <Box>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1.5 }}>
        {t('data.import.readFrom', { file: b.file_name ?? '', sheet: b.sheet_name ?? t('data.none'), n: b.row_count })}
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap', mb: 2 }}>
        <Count label={t('data.import.count.insert')} n={b.insert_count} color="success.main" />
        <Count label={t('data.import.count.update')} n={b.update_count} color="primary.main" />
        <Count label={t('data.import.count.match')} n={b.match_count} />
        <Count label={t('data.import.count.errors')} n={b.error_count} color={b.error_count ? 'error.main' : undefined} />
        <Count label={t('data.import.count.warnings')} n={b.warning_count} color={b.warning_count ? 'status.caution' : undefined} />
      </Stack>
      {b.file_warnings?.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 600, mb: 0.5 }}>{t('data.import.fileWarnings')}</Typography>
          <MsgList msgs={b.file_warnings} cfg={cfg} prefix={false} />
        </Alert>
      )}
      {pv.purged && <Alert severity="info" sx={{ mb: 2 }}>{t('data.import.purged')}</Alert>}
      {!pv.purged && (
        <>
          <ToggleButtonGroup size="small" exclusive value={filter} sx={{ mb: 1 }}
            onChange={(_e, v) => { if (v) { setFilter(v); setPage(0); } }}>
            <ToggleButton value="all">{t('data.import.filter.all', { n: pv.rows.length })}</ToggleButton>
            <ToggleButton value="issues">{t('data.import.filter.issues')}</ToggleButton>
            <ToggleButton value="changes">{t('data.import.filter.changes')}</ToggleButton>
          </ToggleButtonGroup>
          <Table size="small" sx={{ '& td': { verticalAlign: 'top' } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 64 }}>{t('data.import.col.row')}</TableCell>
                <TableCell sx={{ width: 150 }}>{t('data.import.col.verdict')}</TableCell>
                <TableCell sx={{ width: 170 }}>{t('data.import.col.key')}</TableCell>
                <TableCell>{t('data.import.col.changes')}</TableCell>
                <TableCell sx={{ width: '34%' }}>{t('data.import.col.problems')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {shown.map((r) => (
                <TableRow key={r.sheet_row_no}>
                  <TableCell sx={{ fontFamily: MONO, fontSize: 13 }}>{r.sheet_row_no}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
                      <Chip size="small" variant="outlined" color={VERDICT_COLOR[r.verdict] ?? 'default'}
                        label={t(`data.import.verdict.${r.verdict}`)} />
                      {!r.is_valid && <Chip size="small" color="error" label={t('data.import.verdict.error')} />}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ fontFamily: MONO, fontSize: 13, wordBreak: 'break-word' }}>{r.business_key ?? t('data.none')}</Box>
                    <Resolved res={r.resolved} />
                  </TableCell>
                  <TableCell><Changes row={r} cfg={cfg} /></TableCell>
                  <TableCell>
                    <MsgList msgs={r.errors} cfg={cfg} color="error.main" />
                    <MsgList msgs={r.warnings} cfg={cfg} color="status.caution" />
                  </TableCell>
                </TableRow>
              ))}
              {!shown.length && (
                <TableRow><TableCell colSpan={5} sx={{ color: 'text.secondary' }}>{t('data.import.noRows')}</TableCell></TableRow>)}
            </TableBody>
          </Table>
          {rows.length > PAGE && (
            <TablePagination component="div" count={rows.length} page={page} rowsPerPage={PAGE}
              rowsPerPageOptions={[PAGE]} onPageChange={(_e, p) => setPage(p)} />)}
        </>
      )}
    </Box>
  );
}

// A refused upload: the server's file-level message where it sent one, else what the status means.
function uploadError(err) {
  const s = err?.response?.status;
  if (s === 413) return t('data.import.tooBig');
  if (s === 415) return t('data.import.wrongType');
  if (s === 429) return errorText(err, t('data.import.busy'));
  return errorText(err, t(s === 422 ? 'data.import.invalidFile' : 'data.import.uploadFailed'));
}

export function ImportWizard({ projectId, targets = Object.keys(IMPORT_TARGETS), initialTarget, onClose, onCommitted }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState(initialTarget ?? targets[0]);
  const cfg = IMPORT_TARGETS[target];
  const isBook = Boolean(cfg.book);
  const [step, setStep] = useState(initialTarget ? 'file' : 'target');
  const [phase, setPhase] = useState(null);        // the target slug the current batch belongs to
  const [file, setFile] = useState(null);          // { name, size, lastModified, buffer } — read once (4a-R16)
  const [batchId, setBatchId] = useState(null);
  const [typed, setTyped] = useState('');
  const [done, setDone] = useState(null);          // the COMMITTED BatchHeader (the last step's)
  const [entitiesDone, setEntitiesDone] = useState(null);   // a book's step 1, once committed
  const [skippedEntities, setSkippedEntities] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const pq = useQuery({ queryKey: keys.importPreview(batchId), queryFn: () => importApi.preview(batchId),
    enabled: batchId != null, staleTime: 30_000 });
  const pv = pq.data;
  const b = pv?.batch;
  const phaseCfg = IMPORT_TARGETS[phase] ?? cfg;
  const inEntities = isBook && phase === 'data-entities';
  // 4a-R10: after step 1 commits, the fields are owed until they commit or "Do fields later".
  const fieldsOwed = isBook && entitiesDone != null && step !== 'done';

  useEffect(() => {
    if (!fieldsOwed) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [fieldsOwed]);

  const say = (err = '', info = '') => { setError(err); setNotice(info); };

  const dl = useMutation({
    mutationFn: (kind) => importApi[kind](projectId, target),
    onSuccess: (name) => say('', t('data.import.downloaded', { name })),
    onError: (err) => say(errorText(err, t('data.import.downloadFailed'))),
  });

  const pick = async (e) => {
    const f = e.target.files?.[0];
    say();
    if (!f) return;
    try {
      if (!/\.xlsx$/i.test(f.name)) { setFile(null); say(t('data.import.notXlsx')); return; }
      if (f.size > MAX_BYTES) { setFile(null); say(t('data.import.tooBig')); return; }
      const buffer = await f.arrayBuffer();
      setFile({ name: f.name, size: f.size, lastModified: f.lastModified, buffer });
    } catch {
      setFile(null);
      say(t('data.import.readFailed'));
    } finally {
      e.target.value = '';                         // the same name can be picked again after an edit
    }
  };

  const staged = (ph, data) => {
    const id = data.batch.import_batch_id;
    qc.setQueryData(keys.importPreview(id), data);
    setPhase(ph);
    setBatchId(id);
    setTyped('');
    setStep('review');
  };

  const upload = useMutation({
    mutationFn: async () => {
      if (!isBook) return { ph: target, data: await importApi.validate(projectId, target, file.buffer, file.name) };
      if (entitiesDone) {                          // a corrected file goes to the fields step alone
        return { ph: 'data-fields', data: await importApi.validate(projectId, 'data-fields', file.buffer, file.name) };
      }
      // The fields sheet's file-level checks first, so a sheet that cannot be read is found
      // before any entity is written; then step 1, or straight to fields with no entities sheet.
      const chk = await importApi.check(projectId, 'data-fields', file.buffer, file.name);
      const hasEntities = chk.other_sheets.some((x) => x.target === 'data-entities');
      const ph = hasEntities ? 'data-entities' : 'data-fields';
      return { ph, skipped: !hasEntities, data: await importApi.validate(projectId, ph, file.buffer, file.name) };
    },
    onSuccess: ({ ph, skipped, data }) => {
      if (skipped !== undefined) setSkippedEntities(skipped);
      staged(ph, data);
      say('', skipped ? t('data.import.model.noEntitiesSheet') : '');
    },
    onError: (err) => say(uploadError(err)),
  });

  // Step 2 of a book: the same buffer, validated against the entities step 1 just made live.
  const fieldsStep = useMutation({
    mutationFn: () => importApi.validate(projectId, 'data-fields', file.buffer, file.name),
    onSuccess: (data) => { staged('data-fields', data); say('', t('data.import.model.entitiesCommitted')); },
    onError: (err) => { setBatchId(null); setStep('file'); say(uploadError(err)); },
  });

  const finish = (header, info = '') => {
    qc.setQueryData(keys.importBatch(header.import_batch_id), header);
    for (const k of (phaseCfg.refresh ?? cfg.refresh)(projectId)) qc.invalidateQueries({ queryKey: k });
    onCommitted?.(header);
    if (inEntities) {                              // step 1 done: on to the fields, same file
      setEntitiesDone(header);
      say('', info);
      fieldsStep.mutate();
      return;
    }
    setDone(header);
    say('', info);
    setStep('done');
  };

  const commit = useMutation({
    mutationFn: () => importApi.commit(batchId, { row_version: b.row_version,
      acknowledged_inserts: b.insert_count > 0 ? Number(typed.trim()) : null }),
    onSuccess: (header) => finish(header),
    onError: async (err) => {
      const s = err?.response?.status;
      if (isStale(err)) { say(t('data.import.stale')); pq.refetch(); return; }
      if (s === 409) {
        // Already committed (here or in another tab) → done; rejected → the preview says why.
        try {
          const h = await importApi.batch(batchId);
          qc.setQueryData(keys.importBatch(batchId), h);
          if (h.status === 'COMMITTED') { finish(h, t('data.import.alreadyCommitted')); return; }
        } catch { /* fall through to the server's message */ }
        say(errorText(err, t('data.import.notCommittable')));
        pq.refetch();
        return;
      }
      if (s === 429) { say(errorText(err, t('data.import.busy'))); return; }
      if (s === 503) { say(errorText(err, t('data.import.retry'))); return; }
      // 422: still VALIDATED (count or errors) or now REJECTED with fresh row errors — re-read either way.
      say(errorText(err, t('data.import.commitFailed')));
      if (s === 422) pq.refetch();
    },
  });

  // Before step 1 commits, a corrected file starts over; after it, it goes to the fields step alone.
  const reupload = () => { setFile(null); setBatchId(null); setTyped(''); say(); setStep('file'); };

  const committable = b && b.status === 'VALIDATED' && b.error_count === 0 && !pv.purged;
  const countOk = !b?.insert_count || typed.trim() === String(b.insert_count);
  const busy = upload.isPending || commit.isPending || fieldsStep.isPending;
  const steps = isBook ? BOOK_STEPS : STEPS;
  const shownStep = isBook && step === 'review' ? (inEntities ? 'entities' : 'fields')
    : isBook && step === 'file' && entitiesDone ? 'fields' : step;
  const closable = !busy && !fieldsOwed;
  const later = () => { say(); onClose(); };

  return (
    <Dialog open onClose={closable ? onClose : undefined} maxWidth="lg" fullWidth>
      <DialogTitle>{t(isBook ? 'data.import.model.title' : 'data.import.title')}</DialogTitle>
      <DialogContent>
        <Stepper activeStep={steps.indexOf(shownStep)} sx={{ mb: 3, mt: 1 }}>
          {steps.map((s) => (
            <Step key={s} completed={s === 'entities' && (entitiesDone != null || skippedEntities) ? true : undefined}>
              <StepLabel optional={s === 'entities' && skippedEntities
                ? <Typography sx={{ fontSize: 12 }}>{t('data.import.model.skipped')}</Typography> : undefined}>
                {t(`data.import.step.${s}`)}
              </StepLabel>
            </Step>))}
        </Stepper>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        {notice && <Alert severity="info" sx={ERR_SX}>{notice}</Alert>}
        {fieldsOwed && step !== 'review' && (
          <Alert severity="warning" sx={ERR_SX}>{t('data.import.model.fieldsOwed', { n: entitiesDone.insert_count })}</Alert>)}

        {step === 'target' && (
          <RadioGroup value={target} onChange={(e) => setTarget(e.target.value)}>
            {targets.map((k) => (
              <FormControlLabel key={k} value={k} control={<Radio id={`import-target-${k}`} />} label={(
                <Box>
                  <Typography sx={{ fontWeight: 600 }}>{t(IMPORT_TARGETS[k].label)}</Typography>
                  <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t(IMPORT_TARGETS[k].help)}</Typography>
                </Box>)} sx={{ alignItems: 'flex-start', mb: 1, '& .MuiRadio-root': { pt: 0.5 } }} />
            ))}
          </RadioGroup>
        )}

        {step === 'file' && (
          <Stack spacing={3}>
            {!entitiesDone && (
              <Box>
                <Typography variant="h6" sx={{ mb: 0.5 }}>{t('data.import.getFile')}</Typography>
                <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1.5 }}>
                  {t(isBook ? 'data.import.model.getFileHelp' : 'data.import.getFileHelp')}
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Button variant="outlined" startIcon={<DownloadRounded />} disabled={dl.isPending}
                    onClick={() => { say(); dl.mutate('template'); }}>{t('data.import.template')}</Button>
                  <Button variant="outlined" startIcon={<DownloadRounded />} disabled={dl.isPending}
                    onClick={() => { say(); dl.mutate('export'); }}>{t('data.import.export')}</Button>
                </Stack>
              </Box>
            )}
            <Box>
              <Typography variant="h6" sx={{ mb: 0.5 }}>{t(entitiesDone ? 'data.import.model.pickFields' : 'data.import.pickFile')}</Typography>
              <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1.5 }}>
                {t(entitiesDone ? 'data.import.model.pickFieldsHelp' : 'data.import.pickFileHelp')}
              </Typography>
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                <Button component="label" variant="outlined" startIcon={<UploadFileRounded />} disabled={busy}>
                  {t(file ? 'data.import.pickOther' : 'data.import.pick')}
                  <input id="import-file" type="file" hidden onChange={pick}
                    accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
                </Button>
                <FileInfo file={file} />
              </Stack>
            </Box>
          </Stack>
        )}

        {step === 'review' && (
          <>
            {file && <Box sx={{ mb: 1 }}><FileInfo file={file} /></Box>}
            {isBook && (
              <Typography sx={{ fontSize: 13.5, fontWeight: 600, mb: 1 }}>
                {t(inEntities ? 'data.import.model.step1' : 'data.import.model.step2')}
              </Typography>)}
            {!pv && !pq.error && <Typography sx={{ color: 'text.secondary' }}>{t('data.import.loading')}</Typography>}
            {pq.error && <Alert severity="error" sx={ERR_SX}>{errorText(pq.error, t('data.loadFailed'))}</Alert>}
            {b?.status === 'REJECTED' && <Alert severity="error" sx={ERR_SX}>{t('data.import.rejected')}</Alert>}
            {b?.status === 'VALIDATED' && b.error_count > 0 && (
              <Alert severity="error" sx={ERR_SX}>
                {t((fieldsOwed ? 'data.import.model.fixFields' : 'data.import.fixErrors')
                  + (b.error_count === 1 ? 'One' : ''), { n: b.error_count })}
              </Alert>)}
            {committable && b.insert_count + b.update_count === 0 && (
              <Alert severity="info" sx={ERR_SX}>{t('data.import.nothingToChange')}</Alert>)}
            {pv && <Preview key={b.import_batch_id} pv={pv} cfg={phaseCfg} />}
            {committable && inEntities && (
              <Alert severity="warning" sx={{ mt: 3, whiteSpace: 'pre-wrap' }}>{t('data.import.model.step1Confirm')}</Alert>)}
            {committable && b.insert_count > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography sx={{ fontSize: 13.5, mb: 1 }}>{t('data.import.confirmBody', { n: b.insert_count })}</Typography>
                <TextField id="import-confirm-count" label={t('data.import.confirmLabel')} value={typed}
                  onChange={(e) => setTyped(e.target.value)} sx={{ width: 220 }}
                  error={typed.trim() !== '' && !countOk}
                  helperText={typed.trim() !== '' && !countOk ? t('data.import.confirmMismatch') : ' '}
                  slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 6 } }} />
              </Box>
            )}
          </>
        )}

        {step === 'done' && done && (
          <Stack spacing={1.5}>
            {file && <FileInfo file={file} />}
            {entitiesDone && (
              <Alert severity="success">
                {t('data.import.model.entitiesSummary', { inserts: entitiesDone.insert_count,
                  updates: entitiesDone.update_count, matches: entitiesDone.match_count })}
              </Alert>)}
            <Alert severity="success">
              {t(isBook ? 'data.import.model.fieldsSummary' : 'data.import.committed',
                { inserts: done.insert_count, updates: done.update_count, matches: done.match_count })}
            </Alert>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {step === 'target' && (
          <>
            <Button onClick={onClose}>{t('common.cancel')}</Button>
            <Button variant="contained" onClick={() => { say(); setStep('file'); }}>{t('data.import.next')}</Button>
          </>
        )}
        {step === 'file' && (
          <>
            {!entitiesDone && <Button onClick={() => { say(); setStep('target'); }} disabled={busy}>{t('data.import.back')}</Button>}
            {fieldsOwed
              ? <Button onClick={later} disabled={busy}>{t('data.import.model.later')}</Button>
              : <Button onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>}
            <Button variant="contained" disabled={!file || busy}
              onClick={() => { say(); upload.mutate(); }}>{t(upload.isPending ? 'data.import.checking' : 'data.import.upload')}</Button>
          </>
        )}
        {step === 'review' && (
          <>
            {fieldsOwed
              ? <Button onClick={later} disabled={busy}>{t('data.import.model.later')}</Button>
              : <Button onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>}
            <Button onClick={reupload} disabled={busy}>
              {t(fieldsOwed ? 'data.import.model.reuploadFields' : 'data.import.reupload')}
            </Button>
            {committable && (
              <Button variant="contained" color="warning" disabled={!countOk || busy}
                onClick={() => { say(); commit.mutate(); }}>
                {t(commit.isPending || fieldsStep.isPending ? 'data.import.committing'
                  : inEntities ? 'data.import.model.commitEntities' : 'data.import.commit')}
              </Button>)}
          </>
        )}
        {step === 'done' && <Button variant="contained" onClick={onClose}>{t('data.import.close')}</Button>}
      </DialogActions>
    </Dialog>
  );
}
