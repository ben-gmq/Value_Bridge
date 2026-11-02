// Shared pieces of the risk screens (slice Risks, §4.10): the pick lists a risk points at, the exposure tag and the
// fields of the raise / edit form. Strings: en.risks.json.
import { useQuery } from '@tanstack/react-query';
import { Box, TextField } from '@mui/material';
import { bfcApi, controlApi, orgApi, phaseApi, solutionApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { useComponents } from '../../app/useComponents';
import { Status } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';

// Everything a risk can point at, retired rows included so a risk already pointing at one still names it.
export function useRiskRefs(projectId) {
  const { isOn } = useComponents(projectId);
  const roles = useQuery({ queryKey: [...keys.roles(projectId), { retired: true }],
    queryFn: () => orgApi.roles(projectId, true) });
  const waves = useQuery({ queryKey: [...keys.phases(projectId), { retired: true }],
    queryFn: () => phaseApi.list(projectId, true), enabled: isOn('PHASING') });
  const sols = useQuery({ queryKey: [...keys.solutions(projectId), { retired: true }],
    queryFn: () => solutionApi.list(projectId, true), enabled: isOn('SOLUTION') });
  const tree = useQuery({ queryKey: [...keys.tree(projectId), { retired: true }],
    queryFn: () => bfcApi.tree(projectId, true) });
  const rules = useQuery({ queryKey: keys.controlRules(projectId), queryFn: () => controlApi.rules(projectId) });
  const rule = (rules.data ?? []).find((r) => r.analysis_code === 'risk_register');
  const name = (list, id, idKey, label) => {
    const row = (list ?? []).find((x) => x[idKey] === id);
    return row ? label(row) : '';
  };
  const roleLabel = (r) => `${r.org_role_code} · ${r.org_role_name}`;
  const waveLabel = (w) => `${w.phase_code} · ${w.phase_name}`;
  const solLabel = (s) => `${s.solution_number} ${s.solution_name}`;
  const nodeLabel = (n) => `${n.hier_code} ${n.node_name}`;
  const options = (list, idKey, label, current) => (list ?? []).filter((x) => x.is_active || x[idKey] === current)
    .map((x) => ({ value: x[idKey], label: label(x) + (x.is_active ? '' : ` (${t('risks.retiredRef')})`) }));
  return {
    rule, waveOn: isOn('PHASING'), solutionOn: isOn('SOLUTION'), issueOn: isOn('ISSUE'),
    roleName: (id) => name(roles.data, id, 'org_role_id', roleLabel),
    waveName: (id) => name(waves.data, id, 'phase_id', waveLabel),
    roleOptions: (cur) => options(roles.data, 'org_role_id', roleLabel, cur),
    waveOptions: (cur) => options(waves.data, 'phase_id', waveLabel, cur),
    solutionOptions: (cur) => options(sols.data, 'solution_id', solLabel, cur),
    nodeOptions: (cur) => options(tree.data, 'bfc_node_id', nodeLabel, cur),
    error: roles.error || tree.error,
  };
}

// R1-6: coloured only from the project's own risk_register rule, and plain while that rule is off (not yet agreed).
export function ExposureTag({ score, open, rule, size = 'sm' }) {
  let tone = 'neutral';
  if (open && rule?.is_enabled) {
    if (rule.escalate_value != null && score >= Number(rule.escalate_value)) tone = 'escalate';
    else if (score >= Number(rule.threshold_value)) tone = 'caution';
  }
  return <Status tone={tone} size={size}>{score}</Status>;
}

const grid = { display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'repeat(2, minmax(0,1fr))' } };

// The form fields, shared by the raise dialog and the risk page. `lock` disables everything except the four
// re-pointable links (a materialised risk, R2 NEW-1); `disabled` disables all.
export function RiskFields({ projectId, refs, v, set, disabled = false, lock = false, idPrefix = 'rsk' }) {
  const prob = useCodes(projectId, 'RISK_PROBABILITY');
  const imp = useCodes(projectId, 'RISK_IMPACT');
  const fixed = disabled || lock;
  const codes = (c, current) => c.options(current).map((x) => ({ value: x.code, label: x.label }));
  const text = (name, extra = {}) => (
    <TextField fullWidth size="small" id={`${idPrefix}-${name}`} label={t(`risks.field.${name}`)} disabled={fixed}
      value={v[name] ?? ''} onChange={(e) => set(name, e.target.value)} {...extra} />
  );
  const pick = (name, options, off = fixed, allowEmpty = true) => (
    <SimpleSelect id={`${idPrefix}-${name}`} label={t(`risks.field.${name}`)} value={v[name] ?? ''} disabled={off}
      allowEmpty={allowEmpty} onChange={(c) => set(name, c)} options={options} />
  );
  return (
    <>
      {text('title', { required: true, slotProps: { htmlInput: { maxLength: 200 } } })}
      {text('description', { multiline: true, minRows: 2 })}
      <Box sx={grid}>
        {pick('probability_code', codes(prob, v.probability_code), fixed, false)}
        {pick('impact_code', codes(imp, v.impact_code), fixed, false)}
        {pick('owner_org_role_id', refs.roleOptions(v.owner_org_role_id), disabled, false)}
        {text('raised_date', { type: 'date', slotProps: { inputLabel: { shrink: true } } })}
        {text('target_date', { type: 'date', slotProps: { inputLabel: { shrink: true } } })}
        {refs.waveOn && pick('phase_id', refs.waveOptions(v.phase_id), disabled)}
        {refs.solutionOn && pick('solution_id', refs.solutionOptions(v.solution_id), disabled)}
        {pick('bfc_node_id', refs.nodeOptions(v.bfc_node_id), disabled)}
      </Box>
      {text('mitigation', { multiline: true, minRows: 2, helperText: t('risks.mitigationHelp') })}
    </>
  );
}
