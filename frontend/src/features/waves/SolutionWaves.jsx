import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, IconButton, Stack, TextField, Tooltip, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import LinkOffRounded from '@mui/icons-material/LinkOffRounded';
import { errorText, isStale } from '../../api/client';
import { phaseApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code, ListRow, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';
import { WaveStatus, fmtPct } from './waveKit';

const ERR_SX = { whiteSpace: 'pre-wrap' };
const CANCELLED = 'CANCELLED';            // pinned (R8): a cancelled wave keeps or lowers its share, never gains (T4)

// Hundredths, so the 100 % rule is checked on whole numbers, never a float sum (T3). The server checks it again.
const cents = (v) => Math.round(Number(v) * 100);

/** A solution's split across waves (W-5): edited and saved whole, exactly 100 % or empty. */
export function WaveSplitCard({ projectId, solution, canEdit, notify }) {
  const qc = useQueryClient();
  const split = useQuery({ queryKey: keys.phaseSplit(solution.solution_id), queryFn: () => phaseApi.split(solution.solution_id) });
  const waves = useQuery({ queryKey: [...keys.phases(projectId), { retired: false }], queryFn: () => phaseApi.list(projectId) });
  const { getLabel } = useCodes(projectId, 'PHASE_STATUS');
  const [draft, setDraft] = useState(null);          // null = reading; else [{ phase_id, pct }]
  const [basis, setBasis] = useState([]);            // sara M-A: the rows the draft was opened from (T1)
  const [error, setError] = useState('');
  const rows = split.data?.rows ?? [];
  const live = waves.data ?? [];
  const byId = new Map(live.map((w) => [w.phase_id, w]));
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.phaseSplit(solution.solution_id) });
    qc.invalidateQueries({ queryKey: keys.phases(projectId) });
  };
  const save = useMutation({
    mutationFn: (next) => phaseApi.saveSplit(solution.solution_id, {
      based_on: basis,
      rows: next.map((r) => ({ phase_id: r.phase_id, portion_pct: String(r.pct).trim() })) }),
    onSuccess: () => { setDraft(null); setError(''); refresh(); notify(t('waves.split.saved')); },
    onError: (err) => {
      refresh();
      const conflict = isStale(err) || err?.response?.status === 409;
      if (conflict) setDraft(null);                  // re-open from the fresh rows, so the other save is seen
      setError(conflict ? t('waves.split.stale') : errorText(err, t('common.saveFailed')));
    },
  });
  const editable = canEdit && solution.is_active;
  const total = (draft ?? []).reduce((s, r) => s + (Number.isFinite(Number(r.pct)) ? cents(r.pct) : 0), 0);
  const twoDp = (v) => /^\d+(\.\d{1,2})?$/.test(String(v).trim());
  const filled = (draft ?? []).every((r) => r.phase_id && twoDp(r.pct) && cents(r.pct) > 0);
  const valid = draft && filled && (draft.length === 0 || total === 10000);
  const used = new Set((draft ?? []).map((r) => r.phase_id));
  const pickable = (cur) => live.filter((w) => w.phase_id === cur || (!used.has(w.phase_id) && w.status_code !== CANCELLED))
    .map((w) => ({ value: w.phase_id, label: `${w.phase_code} ${w.phase_name}` }));

  return (
    <Card title={t('waves.split.title')} bodySx={{ gap: 1 }}
      action={editable && !draft && live.length > 0 && (
        <Button size="small" variant="outlined" onClick={() => {
          setError(''); setBasis(rows.map((r) => ({ solution_phase_id: r.solution_phase_id, row_version: r.row_version })));
          setDraft(rows.map((r) => ({ phase_id: r.phase_id, pct: fmtPct(r.portion_pct) })));
        }}>{t('waves.split.edit')}</Button>)}>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('waves.split.help')}</Typography>
      {(error || split.error) && <Alert severity="error" sx={ERR_SX}>{error || errorText(split.error)}</Alert>}
      {!draft && rows.length === 0 && !split.isLoading && (
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>
          {live.length === 0 ? t('waves.split.noWaves') : t('waves.split.none')}</Typography>)}
      {!draft && rows.map((r) => (
        <ListRow key={r.solution_phase_id}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, flex: 1 }}>
            <Code>{r.phase_code}</Code>
            <Typography noWrap sx={{ fontSize: 13.5 }}>{r.phase_name}</Typography>
          </Box>
          <WaveStatus code={r.phase_status_code} label={getLabel(r.phase_status_code)} />
          <Tag tone="purple">{t('waves.plan.share', { pct: fmtPct(r.portion_pct) })}</Tag>
        </ListRow>
      ))}
      {draft && (
        <Stack spacing={1}>
          {draft.map((r, i) => {
            const cancelled = byId.get(r.phase_id)?.status_code === CANCELLED;
            return (
              <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <SimpleSelect id={`split-wave-${i}`} label={t('waves.split.wave')} value={r.phase_id}
                    disabled={cancelled}
                    onChange={(v) => setDraft(draft.map((x, j) => (j === i ? { ...x, phase_id: v } : x)))}
                    options={pickable(r.phase_id)} />
                </Box>
                <TextField id={`split-pct-${i}`} size="small" label={t('waves.split.share')} value={r.pct} sx={{ width: 110 }}
                  slotProps={{ htmlInput: { inputMode: 'decimal' } }}
                  onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, pct: e.target.value } : x)))} />
                <Tooltip title={t('waves.split.remove')}>
                  <IconButton size="small" aria-label={t('waves.split.remove')}
                    onClick={() => setDraft(draft.filter((_, j) => j !== i))}><CloseRounded fontSize="small" /></IconButton>
                </Tooltip>
              </Box>
            );
          })}
          {draft.some((r) => byId.get(r.phase_id)?.status_code === CANCELLED) && (
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('waves.split.cancelledHint')}</Typography>)}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button size="small" startIcon={<AddRounded />} disabled={pickable(null).length === 0}
              onClick={() => setDraft([...draft, { phase_id: '', pct: '' }])}>{t('waves.split.addRow')}</Button>
            <Box sx={{ flex: 1 }} />
            {draft.length > 0 && (
              <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: total === 10000 ? 'text.primary' : 'warning.main' }}>
                {t('waves.split.total', { total: (total / 100).toString() })}</Typography>)}
          </Box>
          {draft.length > 0 && total !== 10000 && (
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('waves.split.mustTotal')}</Typography>)}
          <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {rows.length > 0 && <Button size="small" color="warning" disabled={save.isPending}
              onClick={() => save.mutate([])}>{t('waves.split.clear')}</Button>}
            <Button size="small" onClick={() => { setDraft(null); setError(''); }}>{t('waves.split.cancel')}</Button>
            <Button size="small" variant="contained" disabled={!valid || save.isPending}
              onClick={() => save.mutate(draft)}>{t('waves.split.save')}</Button>
          </Box>
        </Stack>)}
    </Card>
  );
}

/** What this solution depends on (D-18), and what depends on it. A loop is refused by the server, naming it. */
export function DependsOnCard({ projectId, solution, canEdit, notify }) {
  const qc = useQueryClient();
  const deps = useQuery({ queryKey: keys.solutionDeps(solution.solution_id), queryFn: () => phaseApi.deps(solution.solution_id) });
  const sols = useQuery({ queryKey: keys.solutions(projectId), queryFn: () => solutionApi.list(projectId), enabled: canEdit });
  const [pick, setPick] = useState('');
  const [error, setError] = useState('');
  const dependsOn = deps.data?.depends_on ?? [];
  const neededBy = deps.data?.needed_by ?? [];
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.solutionDeps(solution.solution_id) });
    qc.invalidateQueries({ queryKey: keys.allSolutionDeps() });             // the other end's "Needed by"
    qc.invalidateQueries({ queryKey: keys.phasePlan(projectId) });
  };
  const fail = (err) => { refresh(); setError(isStale(err) ? t('waves.stale') : errorText(err, t('common.saveFailed'))); };
  const add = useMutation({
    mutationFn: () => phaseApi.link(solution.solution_id, { depends_on_solution_id: pick }),
    onSuccess: () => { setPick(''); setError(''); refresh(); notify(t('waves.deps.added')); },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (row) => phaseApi.unlink(solution.solution_id, row.solution_dependency_id, row.row_version),
    onSuccess: () => { setError(''); refresh(); notify(t('waves.deps.removed')); },
    onError: fail,
  });
  const editable = canEdit && solution.is_active;
  const taken = new Set(dependsOn.map((d) => d.depends_on_solution_id));
  const options = (sols.data ?? []).filter((s) => s.is_active && s.solution_id !== solution.solution_id
    && !taken.has(s.solution_id)).map((s) => ({ value: s.solution_id, label: `${s.solution_number} ${s.solution_name}` }));

  return (
    <Card title={t('waves.deps.title')} bodySx={{ gap: 1 }}>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('waves.deps.help')}</Typography>
      {(error || deps.error) && <Alert severity="error" sx={ERR_SX}>{error || errorText(deps.error)}</Alert>}
      {!deps.isLoading && dependsOn.length === 0 && (
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('waves.deps.none')}</Typography>)}
      {dependsOn.map((d) => (
        <ListRow key={d.solution_dependency_id}>
          <Box component={RouterLink} to={links.solution(projectId, d.depends_on_solution_id)}
            sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, flex: 1, color: 'inherit', textDecoration: 'none' }}>
            <Code>{d.depends_on_solution_number}</Code>
            <Typography noWrap sx={{ fontSize: 13.5 }}>{d.depends_on_solution_name}</Typography>
          </Box>
          {editable && (
            <Tooltip title={t('waves.deps.remove')}>
              <IconButton size="small" aria-label={t('waves.deps.remove')} disabled={remove.isPending}
                onClick={() => remove.mutate(d)}><LinkOffRounded fontSize="small" /></IconButton>
            </Tooltip>)}
        </ListRow>
      ))}
      {editable && (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 1 }}>
          <SimpleSelect id="dep-pick" label={t('waves.deps.pick')} value={pick} onChange={setPick} options={options} />
          <Button variant="outlined" disabled={!pick || add.isPending} onClick={() => add.mutate()}>{t('waves.deps.add')}</Button>
        </Box>)}
      {neededBy.length > 0 && (
        <Box sx={{ mt: 1 }}>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 0.5 }}>{t('waves.deps.neededBy')}</Typography>
          <Stack direction="row" useFlexGap sx={{ gap: 1, flexWrap: 'wrap' }}>
            {neededBy.map((d) => (
              <Box key={d.solution_dependency_id} component={RouterLink} to={links.solution(projectId, d.solution_id)}
                sx={{ textDecoration: 'none' }}><Code>{d.solution_number}</Code></Box>
            ))}
          </Stack>
        </Box>)}
    </Card>
  );
}
