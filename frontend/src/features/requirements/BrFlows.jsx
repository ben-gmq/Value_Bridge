import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, Link, TextField, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import { errorText, isStale } from '../../api/client';
import { appApi, brApi, dataApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Code, SectionLabel, Status } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';
import { FrWarnings } from '../frs/frKit';

const blank = { data_entity_id: '', source_application_id: '', target_application_id: '', flow_note: '' };

/**
 * D-61: what data this requirement copies from which system to which (both from the Systems list, never typed).
 * Each flow shows whether a function requirement already carries it — "covered by FR-0031" or "no interface yet",
 * worked out by the server from the BR's interface (or Data migration) FRs, never stored. Ticking flows that share
 * one from → to pair offers "Create interface FR": one save makes the FR, its interface and the link (§3.1).
 * Writes need Applications on; the create action needs Function requirements too (`frOn`).
 */
export function BrFlows({ projectId, br, disabled, frOn, bare = false }) {
  const qc = useQueryClient();
  const qk = [...keys.br(br.br_id), 'flows'];
  const q = useQuery({ queryKey: qk, queryFn: () => brApi.flows(br.br_id) });
  const appsQ = useQuery({ queryKey: keys.applications(projectId), queryFn: () => appApi.list(projectId) });
  const entQ = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const { options: frTypes } = useCodes(projectId, 'FR_TYPE');
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(null);
  const [picked, setPicked] = useState(() => new Set());
  const [seed, setSeed] = useState(null);                       // { fr_type_code, fr_name } while the form is open
  const [made, setMade] = useState(null);
  const flows = useMemo(() => q.data ?? [], [q.data]);
  const appById = useMemo(() => new Map((appsQ.data ?? []).map((a) => [a.application_id, a])), [appsQ.data]);
  const deById = useMemo(() => new Map((entQ.data ?? []).map((e) => [e.data_entity_id, e])), [entQ.data]);
  const appOptions = (appsQ.data ?? []).filter((a) => a.is_active)
    .map((a) => ({ value: a.application_id, label: `${a.application_code} — ${a.application_name}` }));
  const entOptions = (entQ.data ?? []).filter((e) => e.is_active).map((e) => ({ value: e.data_entity_id, label: `${e.de_number} ${e.de_name}` }));
  const ifaceTypes = frTypes().filter((c) => c.behaviour_code === 'INTERFACE').map((c) => ({ value: c.code, label: c.label }));
  const refresh = () => { qc.invalidateQueries({ queryKey: qk }); qc.invalidateQueries({ queryKey: keys.br(br.br_id) }); };
  const fail = (err) => { refresh(); setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed'))); };

  const add = useMutation({
    mutationFn: (v) => brApi.addFlow(br.br_id, { data_entity_id: Number(v.data_entity_id),
      source_application_id: Number(v.source_application_id), target_application_id: Number(v.target_application_id),
      flow_note: v.flow_note.trim() || null }),
    onSuccess: () => { setAdding(null); setError(''); refresh(); }, onError: fail });
  const remove = useMutation({ mutationFn: (f) => brApi.removeFlow(br.br_id, f.br_system_flow_id, f.row_version),
    onSuccess: (_, f) => {                                   // sara L1: a removed flow leaves the selection too
      setError(''); refresh();
      setPicked((s) => { const n = new Set(s); n.delete(f.br_system_flow_id); return n; });
    },
    onError: fail });
  const toFr = useMutation({
    // sara L1: only flows still listed are sent
    mutationFn: (v) => brApi.flowsToFr(br.br_id, { flow_ids: chosen.map((f) => f.br_system_flow_id),
      fr_type_code: v.fr_type_code, fr_name: v.fr_name.trim() }),
    onSuccess: (fr) => {
      setSeed(null); setPicked(new Set()); setError(''); setMade(fr); refresh();
      qc.invalidateQueries({ queryKey: keys.frs(projectId) });
      qc.invalidateQueries({ queryKey: keys.brFrs(br.br_id) });           // the panel's Function requirements section
    },
    onError: fail });
  const busy = add.isPending || remove.isPending || toFr.isPending;
  const chosen = flows.filter((f) => picked.has(f.br_system_flow_id));
  const onePair = chosen.length > 0 && new Set(chosen.map((f) => `${f.source_application_id}>${f.target_application_id}`)).size === 1;
  const appCode = (id) => appById.get(id)?.application_code ?? `#${id}`;
  const flip = (id) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const okNew = adding && adding.data_entity_id && adding.source_application_id && adding.target_application_id
    && adding.source_application_id !== adding.target_application_id;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      <SectionLabel info={t('requirements.flows.info')} action={!disabled && !adding && (
        <Button size="small" startIcon={<AddRounded />} sx={{ color: 'brand.purpleText' }} disabled={busy}
          onClick={() => { setError(''); setAdding({ ...blank }); }}>{t('requirements.flows.add')}</Button>)}>
        {!bare && t('requirements.flows.title')}
      </SectionLabel>
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      {q.error && <Alert severity="error">{errorText(q.error)}</Alert>}
      {made && (
        <Alert severity="success" onClose={() => setMade(null)}>
          {t('requirements.flows.made')}{' '}
          <Link component={RouterLink} to={links.fr(projectId, made.fr_id)}>{made.fr_number}</Link>
        </Alert>)}
      {/* sara L6: the same warnings the FR screen's create shows (e.g. a duplicate name) */}
      {made && <FrWarnings warnings={made.warnings} onClose={() => setMade({ ...made, warnings: [] })} />}
      {!q.isLoading && !q.error && flows.length === 0 && !adding && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.flows.none')}</Typography>)}
      {flows.map((f) => {
        const de = deById.get(f.data_entity_id);
        return (
          <Box key={f.br_system_flow_id} data-testid="br-flow"
            sx={{ display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr) auto', gap: 1, alignItems: 'start', py: 0.75,
              borderTop: 1, borderColor: 'divider' }}>
            <Checkbox size="small" sx={{ p: 0.5 }} checked={picked.has(f.br_system_flow_id)} disabled={disabled || !frOn || busy}
              onChange={() => flip(f.br_system_flow_id)}
              slotProps={{ input: { 'aria-label': t('requirements.flows.pick', { entity: de?.de_name ?? '' }) } }} />
            <Box sx={{ minWidth: 0 }}>
              <Typography sx={{ fontSize: 14 }}>
                {de && <Code tone="teal" sx={{ fontSize: 12.5, mr: 1 }}>{de.de_number}</Code>}{de?.de_name}
                {' · '}<Code>{appCode(f.source_application_id)}</Code>{' → '}<Code>{appCode(f.target_application_id)}</Code>
              </Typography>
              {f.flow_note && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{f.flow_note}</Typography>}
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 0.5 }}>
                {f.covered_by.length
                  ? <Status tone="ok" size="sm">{t('requirements.flows.covered', { frs: f.covered_by.join(', ') })}</Status>
                  // §3.1 (sara L2): a warning only when Function requirements is on, information otherwise
                  : <Status tone={frOn ? 'caution' : 'neutral'} size="sm">{t('requirements.flows.notCovered')}</Status>}
                {f.info.map((i) => <Typography key={i} sx={{ fontSize: 12, color: 'text.secondary' }}>{t(`requirements.flows.infoCode.${i}`)}</Typography>)}
              </Box>
            </Box>
            {!disabled && (
              <Button size="small" color="warning" disabled={busy} onClick={() => remove.mutate(f)}>{t('requirements.flows.remove')}</Button>)}
          </Box>
        );
      })}
      {!disabled && frOn && chosen.length > 0 && !seed && (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <Button size="small" variant="outlined" disabled={!onePair || busy}
            onClick={() => setSeed({ fr_type_code: ifaceTypes[0]?.value ?? '', fr_name: '' })}>{t('requirements.flows.toFr')}</Button>
          {!onePair && <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('requirements.flows.onePair')}</Typography>}
        </Box>)}
      {seed && (
        <Box sx={{ display: 'grid', gap: 1.25, gridTemplateColumns: 'minmax(0,1fr) minmax(0,2fr)' }}>
          <SimpleSelect id="flow-fr-type" label={t('requirements.flows.frType')} value={seed.fr_type_code}
            onChange={(v) => setSeed({ ...seed, fr_type_code: v })} options={ifaceTypes} />
          <TextField size="small" id="flow-fr-name" label={t('requirements.flows.frName')} value={seed.fr_name}
            onChange={(e) => setSeed({ ...seed, fr_name: e.target.value })} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <Box sx={{ gridColumn: '1 / -1', display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
            <Button onClick={() => setSeed(null)} disabled={busy}>{t('common.cancel')}</Button>
            <Button variant="contained" disabled={!seed.fr_type_code || !seed.fr_name.trim() || busy}
              onClick={() => toFr.mutate(seed)}>{t('requirements.flows.create')}</Button>
          </Box>
        </Box>)}
      {adding && (
        <Box sx={{ display: 'grid', gap: 1.25, gridTemplateColumns: 'repeat(3, minmax(0,1fr))' }}>
          <SimpleSelect id="flow-entity" label={t('requirements.flows.entity')} value={adding.data_entity_id}
            onChange={(v) => setAdding({ ...adding, data_entity_id: v })} options={entOptions} />
          <SimpleSelect id="flow-source" label={t('requirements.flows.from')} value={adding.source_application_id}
            onChange={(v) => setAdding({ ...adding, source_application_id: v })} options={appOptions} />
          <SimpleSelect id="flow-target" label={t('requirements.flows.to')} value={adding.target_application_id}
            onChange={(v) => setAdding({ ...adding, target_application_id: v })} options={appOptions} />
          <TextField sx={{ gridColumn: '1 / -1' }} size="small" id="flow-note" label={t('requirements.flows.note')}
            value={adding.flow_note} onChange={(e) => setAdding({ ...adding, flow_note: e.target.value })}
            slotProps={{ htmlInput: { maxLength: 2000 } }} />
          {adding.source_application_id && adding.source_application_id === adding.target_application_id && (
            <Typography sx={{ gridColumn: '1 / -1', fontSize: 12.5, color: 'error.main' }}>{t('requirements.flows.sameSystem')}</Typography>)}
          <Box sx={{ gridColumn: '1 / -1', display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
            <Button onClick={() => setAdding(null)} disabled={busy}>{t('common.cancel')}</Button>
            <Button variant="contained" disabled={!okNew || busy} onClick={() => add.mutate(adding)}>{t('requirements.flows.add')}</Button>
          </Box>
        </Box>)}
      {appOptions.length < 2 && !appsQ.isLoading && !disabled && (
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
          {t('requirements.flows.needSystems')}{' '}
          <Link component={RouterLink} to={links.applications(projectId)}>{t('requirements.flows.goSystems')}</Link>
        </Typography>)}
    </Box>
  );
}
