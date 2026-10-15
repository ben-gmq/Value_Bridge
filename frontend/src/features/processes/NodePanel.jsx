import { useCallback, useEffect, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, IconButton, InputBase, Link, ListItemText, Menu, MenuItem, TextField, Tooltip,
  Typography } from '@mui/material';
import MoreHorizRounded from '@mui/icons-material/MoreHorizRounded';
import { errorKind, errorText, isStale } from '../../api/client';
import { bfcApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ConflictDialog } from '../../components/ConflictDialog';
import { Card, Code, InfoTip, LevelBadge, Segmented, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { FIRST_PROCESS_LEVEL, blankToNull, useEditForm, useFormSave } from './chartKit';
import { CompletenessPanel } from './StepDfd';
import { RetireStepDialog } from './RetireStepDialog';
import { StepFlows } from './StepSections';
import { HowItRuns } from './HowItRuns';
import { DfdLight } from './DfdLight';
import { PanelSection, useOpenSections, useSectionFacts } from './PanelSections';
import { AppLinkPanel } from '../applications/AppLinkPanel';
import { useBrEditor } from '../requirements/BrEditor';
import { BrSolutionTags } from '../requirements/BrSolutionTags';
import { BrFrLinks } from '../requirements/BrFrLinks';
import { BrStatusTag, OFFER_RETIRE_BR } from '../requirements/reqKit';

const pickNode = (n) => ({ node_name: n.node_name ?? '', purpose_desc: n.purpose_desc ?? '',
  data_processing_desc: n.data_processing_desc ?? '' });

// "Restore these first: A; B" → ['A', 'B'] — the names are the server's, shown as text.
const restoreFirstList = (err) => {
  const detail = errorText(err, '');
  return detail.slice(detail.indexOf(':') + 1).split(';').map((s) => s.trim()).filter(Boolean);
};

/** A panel field: a static 13/600 label above the box (no floating label in the panel, D-63). */
function Field({ id, label, info, children }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, minHeight: 22 }}>
        <Box component="label" htmlFor={id} sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>{label}</Box>
        {info && <InfoTip title={info} />}
      </Box>
      {children}
    </Box>
  );
}

const textBox = (size) => ({ '& .MuiInputBase-input': { fontSize: size, lineHeight: 1.5 } });

/**
 * D-57: what a box that is not a process is, in plain words, and the two ways on — open one of the processes below
 * it, or make this box a process (only where the switch is allowed: level 3 or deeper, nothing below it). "Make this
 * a process" opens the confirmation that says what it creates (DR10c-P2). Viewers read the text only.
 */
function FunctionGuide({ name, level, below, canSwitch, canEdit, busy, onOpenList, onMakeProcess }) {
  const lines = [t('processes.guide.what', { name })];
  if (below.length) lines.push(t('processes.guide.below', { n: below.length }));
  else if (level < FIRST_PROCESS_LEVEL) lines.push(t('processes.guide.tooHigh', { n: FIRST_PROCESS_LEVEL }));
  else if (!canSwitch && canEdit) lines.push(t('processes.guide.noneBelow'));
  if (canSwitch) lines.push(t('processes.guide.make'));
  const showOpen = canEdit && below.length > 0;
  return (
    <Box role="note" sx={(th) => ({ display: 'flex', flexDirection: 'column', gap: 1.25, p: 2, borderRadius: '14px',
      bgcolor: th.vars.palette.background.subtle, border: `1px solid ${th.vars.palette.divider}` })}>
      {lines.map((l, i) => <Typography key={i} sx={{ fontSize: 14, lineHeight: 1.5 }}>{l}</Typography>)}
      {(showOpen || (canEdit && canSwitch)) && (
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {showOpen && (
            <Button variant="outlined" size="small" aria-haspopup="menu" onClick={onOpenList}>
              {t('processes.guide.openBelow')}</Button>)}
          {canEdit && canSwitch && (
            <Button variant={showOpen ? 'text' : 'outlined'} size="small" disabled={busy} onClick={onMakeProcess}>
              {t('processes.guide.makeButton')}</Button>)}
        </Box>
      )}
    </Box>
  );
}

/**
 * One function of the chart, ranked (D-63): the sticky header names it; the requirement leads; "How it runs"
 * shows performer, trigger, Accountable and data as tiles; the rest sits in collapsed sections. Text fields
 * (the name, the requirement, purpose) wait for one Save; everything else saves as it is changed.
 * `guardRef` lets the chart ask before a switch would drop unsaved text (DR 10d-1).
 */
export function NodePanel({ projectId, nodeId, path, br, dfd, hasChildren, processesBelow = [], onOpenNode, showRetired, wide,
  guardRef, onNext, onNotice, onGone }) {
  const { isOn } = useComponents(projectId);
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const nodeQ = useQuery({ queryKey: keys.node(nodeId), queryFn: () => bfcApi.get(nodeId) });
  const node = nodeQ.data;
  const form = useEditForm(node, pickNode);
  // D-53: the process's requirement is edited in this panel, and one Save covers both (Ben, 2026-10-12).
  const brEd = useBrEditor({ projectId, brId: br?.br_id, onNotice, embedded: true });
  const sections = useOpenSections();
  const [actionError, setActionError] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);
  const [confirmSwitch, setConfirmSwitch] = useState(null);     // true = make a process, false = stop
  const [nodeRefused, setNodeRefused] = useState(false);
  const [retiringStep, setRetiringStep] = useState(false);
  const [menuAt, setMenuAt] = useState(null);
  const [belowAt, setBelowAt] = useState(null);                  // the "Open a process below" list (D-57)
  const [draft, setDraft] = useState(false);                     // a half-filled performer or trigger form
  const [saveNote, setSaveNote] = useState('');
  // Which restore fits a retired step is the server's call (SR-1): a step is offered the
  // with-dependents restore until a 409 says it was retired on its own.
  const [plainFor, setPlainFor] = useState(null);
  const [restoreNote, setRestoreNote] = useState(null);       // { nodeId, hint?, first? }

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });
    qc.invalidateQueries({ queryKey: keys.node(nodeId) });
    qc.invalidateQueries({ queryKey: keys.brs(projectId) });
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });      // every DFD and its gaps
  };

  const save = useFormSave({
    save: () => {
      // Only what the user changed: an untouched field never reverts someone else's edit.
      const body = { row_version: form.version };
      for (const k of form.changed) {
        if (k === 'data_processing_desc' && !node.is_process) continue;
        body[k] = k === 'node_name' ? form.values[k].trim() : blankToNull(form.values[k]);
      }
      return bfcApi.update(nodeId, body);
    },
    onSaved: (row) => { form.saved(row); qc.setQueryData(keys.node(nodeId), row); refreshAll(); },
  });
  const reload = async () => {
    try {
      const fresh = await qc.fetchQuery({ queryKey: keys.node(nodeId), queryFn: () => bfcApi.get(nodeId) });
      form.rebase(fresh);
      save.setError('');
      setNodeRefused(false);
    } catch (err) {
      save.setError(errorText(err, t('common.error')));
    } finally {
      save.setConflict(false);
    }
  };

  const actionFail = (err) => {
    refreshAll();
    setActionError(isStale(err) ? t('processes.staleAction') : errorText(err, t('common.saveFailed')));
  };
  const mark = useMutation({
    mutationFn: (isProcess) => bfcApi.markProcess(nodeId, { row_version: node.row_version, is_process: isProcess }),
    onSuccess: (res) => {
      setActionError(''); setConfirmSwitch(null);
      qc.setQueryData(keys.node(nodeId), res.node);
      form.rebase(res.node);                       // our own click is not someone else's edit
      refreshAll();
      onNotice(res.business_requirement
        ? t('processes.promoted', { br: res.business_requirement.br_number }) : t('processes.demoted'));
    },
    onError: (err) => { setConfirmSwitch(null); actionFail(err); },
  });
  const retire = useMutation({
    mutationFn: () => bfcApi.retire(nodeId, node.row_version),
    onSuccess: () => {
      setConfirmRetire(false); setActionError(''); refreshAll(); onNotice(t('processes.retired'));
      if (!showRetired) onGone();
    },
    onError: (err) => { setConfirmRetire(false); actionFail(err); },
  });
  const restore = useMutation({
    mutationFn: (withDependents) => (withDependents ? bfcApi.restoreWithDependents(nodeId) : bfcApi.restore(nodeId)),
    onSuccess: (res, withDependents) => {
      setActionError(''); setRestoreNote(null);
      if (!withDependents) qc.setQueryData(keys.node(nodeId), res);
      refreshAll();
      onNotice(withDependents ? t('processes.restoredWithDependents', { n: res.restored }) : t('processes.restored'));
    },
    onError: (err) => {
      const kind = errorKind(err);
      if (kind === 'USE_PLAIN_RESTORE' || kind === 'USE_RESTORE_WITH_DEPENDENTS') {
        const plain = kind === 'USE_PLAIN_RESTORE';
        setPlainFor(plain ? nodeId : null); setActionError('');
        setRestoreNote({ nodeId, hint: t(plain ? 'processes.restorePlainFits' : 'processes.restoreDependentsFits') });
      } else if (kind === 'RESTORE_FIRST') {
        setActionError(''); setRestoreNote({ nodeId, first: restoreFirstList(err) });
      } else {
        actionFail(err);
      }
    },
  });

  const ready = Boolean(node && form.values);
  const live = node?.is_active;
  const editable = Boolean(live && canEdit);      // a read-only user sees the panel, not its controls (sara LOW-3)
  const v = form.values;
  const showBr = Boolean(node?.is_process && br && brEd.br);
  const nodeSavable = Boolean(ready && live && form.dirty && v.node_name.trim() !== '');
  const brSavable = showBr && brEd.canSave;
  const busy = save.m.isPending || mark.isPending || retire.isPending || restore.isPending || Boolean(brEd.busy);
  const dirtyCount = (ready ? form.changed.length : 0) + (showBr ? brEd.changedCount : 0);

  // One Save: only what is dirty, the function first, then its requirement. Each keeps its own row_version
  // check; a refusal leaves the other saved, keeps the refused edits and shows its own conflict dialog or
  // error. Resolves true only when every dirty part saved (DR 10d-1: Save & next and the leave guard rely on it).
  const saveAll = async () => {
    save.setError(''); setSaveNote('');
    if (!nodeSavable && !brSavable) return dirtyCount === 0;
    const nodeOk = nodeSavable ? await save.m.mutateAsync().then(() => true, () => false) : true;
    if (nodeSavable) setNodeRefused(!nodeOk);
    const brOk = brSavable ? await brEd.saveNow() : true;
    if (nodeOk && brOk) onNotice(t(brSavable ? (nodeSavable ? 'processes.savedBoth' : 'requirements.saved') : 'processes.saved'));
    else if (nodeSavable && brSavable && (nodeOk || brOk)) onNotice(t(nodeOk ? 'processes.savedNodeOnly' : 'processes.savedBrOnly'));
    return nodeOk && brOk && (form.values.node_name.trim() !== '' || !form.changed.includes('node_name'));
  };
  const discardAll = () => { form.discard(); setNodeRefused(false); setSaveNote(''); if (showBr) brEd.discard(); };
  const saveAndNext = async () => {
    if (draft) { setSaveNote(t('processes.save.draftOpen')); return; }
    if (await saveAll()) onNext?.();
  };

  // The chart reads this before it switches node, so a switch never drops typed text (DR 10d-1).
  const latest = useRef({});
  latest.current = { count: dirtyCount, draft, name: node ? `${node.hier_code} ${form.values?.node_name ?? node.node_name}` : '',
    saveAll, discardAll };
  useEffect(() => {
    if (!guardRef) return undefined;
    guardRef.current = { get: () => latest.current };
    return () => { guardRef.current = null; };
  }, [guardRef]);

  // Closing the tab with unsaved text asks the browser's own question.
  const unsavedAny = dirtyCount > 0 || draft;
  useEffect(() => {
    if (!unsavedAny) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [unsavedAny]);

  // Ctrl/Cmd+S saves the text form — never the browser's "save page".
  const onKey = useCallback((e) => {
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 's' || e.altKey || e.shiftKey) return;
    e.preventDefault();
    if (!busy) latest.current.saveAll();
  }, [busy]);
  useEffect(() => {
    if (!canEdit) return undefined;
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canEdit, onKey]);

  const asIs = node?.bfc_set_code === 'AS_IS';
  const dfdOn = asIs ? isOn('AS_IS') : isOn('TO_BE_DFD');      // the chart's DFD component (D-37, D-47)
  const solutionsOn = isOn('SOLUTION');
  const frsOn = isOn('FUNCTION_REQUIREMENT');
  const systemsOn = asIs && isOn('APPLICATION', 'AS_IS');
  const liveDfd = node?.is_process && live && dfdOn && dfd?.light ? dfd : null;
  const facts = useSectionFacts({ projectId, br: showBr ? brEd.br : null, nodeId, solutionsOn, frsOn,
    partiesOn: Boolean(node?.is_process) && dfdOn, systemsOn: Boolean(node?.is_process) && systemsOn });

  if (nodeQ.error) return <Card><Alert severity="error">{errorText(nodeQ.error)}</Alert></Card>;
  if (!ready) return <Card><Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography></Card>;

  const restoreWithDependents = node.is_process && plainFor !== nodeId;
  const note = !live && restoreNote?.nodeId === nodeId ? restoreNote : null;
  const canSwitch = editable && node.level_no >= FIRST_PROCESS_LEVEL && (node.is_process || !hasChildren);
  const labels = { node_name: t('processes.name'), purpose_desc: t(node.is_process ? 'processes.purpose' : 'processes.panel.description'),
    data_processing_desc: t('processes.dataProcessing') };
  const unsaved = Object.fromEntries(form.changed.map((k) => [labels[k], v[k]]));
  const refused = (form.dirty && nodeRefused) || (showBr && brEd.refused && brEd.dirty) || Boolean(save.error || (showBr && brEd.saveError));
  const showFooter = canEdit && (dirtyCount > 0 || refused || Boolean(saveNote));

  const menuItems = !canEdit ? [] : [
    canSwitch && { key: 'switch', label: t(node.is_process ? 'processes.panel.unmakeProcess' : 'processes.panel.makeProcess'),
      run: () => setConfirmSwitch(!node.is_process) },
    live && { key: 'retire', label: t(node.is_process ? 'processes.panel.retireStep' : 'processes.panel.retireFunction'), warn: true,
      run: () => (node.is_process ? setRetiringStep(true) : setConfirmRetire(true)) },
    OFFER_RETIRE_BR && showBr && brEd.live && { key: 'retireBr', label: t('processes.panel.retireBr'), warn: true, run: brEd.askRetire },
    showBr && live && !brEd.live && { key: 'restoreBr', label: t('processes.panel.restoreBr'), run: brEd.restoreNow },
    !live && { key: 'restore', label: t(restoreWithDependents ? 'processes.restoreWithDependents' : 'processes.restore'),
      run: () => { setRestoreNote(null); restore.mutate(restoreWithDependents); } },
    br && { key: 'open', label: t('processes.panel.openBrPage'), to: links.requirement(projectId, br.br_id) },
  ].filter(Boolean);

  // ── header ────────────────────────────────────────────────────────────────────────────────
  const header = (
    <Box sx={(th) => ({ position: 'sticky', top: 0, zIndex: 3, bgcolor: th.vars.palette.background.paper,
      borderBottom: `1px solid ${th.vars.palette.divider}`, px: 2.5, pt: 2, pb: 1.5, display: 'flex', flexDirection: 'column', gap: 0.75 })}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
        <LevelBadge level={node.level_no} label={t('processes.levelN', { n: node.level_no })} />
        <Code tone="muted" sx={{ fontSize: 12.5 }}>{node.hier_code}</Code>
        <Typography noWrap title={path.join(' › ')} sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.muted, minWidth: 0 })}>
          {path.length ? path.join(' › ') : t('processes.panel.topLevel')}</Typography>
        {!live && <Tag tone="neutral" size="lg" sx={{ flex: 'none' }}>{t('processes.retiredChip')}</Tag>}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <InputBase value={v.node_name} onChange={(e) => form.set('node_name', e.target.value.replace(/\n/g, ' '))} readOnly={!editable}
          onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault(); }}
          multiline maxRows={3} inputProps={{ maxLength: 200, 'aria-label': t('processes.name') }}
          sx={(th) => ({ flex: '1 1 260px', minWidth: 0, mx: -1, px: 1, py: 0.25, borderRadius: '10px', fontSize: 20, fontWeight: 700,
            lineHeight: 1.3, color: 'brand.title', '& textarea': { lineHeight: 1.3 },
            ...(editable ? { '&:hover': { bgcolor: th.vars.palette.background.subtle },
              '&.Mui-focused': { bgcolor: th.vars.palette.background.field, outline: `1px solid ${th.vars.palette.brand.ftcViolet}` } } : {}),
            ...(editable && v.node_name.trim() === '' ? { outline: `1px solid ${th.vars.palette.status.escalate}` } : {}) })} />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', ml: 'auto' }}>
          {/* D-68: the process's DFD light, from the tree row the chart already holds (null when the rule is off) */}
          {liveDfd && <DfdLight light={liveDfd.light} missing={liveDfd.missing} advised={liveDfd.advised ?? []} />}
          {showBr && (
            <Tooltip title={t('processes.panel.openBr', { br: brEd.br.br_number })}>
              <Link component={RouterLink} to={links.requirement(projectId, br.br_id)} underline="none"
                sx={(th) => ({ display: 'inline-flex', alignItems: 'center', height: 28, px: 1.25, borderRadius: 999,
                  bgcolor: th.vars.palette.brand.purpleTint, '&:hover': { outline: `1px solid ${th.vars.palette.brand.ftcViolet}` } })}>
                <Code tone="purple">{brEd.br.br_number}</Code></Link>
            </Tooltip>)}
          {showBr && (brEd.statusSettable && brEd.editable ? (
            <Segmented size="sm" label={t('processes.panel.status')} value={brEd.values.status_code}
              onChange={(s) => brEd.set('status_code', s)} options={brEd.statusOptions} />
          ) : <BrStatusTag code={brEd.br.status_code} label={brEd.getLabel(brEd.br.status_code)} />)}
          {menuItems.length > 0 && (
            <IconButton aria-label={t('processes.panel.menu')} aria-haspopup="menu" disabled={busy}
              onClick={(e) => { setActionError(''); setMenuAt(e.currentTarget); }}><MoreHorizRounded /></IconButton>)}
        </Box>
      </Box>
    </Box>
  );

  // ── primary ───────────────────────────────────────────────────────────────────────────────
  const nodeText = (name, label, rows, info) => (
    <Field id={`node-${name}`} label={label} info={info}>
      <TextField fullWidth multiline minRows={rows} id={`node-${name}`} value={v[name]} sx={textBox(14)}
        onChange={(e) => form.set(name, e.target.value)}
        slotProps={{ htmlInput: { maxLength: 4000 }, input: { readOnly: !editable } }} />
    </Field>
  );
  const brText = (name, label, rows, size, placeholder) => (
    <Field id={`br-${name}`} label={label}>
      <TextField fullWidth multiline minRows={rows} id={`br-${name}`} value={brEd.values[name]} sx={textBox(size)}
        placeholder={brEd.editable ? placeholder : undefined} onChange={(e) => brEd.set(name, e.target.value)}
        slotProps={{ htmlInput: { maxLength: 8000 }, input: { readOnly: !brEd.editable } }} />
    </Field>
  );
  const describe = (
    <>
      {nodeText('purpose_desc', t('processes.purpose'), 2)}
      {nodeText('data_processing_desc', t('processes.dataProcessing'), 2, t('processes.panel.dataProcessingInfo'))}
    </>
  );
  let primary;
  if (!node.is_process) {
    primary = nodeText('purpose_desc', t('processes.panel.description'), 3, t('processes.panel.descriptionInfo'));
  } else if (showBr) {
    primary = (
      <>
        {brText('br_statement', t('processes.panel.statement'), 2, 16, t('processes.panel.statementPlaceholder'))}
        {brText('business_logic', t('processes.panel.logic'), 3, 14, t('processes.panel.logicPlaceholder'))}
        {brText('output_expectation', t('processes.panel.output'), 1, 14, t('processes.panel.outputPlaceholder'))}
      </>
    );
  } else if (br && !brEd.error) {
    primary = <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>;
  } else {
    primary = describe;     // an as-is step carries no requirement: what it is for leads
  }

  return (
    <Card sx={wide ? { height: '100%' } : { overflow: 'visible' }}
      bodySx={{ p: 0, gap: 0, ...(wide ? { overflowY: 'auto', minHeight: 0 } : {}) }}>
      {header}
      <Box sx={{ px: 2.5, pt: 2.5, pb: 3, display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        {(actionError || save.error || note || (showBr && (brEd.saveError || brEd.actionError)) || brEd.error) && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {actionError && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setActionError('')}>{actionError}</Alert>}
            {save.error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{save.error}</Alert>}
            {brEd.error && <Alert severity="error">{errorText(brEd.error)}</Alert>}
            {showBr && brEd.alerts}
            {note?.hint && <Alert severity="info" onClose={() => setRestoreNote(null)}>{note.hint}</Alert>}
            {note?.first && (
              <Alert severity="warning" onClose={() => setRestoreNote(null)}>
                <Typography sx={{ fontSize: 13, mb: 0.5 }}>{t('processes.restoreFirstTitle')}</Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                  {note.first.map((name, i) => <Typography component="li" key={i} sx={{ fontSize: 13 }}>{name}</Typography>)}
                </Box>
              </Alert>
            )}
          </Box>
        )}

        {!node.is_process && live && (
          <FunctionGuide name={node.node_name} level={node.level_no} below={processesBelow} canSwitch={canSwitch} canEdit={editable}
            busy={busy} onOpenList={(e) => setBelowAt(e.currentTarget)} onMakeProcess={() => setConfirmSwitch(true)} />
        )}

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>{primary}</Box>

        {node.is_process && (
          <HowItRuns projectId={projectId} node={node} br={showBr ? brEd.br : null} brEditable={showBr && brEd.editable}
            editable={editable} dfdOn={dfdOn} dfd={liveDfd} onDraftChange={setDraft} />
        )}

        {!node.is_process && live && node.level_no >= FIRST_PROCESS_LEVEL - 1 && dfdOn && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Button variant="outlined" sx={{ alignSelf: 'flex-start' }} component={RouterLink} to={links.dfd(projectId, nodeId)}>
              {t('processes.openDfd')}</Button>
            <CompletenessPanel projectId={projectId} node={node} />
          </Box>
        )}

        {node.is_process && (
          <Box>
            {/* D-66: the delivery items lead the collapsed sections — Solutions, then Function requirements */}
            {showBr && solutionsOn && (
              <PanelSection id="solutions" sections={sections} title={t('processes.sec.solutions')}
                count={facts.solutions.count} summary={facts.solutions.summary}>
                <BrSolutionTags projectId={projectId} br={brEd.br} disabled={!brEd.editable} onWarnings={brEd.onLinkWarnings} bare />
              </PanelSection>
            )}
            {/* D-52: the BR maps to FRs directly; linking needs FUNCTION_REQUIREMENT only, the solution picker SOLUTION too */}
            {showBr && frsOn && (
              <PanelSection id="frs" sections={sections} title={t('processes.sec.frs')}
                count={facts.frs.count} summary={facts.frs.summary}>
                <BrFrLinks projectId={projectId} br={brEd.br} disabled={!brEd.editable} solutionsOn={solutionsOn} bare
                  warnings={brEd.frWarnings} setWarnings={brEd.setFrWarnings} onNotice={onNotice} />
              </PanelSection>
            )}
            {dfdOn && (
              <PanelSection id="parties" sections={sections} title={t('processes.sec.parties')}
                count={facts.parties.count} summary={facts.parties.summary}>
                <StepFlows projectId={projectId} node={node} disabled={!editable} bare />
              </PanelSection>
            )}
            {showBr && (
              <PanelSection id="description" sections={sections} title={t('processes.sec.description')}
                summary={facts.description(v.purpose_desc)}>
                {describe}
              </PanelSection>
            )}
            {/* Supporting systems of an as-is step (Q-23): a to-be step's come from its solutions. */}
            {systemsOn && (
              <PanelSection id="systems" sections={sections} title={t('processes.sec.systems')}
                count={facts.systems.count} summary={facts.systems.summary}>
                <AppLinkPanel projectId={projectId} title={t('applications.links.supportedBy')}
                  empty={t('applications.links.noneSupported')} ownerKey={['step', nodeId]}
                  rowId="application_bfc_node_id" disabled={!editable}
                  api={{ list: () => bfcApi.apps(nodeId),
                    link: (applicationId, n) => bfcApi.linkApp(nodeId, { application_id: applicationId, note: n }),
                    edit: (row, n) => bfcApi.editAppLink(nodeId, row.application_bfc_node_id, { row_version: row.row_version, note: n }),
                    unlink: (row) => bfcApi.unlinkApp(nodeId, row.application_bfc_node_id, row.row_version) }} />
              </PanelSection>
            )}
          </Box>
        )}
      </Box>

      {showFooter && (
        <Box role="region" aria-label={t('common.save')} sx={(th) => ({ position: 'sticky', bottom: 0, zIndex: 3, mt: 'auto', px: 2.5, py: 1.5,
          display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end',
          bgcolor: th.vars.palette.background.paper, borderTop: `1px solid ${th.vars.palette.divider}`,
          borderBottomLeftRadius: 24, borderBottomRightRadius: 24 })}>
          <Typography role="status" sx={{ fontSize: 13, fontWeight: 600, mr: 'auto',
            color: refused || saveNote ? 'error.main' : 'text.primary' }}>
            {saveNote || (refused ? t('processes.save.refused') : t('processes.save.unsavedN', { n: dirtyCount }))}</Typography>
          <Button disabled={dirtyCount === 0 || busy} onClick={discardAll}>{t('processes.discard')}</Button>
          {node.is_process && onNext && (
            <Button variant="outlined" disabled={(!nodeSavable && !brSavable) || busy} onClick={saveAndNext}>
              {t('processes.save.next')}</Button>)}
          <Tooltip title={t('processes.save.shortcut')}>
            <span>
              <Button variant="contained" disabled={(!nodeSavable && !brSavable) || busy} onClick={saveAll}>{t('common.save')}</Button>
            </span>
          </Tooltip>
        </Box>
      )}

      <Menu anchorEl={menuAt} open={Boolean(menuAt)} onClose={() => setMenuAt(null)}>
        {menuItems.map((m) => (m.to ? (
          <MenuItem key={m.key} component={RouterLink} to={m.to} onClick={() => setMenuAt(null)}>
            <ListItemText>{m.label}</ListItemText></MenuItem>
        ) : (
          <MenuItem key={m.key} onClick={() => { setMenuAt(null); m.run(); }}
            sx={m.warn ? { color: 'warning.main' } : undefined}><ListItemText>{m.label}</ListItemText></MenuItem>
        )))}
      </Menu>
      <Menu anchorEl={belowAt} open={Boolean(belowAt)} onClose={() => setBelowAt(null)}
        slotProps={{ paper: { sx: { maxHeight: 360, maxWidth: 420 } } }}>
        {processesBelow.map((p) => (
          <MenuItem key={p.bfc_node_id} onClick={() => { setBelowAt(null); onOpenNode?.(p.bfc_node_id); }}>
            <ListItemText primary={<><Code tone="muted" sx={{ fontSize: 12.5, mr: 1 }}>{p.hier_code}</Code>{p.node_name}</>}
              slotProps={{ primary: { sx: { whiteSpace: 'normal', fontSize: 14 } } }} />
          </MenuItem>))}
      </Menu>
      <ConflictDialog open={save.conflict} unsaved={unsaved} onReload={reload} onClose={() => save.setConflict(false)} />
      {showBr && brEd.dialogs}
      <ConfirmDialog open={confirmRetire} title={t('processes.retireTitle')}
        body={t('processes.retireBody', { name: `${node.hier_code} ${node.node_name}` })}
        confirmLabel={t('processes.retire')} busy={retire.isPending}
        onClose={() => setConfirmRetire(false)} onConfirm={() => retire.mutate()} />
      <ConfirmDialog open={confirmSwitch !== null} busy={mark.isPending} onClose={() => setConfirmSwitch(null)}
        onConfirm={() => mark.mutate(Boolean(confirmSwitch))}
        title={t(confirmSwitch ? 'processes.promoteTitle' : 'processes.demoteTitle')}
        confirmLabel={t(confirmSwitch ? 'processes.promoteConfirm' : 'processes.demoteConfirm')}
        body={t(confirmSwitch ? 'processes.promoteBody' : 'processes.demoteBody', { name: `${node.hier_code} ${node.node_name}` })}>
        {confirmSwitch && (
          <Box component="ul" sx={{ m: 0, pl: 2.5, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
            {(asIs ? ['asIs', 'noChildren', 'freeze'] : ['br', 'noChildren', 'undo', 'freeze']).map((k) => (
              <Typography component="li" key={k} sx={{ fontSize: 14 }}>{t(`processes.promote.${k}`)}</Typography>))}
          </Box>
        )}
      </ConfirmDialog>
      {retiringStep && (
        <RetireStepDialog step={node} onClose={() => setRetiringStep(false)}
          onRetired={() => {
            setRetiringStep(false); setActionError(''); setPlainFor(null); refreshAll();
            onNotice(t('processes.retiredWithDependents'));
            if (!showRetired) onGone();
          }} />
      )}
    </Card>
  );
}
