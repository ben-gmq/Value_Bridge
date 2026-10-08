import { useState } from 'react';
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
 * count → commit. Everything a target changes lives in IMPORT_TARGETS, so 4a-2 adds data-fields
 * there. Every server text (messages, params, names, cell values) is untrusted and renders as text.
 */
export const IMPORT_TARGETS = {
  'data-entities': {
    label: 'data.import.target.entities',
    help: 'data.import.target.entitiesHelp',
    // Column codes the server's messages and changes name → the labels the screens already use.
    columns: { de_number: 'data.number', de_name: 'data.name', description: 'data.description',
      business_owner_note: 'data.ownerNote', row_token: 'data.import.col.rowToken' },
    refresh: (p) => [keys.entities(p)],          // what a commit makes stale
  },
};

const MAX_BYTES = 10 * 1024 * 1024;              // the server's ingress cap (§4 validate, step 2)
const PAGE = 100;
const STEPS = ['target', 'file', 'review', 'done'];
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
                <TableCell sx={{ width: 110 }}>{t('data.import.col.key')}</TableCell>
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
                  <TableCell sx={{ fontFamily: MONO, fontSize: 13 }}>{r.business_key ?? t('data.none')}</TableCell>
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

export function ImportWizard({ projectId, targets = Object.keys(IMPORT_TARGETS), onClose, onCommitted }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState(targets[0]);
  const cfg = IMPORT_TARGETS[target];
  const [step, setStep] = useState('target');
  const [file, setFile] = useState(null);          // { name, size, lastModified, buffer } — read once (4a-R16)
  const [batchId, setBatchId] = useState(null);
  const [typed, setTyped] = useState('');
  const [done, setDone] = useState(null);          // the COMMITTED BatchHeader
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const pq = useQuery({ queryKey: keys.importPreview(batchId), queryFn: () => importApi.preview(batchId),
    enabled: batchId != null, staleTime: 30_000 });
  const pv = pq.data;
  const b = pv?.batch;

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

  const upload = useMutation({
    mutationFn: () => importApi.validate(projectId, target, file.buffer, file.name),
    onSuccess: (data) => {
      const id = data.batch.import_batch_id;
      qc.setQueryData(keys.importPreview(id), data);
      setBatchId(id);
      setTyped('');
      say();
      setStep('review');
    },
    onError: (err) => say(uploadError(err)),
  });

  const finish = (header, info = '') => {
    qc.setQueryData(keys.importBatch(header.import_batch_id), header);
    for (const k of cfg.refresh(projectId)) qc.invalidateQueries({ queryKey: k });
    setDone(header);
    say('', info);
    setStep('done');
    onCommitted?.(header);
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

  const reupload = () => { setFile(null); setBatchId(null); setTyped(''); say(); setStep('file'); };

  const committable = b && b.status === 'VALIDATED' && b.error_count === 0 && !pv.purged;
  const countOk = !b?.insert_count || typed.trim() === String(b.insert_count);
  const busy = upload.isPending || commit.isPending;

  return (
    <Dialog open onClose={busy ? undefined : onClose} maxWidth="lg" fullWidth>
      <DialogTitle>{t('data.import.title')}</DialogTitle>
      <DialogContent>
        <Stepper activeStep={STEPS.indexOf(step)} sx={{ mb: 3, mt: 1 }}>
          {STEPS.map((s) => <Step key={s}><StepLabel>{t(`data.import.step.${s}`)}</StepLabel></Step>)}
        </Stepper>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        {notice && <Alert severity="info" sx={ERR_SX}>{notice}</Alert>}

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
            <Box>
              <Typography variant="h6" sx={{ mb: 0.5 }}>{t('data.import.getFile')}</Typography>
              <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1.5 }}>{t('data.import.getFileHelp')}</Typography>
              <Stack direction="row" spacing={1}>
                <Button variant="outlined" startIcon={<DownloadRounded />} disabled={dl.isPending}
                  onClick={() => { say(); dl.mutate('template'); }}>{t('data.import.template')}</Button>
                <Button variant="outlined" startIcon={<DownloadRounded />} disabled={dl.isPending}
                  onClick={() => { say(); dl.mutate('export'); }}>{t('data.import.export')}</Button>
              </Stack>
            </Box>
            <Box>
              <Typography variant="h6" sx={{ mb: 0.5 }}>{t('data.import.pickFile')}</Typography>
              <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1.5 }}>{t('data.import.pickFileHelp')}</Typography>
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
            {!pv && !pq.error && <Typography sx={{ color: 'text.secondary' }}>{t('data.import.loading')}</Typography>}
            {pq.error && <Alert severity="error" sx={ERR_SX}>{errorText(pq.error, t('data.loadFailed'))}</Alert>}
            {b?.status === 'REJECTED' && <Alert severity="error" sx={ERR_SX}>{t('data.import.rejected')}</Alert>}
            {b?.status === 'VALIDATED' && b.error_count > 0 && (
              <Alert severity="error" sx={ERR_SX}>{t('data.import.fixErrors', { n: b.error_count })}</Alert>)}
            {committable && b.insert_count + b.update_count === 0 && (
              <Alert severity="info" sx={ERR_SX}>{t('data.import.nothingToChange')}</Alert>)}
            {pv && <Preview key={b.import_batch_id} pv={pv} cfg={cfg} />}
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
          <Alert severity="success">
            {t('data.import.committed', { inserts: done.insert_count, updates: done.update_count, matches: done.match_count })}
          </Alert>
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
            <Button onClick={() => { say(); setStep('target'); }} disabled={busy}>{t('data.import.back')}</Button>
            <Button onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
            <Button variant="contained" disabled={!file || busy}
              onClick={() => { say(); upload.mutate(); }}>{t(upload.isPending ? 'data.import.checking' : 'data.import.upload')}</Button>
          </>
        )}
        {step === 'review' && (
          <>
            <Button onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
            <Button onClick={reupload} disabled={busy}>{t('data.import.reupload')}</Button>
            {committable && (
              <Button variant="contained" color="warning" disabled={!countOk || busy}
                onClick={() => { say(); commit.mutate(); }}>{t(commit.isPending ? 'data.import.committing' : 'data.import.commit')}</Button>)}
          </>
        )}
        {step === 'done' && <Button variant="contained" onClick={onClose}>{t('data.import.close')}</Button>}
      </DialogActions>
    </Dialog>
  );
}
