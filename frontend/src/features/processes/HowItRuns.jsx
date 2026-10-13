import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, Fade } from '@mui/material';
import CheckRounded from '@mui/icons-material/CheckRounded';
import { bfcApi, brApi, orgApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { FactTile, GroupHeader } from '../../components/kit';
import { t } from '../../i18n/t';
import { FORM_SAVE, RaciPanel } from './chartKit';
import { PerformerPanel, TriggerPanel, usePerformerText } from './StepDfd';
import { StepData, StepDataNotOnBr, stepKey } from './StepSections';
import { BrRaci } from '../requirements/BrRaci';
import { CrudGrid, brDataKey } from '../requirements/CrudGrid';
import { DfdMark } from './DfdLight';

const SINGLE = ['ACCOUNTABLE'];      // services/raci.py SINGLE — the one Accountable, named by behaviour (law 5)

/** A brief ✓ after any immediate save (a link, a tick, a role) — never after the Save button's form saves. */
export function useSavedFlash() {
  const qc = useQueryClient();
  const [on, setOn] = useState(false);
  const timer = useRef(null);
  useEffect(() => {
    const off = qc.getMutationCache().subscribe((e) => {
      if (e.type !== 'updated' || e.action?.type !== 'success') return;
      if (e.mutation?.options?.mutationKey?.[0] === FORM_SAVE) return;
      setOn(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setOn(false), 1600);
    });
    return () => { off(); clearTimeout(timer.current); };
  }, [qc]);
  return on;
}

/** The one Accountable and the count of the other codes, from the same list the editor shows. */
function useRaciFact(projectId, queryKey, list, enabled) {
  const { codes } = useCodes(projectId, 'RACI_TYPE');
  const q = useQuery({ queryKey, queryFn: list, enabled });
  const rolesQ = useQuery({ queryKey: keys.roles(projectId), queryFn: () => orgApi.roles(projectId), enabled });
  return useMemo(() => {
    const rows = q.data ?? [];
    // Branch on the row's behaviour (law 5), never on a code; the codes only label the counts.
    const a = rows.find((r) => SINGLE.includes(r.raci_behaviour));
    const role = a && (rolesQ.data ?? []).find((r) => r.org_role_id === a.org_role_id);
    const counts = codes.filter((c) => !SINGLE.includes(c.behaviour_code))
      .map((c) => [c.label, rows.filter((r) => r.raci_code === c.code).length]).filter(([, n]) => n > 0);
    return { name: a ? (role?.org_role_name ?? t('processes.run.unknownRole')) : null,
      note: counts.length ? counts.map(([label, n]) => `${n} ${label}`).join(' · ') : t('processes.run.noOthers'),
      loading: q.isLoading };
  }, [q.data, q.isLoading, rolesQ.data, codes]);
}

/** Entities in and out of the step. The tile counts the step's own I/O — the one record (D-24) that the DFD, the
 * readiness tick and "Started by" read, so all four agree (10f, critique P2). A to-be process edits them through its
 * requirement's CRUD; step rows the CRUD does not hold (an external flow, a chart copy — DR 10d-4) are named apart as
 * "n not on the requirement yet", the rows the editor lists under "Recorded on the DFD". Nothing stored changes. */
function useDataFact(nodeId, br) {
  const stepQ = useQuery({ queryKey: stepKey(nodeId, 'data'), queryFn: () => bfcApi.stepData(nodeId) });
  const brQ = useQuery({ queryKey: br ? brDataKey(br.br_id) : ['none'], queryFn: () => brApi.data(br.br_id), enabled: Boolean(br) });
  const stepRows = stepQ.data ?? [];
  const brRows = br ? brQ.data ?? [] : [];
  const count = (d) => new Set(stepRows.filter((r) => r.direction === d).map((r) => r.data_entity_id)).size;
  const onBr = new Set(brRows.map((r) => `${r.data_entity_id}:${r.direction}`));
  const dfdOnly = br ? stepRows.filter((r) => !onBr.has(`${r.data_entity_id}:${r.direction}`)).length : 0;
  return { inN: count('I'), outN: count('O'), dfdOnly, loading: stepQ.isLoading || (Boolean(br) && brQ.isLoading), brRows: brQ.data };
}

function useTriggerFact(nodeId, enabled) {
  const q = useQuery({ queryKey: keys.stepTriggers(nodeId), queryFn: () => bfcApi.triggers(nodeId), enabled });
  const names = (q.data ?? []).map((r) => r.trigger_row.trigger_name);
  return { first: names[0] ?? null, more: names.length - 1, loading: q.isLoading };
}

/**
 * "How it runs — saves as you go" (D-63): the four facts a consultant sets after the requirement, as tiles
 * that open the existing editors full width below, one at a time. Performer and trigger are written only
 * where the chart's DFD is on (10c widens the performer). D-64: a to-be process has one RACI — its
 * requirement's — and its data is the CRUD grid; an as-is process keeps the step's roles and data.
 */
export function HowItRuns({ projectId, node, br, brEditable, editable, dfdOn, dfd, onDraftChange }) {
  const asIs = node.bfc_set_code === 'AS_IS';
  const nodeId = node.bfc_node_id;
  const hasBr = !asIs && Boolean(br);
  const [open, setOpen] = useState(null);
  // Editors stay mounted once opened (hidden when closed), so Done or another tile never drops a half-filled
  // performer or trigger form (DR 10d-2); the panel's leave guard counts those drafts.
  const [mounted, setMounted] = useState(() => new Set());
  const [drafts, setDrafts] = useState({});
  const draftSetter = useCallback((key) => (v) => setDrafts((d) => (Boolean(d[key]) === v ? d : { ...d, [key]: v })), []);
  const onPerformerDraft = useMemo(() => draftSetter('performer'), [draftSetter]);
  const onTriggerDraft = useMemo(() => draftSetter('trigger'), [draftSetter]);
  const anyDraft = Object.values(drafts).some(Boolean);
  useEffect(() => { onDraftChange?.(anyDraft); }, [anyDraft, onDraftChange]);
  const flash = useSavedFlash();
  const performer = usePerformerText(projectId, node);
  const trigger = useTriggerFact(nodeId, dfdOn);
  const raci = useRaciFact(projectId, hasBr ? [...keys.br(br.br_id), 'roles'] : stepKey(nodeId, 'roles'),
    hasBr ? () => brApi.roles(br.br_id) : () => bfcApi.roles(nodeId), asIs || hasBr);
  const data = useDataFact(nodeId, hasBr ? br : null);
  const factsEditable = hasBr ? brEditable : editable;
  const dataEmpty = !data.loading && data.inN + data.outN + data.dfdOnly === 0;
  const emptyText = t(factsEditable ? 'processes.run.notSetSet' : 'processes.run.notSet');

  const tiles = [
    dfdOn && { key: 'performer', label: t('processes.run.performer'), value: performer.text,
      empty: !node.performer_kind,
      editor: <PerformerPanel projectId={projectId} node={node} disabled={!editable} startEditing onDraftChange={onPerformerDraft} /> },
    // D-69: one STARTED mark on "Started by" (a trigger, a data input or an inbound party all meet it — DR13-D1)
    dfdOn && { key: 'trigger', label: t('processes.run.trigger'), mark: <DfdMark dfd={dfd} element="STARTED" />, value: trigger.first,
      note: trigger.more > 0 ? t('processes.run.more', { n: trigger.more }) : null, empty: !trigger.loading && !trigger.first,
      editor: <TriggerPanel projectId={projectId} node={node} disabled={!editable} onDraftChange={onTriggerDraft} /> },
    (asIs || hasBr) && { key: 'accountable', label: t('processes.run.accountable'), value: raci.name, note: raci.note,
      empty: !raci.loading && !raci.name,
      editor: hasBr ? <BrRaci projectId={projectId} br={br} disabled={!brEditable} />
        : <RaciPanel projectId={projectId} queryKey={stepKey(nodeId, 'roles')} disabled={!editable}
            list={() => bfcApi.roles(nodeId)} link={(body) => bfcApi.linkRole(nodeId, body)}
            unlink={(id, rv) => bfcApi.unlinkRole(nodeId, id, rv)} linkId="bfc_node_org_role_id" single={SINGLE} /> },
    // D-69: the DATA_OUT mark sits on the tile's "out" half; no data-in mark under the fixed rule
    (asIs || hasBr) && { key: 'data', label: t('processes.run.data'),
      mark: dataEmpty ? <DfdMark dfd={dfd} element="DATA_OUT" /> : null,            // an empty tile shows no "out" half
      value: <>{t('processes.run.dataValue', { in: data.inN, out: data.outN })} <DfdMark dfd={dfd} element="DATA_OUT" /></>,
      note: data.dfdOnly > 0 ? t('processes.run.dfdOnlyCount', { n: data.dfdOnly }) : null,
      empty: dataEmpty,
      editor: hasBr ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <CrudGrid projectId={projectId} br={br} disabled={!brEditable}
            emptyText={data.dfdOnly > 0 ? t('processes.run.noBrDataButDfd') : undefined} />
          <StepDataNotOnBr projectId={projectId} node={node} brRows={data.brRows} />
        </Box>)
        : <StepData projectId={projectId} node={node} disabled={!editable} /> },
  ].filter(Boolean);
  if (tiles.length === 0) return null;
  const current = tiles.find((x) => x.key === open);
  const editorId = (key) => `run-editor-${nodeId}-${key}`;
  const toggle = (key) => {
    setOpen(open === key ? null : key);
    setMounted((m) => (m.has(key) ? m : new Set([...m, key])));
  };

  return (
    <Box component="section" aria-labelledby={`run-title-${nodeId}`} sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      <GroupHeader id={`run-title-${nodeId}`} info={t('processes.run.info')}
        action={(
          <Fade in={flash} timeout={{ enter: 120, exit: 400 }}>
            <Box component="span" role="status" sx={(th) => ({ display: 'inline-flex', alignItems: 'center', gap: 0.5,
              fontSize: 12.5, fontWeight: 600, color: th.vars.palette.status.ok })}>
              <CheckRounded sx={{ fontSize: 16 }} />{t('processes.run.saved')}
            </Box>
          </Fade>)}>
        {t('processes.run.title')}
        <Box component="span" sx={(th) => ({ fontWeight: 400, color: th.vars.palette.brand.muted, ml: 0.75 })}>
          · {t('processes.run.savesAsYouGo')}</Box>
      </GroupHeader>
      <Box sx={{ containerType: 'inline-size' }}>
        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: 'minmax(0,1fr)',
          '@container (min-width: 420px)': { gridTemplateColumns: 'repeat(2, minmax(0,1fr))' } }}>
          {tiles.map((x) => (
            <FactTile key={x.key} label={x.mark ? <>{x.label}{x.mark}</> : x.label} value={x.value} empty={x.empty} emptyText={emptyText}
              note={drafts[x.key] && open !== x.key ? t('processes.run.draft') : x.note}
              selected={open === x.key} controls={mounted.has(x.key) ? editorId(x.key) : undefined} onClick={() => toggle(x.key)} />
          ))}
        </Box>
      </Box>
      {tiles.filter((x) => mounted.has(x.key)).map((x) => (
        <Box key={x.key} id={editorId(x.key)} role="region" aria-label={x.label} hidden={current?.key !== x.key}
          sx={(th) => ({ display: current?.key === x.key ? 'flex' : 'none', flexDirection: 'column', gap: 1.5, p: 2,
            borderRadius: '14px', border: `1px solid ${th.vars.palette.brand.ftcViolet}`,
            bgcolor: th.vars.palette.background.paper, minWidth: 0 })}>
          {x.editor}
          {factsEditable && (
            <Button size="small" variant="outlined" sx={{ alignSelf: 'flex-end' }} onClick={() => setOpen(null)}>
              {t('processes.run.done')}</Button>)}
        </Box>
      ))}
    </Box>
  );
}
