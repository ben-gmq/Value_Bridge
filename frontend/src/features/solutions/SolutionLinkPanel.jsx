import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Link, Stack,
  TextField, Tooltip, Typography } from '@mui/material';
import EditRounded from '@mui/icons-material/EditRounded';
import LinkOffRounded from '@mui/icons-material/LinkOffRounded';
import { errorText, isStale } from '../../api/client';
import { bfcApi, brApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { t } from '../../i18n/t';
import { Mono, PickDialog, SectionTitle } from '../processes/chartKit';

const NOTE_MAX = 4000;
const ERR_SX = { mb: 1, whiteSpace: 'pre-wrap' };

function NoteField({ value, onChange, autoFocus }) {
  return (
    <TextField id="brsol-note" label={t('solutions.links.note')} helperText={t('solutions.links.noteHint')}
      multiline minRows={2} fullWidth autoFocus={autoFocus} value={value} onChange={(e) => onChange(e.target.value)}
      slotProps={{ htmlInput: { maxLength: NOTE_MAX } }} />
  );
}

function EditNoteDialog({ row, save, onClose, onDone, onStale }) {
  const [note, setNote] = useState(row.coverage_note ?? '');
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => save(row, note.trim() || null),
    onSuccess: () => { onDone(); onClose(); },
    // sara M-1: a stale note closes the dialog and refreshes, so a retry starts from the fresh row.
    onError: (err) => { if (isStale(err)) { onStale(); onClose(); } else setError(errorText(err, t('common.saveFailed'))); },
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('solutions.links.editTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Box sx={{ mt: 1 }}><NoteField value={note} onChange={setNote} autoFocus /></Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending} onClick={() => { setError(''); m.mutate(); }}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/**
 * BR ↔ solution links, from either end (§4.3, docs/slice5_spec.md). `side` is the page's own
 * object: 'br' lists the solutions answering `br`; 'solution' lists the BRs `solution` answers.
 * Every write goes through the link's BR route, so one server rule serves both pages.
 */
export function SolutionLinkPanel({ projectId, side, br, solution, disabled }) {
  const qc = useQueryClient();
  const canEdit = useCanEdit() && !disabled;
  const onBr = side === 'br';
  const { getLabel: categoryLabel } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const { getLabel: statusLabel } = useCodes(projectId, 'SOLUTION_STATUS');
  const ownId = onBr ? br.br_id : solution.solution_id;
  const listKey = [...keys.solutionLinks(), side, String(ownId)];
  const q = useQuery({ queryKey: listKey, queryFn: () => (onBr ? brApi.solutions(ownId) : solutionApi.brs(ownId)) });
  const rows = useMemo(() => q.data ?? [], [q.data]);
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [error, setError] = useState('');

  // The picker's options: the other end's live rows not already linked.
  const solsQ = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId),
    enabled: adding && onBr });
  const brsQ = useQuery({ queryKey: keys.brs(projectId), queryFn: () => brApi.list(projectId), enabled: adding && !onBr });
  const treeQ = useQuery({ queryKey: keys.tree(projectId), queryFn: () => bfcApi.tree(projectId), enabled: adding && !onBr });
  const nodeName = useMemo(() => new Map((treeQ.data ?? []).map((n) => [n.bfc_node_id, n.node_name])), [treeQ.data]);
  const linked = new Set(rows.map((r) => (onBr ? r.solution_id : r.br_id)));
  const options = onBr
    ? (solsQ.data ?? []).filter((s) => !linked.has(s.solution_id))
    : (brsQ.data ?? []).filter((b) => !linked.has(b.br_id));
  const optionLabel = onBr
    ? (s) => `${s.solution_number} ${s.solution_name}`
    : (b) => `${b.br_number} ${nodeName.get(b.bfc_node_id) ?? ''}`.trim();

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.solutionLinks() });
    qc.invalidateQueries({ queryKey: keys.solutions(projectId) });   // the register's counts
  };
  const brIdOf = (row) => (onBr ? br.br_id : row.br_id);
  const unlink = useMutation({
    mutationFn: (row) => brApi.unlinkSolution(brIdOf(row), row.br_solution_id, row.row_version),
    onSuccess: () => { setRemoving(null); setError(''); refresh(); },
    onError: (err) => { setRemoving(null); refresh();
      setError(isStale(err) ? t('solutions.links.stale') : errorText(err, t('common.saveFailed'))); },
  });

  const other = (row) => (onBr ? (
    <Link component={RouterLink} to={links.solution(projectId, row.solution_id)} underline="hover">
      <Mono>{row.solution_number}</Mono> {row.solution_name}</Link>
  ) : (
    <Link component={RouterLink} to={links.requirement(projectId, row.br_id)} underline="hover">
      <Mono>{row.br_number}</Mono> {row.node_name}</Link>
  ));
  const otherText = (row) => (onBr ? `${row.solution_number} ${row.solution_name}` : `${row.br_number} ${row.node_name}`);
  const ownText = onBr ? br.br_number : `${solution.solution_number} ${solution.solution_name}`;

  return (
    <Box>
      <SectionTitle action={canEdit && (
        <Button size="small" onClick={() => { setError(''); setNote(''); setAdding(true); }}>{t('solutions.links.add')}</Button>)}>
        {t(onBr ? 'solutions.links.solutionTitle' : 'solutions.links.brTitle')}
      </SectionTitle>
      {error && <Alert severity="error" sx={ERR_SX} onClose={() => setError('')}>{error}</Alert>}
      {q.error && <Alert severity="error" sx={ERR_SX}>{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
          {t(onBr ? 'solutions.links.noneSolution' : 'solutions.links.noneBr')}</Typography>)}
      <Stack spacing={1.5}>
        {rows.map((row) => (
          <Stack key={row.br_solution_id} direction="row" sx={{ alignItems: 'flex-start', gap: 1 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography component="span" sx={{ fontWeight: 600 }}>{other(row)}</Typography>
                {onBr && <Chip size="small" variant="outlined" label={categoryLabel(row.category_code)} />}
                {onBr && (row.status_code === 'REJECTED' ? (
                  <Tooltip title={t('solutions.links.rejectedTip')}>
                    <Chip size="small" variant="outlined" label={statusLabel(row.status_code)}
                      sx={{ color: 'status.caution', borderColor: 'status.caution' }} />
                  </Tooltip>
                ) : <Chip size="small" label={statusLabel(row.status_code)} />)}
              </Stack>
              {row.coverage_note && (
                <Typography sx={{ fontSize: 13, color: 'text.secondary', mt: 0.5, whiteSpace: 'pre-wrap' }}>
                  {row.coverage_note}</Typography>)}
            </Box>
            {canEdit && (
              <>
                <Tooltip title={t('solutions.links.edit')}>
                  <IconButton size="small" aria-label={t('solutions.links.edit')} onClick={() => { setError(''); setEditing(row); }}>
                    <EditRounded fontSize="small" /></IconButton>
                </Tooltip>
                <Tooltip title={t('solutions.links.remove')}>
                  <IconButton size="small" aria-label={t('solutions.links.remove')} onClick={() => { setError(''); setRemoving(row); }}>
                    <LinkOffRounded fontSize="small" /></IconButton>
                </Tooltip>
              </>)}
          </Stack>
        ))}
      </Stack>

      {adding && (
        <PickDialog open title={t(onBr ? 'solutions.links.addSolutionTitle' : 'solutions.links.addBrTitle')}
          optionLabel={t(onBr ? 'solutions.links.pickSolution' : 'solutions.links.pickBr')}
          options={options} getOptionLabel={optionLabel} submitLabel={t('solutions.links.add')}
          emptyHint={(
            <Alert severity="info">
              {t(onBr ? 'solutions.links.noSolutions' : 'solutions.links.noBrs')}{' '}
              {onBr && <Link component={RouterLink} to={links.solutions(projectId)}>{t('solutions.links.goSolutions')}</Link>}
            </Alert>)}
          extra={<NoteField value={note} onChange={setNote} />}
          onSubmit={(picked) => (onBr
            ? brApi.linkSolution(br.br_id, { solution_id: picked.solution_id, coverage_note: note.trim() || null })
            : brApi.linkSolution(picked.br_id, { solution_id: solution.solution_id, coverage_note: note.trim() || null }))}
          onDone={refresh} onClose={() => setAdding(false)} />)}
      {editing && (
        <EditNoteDialog row={editing} onClose={() => setEditing(null)} onDone={refresh}
          onStale={() => { refresh(); setError(t('solutions.links.stale')); }}
          save={(row, value) => brApi.editSolutionLink(brIdOf(row), row.br_solution_id,
            { row_version: row.row_version, coverage_note: value })} />)}
      <ConfirmDialog open={Boolean(removing)} title={t('solutions.links.removeTitle')}
        body={removing ? t('solutions.links.removeBody', onBr
          ? { br: ownText, solution: otherText(removing) } : { br: otherText(removing), solution: ownText }) : ''}
        confirmLabel={t('solutions.links.remove')} busy={unlink.isPending}
        onClose={() => setRemoving(null)} onConfirm={() => unlink.mutate(removing)} />
    </Box>
  );
}
