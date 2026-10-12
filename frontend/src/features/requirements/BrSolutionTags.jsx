import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Link,
  TextField, Tooltip, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import EditRounded from '@mui/icons-material/EditRounded';
import { errorText, isStale } from '../../api/client';
import { brApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Code, SectionLabel, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { PickDialog } from '../processes/chartKit';
import { pillBox } from './reqKit';

const NOTE_MAX = 4000;
const ERR_SX = { whiteSpace: 'pre-wrap' };

export function NoteField({ value, onChange, autoFocus }) {
  return (
    <TextField id="brsol-note" label={t('solutions.links.note')} helperText={t('solutions.links.noteHint')}
      multiline minRows={2} fullWidth autoFocus={autoFocus} value={value} onChange={(e) => onChange(e.target.value)}
      slotProps={{ htmlInput: { maxLength: NOTE_MAX } }} />
  );
}

export function EditNoteDialog({ row, save, onClose, onDone, onStale }) {
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
 * The solutions answering one requirement, as the mockup's removable tags with "+ Link" (D-51).
 * The same calls and dialogs as the BR side of SolutionLinkPanel: link with a coverage note, edit
 * the note, unlink after a confirm. The note and the solution's category/status sit in the tag's
 * tooltip; a rejected solution is flagged on the tag itself.
 */
export function BrSolutionTags({ projectId, br, disabled, onWarnings }) {
  const qc = useQueryClient();
  const { getLabel: categoryLabel } = useCodes(projectId, 'SOLUTION_CATEGORY');
  const { getLabel: statusLabel } = useCodes(projectId, 'SOLUTION_STATUS');
  const listKey = [...keys.solutionLinks(), 'br', String(br.br_id)];
  const q = useQuery({ queryKey: listKey, queryFn: () => brApi.solutions(br.br_id) });
  const rows = useMemo(() => q.data ?? [], [q.data]);
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [error, setError] = useState('');

  const solsQ = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId), enabled: adding });
  const linked = new Set(rows.map((r) => r.solution_id));
  const options = (solsQ.data ?? []).filter((s) => !linked.has(s.solution_id));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.solutionLinks() });
    qc.invalidateQueries({ queryKey: keys.solutions(projectId) });   // the register's counts
    qc.invalidateQueries({ queryKey: keys.frTrace() });             // each FR row's "answers this BR" flag
  };
  const unlink = useMutation({
    mutationFn: (row) => brApi.unlinkSolution(br.br_id, row.br_solution_id, row.row_version),
    // D-52: the response names any FR whose solution now answers none of its requirements (Q-4).
    onSuccess: (res) => { setRemoving(null); setError(''); refresh(); onWarnings?.(res?.warnings); },
    onError: (err) => { setRemoving(null); refresh();
      setError(isStale(err) ? t('solutions.links.stale') : errorText(err, t('common.saveFailed'))); },
  });
  const solText = (row) => `${row.solution_number} ${row.solution_name}`;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      <SectionLabel>{t('requirements.solutionsTitle')}</SectionLabel>
      {error && <Alert severity="error" sx={ERR_SX} onClose={() => setError('')}>{error}</Alert>}
      {q.error && <Alert severity="error" sx={ERR_SX}>{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('solutions.links.noneSolution')}</Typography>)}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
        {rows.map((row) => {
          const tip = [`${categoryLabel(row.category_code)} · ${statusLabel(row.status_code)}`, row.coverage_note]
            .filter(Boolean).join('\n');
          return (
            <Box key={row.br_solution_id} sx={(th) => ({ ...pillBox(th), bgcolor: th.vars.palette.background.subtle, gap: 0.75,
              minHeight: 32, pl: 1.25, pr: disabled ? 1.25 : 0.5, maxWidth: '100%' })}>
              <Tooltip title={<Box component="span" sx={{ whiteSpace: 'pre-wrap' }}>{tip}</Box>}>
                <Link component={RouterLink} to={links.solution(projectId, row.solution_id)} underline="hover" color="inherit"
                  sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, minWidth: 0, fontSize: 13.5 }}>
                  <Code sx={{ fontSize: 12 }}>{row.solution_number}</Code>
                  <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.solution_name}</Box>
                </Link>
              </Tooltip>
              {row.status_code === 'REJECTED' && (
                <Tooltip title={t('solutions.links.rejectedTip')}>
                  <Box component="span" sx={{ display: 'inline-flex' }}>
                    <Tag tone="caution" sx={{ height: 20, fontSize: 11 }}>{statusLabel(row.status_code)}</Tag></Box>
                </Tooltip>)}
              {!disabled && (
                <>
                  <IconButton size="small" aria-label={t('solutions.links.edit')} title={t('solutions.links.edit')}
                    sx={{ width: 24, height: 24 }} onClick={() => { setError(''); setEditing(row); }}>
                    <EditRounded sx={{ fontSize: 14 }} /></IconButton>
                  <IconButton size="small" aria-label={t('solutions.links.remove')} title={t('solutions.links.remove')}
                    sx={{ width: 24, height: 24 }} onClick={() => { setError(''); setRemoving(row); }}>
                    <CloseRounded sx={{ fontSize: 15 }} /></IconButton>
                </>)}
            </Box>
          );
        })}
        {!disabled && (
          <Button size="small" variant="outlined" startIcon={<AddRounded />}
            onClick={() => { setError(''); setNote(''); setAdding(true); }}>{t('requirements.linkSolution')}</Button>)}
      </Box>

      {adding && (
        <PickDialog open title={t('solutions.links.addSolutionTitle')} optionLabel={t('solutions.links.pickSolution')}
          options={options} getOptionLabel={(s) => `${s.solution_number} ${s.solution_name}`} submitLabel={t('solutions.links.add')}
          emptyHint={(
            <Alert severity="info">
              {t('solutions.links.noSolutions')}{' '}
              <Link component={RouterLink} to={links.solutions(projectId)}>{t('solutions.links.goSolutions')}</Link>
            </Alert>)}
          extra={<NoteField value={note} onChange={setNote} />}
          onSubmit={(picked) => brApi.linkSolution(br.br_id, { solution_id: picked.solution_id, coverage_note: note.trim() || null })}
          onDone={refresh} onClose={() => setAdding(false)} />)}
      {editing && (
        <EditNoteDialog row={editing} onClose={() => setEditing(null)} onDone={refresh}
          onStale={() => { refresh(); setError(t('solutions.links.stale')); }}
          save={(row, value) => brApi.editSolutionLink(br.br_id, row.br_solution_id,
            { row_version: row.row_version, coverage_note: value })} />)}
      <ConfirmDialog open={Boolean(removing)} title={t('solutions.links.removeTitle')}
        body={removing ? t('solutions.links.removeBody', { br: br.br_number, solution: solText(removing) }) : ''}
        confirmLabel={t('solutions.links.remove')} busy={unlink.isPending}
        onClose={() => setRemoving(null)} onConfirm={() => unlink.mutate(removing)} />
    </Box>
  );
}
