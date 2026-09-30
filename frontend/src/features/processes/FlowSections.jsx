import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, Link, Stack, TextField, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/EditOutlined';
import { errorText, isStale } from '../../api/client';
import { bfcApi, flowApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { t } from '../../i18n/t';
import { Mono, SectionTitle, SimpleSelect, blankToNull } from './chartKit';
import { LoadError } from './StepSections';

const FLOW_TYPES = ['SEQUENCE', 'CONDITIONAL', 'PARALLEL', 'HANDOFF'];     // = ck_bnf_flow_type (S2-1)
const typeLabel = (ft) => t(`processes.flowType.${ft}`);
const stepLabel = (n) => (n ? `${n.hier_code} ${n.node_name}` : '');

/** Live process steps of the project, by id — the other end of every edge. */
function useSteps(projectId) {
  const q = useQuery({ queryKey: keys.tree(projectId), queryFn: () => bfcApi.tree(projectId) });
  return useMemo(() => {
    const steps = (q.data ?? []).filter((n) => n.is_process && n.is_active);
    return { list: steps, byId: new Map(steps.map((n) => [n.bfc_node_id, n])), error: q.error };
  }, [q.data, q.error]);
}

function EdgeDialog({ projectId, node, edge, steps, onClose, onDone }) {
  const editing = Boolean(edge);
  const [dir, setDir] = useState('O');
  const [other, setOther] = useState(null);
  const [v, setV] = useState({
    flow_type: edge?.flow_type ?? 'SEQUENCE', condition_label: edge?.condition_label ?? '',
    seq_no: edge?.seq_no ?? '', note: edge?.note ?? '' });
  const [error, setError] = useState('');
  const set = (k) => (val) => setV((s) => ({ ...s, [k]: val }));
  const needsLabel = v.flow_type === 'CONDITIONAL' && !v.condition_label.trim();
  const seqOk = v.seq_no === '' || (/^\d+$/.test(String(v.seq_no)) && +v.seq_no >= 1 && +v.seq_no <= 99);
  const fields = () => ({ flow_type: v.flow_type, condition_label: blankToNull(v.condition_label.trim()),
    seq_no: v.seq_no === '' ? null : +v.seq_no, note: blankToNull(v.note) });
  const m = useMutation({
    mutationFn: () => {
      if (editing) return flowApi.update(edge.bfc_node_flow_id, { row_version: edge.row_version, ...fields() });
      const otherId = other?.bfc_node_id ?? null;
      return flowApi.create(projectId, { ...fields(),
        from_bfc_node_id: dir === 'O' ? node.bfc_node_id : otherId,
        to_bfc_node_id: dir === 'O' ? otherId : node.bfc_node_id });
    },
    onSuccess: () => { onDone(); onClose(); },
    onError: (err) => {
      if (isStale(err)) onDone();
      setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed')));
    },
  });
  const end = (id, fallback) => (id == null ? t(fallback) : stepLabel(steps.byId.get(id)) || `#${id}`);
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t(editing ? 'processes.editEdgeTitle' : 'processes.addEdgeTitle')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2} sx={{ mt: 1 }}>
          {editing ? (
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
              {t('processes.edgeFixed', { from: end(edge.from_bfc_node_id, 'processes.flowStart'),
                to: end(edge.to_bfc_node_id, 'processes.flowEnd') })}</Typography>
          ) : (
            <>
              <SimpleSelect id="edge-dir" label={t('processes.edgeDirection')} value={dir} onChange={setDir}
                options={[{ value: 'O', label: t('processes.edgeGoesTo') }, { value: 'I', label: t('processes.edgeComesFrom') }]} />
              <Autocomplete options={steps.list} getOptionLabel={stepLabel} value={other}
                onChange={(_, val) => setOther(val)}
                isOptionEqualToValue={(a, b) => a.bfc_node_id === b.bfc_node_id}
                renderInput={(params) => (
                  <TextField {...params} label={t('processes.edgeOther')} helperText={t('processes.edgeOtherHelp')} />)} />
            </>
          )}
          <SimpleSelect id="edge-type" label={t('processes.flowType')} value={v.flow_type} onChange={set('flow_type')}
            options={FLOW_TYPES.map((ft) => ({ value: ft, label: typeLabel(ft) }))} />
          <TextField id="edge-condition" label={t('processes.condition')} value={v.condition_label}
            required={v.flow_type === 'CONDITIONAL'} error={needsLabel}
            helperText={needsLabel ? t('processes.conditionRequired')
              : (v.flow_type === 'HANDOFF' ? t('processes.conditionHandoff') : ' ')}
            onChange={(e) => set('condition_label')(e.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }} />
          <TextField id="edge-order" label={t('processes.edgeOrder')} value={v.seq_no} error={!seqOk}
            onChange={(e) => set('seq_no')(e.target.value)} slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 2 } }} />
          <TextField id="edge-note" label={t('processes.edgeNote')} value={v.note} multiline minRows={2}
            onChange={(e) => set('note')(e.target.value)} slotProps={{ htmlInput: { maxLength: 2000 } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={needsLabel || !seqOk || m.isPending}
          onClick={() => { setError(''); m.mutate(); }}>{t(editing ? 'common.save' : 'processes.add')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/** What comes before and after a process step (bfc_node_flow, D-20). */
export function StepSequence({ projectId, node, disabled }) {
  const qc = useQueryClient();
  const qk = [...keys.flows(projectId), 'node', String(node.bfc_node_id)];
  const q = useQuery({ queryKey: qk, queryFn: () => flowApi.list(projectId, node.bfc_node_id) });
  const steps = useSteps(projectId);
  const [dialog, setDialog] = useState(null);       // null | 'new' | edge
  const [error, setError] = useState('');
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });
    qc.invalidateQueries({ queryKey: keys.flowGaps(projectId) });
  };
  const remove = useMutation({
    mutationFn: (e) => flowApi.remove(e.bfc_node_flow_id, e.row_version),
    onSuccess: () => { setError(''); refresh(); },
    onError: (err) => { refresh(); setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed'))); },
  });
  const rows = q.data ?? [];
  const me = node.bfc_node_id;
  const column = (incoming) => {
    const mine = rows.filter((e) => (incoming ? e.to_bfc_node_id === me : e.from_bfc_node_id === me));
    return (
      <Box sx={{ flex: 1, minWidth: 240 }}>
        <SectionTitle>{t(incoming ? 'processes.flowFrom' : 'processes.flowTo')}</SectionTitle>
        <Stack spacing={0.75}>
          {mine.map((e) => {
            const otherId = incoming ? e.from_bfc_node_id : e.to_bfc_node_id;
            const other = otherId == null ? null : steps.byId.get(otherId);
            const name = otherId == null ? t(incoming ? 'processes.flowStart' : 'processes.flowEnd')
              : (stepLabel(other) || `#${otherId}`);
            return (
              <Stack key={`${incoming}-${e.bfc_node_flow_id}`} direction="row" sx={{ alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Chip size="small" variant={e.flow_type === 'SEQUENCE' ? 'outlined' : 'filled'} label={typeLabel(e.flow_type)} />
                {otherId == null || !other ? (
                  <Typography sx={{ fontWeight: 600 }}>{name}</Typography>
                ) : (
                  <Link component={RouterLink} to={links.node(projectId, otherId)} sx={{ fontWeight: 600 }}>
                    <Mono>{other.hier_code}</Mono> {other.node_name}</Link>
                )}
                {e.condition_label && (
                  <Typography sx={{ fontSize: 13, color: 'text.secondary', whiteSpace: 'pre-wrap' }}>
                    {t('processes.edgeCondition', { label: e.condition_label })}</Typography>
                )}
                {e.seq_no != null && (
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('processes.edgeOrderShort', { n: e.seq_no })}</Typography>
                )}
                {!disabled && (
                  <>
                    <IconButton size="small" aria-label={t(incoming ? 'processes.editEdgeFrom' : 'processes.editEdge', { step: name })}
                      onClick={() => { setError(''); setDialog(e); }}><EditIcon fontSize="small" /></IconButton>
                    <IconButton size="small" aria-label={t(incoming ? 'processes.removeEdgeFrom' : 'processes.removeEdge', { step: name })}
                      disabled={remove.isPending} onClick={() => remove.mutate(e)}><CloseIcon fontSize="small" /></IconButton>
                  </>
                )}
              </Stack>
            );
          })}
          {!q.isLoading && !q.error && mine.length === 0 && (
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
              {t(incoming ? 'processes.noFlowIn' : 'processes.noFlowOut')}</Typography>
          )}
        </Stack>
      </Box>
    );
  };
  return (
    <Box>
      <SectionTitle action={!disabled && (
        <Button size="small" onClick={() => { setError(''); setDialog('new'); }}>{t('processes.addEdge')}</Button>)}>
        {t('processes.flowTitle')}</SectionTitle>
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <LoadError errors={[q.error, steps.error]} />
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 3 }}>
        {column(true)}
        {column(false)}
      </Stack>
      {dialog && (
        <EdgeDialog projectId={projectId} node={node} steps={steps} edge={dialog === 'new' ? null : dialog}
          onClose={() => setDialog(null)} onDone={refresh} />
      )}
    </Box>
  );
}

const GAP_KINDS = ['orphan_steps', 'no_start', 'no_end', 'no_output', 'no_lane'];

/** The flow completeness report (§7.2a), narrowed to the steps under one parent node. */
export function FlowGaps({ projectId, node }) {
  const q = useQuery({ queryKey: keys.flowGaps(projectId), queryFn: () => flowApi.completeness(projectId) });
  const under = (r) => r.hier_code === node.hier_code || r.hier_code.startsWith(`${node.hier_code}.`);
  const gaps = GAP_KINDS.map((k) => [k, (q.data?.[k] ?? []).filter(under)]).filter(([, rs]) => rs.length);
  return (
    <Box>
      <SectionTitle>{t('processes.flowGaps')}</SectionTitle>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1 }}>{t('processes.flowGapsHelp')}</Typography>
      <LoadError errors={[q.error]} />
      {q.data && gaps.length === 0 && <Typography sx={{ fontSize: 13 }}>{t('processes.flowGapsNone')}</Typography>}
      <Stack spacing={1.5}>
        {gaps.map(([k, rs]) => (
          <Box key={k}>
            <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{t('processes.gapCount', { what: t(`processes.gap.${k}`), n: rs.length })}</Typography>
            <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 0.75, mt: 0.5 }}>
              {rs.map((r) => (
                <Chip key={r.bfc_node_id} size="small" variant="outlined" clickable component={RouterLink}
                  to={links.node(projectId, r.bfc_node_id)} label={<><Mono>{r.hier_code}</Mono> {r.node_name}</>} />
              ))}
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
