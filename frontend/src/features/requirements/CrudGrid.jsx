import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, Chip, Link, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Typography } from '@mui/material';
import { errorText, isStale } from '../../api/client';
import { brApi, dataApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { t } from '../../i18n/t';
import { Mono, PickDialog, SectionTitle, dirLabel, entityLabel } from '../processes/chartKit';
import { LoadError } from '../processes/StepSections';

const CRUD = ['C', 'R', 'U', 'D'];
export const brDataKey = (brId) => [...keys.br(brId), 'data'];

/**
 * Data usage · CRUD for one requirement (br_data_entity, D-24). One row per entity; the
 * In/Out column is the server's derived `direction` of the live links — never sent.
 * Ticking a CRUD also creates the step's data in/out on the server, so the node is refreshed.
 */
export function CrudGrid({ projectId, br, disabled }) {
  const qc = useQueryClient();
  const qk = brDataKey(br.br_id);
  const q = useQuery({ queryKey: qk, queryFn: () => brApi.data(br.br_id) });
  const entQ = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const byId = useMemo(() => new Map((entQ.data ?? []).map((e) => [e.data_entity_id, e])), [entQ.data]);
  const [added, setAdded] = useState([]);          // entities picked but not yet ticked
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState('');
  const linksList = useMemo(() => q.data ?? [], [q.data]);

  const entityIds = [...new Set([...linksList.map((l) => l.data_entity_id), ...added])];
  const refresh = (deId) => {
    qc.invalidateQueries({ queryKey: qk });
    qc.invalidateQueries({ queryKey: keys.node(br.bfc_node_id) });
    if (deId) qc.invalidateQueries({ queryKey: keys.entity(deId) });
  };
  const toggle = useMutation({
    mutationFn: ({ deId, crud, link }) => (link
      ? brApi.unlinkData(br.br_id, link.br_data_entity_id, link.row_version)
      : brApi.linkData(br.br_id, { data_entity_id: deId, crud_code: crud })),
    onSuccess: (_, { deId }) => { setError(''); refresh(deId); },
    onError: (err, { deId }) => {
      refresh(deId);
      setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed')));
    },
  });

  const available = (entQ.data ?? []).filter((e) => e.is_active && !entityIds.includes(e.data_entity_id));

  return (
    <Box>
      <SectionTitle action={!disabled && (
        <Button size="small" onClick={() => { setError(''); setAdding(true); }}>{t('requirements.addEntity')}</Button>)}>
        {t('requirements.crudTitle')}
      </SectionTitle>
      {error && <Alert severity="error" sx={{ mb: 1, whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <LoadError errors={[q.error, entQ.error]} />
      <TableContainer sx={{ border: 1, borderColor: 'divider', borderRadius: 2 }}>
        <Table size="small" aria-label={t('requirements.crudTitle')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('requirements.entity')}</TableCell>
              {CRUD.map((c) => <TableCell key={c} align="center" sx={{ width: 44 }}>{t(`requirements.crud.${c}`)}</TableCell>)}
              <TableCell sx={{ width: 90 }}>{t('requirements.derived')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!q.isLoading && !q.error && entityIds.length === 0 && (
              <TableRow><TableCell colSpan={6}>
                <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.noData')}</Typography>
              </TableCell></TableRow>
            )}
            {entityIds.map((deId) => {
              const de = byId.get(deId);
              const mine = linksList.filter((l) => l.data_entity_id === deId);
              const dirs = ['I', 'O'].filter((d) => mine.some((l) => l.direction === d));
              return (
                <TableRow key={deId}>
                  <TableCell>
                    <Link component={RouterLink} to={links.entity(projectId, deId)}>
                      {de ? <><Mono>{de.de_number}</Mono> {de.de_name}</> : `#${deId}`}</Link>
                  </TableCell>
                  {CRUD.map((c) => {
                    const link = mine.find((l) => l.crud_code === c);
                    return (
                      <TableCell key={c} align="center" padding="checkbox">
                        <Checkbox size="small" checked={Boolean(link)} disabled={disabled || toggle.isPending}
                          slotProps={{ input: { 'aria-label': t('requirements.crudFor', { crud: t(`requirements.crudName.${c}`), entity: entityLabel(de) }) } }}
                          onChange={() => toggle.mutate({ deId, crud: c, link })} />
                      </TableCell>
                    );
                  })}
                  <TableCell>
                    {dirs.length > 0 && <Chip size="small" label={dirs.map(dirLabel).join(' · ')} />}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 1 }}>{t('requirements.crudHelp')}</Typography>
      {adding && (
        <PickDialog open title={t('requirements.addEntityTitle')} optionLabel={t('requirements.entity')}
          options={available} getOptionLabel={entityLabel} submitLabel={t('processes.add')}
          emptyHint={(
            <Alert severity="info">
              {t('processes.noEntities')}{' '}
              <Link component={RouterLink} to={links.data(projectId)}>{t('processes.goData')}</Link>
            </Alert>)}
          onSubmit={async (de) => de}
          onDone={(de) => setAdded((a) => [...a, de.data_entity_id])} onClose={() => setAdding(false)} />
      )}
    </Box>
  );
}
