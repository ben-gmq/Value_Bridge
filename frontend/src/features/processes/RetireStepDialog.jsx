import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Box, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { bfcApi } from '../../api/scope';
import { keys } from '../../app/links';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { t } from '../../i18n/t';
import { Mono } from './chartKit';

// Preview order = the spec's owned set (docs/step_retire_spec.md §4). Unknown tables still list.
const KINDS = ['business_requirement', 'br_data_entity', 'br_org_role', 'bfc_node_data_entity',
  'bfc_node_org_role', 'bfc_node_external_flow', 'bfc_node_flow'];

const count = (owned, ...tables) => owned.filter((o) => tables.includes(o.table)).length;

function summary(owned) {
  const br = owned.find((o) => o.table === 'business_requirement');
  const vars = {
    br: br?.label,
    data: count(owned, 'br_data_entity', 'bfc_node_data_entity'),
    roles: count(owned, 'br_org_role', 'bfc_node_org_role'),
    outside: count(owned, 'bfc_node_external_flow'),
    arrows: count(owned, 'bfc_node_flow'),
  };
  return t(br ? 'processes.retireStepSummary' : 'processes.retireStepSummaryNoBr', vars);
}

function RowList({ rows }) {
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
      {rows.map((r) => (
        <Typography component="li" key={`${r.table}:${r.id}`} sx={{ fontSize: 13 }}>{r.label}</Typography>
      ))}
    </Box>
  );
}

/**
 * The one retire for a process step, shared by the flow canvas pop-up and the node panel. It
 * shows what goes with the step (and anything outside it that still blocks), then retires on
 * confirm with the preview's hash, so a step changed in between is refused, not guessed at.
 */
export function RetireStepDialog({ step, onClose, onRetired }) {
  const [error, setError] = useState('');
  const id = step.bfc_node_id;
  const q = useQuery({ queryKey: keys.retirePreview(id), queryFn: () => bfcApi.retirePreview(id),
    staleTime: 0, refetchOnMount: 'always' });
  const pv = q.data;
  const retire = useMutation({
    mutationFn: () => bfcApi.retireWithDependents(id, pv.confirm_hash),
    onSuccess: () => onRetired(),
    onError: (err) => { setError(errorText(err, t('common.saveFailed'))); q.refetch(); },
  });
  const blocked = Boolean(pv?.blockers.length);
  const groups = pv ? [...KINDS, ...new Set(pv.owned.map((o) => o.table).filter((x) => !KINDS.includes(x)))]
    .map((k) => ({ k, rows: pv.owned.filter((o) => o.table === k) })).filter((g) => g.rows.length) : [];

  return (
    <ConfirmDialog open title={t('processes.retireStepTitle')}
      body={t('processes.retireStepBody', { name: `${step.hier_code} ${step.node_name}` })}
      confirmLabel={t('processes.retireWithDependents')} busy={!pv || blocked || retire.isPending || q.isFetching}
      onClose={onClose} onConfirm={() => { setError(''); retire.mutate(); }}>
      {(error || q.error) && (
        <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error || errorText(q.error)}</Alert>)}
      {!pv && !q.error && <Typography sx={{ color: 'text.secondary' }}>{t('processes.retireStepLoading')}</Typography>}
      {pv && (
        <>
          <Typography sx={{ fontWeight: 600, mb: 1 }}>
            {pv.owned.length ? summary(pv.owned) : t('processes.retireStepNothing')}</Typography>
          {groups.map(({ k, rows }) => (
            <Box key={k} sx={{ mb: 1.5 }}>
              <Typography sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary' }}>
                {t(KINDS.includes(k) ? `processes.retireKind.${k}` : 'processes.retireKind.other', { n: rows.length, table: k })}
              </Typography>
              {k === 'business_requirement'
                ? <Typography sx={{ fontSize: 13 }}><Mono>{rows[0].label}</Mono></Typography>
                : <RowList rows={rows} />}
            </Box>
          ))}
          {blocked && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              <Typography sx={{ fontSize: 13, mb: 0.5 }}>{t('processes.retireStepBlocked')}</Typography>
              <RowList rows={pv.blockers} />
            </Alert>
          )}
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 1 }}>{t('processes.retireStepUndo')}</Typography>
        </>
      )}
    </ConfirmDialog>
  );
}
