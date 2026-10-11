import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Stack, TextField, Tooltip, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { errorText } from '../../api/client';
import { appApi, bfcApi, chartApi, orgApi, triggerApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { t } from '../../i18n/t';
import { Mono, SectionTitle, SimpleSelect, blankToNull } from './chartKit';
import { LoadError } from './StepSections';

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

/** Who or what performs the step — the step's lane on the DFD (D-46): a department, a position,
 * an IT system (chosen by code) or an AI (named). One per step. */
export function PerformerPanel({ projectId, node, disabled }) {
  const refresh = useRefresh(projectId, node.bfc_node_id);
  const units = useQuery({ queryKey: keys.units(projectId), queryFn: () => orgApi.units(projectId) });
  const roles = useQuery({ queryKey: keys.roles(projectId), queryFn: () => orgApi.roles(projectId) });
  const apps = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId) });
  const [editing, setEditing] = useState(false);
  const [kind, setKind] = useState(node.performer_kind ?? '');
  const [code, setCode] = useState('');
  const [label, setLabel] = useState(node.performer_label ?? '');
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');

  const options = {
    ORG_UNIT: (units.data ?? []).filter((u) => u.is_active).map((u) => ({ value: u.org_unit_code, label: `${u.org_unit_code} ${u.org_unit_name}` })),
    ORG_ROLE: (roles.data ?? []).filter((r) => r.is_active).map((r) => ({ value: r.org_role_code, label: `${r.org_role_code} ${r.org_role_name}` })),
    APPLICATION: (apps.data ?? []).filter((a) => a.is_active).map((a) => ({ value: a.application_code, label: `${a.application_code} ${a.application_name}` })),
  };
  const current = (() => {
    switch (node.performer_kind) {
      case 'ORG_UNIT': { const u = (units.data ?? []).find((x) => x.org_unit_id === node.performer_org_unit_id); return u && `${u.org_unit_code} ${u.org_unit_name}`; }
      case 'ORG_ROLE': { const r = (roles.data ?? []).find((x) => x.org_role_id === node.performer_org_role_id); return r && `${r.org_role_code} ${r.org_role_name}`; }
      case 'APPLICATION': { const a = (apps.data ?? []).find((x) => x.application_id === node.performer_application_id); return a && `${a.application_code} ${a.application_name}`; }
      case 'AI': return node.performer_label;
      default: return null;
    }
  })();
  const m = useMutation({
    mutationFn: () => bfcApi.setPerformer(node.bfc_node_id, { row_version: node.row_version,
      performer_kind: kind || null, code: kind && kind !== 'AI' ? code : null, performer_label: kind === 'AI' ? blankToNull(label) : null }),
    onSuccess: (row) => { setEditing(false); setError('');
      setWarning(row.warnings?.includes('TO_BE_APPLICATION_PERFORMS_AS_IS') ? t('processes.performer.toBeWarning') : '');
      refresh(); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });
  const ready = kind === '' || (kind === 'AI' ? label.trim() : code);
  return (
    <Box>
      <SectionTitle action={!disabled && !editing && (
        <Button size="small" onClick={() => { setEditing(true); setKind(node.performer_kind ?? ''); setCode(''); }}>
          {t('processes.performer.change')}</Button>)}>{t('processes.performer.title')}</SectionTitle>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1 }}>{t('processes.performer.help')}</Typography>
      <LoadError errors={[units.error, roles.error, apps.error]} />
      {warning && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setWarning('')}>{warning}</Alert>}
      {!editing && (node.performer_kind
        ? <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip size="small" label={t(`processes.performer.kind.${node.performer_kind}`)} />
            <Typography sx={{ fontWeight: 600 }}>{current ?? '…'}</Typography>
          </Stack>
        : <Alert severity="warning">{t('processes.performer.none')}</Alert>)}
      {editing && (
        <Stack spacing={1.5}>
          {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
          <SimpleSelect id="performer-kind" label={t('processes.performer.kindLabel')} value={kind} allowEmpty
            emptyLabel={t('processes.performer.unassigned')} onChange={(v) => { setKind(v); setCode(''); }}
            options={KINDS.map((k) => ({ value: k, label: t(`processes.performer.kind.${k}`) }))} />
          {kind && kind !== 'AI' && (
            <SimpleSelect id="performer-code" label={t(`processes.performer.kind.${kind}`)} value={code}
              onChange={setCode} options={options[kind]} />)}
          {kind === 'AI' && (
            <TextField id="performer-label" size="small" label={t('processes.performer.aiLabel')} value={label}
              onChange={(e) => setLabel(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />)}
          <Stack direction="row" spacing={1}>
            <Button variant="contained" size="small" disabled={!ready || m.isPending} onClick={() => m.mutate()}>{t('common.save')}</Button>
            <Button size="small" onClick={() => { setEditing(false); setError(''); }}>{t('common.cancel')}</Button>
          </Stack>
        </Stack>
      )}
    </Box>
  );
}

/** The time or event triggers that start the step (D-49): picked from the project's catalogue, or
 * added to it here. A trigger counts as the step's input. */
export function TriggerPanel({ projectId, node, disabled }) {
  const qc = useQueryClient();
  const refresh = useRefresh(projectId, node.bfc_node_id);
  const linkKey = keys.stepTriggers(node.bfc_node_id);
  const links_ = useQuery({ queryKey: linkKey, queryFn: () => bfcApi.triggers(node.bfc_node_id) });
  const cat = useQuery({ queryKey: keys.triggers(projectId), queryFn: () => triggerApi.list(projectId) });
  const [pick, setPick] = useState('');
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState('EVENT');
  const [schedule, setSchedule] = useState('');
  const [error, setError] = useState('');
  const done = () => { setError(''); qc.invalidateQueries({ queryKey: linkKey }); qc.invalidateQueries({ queryKey: keys.triggers(projectId) }); refresh(); };
  const fail = (err) => setError(errorText(err, t('common.saveFailed')));
  const link = useMutation({ mutationFn: (id) => bfcApi.linkTrigger(node.bfc_node_id, { process_trigger_id: id }),
    onSuccess: () => { setPick(''); done(); }, onError: fail });
  const create = useMutation({
    mutationFn: async () => {
      const row = await triggerApi.create(projectId, { trigger_name: name.trim(), trigger_kind: kind,
        schedule_note: kind === 'TIME' ? blankToNull(schedule) : null });
      return bfcApi.linkTrigger(node.bfc_node_id, { process_trigger_id: row.process_trigger_id });
    },
    onSuccess: () => { setAdding(false); setName(''); setSchedule(''); done(); }, onError: fail });
  const unlink = useMutation({ mutationFn: (row) => bfcApi.unlinkTrigger(node.bfc_node_id, row.bfc_node_trigger_id, row.row_version),
    onSuccess: done, onError: fail });
  const linked = new Set((links_.data ?? []).map((r) => r.process_trigger_id));
  const free = (cat.data ?? []).filter((c) => !linked.has(c.process_trigger_id));
  return (
    <Box>
      <SectionTitle>{t('processes.trigger.title')}</SectionTitle>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1 }}>{t('processes.trigger.help')}</Typography>
      <LoadError errors={[links_.error, cat.error]} />
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 1, mb: 1 }}>
        {(links_.data ?? []).length === 0 && <Typography sx={{ fontSize: 13 }}>{t('processes.trigger.none')}</Typography>}
        {(links_.data ?? []).map((r) => (
          <Chip key={r.bfc_node_trigger_id} variant="outlined"
            label={`${r.trigger_row.trigger_name} · ${t(`processes.trigger.kind.${r.trigger_row.trigger_kind}`)}`
              + (r.trigger_row.schedule_note ? ` (${r.trigger_row.schedule_note})` : '')}
            onDelete={disabled ? undefined : () => unlink.mutate(r)}
            deleteIcon={<Tooltip title={t('processes.trigger.remove')}><CloseIcon /></Tooltip>} />
        ))}
      </Stack>
      {!disabled && !adding && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Box sx={{ minWidth: 240 }}>
            <SimpleSelect id="trigger-pick" label={t('processes.trigger.pick')} value={pick} onChange={setPick}
              options={free.map((c) => ({ value: c.process_trigger_id, label: c.trigger_name }))} />
          </Box>
          <Button size="small" variant="outlined" disabled={!pick || link.isPending} onClick={() => link.mutate(pick)}>
            {t('processes.trigger.link')}</Button>
          <Button size="small" onClick={() => setAdding(true)}>{t('processes.trigger.new')}</Button>
        </Stack>
      )}
      {!disabled && adding && (
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          <TextField id="trigger-name" size="small" label={t('processes.trigger.name')} value={name}
            onChange={(e) => setName(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <SimpleSelect id="trigger-kind" label={t('processes.trigger.kindLabel')} value={kind} onChange={setKind}
            options={['EVENT', 'TIME'].map((k) => ({ value: k, label: t(`processes.trigger.kind.${k}`) }))} />
          {kind === 'TIME' && (
            <TextField id="trigger-schedule" size="small" label={t('processes.trigger.schedule')} value={schedule}
              onChange={(e) => setSchedule(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />)}
          <Stack direction="row" spacing={1}>
            <Button variant="contained" size="small" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
              {t('processes.trigger.addAndLink')}</Button>
            <Button size="small" onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
          </Stack>
        </Stack>
      )}
    </Box>
  );
}

const GAP_KINDS = ['missing_input', 'missing_output', 'no_performer'];

/** The gaps of the steps under one parent (§9.7): with no input or trigger, or no output, a step
 * blocks the baseline freeze while its chart's DFD is used (D-38, S7-3); no performer only warns. */
export function CompletenessPanel({ projectId, node }) {
  const q = useQuery({ queryKey: [...keys.flowGaps(projectId), node.bfc_set_code],
    queryFn: () => chartApi.completeness(projectId, node.bfc_set_code) });
  const under = (r) => r.hier_code === node.hier_code || r.hier_code.startsWith(`${node.hier_code}.`);
  const gaps = GAP_KINDS.map((k) => [k, (q.data?.[k] ?? []).filter(under)]).filter(([, rs]) => rs.length);
  return (
    <Box>
      <SectionTitle>{t('processes.gapsTitle')}</SectionTitle>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1 }}>{t('processes.gapsHelp')}</Typography>
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

