import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Link, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { errorText, isStale } from '../../api/client';
import { brApi, orgApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { SectionLabel } from '../../components/kit';
import { t } from '../../i18n/t';
import { PickDialog, SimpleSelect } from '../processes/chartKit';
import { pillBox } from './reqKit';

const BR_SINGLE = ['ACCOUNTABLE'];                      // services/raci.py SINGLE[BrOrgRole]

/**
 * RACI for one requirement, drawn as the mockup's R/A/C/I pill toggle (D-51). Same calls as the
 * shared RaciPanel: each pill links or unlinks one br_org_role row; a role may hold several codes.
 * Pills come from RACI_TYPE (code_master), never a fixed letter list; which behaviours are "one
 * only" is the server's rule (services/raci.py SINGLE), named here by behaviour code.
 */
export function BrRaci({ projectId, br, disabled }) {
  const qc = useQueryClient();
  const queryKey = [...keys.br(br.br_id), 'roles'];
  const { codes } = useCodes(projectId, 'RACI_TYPE');
  const q = useQuery({ queryKey, queryFn: () => brApi.roles(br.br_id) });
  const rolesQ = useQuery({ queryKey: keys.roles(projectId), queryFn: () => orgApi.roles(projectId) });
  const unitsQ = useQuery({ queryKey: keys.units(projectId), queryFn: () => orgApi.units(projectId) });
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [addCode, setAddCode] = useState('');
  const roleById = useMemo(() => new Map((rolesQ.data ?? []).map((r) => [r.org_role_id, r])), [rolesQ.data]);
  const unitById = useMemo(() => new Map((unitsQ.data ?? []).map((u) => [u.org_unit_id, u])), [unitsQ.data]);
  const linksList = useMemo(() => q.data ?? [], [q.data]);
  const roleIds = [...new Set(linksList.map((l) => l.org_role_id))];
  const refresh = () => qc.invalidateQueries({ queryKey });
  const toggle = useMutation({
    mutationFn: ({ roleId, code, on }) => {
      if (on) return brApi.linkRole(br.br_id, { org_role_id: roleId, raci_code: code });
      const row = linksList.find((l) => l.org_role_id === roleId && l.raci_code === code);
      return brApi.unlinkRole(br.br_id, row.br_org_role_id, row.row_version);
    },
    onSuccess: () => { setError(''); refresh(); },
    onError: (err) => {
      refresh();
      setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed')));
    },
  });
  const rule = codes.filter((c) => BR_SINGLE.includes(c.behaviour_code))
    .map((c) => t('processes.raciOne', { label: c.label })).join(', ');
  const activeRoles = (rolesQ.data ?? []).filter((r) => r.is_active);
  const roleName = (r) => (r ? `${r.org_role_code} — ${r.org_role_name}` : '');

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, minWidth: 0 }}>
      <SectionLabel action={!disabled && (
        <Button size="small" startIcon={<AddRounded />} sx={{ color: 'brand.purpleText' }}
          onClick={() => { setError(''); setAddCode(''); setAdding(true); }}>{t('processes.addRole')}</Button>)}>
        {t('requirements.raciTitle')}
      </SectionLabel>
      {rule && <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: -0.75 }}>{t('requirements.raciRule', { rule })}</Typography>}
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      {[q.error, rolesQ.error, unitsQ.error].some(Boolean) && (
        <Alert severity="error">{errorText(q.error || rolesQ.error || unitsQ.error)}</Alert>)}
      {!q.isLoading && !q.error && roleIds.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('processes.noRoles')}</Typography>
      )}
      {roleIds.map((roleId) => {
        const role = roleById.get(roleId);
        const held = linksList.filter((l) => l.org_role_id === roleId).map((l) => l.raci_code);
        return (
          <Box key={roleId} sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Box sx={{ minWidth: 0, flex: '1 1 120px' }}>
              <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{role ? role.org_role_name : `#${roleId}`}</Typography>
              <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                {role && [role.org_role_code, unitById.get(role.org_unit_id)?.org_unit_name].filter(Boolean).join(' · ')}
              </Typography>
            </Box>
            <ToggleButtonGroup size="small" value={held} aria-label={t('processes.raciFor', { role: roleName(role) })}
              sx={(th) => ({ ...pillBox(th), p: '3px', gap: '2px',
                '& .MuiToggleButton-root': { border: 0, borderRadius: '999px !important', minWidth: 30, height: 26, px: 0.75,
                  fontSize: 12.5, fontWeight: 700, color: th.vars.palette.brand.muted },
                '& .Mui-selected': { bgcolor: `${th.vars.palette.brand.ftcViolet} !important`, color: `${th.vars.palette.brand.onFtc} !important` } })}>
              {codes.map((c) => (
                <ToggleButton key={c.code} value={c.code} aria-label={c.label} title={c.label}
                  disabled={disabled || toggle.isPending}
                  onClick={() => toggle.mutate({ roleId, code: c.code, on: !held.includes(c.code) })}>
                  {c.label.charAt(0)}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>
        );
      })}
      {adding && (
        <PickDialog open title={t('processes.addRoleTitle')} optionLabel={t('processes.orgRole')}
          options={activeRoles} getOptionLabel={roleName} submitLabel={t('processes.add')}
          canSubmit={Boolean(addCode)}
          emptyHint={(
            <Alert severity="info">
              {t('processes.noOrgRoles')}{' '}
              <Link component={RouterLink} to={links.organisation(projectId)}>{t('processes.goOrganisation')}</Link>
            </Alert>)}
          extra={(
            <SimpleSelect id="raci-add-code" label={t('processes.raciCode')} value={addCode} onChange={setAddCode}
              options={codes.map((c) => ({ value: c.code, label: c.label }))} />)}
          onSubmit={(role) => brApi.linkRole(br.br_id, { org_role_id: role.org_role_id, raci_code: addCode })}
          onDone={refresh} onClose={() => setAdding(false)} />
      )}
    </Box>
  );
}
