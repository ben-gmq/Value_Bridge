import { useEffect, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Stack, TextField, Tooltip, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import AddRounded from '@mui/icons-material/AddRounded';
import { errorText } from '../../api/client';
import { appApi, bfcApi, chartApi, orgApi, triggerApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { t } from '../../i18n/t';
import { Mono, SectionTitle, SimpleSelect, blankToNull } from './chartKit';
import { LoadError } from './StepSections';
import { Segmented } from '../../components/kit';

const KINDS = ['ORG_UNIT', 'ORG_ROLE', 'APPLICATION', 'AI'];

/** Refresh everything a step's DFD facts feed: the node, the chart, every DFD and its gaps. */
function useRefresh(projectId, nodeId) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.node(nodeId) });
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });
  };
}

/** The performer as one line ("FIN Finance"), from the lists the editor loads too — null when unset. */
export function usePerformerText(projectId, node) {
  const units = useQuery({ queryKey: keys.units(projectId), queryFn: () => orgApi.units(projectId) });
  const roles = useQuery({ queryKey: keys.roles(projectId), queryFn: () => orgApi.roles(projectId) });
  const apps = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId) });
  const text = (() => {
    switch (node.performer_kind) {
      case 'ORG_UNIT': { const u = (units.data ?? []).find((x) => x.org_unit_id === node.performer_org_unit_id); return u?.org_unit_name; }
      case 'ORG_ROLE': { const r = (roles.data ?? []).find((x) => x.org_role_id === node.performer_org_role_id); return r?.org_role_name; }
      case 'APPLICATION': { const a = (apps.data ?? []).find((x) => x.application_id === node.performer_application_id); return a?.application_name; }
      case 'AI': return node.performer_label;
      default: return null;
    }
  })();
  return { text, units, roles, apps };
}

/** Who or what performs the step — the step's lane on the DFD (D-46): a department, a position,
 * an IT system (chosen by code) or an AI (named). One per step.
 * SP-1 (Ben, 2026-10-14) — one save model: a choice saves the moment it is made, the AI's name on Enter or on
 * leaving the field. No Save or Cancel here; the editor's Done only closes. */
export function PerformerPanel({ projectId, node, disabled, onDraftChange }) {
  const refresh = useRefresh(projectId, node.bfc_node_id);
  const { text: current, units, roles, apps } = usePerformerText(projectId, node);
  const saved = node.performer_kind ?? '';
  const savedLabel = (node.performer_label ?? '').trim();
  const [kind, setKind] = useState(saved);
  const [label, setLabel] = useState(node.performer_label ?? '');
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  // What is stored wins: after a save (or on another step) the pickers show the server's row.
  useEffect(() => { setKind(node.performer_kind ?? ''); setLabel(node.performer_label ?? ''); },
    [node.bfc_node_id, node.row_version, node.performer_kind, node.performer_label]);

  const savedCode = {
    ORG_UNIT: (units.data ?? []).find((u) => u.org_unit_id === node.performer_org_unit_id)?.org_unit_code,
    ORG_ROLE: (roles.data ?? []).find((r) => r.org_role_id === node.performer_org_role_id)?.org_role_code,
    APPLICATION: (apps.data ?? []).find((a) => a.application_id === node.performer_application_id)?.application_code,
  }[saved] ?? '';
  // Active rows, plus the stored one even if it was retired since, so the picker can show it.
  const live = (rows, code) => (rows ?? []).filter((r) => r.is_active || (r[code] === savedCode && savedCode));
  const options = {
    ORG_UNIT: live(units.data, 'org_unit_code').map((u) => ({ value: u.org_unit_code, label: `${u.org_unit_code} ${u.org_unit_name}` })),
    ORG_ROLE: live(roles.data, 'org_role_code').map((r) => ({ value: r.org_role_code, label: `${r.org_role_code} ${r.org_role_name}` })),
    APPLICATION: live(apps.data, 'application_code').map((a) => ({ value: a.application_code, label: `${a.application_code} ${a.application_name}` })),
  };
  const m = useMutation({
    mutationFn: (body) => bfcApi.setPerformer(node.bfc_node_id, { row_version: node.row_version, ...body }),
    onSuccess: (row) => { setError('');
      setWarning(row.warnings?.includes('TO_BE_APPLICATION_PERFORMS_AS_IS') ? t('processes.performer.toBeWarning') : '');
      refresh(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const save = (k, c, l) => { if (m.isPending) return; setError('');
    m.mutate({ performer_kind: k || null, code: k && k !== 'AI' ? c : null, performer_label: k === 'AI' ? blankToNull(l) : null }); };
  // "Nobody yet" saves at once; a department, position or IT system saves when its code is chosen; an AI when named.
  const onKind = (v) => { setKind(v); setError(''); if (v === '' && saved !== '') save('', null, null); };
  const onCode = (c) => { if (c && (kind !== saved || c !== savedCode)) save(kind, c, null); };
  const aiDraft = kind === 'AI' && Boolean(label.trim()) && !(saved === 'AI' && label.trim() === savedLabel);
  const commitLabel = () => { if (aiDraft) save('AI', null, label); };
  // Only a typed AI name not yet saved is a draft (SP-1: typed text); the panel's leave guard counts it.
  const draft = aiDraft && !m.isPending;
  useEffect(() => { onDraftChange?.(draft); }, [draft, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  return (
    <Box>
      <SectionTitle info={t('processes.performer.help')}>{null}</SectionTitle>
      <LoadError errors={[units.error, roles.error, apps.error]} />
      {warning && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setWarning('')}>{warning}</Alert>}
      {disabled && (node.performer_kind
        ? <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip size="small" label={t(`processes.performer.kind.${node.performer_kind}`)} />
            <Typography sx={{ fontWeight: 600 }}>{current ?? '…'}</Typography>
          </Stack>
        : <Typography sx={{ fontSize: 14, color: 'text.secondary' }}>{t('processes.performer.none')}</Typography>)}
      {!disabled && (
        <Stack spacing={1.5}>
          {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
          <SimpleSelect id={`performer-kind-${node.bfc_node_id}`} label={t('processes.performer.kindLabel')} value={kind} allowEmpty
            emptyLabel={t('processes.performer.unassigned')} onChange={onKind} disabled={m.isPending}
            options={KINDS.map((k) => ({ value: k, label: t(`processes.performer.kind.${k}`) }))} />
          {kind && kind !== 'AI' && (
            <SimpleSelect id={`performer-code-${node.bfc_node_id}`} label={t(`processes.performer.kind.${kind}`)}
              value={kind === saved ? savedCode : ''} onChange={onCode} options={options[kind]} disabled={m.isPending} />)}
          {kind === 'AI' && (
            <TextField id={`performer-label-${node.bfc_node_id}`} size="small" label={t('processes.performer.aiLabel')} value={label}
              autoFocus={saved !== 'AI'} disabled={m.isPending} helperText={t('processes.performer.aiHint')}
              onChange={(e) => setLabel(e.target.value)} onBlur={commitLabel}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); commitLabel(); }
                if (e.key === 'Escape') { e.stopPropagation(); setLabel(node.performer_label ?? ''); }
              }}
              slotProps={{ htmlInput: { maxLength: 200 } }} />)}
        </Stack>
      )}
    </Box>
  );
}

/** The time or event triggers that start the step (D-49): picked from the project's catalogue, or
 * added to it here. A trigger counts as the step's input.
 * SP-1 (Ben, 2026-10-14): picking a trigger adds it at once; a new trigger saves on Enter or when focus leaves
 * its little form (Esc discards it). A name already in the catalogue links that trigger — never a second copy. */
export function TriggerPanel({ projectId, node, disabled, onDraftChange }) {
  const qc = useQueryClient();
  const refresh = useRefresh(projectId, node.bfc_node_id);
  const linkKey = keys.stepTriggers(node.bfc_node_id);
  const links_ = useQuery({ queryKey: linkKey, queryFn: () => bfcApi.triggers(node.bfc_node_id) });
  const cat = useQuery({ queryKey: keys.triggers(projectId), queryFn: () => triggerApi.list(projectId) });
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState('EVENT');
  const [schedule, setSchedule] = useState('');
  const [error, setError] = useState('');
  const busy = useRef(false);                       // Enter then blur must create one trigger, not two
  const nameRef = useRef('');                        // read at commit, so Esc's reset wins over a late blur
  const done = () => { setError(''); qc.invalidateQueries({ queryKey: linkKey }); qc.invalidateQueries({ queryKey: keys.triggers(projectId) }); refresh(); };
  const fail = (err) => setError(errorText(err, t('common.saveFailed')));
  const linked = new Set((links_.data ?? []).map((r) => r.process_trigger_id));
  const link = useMutation({ mutationFn: (id) => bfcApi.linkTrigger(node.bfc_node_id, { process_trigger_id: id }),
    onSuccess: done, onError: fail });
  const typeName = (v) => { nameRef.current = v; setName(v); };
  const reset = () => { nameRef.current = ''; setAdding(false); setName(''); setSchedule(''); setKind('EVENT'); };
  const create = useMutation({
    mutationFn: async (body) => {
      const same = (cat.data ?? []).find((c) => c.trigger_name.trim().toLowerCase() === body.trigger_name.toLowerCase());
      const id = same ? same.process_trigger_id : (await triggerApi.create(projectId, body)).process_trigger_id;
      return linked.has(id) ? null : bfcApi.linkTrigger(node.bfc_node_id, { process_trigger_id: id });
    },
    onSuccess: () => { reset(); done(); }, onError: fail, onSettled: () => { busy.current = false; } });
  const unlink = useMutation({ mutationFn: (row) => bfcApi.unlinkTrigger(node.bfc_node_id, row.bfc_node_trigger_id, row.row_version),
    onSuccess: done, onError: fail });
  const commit = () => {
    const n = nameRef.current.trim();
    if (!n || busy.current) return;
    busy.current = true;
    create.mutate({ trigger_name: n, trigger_kind: kind, schedule_note: kind === 'TIME' ? blankToNull(schedule) : null });
  };
  const keyDown = (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { e.stopPropagation(); reset(); }
  };
  // Only a typed name not yet saved is a draft (SP-1: typed text); the panel's leave guard counts it.
  const draft = adding && Boolean(name.trim()) && !create.isPending;
  useEffect(() => { onDraftChange?.(draft); }, [draft, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  const free = (cat.data ?? []).filter((c) => !linked.has(c.process_trigger_id));
  return (
    <Box>
      {/* 10e: the tile above already says "Started by"; the editor keeps only its (i) */}
      <SectionTitle info={t('processes.trigger.help')}>{null}</SectionTitle>
      <LoadError errors={[links_.error, cat.error]} />
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 1, mb: 1 }}>
        {(links_.data ?? []).length === 0 && <Typography sx={{ fontSize: 13 }}>{t('processes.trigger.none')}</Typography>}
        {(links_.data ?? []).map((r) => (
          <Chip key={r.bfc_node_trigger_id} variant="outlined" sx={{ maxWidth: '100%' }}
            label={`${r.trigger_row.trigger_name} · ${t(`processes.trigger.kind.${r.trigger_row.trigger_kind}`)}`
              + (r.trigger_row.schedule_note ? ` (${r.trigger_row.schedule_note})` : '')}
            onDelete={disabled || unlink.isPending ? undefined : () => unlink.mutate(r)}
            deleteIcon={<Tooltip title={t('processes.trigger.remove')}><CloseIcon /></Tooltip>} />
        ))}
      </Stack>
      {!disabled && !adding && (
        // 10e (VB-005 UAT 10a): the picker shrinks first and the button never does, so nothing passes the panel's edge
        <Stack direction="row" useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1, minWidth: 0 }}>
          <Box sx={{ flex: '1 1 180px', minWidth: 0, maxWidth: 360 }}>
            <SimpleSelect id={`trigger-pick-${node.bfc_node_id}`} label={t('processes.trigger.pick')} value=""
              disabled={link.isPending} onChange={(id) => id && link.mutate(id)}
              options={free.map((c) => ({ value: c.process_trigger_id, label: c.trigger_name }))} />
          </Box>
          <Button size="small" startIcon={<AddRounded />} sx={{ flex: 'none', whiteSpace: 'nowrap' }} onClick={() => setAdding(true)}>
            {t('processes.trigger.new')}</Button>
        </Stack>
      )}
      {!disabled && adding && (
        // Focus leaving this group (Done, another tile, the tree) saves the typed trigger; moving inside it does not.
        <Stack spacing={1.5} sx={{ mt: 1 }} onKeyDown={keyDown}
          onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) commit(); }}>
          <TextField id={`trigger-name-${node.bfc_node_id}`} size="small" label={t('processes.trigger.name')} value={name} autoFocus
            disabled={create.isPending} onChange={(e) => typeName(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <Segmented size="sm" label={t('processes.trigger.kindLabel')} value={kind} onChange={setKind}
            options={['EVENT', 'TIME'].map((k) => ({ value: k, label: t(`processes.trigger.kind.${k}`) }))} />
          {kind === 'TIME' && (
            <TextField id={`trigger-schedule-${node.bfc_node_id}`} size="small" label={t('processes.trigger.schedule')} value={schedule}
              disabled={create.isPending} onChange={(e) => setSchedule(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />)}
          <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.trigger.newHint')}</Typography>
        </Stack>
      )}
    </Box>
  );
}

// D-70: one list per element of the chart's DFD rule (empty when the element is off the rule), then the performer
// warning. The per-diagram outside-party check shows on the DFD list only (Q-16).
const GAP_KINDS = ['missing_input', 'missing_data_in', 'missing_output', 'missing_order', 'no_performer'];

/** The gaps of the steps under one parent (§9.7): a step missing an element of its chart's DFD rule blocks the
 * baseline freeze while that chart's DFD is used (D-38, D-70, S7-3); no performer only warns. */
export function CompletenessPanel({ projectId, node }) {
  const q = useQuery({ queryKey: [...keys.flowGaps(projectId), node.bfc_set_code],
    queryFn: () => chartApi.completeness(projectId, node.bfc_set_code) });
  const under = (r) => r.hier_code === node.hier_code || r.hier_code.startsWith(`${node.hier_code}.`);
  const gaps = GAP_KINDS.map((k) => [k, (q.data?.[k] ?? []).filter(under)]).filter(([, rs]) => rs.length);
  return (
    <Box>
      <SectionTitle info={t('processes.gapsHelp')}>{t('processes.gapsTitle')}</SectionTitle>
      <LoadError errors={[q.error]} />
      {q.data && !q.data.rule_applies && <Typography sx={{ fontSize: 13, mb: 1 }}>{t('processes.gapsRuleOff')}</Typography>}
      {q.data && gaps.length === 0 && <Typography sx={{ fontSize: 13 }}>{t('processes.gapsNone')}</Typography>}
      <Stack spacing={1.5}>
        {gaps.map(([k, rs]) => (
          <Box key={k}>
            <Typography component="div" sx={{ fontSize: 13, fontWeight: 600 }}>
              {t('processes.gapCount', { what: t(`processes.gap.${k}`), n: rs.length })}
              {k !== 'no_performer' && q.data.rule_applies && <Chip size="small" color="warning" variant="outlined" sx={{ ml: 1 }}
                label={t('processes.gapBlocksFreeze')} />}
            </Typography>
            <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 0.75, mt: 0.5 }}>
              {rs.map((r) => (
                <Chip key={r.bfc_node_id} size="small" variant="outlined" clickable component={RouterLink}
                  to={links.node(projectId, r.bfc_node_id, node.bfc_set_code)} label={<><Mono>{r.hier_code}</Mono> {r.node_name}</>} />
              ))}
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

/** Start an empty chart by copying the other one (Q-24): a preview with the counts, then confirm. */
export function CopyChartButton({ projectId, toSet, fromSet, onCopied }) {
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const m = useMutation({ mutationFn: (hash) => chartApi.copy(projectId, toSet, fromSet, hash),
    onSuccess: (res) => { setError(''); if (res.applied) { setPreview(null); onCopied(res); } else setPreview(res); },
    onError: (err) => { setPreview(null); setError(errorText(err, t('common.saveFailed'))); } });
  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      {!preview && <Button variant="outlined" disabled={m.isPending} onClick={() => m.mutate(null)}>
        {t(`processes.chart.copyFrom.${fromSet}`)}</Button>}
      {preview && (
        <Alert severity="info" action={(
          <Stack direction="row" spacing={1}>
            <Button size="small" onClick={() => setPreview(null)}>{t('common.cancel')}</Button>
            <Button size="small" variant="contained" disabled={m.isPending} onClick={() => m.mutate(preview.confirm_hash)}>
              {t('processes.chart.copy')}</Button>
          </Stack>)}>
          {t(toSet === 'TO_BE' ? 'processes.chart.copyPreviewToBe' : 'processes.chart.copyPreview', { nodes: preview.nodes,
            processes: preview.processes, data: preview.step_data, triggers: preview.triggers, requirements: preview.new_requirements })}
        </Alert>
      )}
    </Box>
  );
}

