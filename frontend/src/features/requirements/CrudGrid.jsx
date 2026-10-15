import { Fragment, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, IconButton, Link, Table, TableBody, TableCell, TableHead,
  TableRow, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import KeyboardArrowDownRounded from '@mui/icons-material/KeyboardArrowDownRounded';
import KeyboardArrowRightRounded from '@mui/icons-material/KeyboardArrowRightRounded';
import { errorText, isStale } from '../../api/client';
import { brApi, dataApi } from '../../api/scope';
import { api } from '../../api/vb';
import { useCodes } from '../../app/useCodes';
import { keys, links } from '../../app/links';
import { t } from '../../i18n/t';
import { Code, MonoChip, SectionLabel, Tag } from '../../components/kit';
import { MONO } from '../../theme/theme';
import { PickDialog, dirLabel, entityLabel } from '../processes/chartKit';
import { LoadError } from '../processes/StepSections';
import { requiredText } from '../data/fieldRules';

const CRUD = ['C', 'R', 'U', 'D'];
export const brDataKey = (brId) => [...keys.br(brId), 'data'];

/**
 * D-60(a): one entity's live attributes under its grid row, read-only, in field order — the same query the entity
 * page reads, fetched on first expand. Under KEYS_ONLY (D-39) only keys are expected, so keys alone raise nothing;
 * under FULL an entity whose fields are all keys says so, as the consistency report does (entities_keys_only).
 */
function Attributes({ projectId, deId, depth }) {
  const q = useQuery({ queryKey: [...keys.entity(deId), 'fields'], queryFn: () => dataApi.fields(deId) });
  const { getLabel } = useCodes(projectId, 'FIELD_DATA_TYPE');
  if (q.isLoading) return <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.attr.loading')}</Typography>;
  if (q.error) return <LoadError errors={[q.error]} />;
  const fields = (q.data ?? []).filter((f) => f.is_active !== false).sort((a, b) => a.seq_no - b.seq_no);
  if (!fields.length) return <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.attr.none')}</Typography>;
  const keysOnly = depth === 'FULL' && fields.every((f) => f.is_primary_key || f.is_foreign_key);
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, minWidth: 0 }}>
      <Box component="ul" aria-label={t('requirements.attr.title')} sx={{ m: 0, p: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {fields.map((f) => (
          <Box component="li" key={f.data_field_id} sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', fontSize: 13 }}>
            <Box component="span" sx={{ fontWeight: f.is_primary_key ? 700 : 500, wordBreak: 'break-word' }}>{f.field_name}</Box>
            {f.data_type_code && <Box component="span" sx={{ fontFamily: MONO, fontSize: 12.5, color: 'text.secondary' }}>{getLabel(f.data_type_code)}</Box>}
            {f.is_primary_key && <Tag tone="caution">{t('requirements.attr.pk')}</Tag>}
            {f.is_foreign_key && <Tag tone="teal">{t('requirements.attr.fk')}</Tag>}
            <Box component="span" sx={{ fontSize: 12.5, color: 'brand.muted' }}>
              {t('requirements.attr.mandatory', { value: requiredText(f.is_mandatory) })}</Box>
          </Box>))}
      </Box>
      {keysOnly && <Typography sx={{ fontSize: 12.5, color: 'warning.main' }}>{t('requirements.attr.keysOnly')}</Typography>}
    </Box>
  );
}

/**
 * Data usage · CRUD for one requirement (br_data_entity, D-24). One row per entity; the
 * In/Out column is the server's derived `direction` of the live links — never sent.
 * Ticking a CRUD also creates the step's data in/out on the server, so the node is refreshed. `emptyText` lets the
 * process panel say why an empty grid sits over rows recorded on the DFD only (10e).
 */
export function CrudGrid({ projectId, br, disabled, mark, emptyText }) {
  const qc = useQueryClient();
  const qk = brDataKey(br.br_id);
  const q = useQuery({ queryKey: qk, queryFn: () => brApi.data(br.br_id) });
  const entQ = useQuery({ queryKey: keys.entities(projectId), queryFn: () => dataApi.list(projectId) });
  const byId = useMemo(() => new Map((entQ.data ?? []).map((e) => [e.data_entity_id, e])), [entQ.data]);
  const projQ = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const [open, setOpen] = useState(() => new Set());   // entities whose attributes are shown (D-60a)
  const flip = (deId) => setOpen((o) => { const n = new Set(o); if (n.has(deId)) n.delete(deId); else n.add(deId); return n; });
  const [added, setAdded] = useState([]);          // entities picked but not yet ticked
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState('');
  const linksList = useMemo(() => q.data ?? [], [q.data]);

  const entityIds = [...new Set([...linksList.map((l) => l.data_entity_id), ...added])];
  const refresh = (deId) => {
    qc.invalidateQueries({ queryKey: qk });
    qc.invalidateQueries({ queryKey: keys.node(br.bfc_node_id) });
    qc.invalidateQueries({ queryKey: keys.tree(projectId) });          // DR13-D2: CRUD writes step I/O → the light
    qc.invalidateQueries({ queryKey: keys.flows(projectId) });         // …and the DFD graph and gaps draw it (sara L1)
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
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      <SectionLabel action={!disabled && (
        <Button size="small" startIcon={<AddRounded />} sx={{ color: 'brand.purpleText' }}
          onClick={() => { setError(''); setAdding(true); }}>{t('requirements.addEntity')}</Button>)} info={t('requirements.crudHelp')}>
        {t('requirements.crudTitle')}
        {mark && <Box component="span" sx={{ ml: 0.75, textTransform: 'none', letterSpacing: 0 }}>{mark}</Box>}
      </SectionLabel>
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      <LoadError errors={[q.error, entQ.error]} />
      <Box sx={(th) => ({ border: `1px solid ${th.vars.palette.divider}`, borderRadius: '16px', overflowX: 'auto' })}>
        <Table size="small" aria-label={t('requirements.crudTitle')}>
          <TableHead>
            <TableRow sx={{ bgcolor: 'background.subtle' }}>
              <TableCell>{t('requirements.entity')}</TableCell>
              {CRUD.map((c) => (
                <TableCell key={c} align="center" sx={{ width: 36, px: 0.25, fontFamily: MONO }}>{t(`requirements.crud.${c}`)}</TableCell>))}
              <TableCell sx={{ width: 76, pl: 1 }}>{t('requirements.derived')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!q.isLoading && !q.error && entityIds.length === 0 && (
              <TableRow><TableCell colSpan={6}>
                <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{emptyText ?? t('requirements.noData')}</Typography>
              </TableCell></TableRow>
            )}
            {entityIds.map((deId) => {
              const de = byId.get(deId);
              const mine = linksList.filter((l) => l.data_entity_id === deId);
              const dirs = ['I', 'O'].filter((d) => mine.some((l) => l.direction === d));
              const shown = open.has(deId);
              return (
                <Fragment key={deId}>
                <TableRow sx={shown ? { '& > td': { borderBottom: 0 } } : undefined}>
                  <TableCell sx={{ minWidth: 150, pl: 0.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                      <IconButton size="small" onClick={() => flip(deId)} aria-expanded={shown} aria-controls={`attrs-${br.br_id}-${deId}`}
                        aria-label={t(shown ? 'requirements.attr.hide' : 'requirements.attr.show', { entity: entityLabel(de) || `#${deId}` })}
                        sx={{ width: 28, height: 28, flex: 'none' }}>
                        {shown ? <KeyboardArrowDownRounded fontSize="small" /> : <KeyboardArrowRightRounded fontSize="small" />}
                      </IconButton>
                      <Link component={RouterLink} to={links.entity(projectId, deId)} underline="hover" color="inherit">
                        {de ? <><Code tone="teal" sx={{ fontSize: 12.5, mr: 1 }}>{de.de_number}</Code>{de.de_name}</> : `#${deId}`}
                      </Link>
                    </Box>
                  </TableCell>
                  {CRUD.map((c) => {
                    const link = mine.find((l) => l.crud_code === c);
                    return (
                      <TableCell key={c} align="center" padding="none" sx={{ px: 0.25 }}>
                        <Checkbox size="small" checked={Boolean(link)} disabled={disabled || toggle.isPending}
                          sx={{ '&.Mui-checked': { color: 'brand.ftcViolet' } }}
                          slotProps={{ input: { 'aria-label': t('requirements.crudFor', { crud: t(`requirements.crudName.${c}`), entity: entityLabel(de) }) } }}
                          onChange={() => toggle.mutate({ deId, crud: c, link })} />
                      </TableCell>
                    );
                  })}
                  <TableCell sx={{ pl: 1, whiteSpace: 'nowrap' }}>
                    {dirs.length > 0 && (
                      <MonoChip size="lg" tone={dirs.includes('O') ? 'purple' : 'neutral'}>{dirs.map(dirLabel).join(' · ')}</MonoChip>)}
                  </TableCell>
                </TableRow>
                {shown && (
                  <TableRow id={`attrs-${br.br_id}-${deId}`}>
                    <TableCell colSpan={6} sx={{ pl: 5, pt: 0, pb: 1.5 }}>
                      <Attributes projectId={projectId} deId={deId} depth={projQ.data?.data_model_depth} />
                    </TableCell>
                  </TableRow>)}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </Box>
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
