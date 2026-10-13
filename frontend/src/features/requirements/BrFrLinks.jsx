import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Link, Stack, TextField,
  Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import EditRounded from '@mui/icons-material/EditRounded';
import LinkRounded from '@mui/icons-material/LinkRounded';
import { errorText, isStale } from '../../api/client';
import { brApi, frApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Code, SectionLabel, Tag } from '../../components/kit';
import { t, tOr } from '../../i18n/t';
import { PickDialog, SimpleSelect } from '../processes/chartKit';
import { EditNoteDialog, NoteField } from './BrSolutionTags';
import { warningList } from '../frs/frKit';

const ERR_SX = { whiteSpace: 'pre-wrap' };
const solLabel = (s) => `${s.solution_number} ${s.solution_name}`;

function NewFrDialog({ projectId, br, brSolutions, solutionsOn, onClose, onDone }) {
  const [f, setF] = useState({ fr_name: '', fr_type_code: '', solution_id: '', description: '' });
  const [error, setError] = useState('');
  const { codes: types } = useCodes(projectId, 'FR_TYPE');
  const m = useMutation({
    // One step: the FR is created and linked to this BR (Q-20). Number, status and behaviour are the server's (law 6).
    mutationFn: () => frApi.create(projectId, { fr_name: f.fr_name.trim(), fr_type_code: f.fr_type_code,
      solution_id: solutionsOn && f.solution_id !== '' ? f.solution_id : null, description: f.description.trim() || null,
      br_id: br.br_id }),
    onSuccess: (fr) => { onDone(fr); onClose(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('requirements.frs.newTitle', { br: br.br_number })}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, ...ERR_SX }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="brfr-new-name" label={t('frs.name')} required autoFocus value={f.fr_name}
            onChange={(e) => setF({ ...f, fr_name: e.target.value })} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <SimpleSelect id="brfr-new-type" label={t('frs.type')} value={f.fr_type_code}
            onChange={(v) => setF({ ...f, fr_type_code: v })} options={types.map((c) => ({ value: c.code, label: c.label }))} />
          {solutionsOn && (
            <SimpleSelect id="brfr-new-solution" label={t('requirements.frs.solution')} value={f.solution_id} allowEmpty
              emptyLabel={t('requirements.frs.noSolution')} onChange={(v) => setF({ ...f, solution_id: v })}
              options={brSolutions.map((s) => ({ value: s.solution_id, label: solLabel(s) }))} />)}
          <TextField id="brfr-new-desc" label={t('frs.description')} multiline minRows={2} value={f.description}
            onChange={(e) => setF({ ...f, description: e.target.value })} slotProps={{ htmlInput: { maxLength: 4000 } }} />
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.frs.newHint', { br: br.br_number })}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        {/* disabled while in flight, so a double click cannot create two (DR6a-P2) */}
        <Button variant="contained" disabled={m.isPending || !f.fr_name.trim() || !f.fr_type_code}
          onClick={() => { setError(''); m.mutate(); }}>{t('common.create')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/**
 * The function requirements one business requirement maps to (D-52) — the stored BR ↔ FR links, made here
 * and nowhere else. Each row: the FR, its type, the solution it delivers through (picked only from this BR's
 * own solutions, or none; hidden when SOLUTION is off), its coverage note, and unlink. Every action is
 * immediate, like solution linking — none of it is part of the process panel's one Save (Slice 10a).
 * The server's drift warnings (`warnings`, kept by the editor so a solution unlink can report too) are shown
 * with their two explicit fixes; nothing is ever fixed implicitly (Q-4, Q-5).
 */
export function BrFrLinks({ projectId, br, disabled, solutionsOn, warnings, setWarnings, onNotice, bare = false }) {
  const qc = useQueryClient();
  const brId = br.br_id;
  const { getLabel: typeLabel } = useCodes(projectId, 'FR_TYPE');
  const q = useQuery({ queryKey: keys.brFrs(brId), queryFn: () => frApi.ofBr(brId) });
  const rows = useMemo(() => q.data ?? [], [q.data]);
  // The BR's own solutions — the same query (and cache) as its Solutions tags.
  const brSolsQ = useQuery({ queryKey: [...keys.solutionLinks(), 'br', String(brId)], queryFn: () => brApi.solutions(brId),
    enabled: solutionsOn });
  const brSols = useMemo(() => brSolsQ.data ?? [], [brSolsQ.data]);
  const solsQ = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId), enabled: solutionsOn });
  const solById = useMemo(() => new Map((solsQ.data ?? []).map((s) => [s.solution_id, s])), [solsQ.data]);
  // The live register's default view: link options, and the FRs a warning names that are not linked here.
  const frsQ = useQuery({ queryKey: keys.frList(projectId), queryFn: () => frApi.list(projectId),
    enabled: !disabled });
  const [linking, setLinking] = useState(false);
  const [note, setNote] = useState('');
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [error, setError] = useState(null);       // { text, addSolutionId?, row? }

  const linkedIds = new Set(rows.map((r) => r.fr_id));
  const linkOptions = (frsQ.data ?? []).filter((f) => f.is_active && !linkedIds.has(f.fr_id));
  const brSolIds = new Set(brSols.map((s) => s.solution_id));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.frTrace() });          // this list and the Coverage panel
    qc.invalidateQueries({ queryKey: keys.frs(projectId) });     // the register's BR counts and tags
    qc.invalidateQueries({ queryKey: keys.solutionLinks() });
    qc.invalidateQueries({ queryKey: keys.effortSummary(projectId) });
  };
  const took = (res) => { const l = warningList(res?.warnings); if (l.length) setWarnings(() => l); };
  const fail = (err) => {
    refresh();
    setError({ text: isStale(err) ? t('requirements.frs.stale') : errorText(err, t('common.saveFailed')) });
  };
  // Drop the FRs a fix has dealt with from the warnings it answered.
  const settle = (frNumber) => setWarnings((ws) => ws.flatMap((w) => {
    if (!w.frs.includes(frNumber)) return [w];
    const frs = w.frs.filter((n) => n !== frNumber);
    return frs.length ? [{ ...w, frs }] : [];
  }));

  const unlink = useMutation({
    mutationFn: (row) => frApi.unlinkFromBr(brId, row.br_function_requirement_id, row.row_version),
    onSuccess: (res, row) => { setRemoving(null); setError(null); refresh(); took(res);
      onNotice?.(t('requirements.frs.unlinked', { fr: row.fr_number })); },
    onError: (err) => { setRemoving(null); fail(err); },
  });
  // The FR's solution tag from this BR's row. A 422 means the solution is not one of this BR's: the message
  // comes with the one explicit fix — add it to this requirement, then set the tag (the server never adds it).
  const tag = useMutation({
    mutationFn: ({ row, solutionId }) => frApi.setSolutionFromBr(brId, row.br_function_requirement_id,
      { solution_id: solutionId, fr_row_version: row.fr_row_version }),
    onSuccess: (res, { row }) => { setError(null); refresh(); took(res); settle(row.fr_number); },
    onError: (err, { row, solutionId }) => {
      if (err?.response?.status === 422 && solutionId != null) {
        refresh();
        setError({ text: errorText(err, t('requirements.frs.notThisBrError')), addSolutionId: solutionId, row });
      } else fail(err);
    },
  });
  const addSolution = useMutation({
    mutationFn: async ({ solutionId, row }) => {
      await brApi.linkSolution(brId, { solution_id: solutionId, coverage_note: null });
      if (!row) return null;
      // The tag write needs the FR's current version: read the row again after the link.
      const fresh = (await frApi.ofBr(brId)).find((r) => r.br_function_requirement_id === row.br_function_requirement_id);
      if (!fresh || fresh.solution_id === solutionId) return null;
      return frApi.setSolutionFromBr(brId, fresh.br_function_requirement_id,
        { solution_id: solutionId, fr_row_version: fresh.fr_row_version });
    },
    onSuccess: (res, { row, frNumber }) => { setError(null); refresh(); took(res); settle(row?.fr_number ?? frNumber); },
    onError: fail,
  });
  // Clearing a tag: through this BR's row when the FR is linked here, else through the FR itself.
  const clear = useMutation({
    mutationFn: ({ row, fr }) => (row
      ? frApi.setSolutionFromBr(brId, row.br_function_requirement_id, { solution_id: null, fr_row_version: row.fr_row_version })
      : frApi.update(fr.fr_id, { row_version: fr.row_version, solution_id: null })),
    onSuccess: (res, { frNumber }) => { setError(null); refresh(); took(res); settle(frNumber); },
    onError: fail,
  });
  const busy = unlink.isPending || tag.isPending || addSolution.isPending || clear.isPending;

  const rowByNumber = new Map(rows.map((r) => [r.fr_number, r]));
  const frByNumber = new Map((frsQ.data ?? []).map((f) => [f.fr_number, f]));
  const solNumber = (id, fallback) => solById.get(id)?.solution_number ?? fallback ?? '';

  // The fixes for one FR whose tag answers none of its BRs: clear it, or add its solution to this BR.
  const fixes = (frNumber) => {
    if (disabled) return null;
    const row = rowByNumber.get(frNumber);
    const fr = frByNumber.get(frNumber);
    const solutionId = row?.solution_id ?? fr?.solution_id;
    if (!solutionId) return null;
    const canAdd = solutionsOn && row && !brSolIds.has(solutionId);
    return (
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        {(row || fr) && (
          <Button size="small" variant="outlined" disabled={busy}
            onClick={() => clear.mutate({ row, fr, frNumber })}>{t('requirements.frs.clearSolution', { fr: frNumber })}</Button>)}
        {canAdd && (
          <Button size="small" variant="outlined" disabled={busy}
            onClick={() => addSolution.mutate({ solutionId, row, frNumber })}>
            {t('requirements.frs.addSolution', { solution: solNumber(solutionId, row?.solution_number) })}</Button>)}
      </Box>
    );
  };

  return (
    <Box component="section" aria-labelledby={bare ? undefined : `brfr-title-${brId}`} aria-label={bare ? t('requirements.frs.title') : undefined}
      sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      {/* `bare`: inside the process panel's section already titled "Function requirements" (10e), only the actions show */}
      {(!bare || !disabled) && <SectionLabel action={!disabled && (
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Button size="small" variant="outlined" startIcon={<LinkRounded />}
            onClick={() => { setError(null); setNote(''); setLinking(true); }}>{t('requirements.frs.link')}</Button>
          <Button size="small" variant="outlined" startIcon={<AddRounded />}
            onClick={() => { setError(null); setCreating(true); }}>{t('requirements.frs.new')}</Button>
        </Box>)}>
        {!bare && <Box component="span" id={`brfr-title-${brId}`}>{t('requirements.frs.title')}</Box>}
      </SectionLabel>}

      {warnings.map((w) => (
        <Alert key={w.code} severity="warning" sx={ERR_SX} onClose={() => setWarnings((ws) => ws.filter((x) => x.code !== w.code))}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <span>{tOr(`requirements.frs.warn.${w.code}`, { frs: w.frs.join(', ') }, w.code)}</span>
            {/* an FR linked here carries its fixes on its own row below; the others get them here */}
            {w.code === 'fr_solution_outside_its_brs' && w.frs.filter((n) => !rowByNumber.has(n))
              .map((n) => <Box key={n}>{fixes(n)}</Box>)}
          </Box>
        </Alert>
      ))}
      {error && (
        <Alert severity="error" sx={ERR_SX} onClose={() => setError(null)}
          action={!disabled && solutionsOn && error.addSolutionId != null ? (
            <Button color="inherit" size="small" disabled={busy}
              onClick={() => addSolution.mutate({ solutionId: error.addSolutionId, row: error.row })}>
              {t('requirements.frs.addSolution', { solution: solNumber(error.addSolutionId) })}</Button>) : undefined}>
          {error.text}
        </Alert>)}
      {q.error && <Alert severity="error" sx={ERR_SX}>{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.frs.none')}</Typography>)}

      {rows.map((row) => {
        const outside = row.solution_id != null && row.tag_answers_this_br === false;
        const options = brSols.map((s) => ({ value: s.solution_id, label: solLabel(s) }));
        if (row.solution_id != null && !brSolIds.has(row.solution_id)) {
          options.push({ value: row.solution_id,
            label: t('requirements.frs.otherSolution', { solution: `${row.solution_number ?? ''} ${row.solution_name ?? ''}`.trim() }) });
        }
        return (
          <Box key={row.br_function_requirement_id} sx={(th) => ({ display: 'flex', flexDirection: 'column', gap: 1, p: 1.5,
            borderRadius: '14px', bgcolor: th.vars.palette.background.subtle, minWidth: 0 })}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', minWidth: 0 }}>
              <Link component={RouterLink} to={links.fr(projectId, row.fr_id)} underline="hover"><Code>{row.fr_number}</Code></Link>
              <Typography noWrap sx={{ fontSize: 13.5, fontWeight: 600, flex: '1 1 140px', minWidth: 0 }} title={row.fr_name}>
                {row.fr_name}</Typography>
              {row.fr_type_code && <Tag tone="navy" size="lg">{typeLabel(row.fr_type_code)}</Tag>}
              {!disabled && (
                <Box sx={{ display: 'inline-flex' }}>
                  <IconButton size="small" aria-label={t('requirements.frs.editNote')} title={t('requirements.frs.editNote')}
                    disabled={busy} onClick={() => { setError(null); setEditing(row); }}><EditRounded sx={{ fontSize: 16 }} /></IconButton>
                  <IconButton size="small" aria-label={t('requirements.frs.unlink')} title={t('requirements.frs.unlink')}
                    disabled={busy} onClick={() => { setError(null); setRemoving(row); }}><CloseRounded sx={{ fontSize: 17 }} /></IconButton>
                </Box>)}
            </Box>
            {solutionsOn && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', minWidth: 0 }}>
                {disabled ? (
                  <Typography sx={{ fontSize: 13, color: 'text.secondary', display: 'inline-flex', gap: 0.75, alignItems: 'baseline' }}>
                    {t('requirements.frs.solution')}:
                    {row.solution_id != null ? (
                      <Link component={RouterLink} to={links.solution(projectId, row.solution_id)} underline="hover" color="inherit"
                        sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'baseline' }}>
                        <Code sx={{ fontSize: 12.5 }}>{row.solution_number}</Code>{row.solution_name}</Link>
                    ) : <span>{t('requirements.frs.noSolution')}</span>}
                  </Typography>
                ) : (
                  <Box sx={{ width: 300, maxWidth: '100%' }}>
                    <SimpleSelect id={`brfr-sol-${row.br_function_requirement_id}`} label={t('requirements.frs.solution')}
                      value={row.solution_id ?? ''} allowEmpty emptyLabel={t('requirements.frs.noSolution')} options={options}
                      onChange={(v) => {
                        const next = v === '' ? null : v;
                        if (busy || next === (row.solution_id ?? null)) return;
                        setError(null);
                        tag.mutate({ row, solutionId: next });
                      }} />
                  </Box>)}
                {outside && <Tag tone="caution" size="lg">{t('requirements.frs.notThisBr')}</Tag>}
                {outside && fixes(row.fr_number)}
              </Box>)}
            {row.coverage_note && (
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {row.coverage_note}</Typography>)}
          </Box>
        );
      })}

      {linking && (
        <PickDialog open title={t('requirements.frs.linkTitle')} optionLabel={t('requirements.frs.pick')}
          options={linkOptions} getOptionLabel={(f) => `${f.fr_number} ${f.fr_name}`} submitLabel={t('requirements.frs.linkSubmit')}
          emptyHint={<Alert severity="info">{t('requirements.frs.noneToLink')}</Alert>}
          extra={<NoteField value={note} onChange={setNote} />}
          onSubmit={(picked) => frApi.linkToBr(brId, { fr_id: picked.fr_id, coverage_note: note.trim() || null })}
          onDone={(res) => { refresh(); took(res); onNotice?.(t('requirements.frs.linked', { fr: res?.fr_number ?? '' })); }}
          onClose={() => setLinking(false)} />)}
      {creating && (
        <NewFrDialog projectId={projectId} br={br} brSolutions={brSols} solutionsOn={solutionsOn}
          onClose={() => setCreating(false)}
          onDone={(fr) => { refresh(); took(fr); onNotice?.(t('requirements.frs.created', { fr: fr?.fr_number ?? '' })); }} />)}
      {editing && (
        <EditNoteDialog row={editing} onClose={() => setEditing(null)} onDone={refresh}
          onStale={() => { refresh(); setError({ text: t('requirements.frs.stale') }); }}
          save={(row, value) => frApi.editBrLink(brId, row.br_function_requirement_id,
            { row_version: row.row_version, coverage_note: value })} />)}
      <ConfirmDialog open={Boolean(removing)} title={t('requirements.frs.unlinkTitle')}
        body={removing ? t('requirements.frs.unlinkBody', { fr: `${removing.fr_number} ${removing.fr_name}`, br: br.br_number }) : ''}
        confirmLabel={t('requirements.frs.unlink')} busy={unlink.isPending}
        onClose={() => setRemoving(null)} onConfirm={() => unlink.mutate(removing)} />
    </Box>
  );
}
