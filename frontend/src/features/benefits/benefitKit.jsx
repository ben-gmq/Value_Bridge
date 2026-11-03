// Shared pieces of the benefit screens (slice Benefits, D-14): the pick lists, the form fields, the tabs between the
// register, the ranking and the gap, and the solution page's read-only list. Strings: en.benefits.json.
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Autocomplete, Box, Link, Stack, TextField, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { benefitApi, orgApi, solutionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code, Segmented } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';

export function useBenefitRefs(projectId) {
  const roles = useQuery({ queryKey: [...keys.roles(projectId), { retired: true }],
    queryFn: () => orgApi.roles(projectId, true) });
  const sols = useQuery({ queryKey: [...keys.solutions(projectId), { retired: true }],
    queryFn: () => solutionApi.list(projectId, true) });
  const all = useQuery({ queryKey: [...keys.benefits(projectId), { units: true }],
    queryFn: () => benefitApi.list(projectId) });
  const roleLabel = (r) => `${r.org_role_code} · ${r.org_role_name}`;
  const solLabel = (s) => `${s.solution_number} ${s.solution_name}`;
  const options = (list, idKey, label, current) => (list ?? []).filter((x) => x.is_active || x[idKey] === current)
    .map((x) => ({ value: x[idKey], label: label(x) + (x.is_active ? '' : ` (${t('benefits.retiredRef')})`) }));
  // BN-6: the project's own units first, one spelling per case-insensitive key.
  const units = [...new Map((all.data ?? []).map((b) => [b.measure_unit.trim().toLowerCase(), b.measure_unit.trim()]))
    .values()].sort();
  return {
    roleName: (id) => { const r = (roles.data ?? []).find((x) => x.org_role_id === id); return r ? roleLabel(r) : ''; },
    roleOptions: (cur) => options(roles.data, 'org_role_id', roleLabel, cur),
    solutionOptions: (taken = []) => (sols.data ?? []).filter((s) => s.is_active && !taken.includes(s.solution_id))
      .map((s) => ({ value: s.solution_id, label: solLabel(s) })),
    units,
    error: roles.error || sols.error || all.error,
  };
}

const grid = { display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', sm: 'repeat(2, minmax(0,1fr))' } };

// The form fields, shared by the new-benefit dialog and the benefit page.
export function BenefitFields({ projectId, refs, v, set, disabled = false, idPrefix = 'ben' }) {
  const typ = useCodes(projectId, 'BENEFIT_TYPE');
  const text = (name, extra = {}) => (
    <TextField fullWidth size="small" id={`${idPrefix}-${name}`} label={t(`benefits.field.${name}`)} disabled={disabled}
      value={v[name] ?? ''} onChange={(e) => set(name, e.target.value)} {...extra} />
  );
  const num = (name) => text(name, { type: 'number', required: true, slotProps: { htmlInput: { step: '0.01' } } });
  return (
    <>
      {text('benefit_name', { required: true, slotProps: { htmlInput: { maxLength: 200 } } })}
      {text('description', { multiline: true, minRows: 2 })}
      <Box sx={grid}>
        <SimpleSelect id={`${idPrefix}-benefit_type_code`} label={t('benefits.field.benefit_type_code')}
          value={v.benefit_type_code ?? ''} disabled={disabled} onChange={(c) => set('benefit_type_code', c)}
          options={typ.options(v.benefit_type_code).map((x) => ({ value: x.code, label: x.label }))} />
        <SimpleSelect id={`${idPrefix}-accountable_org_role_id`} label={t('benefits.field.accountable_org_role_id')}
          value={v.accountable_org_role_id ?? ''} disabled={disabled} onChange={(c) => set('accountable_org_role_id', c)}
          options={refs.roleOptions(v.accountable_org_role_id)} />
        {text('measure_name', { required: true, slotProps: { htmlInput: { maxLength: 200 } } })}
        {/* The typed text is the value (free text, BN-6), so it is controlled through inputValue. Autocomplete's own
            slot props carry the input's ref: ours are merged into them, never put in their place. */}
        <Autocomplete freeSolo id={`${idPrefix}-measure_unit`} disabled={disabled} options={refs.units}
          inputValue={v.measure_unit ?? ''} onInputChange={(_, val) => set('measure_unit', val)}
          renderInput={(params) => (
            <TextField {...params} size="small" required
              label={t('benefits.field.measure_unit')} helperText={t('benefits.unitHelp')}
              slotProps={{ ...params.slotProps,
                htmlInput: { ...params.inputProps, ...params.slotProps?.htmlInput, maxLength: 40 } }} />)} />
        {num('baseline_value')}
        {num('target_value')}
        {text('realisation_date', { type: 'date', slotProps: { inputLabel: { shrink: true } } })}
      </Box>
    </>
  );
}

// Register · Value ranking · Gap — three addresses, one switch.
export function BenefitTabs({ projectId, value }) {
  const navigate = useNavigate();
  const to = { register: links.benefits, ranking: links.valueRanking, gap: links.benefitGap };
  return (
    <Box sx={{ mb: 2 }}>
      <Segmented label={t('benefits.title')} value={value} onChange={(v) => navigate(to[v](projectId))}
        options={['register', 'ranking', 'gap'].map((k) => ({ value: k, label: t(`benefits.tab.${k}`) }))} />
    </Box>
  );
}

// The solution page's read-only list (spec §9).
export function SolutionBenefits({ projectId, solutionId }) {
  const q = useQuery({ queryKey: keys.solutionBenefits(solutionId), queryFn: () => benefitApi.ofSolution(solutionId) });
  const rows = q.data ?? [];
  return (
    <Card title={t('benefits.onSolution.title')} bodySx={{ gap: 0.75 }}>
      {/* A failed load is never shown as "no benefit" — that is what the gap challenge acts on (sara M1). */}
      {q.error && <Alert severity="error">{errorText(q.error)}</Alert>}
      {q.isSuccess && rows.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('benefits.onSolution.empty')}</Typography>}
      {rows.map((r) => (
        <Stack key={r.benefit_solution_id} direction="row" spacing={1} sx={{ alignItems: 'center', fontSize: 13.5 }}>
          <Link component={RouterLink} to={links.benefit(projectId, r.benefit_id)} underline="hover"><Code>{r.benefit_number}</Code></Link>
          <Box component="span" sx={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.benefit_name}</Box>
          <Box component="span" sx={{ color: 'text.secondary', whiteSpace: 'nowrap' }}>{r.contribution_pct} % · {r.value} {r.measure_unit}</Box>
        </Stack>))}
    </Card>
  );
}
