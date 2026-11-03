// A 409 (stale version, an overlapping seed, a moved price) shows the server's reason and refreshes the page behind.
// The change-request page's dialogs and seed editor (§4.11 set_cr_seeds, decide_cr, correct_cr_decision). Every
// figure here is the server's; the cover shown in the decide dialog is a preview, the server re-checks it (CR-3).
import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, TextField,
  Tooltip, Typography } from '@mui/material';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import { errorText, isStale } from '../../api/client';
import { brApi, changeApi, frApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';
import { OUTCOMES, days } from './changeKit';

const ERR_SX = { mb: 2, whiteSpace: 'pre-wrap' };
const today = () => new Date().toLocaleDateString('en-CA');
const seedKey = (s) => `${s.kind}-${s.id}`;
export const seedsOf = (cr) => cr.seeds.map((s) => ({ kind: s.kind, id: s.object_id, impact_type_code: s.impact_type_code }));

// CR-1: seeds are BRs and FRs only; the whole list is saved in one PUT, which clears the trace and price.
export function SeedsCard({ projectId, cr, editable, onSaved, onStale }) {
  const brs = useQuery({ queryKey: keys.brs(projectId), queryFn: () => brApi.list(projectId), enabled: editable });
  const frs = useQuery({ queryKey: keys.frs(projectId), queryFn: () => frApi.list(projectId), enabled: editable });
  const typ = useCodes(projectId, 'CR_IMPACT_TYPE');
  const [list, setList] = useState(() => seedsOf(cr));
  const [pick, setPick] = useState({ kind: 'FR', id: '', impact_type_code: '' });
  const [error, setError] = useState('');
  const base = useMemo(() => JSON.stringify(seedsOf(cr)), [cr]);
  const dirty = JSON.stringify(list) !== base;
  const names = useMemo(() => {
    const out = {};
    for (const s of cr.seeds) out[seedKey({ kind: s.kind, id: s.object_id })] = { number: s.number, name: s.name, retired: s.object_retired };
    for (const b of brs.data ?? []) out[`BR-${b.br_id}`] = { number: b.br_number, name: b.br_statement ?? '', retired: !b.is_active };
    for (const f of frs.data ?? []) out[`FR-${f.fr_id}`] = { number: f.fr_number, name: f.fr_name, retired: !f.is_active };
    return out;
  }, [cr.seeds, brs.data, frs.data]);
  const objects = (pick.kind === 'BR' ? brs.data ?? [] : frs.data ?? []).filter((x) => x.is_active)
    .filter((x) => !list.some((s) => s.kind === pick.kind && s.id === (pick.kind === 'BR' ? x.br_id : x.fr_id)))
    .map((x) => (pick.kind === 'BR'
      ? { value: x.br_id, label: `${x.br_number} ${(x.br_statement ?? '').slice(0, 80)}` }
      : { value: x.fr_id, label: `${x.fr_number} ${x.fr_name}` }));
  const m = useMutation({
    mutationFn: () => changeApi.seeds(cr.change_request_id, { row_version: cr.row_version,
      seeds: list.map((s) => ({ [s.kind === 'BR' ? 'br_id' : 'fr_id']: s.id, impact_type_code: s.impact_type_code })) }),
    onSuccess: (row) => { setError(''); onSaved(row); },
    onError: (err) => { setError(errorText(err, t('common.saveFailed'))); if (isStale(err)) onStale(); },
  });
  const add = () => { setList([...list, { kind: pick.kind, id: pick.id, impact_type_code: pick.impact_type_code }]);
    setPick({ ...pick, id: '' }); };
  return (
    <Card title={t('changes.seedsTitle')} bodySx={{ gap: 1.25 }}
      action={editable && dirty && (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setList(seedsOf(cr))} disabled={m.isPending}>{t('changes.discard')}</Button>
          <Button size="small" variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('changes.saveSeeds')}</Button>
        </Stack>)}>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('changes.seedsHelp')}</Typography>
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
      {list.length === 0 && <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('changes.noSeeds')}</Typography>}
      {list.map((s) => {
        const n = names[seedKey(s)] ?? {};
        const priced = cr.seeds.find((x) => x.kind === s.kind && x.object_id === s.id && x.impact_type_code === s.impact_type_code);
        return (
          <Box key={seedKey(s)} sx={{ display: 'flex', gap: 1, alignItems: 'center', fontSize: 13.5 }}>
            <Code tone={n.retired ? 'muted' : 'navy'}>{n.number ?? '…'}</Code>
            <Typography noWrap sx={{ flex: 1, minWidth: 0, fontSize: 13.5 }}>{n.name}</Typography>
            {n.retired && <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('changes.retiredMark')}</Typography>}
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary', width: 70 }}>{typ.getLabel(s.impact_type_code)}</Typography>
            {s.kind === 'FR' && priced && (
              <Typography sx={{ fontSize: 12.5, width: 160, textAlign: 'right' }}>
                {t('changes.seedDays', { agreed: priced.agreed_effort_days ?? '–', live: priced.live_effort_days ?? '–' })}
                {' · '}{days(priced.effort_delta_days)}</Typography>)}
            {editable && (
              <Tooltip title={t('changes.removeSeed')}>
                <IconButton size="small" aria-label={t('changes.removeSeed')}
                  onClick={() => setList(list.filter((x) => seedKey(x) !== seedKey(s)))}><DeleteOutlineRounded fontSize="small" /></IconButton>
              </Tooltip>)}
          </Box>);
      })}
      {editable && (
        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: '90px minmax(0,1fr) 120px auto', alignItems: 'center', mt: 1 }}>
          <SimpleSelect id="cr-seed-kind" label={t('changes.seedKind')} value={pick.kind}
            onChange={(v) => setPick({ ...pick, kind: v, id: '' })}
            options={[{ value: 'FR', label: t('changes.kind.FR') }, { value: 'BR', label: t('changes.kind.BR') }]} />
          <SimpleSelect id="cr-seed-object" label={t('changes.seedObject')} value={pick.id}
            onChange={(v) => setPick({ ...pick, id: v })} options={objects} />
          <SimpleSelect id="cr-seed-type" label={t('changes.seedType')} value={pick.impact_type_code}
            onChange={(v) => setPick({ ...pick, impact_type_code: v })}
            options={typ.options().map((c) => ({ value: c.code, label: c.label }))} />
          <Button variant="outlined" disabled={pick.id === '' || !pick.impact_type_code} onClick={add}>{t('changes.addSeed')}</Button>
        </Box>)}
    </Card>
  );
}

// decide_cr: outcome, date, rationale, alternative; an approved increase needs a cut and/or a budget record (CR-3).
export function DecideDialog({ projectId, cr, onClose, onDone, onStale }) {
  const sts = useCodes(projectId, 'CR_STATUS');
  const all = useQuery({ queryKey: [...keys.changes(projectId), { include_retired: false }],
    queryFn: () => changeApi.list(projectId, { include_retired: false }) });
  const [f, setF] = useState({ outcome_code: '', decided_on: today(), rationale: '', alternative_rejected: '',
    displaces_cr_id: '', budget_reference: '', budget_approved_by: '' });
  const [error, setError] = useState('');
  const set = (k, v) => setF((cur) => ({ ...cur, [k]: v }));
  const rows = all.data ?? [];
  const used = new Set(rows.map((r) => r.displaces_cr_id).filter(Boolean));
  const cuts = rows.filter((r) => r.status_behaviour === 'APPROVED' && Number(r.effort_delta_days) < 0
    && r.against_baseline_id === cr.against_baseline_id && !used.has(r.change_request_id));
  const outcomes = sts.options().filter((c) => OUTCOMES.includes(c.behaviour_code)
    && !(c.behaviour_code === 'DEFERRED' && cr.status_behaviour === 'DEFERRED'));
  const behaviour = sts.codes.find((c) => c.code === f.outcome_code)?.behaviour_code;
  const delta = Number(cr.effort_delta_days ?? 0);
  const increase = behaviour === 'APPROVED' && delta > 0;
  const cut = cuts.find((c) => c.change_request_id === f.displaces_cr_id);
  const left = increase ? Math.max(0, delta + (cut ? Number(cut.effort_delta_days) : 0)) : 0;
  const budget = increase && left > 0;
  const m = useMutation({
    mutationFn: () => changeApi.decide(cr.change_request_id, {
      row_version: cr.row_version, outcome_code: f.outcome_code, decided_on: f.decided_on || null,
      rationale: f.rationale.trim(), alternative_rejected: f.alternative_rejected.trim(),
      displaces_cr_id: increase && f.displaces_cr_id !== '' ? f.displaces_cr_id : null,
      budget_reference: budget ? f.budget_reference.trim() : null,
      budget_approved_by: budget ? f.budget_approved_by.trim() : null }),
    onSuccess: (row) => { onDone(row); onClose(); },
    onError: (err) => { setError(errorText(err, t('common.saveFailed'))); if (isStale(err)) onStale(); },
  });
  const ready = f.outcome_code && f.rationale.trim() && f.alternative_rejected.trim()
    && (!budget || (f.budget_reference.trim() && f.budget_approved_by.trim()));
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('changes.decideTitle', { number: cr.cr_number })}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mb: 1 }}>
          {t('changes.decideBody', { delta: days(cr.effort_delta_days) })}</Typography>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
            <SimpleSelect id="cr-decide-outcome" label={t('changes.field.outcome')} value={f.outcome_code}
              onChange={(v) => set('outcome_code', v)} options={outcomes.map((c) => ({ value: c.code, label: c.label }))} />
            <TextField id="cr-decide-on" type="date" size="small" label={t('changes.field.decided_on')} value={f.decided_on}
              onChange={(e) => set('decided_on', e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          </Box>
          {behaviour === 'APPROVED' && !(cr.priced_at && cr.unrated_fr_count === 0) && (
            <Alert severity="info">{t('changes.needPriced')}</Alert>)}
          <TextField id="cr-decide-rationale" size="small" fullWidth required multiline minRows={2}
            label={t('changes.field.decisionRationale')} value={f.rationale} onChange={(e) => set('rationale', e.target.value)} />
          <TextField id="cr-decide-alternative" size="small" fullWidth required multiline minRows={2}
            label={t('changes.field.alternative_rejected')} value={f.alternative_rejected}
            onChange={(e) => set('alternative_rejected', e.target.value)} />
          {increase && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{t('changes.coverTitle')}</Typography>
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('changes.coverHelp')}</Typography>
              <SimpleSelect id="cr-decide-cut" label={t('changes.field.cut')} value={f.displaces_cr_id} allowEmpty
                emptyLabel={t('changes.noCut')} onChange={(v) => set('displaces_cr_id', v)}
                options={cuts.map((c) => ({ value: c.change_request_id,
                  label: `${c.cr_number} ${c.title} (${days(c.effort_delta_days)})` }))} />
              {cuts.length === 0 && <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('changes.noCuts')}</Typography>}
              {budget ? (
                <>
                  <Alert severity="warning">{t('changes.budgetNeeded', { n: left.toFixed(2) })}</Alert>
                  <TextField id="cr-decide-budget-ref" size="small" fullWidth required label={t('changes.field.budget_reference')}
                    value={f.budget_reference} onChange={(e) => set('budget_reference', e.target.value)}
                    slotProps={{ htmlInput: { maxLength: 200 } }} />
                  <TextField id="cr-decide-budget-by" size="small" fullWidth required label={t('changes.field.budget_approved_by')}
                    value={f.budget_approved_by} onChange={(e) => set('budget_approved_by', e.target.value)}
                    slotProps={{ htmlInput: { maxLength: 200 } }} />
                </>
              ) : <Alert severity="success">{t('changes.covered')}</Alert>}
            </Box>)}
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('changes.decidePermanent')}</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !ready}
          onClick={() => { setError(''); m.mutate(); }}>{t('changes.decide')}</Button>
      </DialogActions>
    </Dialog>
  );
}

// correct_cr_decision: a superseding decision with the same outcome; the CR then points at it.
export function CorrectDialog({ cr, onClose, onDone, onStale }) {
  const [f, setF] = useState({ decided_on: cr.decided_on ?? today(), rationale: '', alternative_rejected: '' });
  const [error, setError] = useState('');
  const m = useMutation({
    mutationFn: () => changeApi.correct(cr.change_request_id, { row_version: cr.row_version, decided_on: f.decided_on || null,
      rationale: f.rationale.trim(), alternative_rejected: f.alternative_rejected.trim() }),
    onSuccess: (row) => { onDone(row); onClose(); },
    onError: (err) => { setError(errorText(err, t('common.saveFailed'))); if (isStale(err)) onStale(); },
  });
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('changes.correctTitle', { number: cr.decision_number })}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={ERR_SX}>{error}</Alert>}
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary', mb: 1 }}>
          {t('changes.correctBody', { number: cr.decision_number })}</Typography>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField id="cr-correct-on" type="date" size="small" label={t('changes.field.decided_on')} value={f.decided_on}
            onChange={(e) => setF({ ...f, decided_on: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField id="cr-correct-rationale" size="small" fullWidth required multiline minRows={2}
            label={t('changes.field.decisionRationale')} value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} />
          <TextField id="cr-correct-alternative" size="small" fullWidth required multiline minRows={2}
            label={t('changes.field.alternative_rejected')} value={f.alternative_rejected}
            onChange={(e) => setF({ ...f, alternative_rejected: e.target.value })} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={m.isPending || !f.rationale.trim() || !f.alternative_rejected.trim()}
          onClick={() => { setError(''); m.mutate(); }}>{t('changes.correct')}</Button>
      </DialogActions>
    </Dialog>
  );
}
