import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Collapse, IconButton, TextField, Tooltip, Typography } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import ArrowDownwardRounded from '@mui/icons-material/ArrowDownwardRounded';
import ArrowUpwardRounded from '@mui/icons-material/ArrowUpwardRounded';
import EditRounded from '@mui/icons-material/EditRounded';
import { errorText, isStale } from '../../api/client';
import { brApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Code, SectionLabel, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';

const blank = { line_kind_code: '', priority_code: '', line_text: '' };

/** The add / edit form of one line: kind, priority (blank = not yet prioritised) and the statement. */
function LineForm({ id, kinds, priorities, value, onChange, onSubmit, onCancel, submitLabel, busy }) {
  const ok = value.line_kind_code && value.line_text.trim();
  return (
    <Box sx={{ display: 'grid', gap: 1.25, gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
      <SimpleSelect id={`${id}-kind`} label={t('requirements.lines.kind')} value={value.line_kind_code}
        onChange={(v) => onChange({ ...value, line_kind_code: v })} options={kinds} />
      <SimpleSelect id={`${id}-priority`} label={t('requirements.lines.priority')} value={value.priority_code}
        onChange={(v) => onChange({ ...value, priority_code: v })} options={priorities} allowEmpty
        emptyLabel={t('requirements.lines.notPrioritised')} />
      <TextField sx={{ gridColumn: '1 / -1' }} fullWidth multiline minRows={2} size="small" id={`${id}-text`}
        label={t('requirements.lines.text')} value={value.line_text}
        onChange={(e) => onChange({ ...value, line_text: e.target.value })} slotProps={{ htmlInput: { maxLength: 8000 } }} />
      <Box sx={{ gridColumn: '1 / -1', display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
        <Button onClick={onCancel} disabled={busy}>{t('common.cancel')}</Button>
        <Button variant="contained" onClick={onSubmit} disabled={!ok || busy}>{submitLabel}</Button>
      </Box>
    </Box>
  );
}

/**
 * D-59: the requirement's numbered lines (BR-0043.1, .2 …), each with a kind and an optional priority. Each change
 * saves on its own, like the other sections of a requirement. The number is minted by the server and kept for life;
 * the order is changed with the arrows and never renumbers. The requirement's own priority is the highest of its
 * live lines (derived by the server). The old free-text fields are shown read-only as "Earlier free text".
 */
export function BrLines({ projectId, br, priorityCode, disabled }) {
  const qc = useQueryClient();
  const [showRetired, setShowRetired] = useState(false);
  const q = useQuery({ queryKey: [...keys.brLines(br.br_id), showRetired],
    queryFn: () => brApi.lines(br.br_id, showRetired) });
  const { options: kindOptions, getLabel: kindLabel } = useCodes(projectId, 'BR_LINE_KIND');
  const { options: prioOptions, getLabel: prioLabel } = useCodes(projectId, 'BR_PRIORITY');
  // A picker offers the visible codes plus the line's own (wave 1g); a new line passes nothing.
  const kinds = (current) => kindOptions(current).map((c) => ({ value: c.code, label: c.label }));
  const priorities = (current) => prioOptions(current).map((c) => ({ value: c.code, label: c.label }));
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(null);           // the add form's values, or null
  const [editing, setEditing] = useState(null);         // { id, values }
  const [legacyOpen, setLegacyOpen] = useState(false);
  const all = q.data ?? [];
  const live = all.filter((l) => l.is_active);
  const retired = all.filter((l) => !l.is_active);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.br(br.br_id) });   // the lines and the derived priority
  const fail = (err) => { refresh(); setError(isStale(err) ? t('processes.staleLink') : errorText(err, t('common.saveFailed'))); };
  const done = () => { setError(''); refresh(); };
  const body = (v) => ({ line_kind_code: v.line_kind_code, priority_code: v.priority_code || null, line_text: v.line_text });

  const add = useMutation({ mutationFn: (v) => brApi.addLine(br.br_id, body(v)), onSuccess: () => { setAdding(null); done(); }, onError: fail });
  const edit = useMutation({
    mutationFn: ({ line, v }) => brApi.editLine(br.br_id, line.br_requirement_line_id, { row_version: line.row_version, ...body(v) }),
    onSuccess: () => { setEditing(null); done(); }, onError: fail });
  const move = useMutation({
    mutationFn: ({ from, to }) => {
      const next = [...live];
      const [x] = next.splice(from, 1);
      next.splice(to, 0, x);
      return brApi.orderLines(br.br_id, next.map((l) => ({ br_requirement_line_id: l.br_requirement_line_id, row_version: l.row_version })));
    },
    onSuccess: done, onError: fail });
  const retire = useMutation({ mutationFn: (line) => brApi.retireLine(br.br_id, line.br_requirement_line_id, line.row_version),
    onSuccess: done, onError: fail });
  const restore = useMutation({ mutationFn: (line) => brApi.restoreLine(br.br_id, line.br_requirement_line_id),
    onSuccess: done, onError: fail });
  const busy = add.isPending || edit.isPending || move.isPending || retire.isPending || restore.isPending;
  const legacy = [[t('requirements.lines.legacyLogic'), br.business_logic], [t('requirements.lines.legacyOutput'), br.output_expectation]]
    .filter(([, v]) => v && v.trim());

  const row = (line, i) => {
    const label = line.line_label;
    if (editing?.id === line.br_requirement_line_id) {
      return (
        <Box key={line.br_requirement_line_id} sx={{ py: 1 }}>
          <Typography sx={{ mb: 1 }}><Code>{label}</Code></Typography>
          <LineForm id={`line-${line.br_requirement_line_id}`} kinds={kinds(line.line_kind_code)} priorities={priorities(line.priority_code)} value={editing.values}
            onChange={(values) => setEditing({ ...editing, values })} busy={busy} submitLabel={t('common.save')}
            onCancel={() => setEditing(null)} onSubmit={() => edit.mutate({ line, v: editing.values })} />
        </Box>
      );
    }
    return (
      <Box key={line.br_requirement_line_id} data-testid="br-line"
        sx={{ display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr) auto', gap: 1.25, alignItems: 'start', py: 1,
          borderTop: 1, borderColor: 'divider', opacity: line.is_active ? 1 : 0.6 }}>
        <Code>{label}</Code>
        <Box sx={{ minWidth: 0 }}>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 0.5 }}>
            <Tag tone="navy" size="sm">{kindLabel(line.line_kind_code)}</Tag>
            {line.priority_code
              ? <Tag tone="purple" size="sm">{prioLabel(line.priority_code)}</Tag>
              : <Tag tone="neutral" size="sm">{t('requirements.lines.notPrioritised')}</Tag>}
            {!line.is_active && <Tag tone="neutral" size="sm">{t('processes.retiredChip')}</Tag>}
          </Box>
          <Typography sx={{ fontSize: 14, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{line.line_text}</Typography>
        </Box>
        {!disabled && (line.is_active ? (
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Tooltip title={t('requirements.lines.up')}><span>
              <IconButton size="small" aria-label={t('requirements.lines.upFor', { label })} disabled={busy || i === 0}
                onClick={() => move.mutate({ from: i, to: i - 1 })}><ArrowUpwardRounded fontSize="small" /></IconButton></span></Tooltip>
            <Tooltip title={t('requirements.lines.down')}><span>
              <IconButton size="small" aria-label={t('requirements.lines.downFor', { label })} disabled={busy || i === live.length - 1}
                onClick={() => move.mutate({ from: i, to: i + 1 })}><ArrowDownwardRounded fontSize="small" /></IconButton></span></Tooltip>
            <Tooltip title={t('requirements.lines.edit')}>
              <IconButton size="small" aria-label={t('requirements.lines.editFor', { label })} disabled={busy}
                onClick={() => setEditing({ id: line.br_requirement_line_id, values: {
                  line_kind_code: line.line_kind_code, priority_code: line.priority_code ?? '', line_text: line.line_text } })}>
                <EditRounded fontSize="small" /></IconButton></Tooltip>
            <Button size="small" color="warning" disabled={busy} onClick={() => retire.mutate(line)}>{t('requirements.lines.retire')}</Button>
          </Box>
        ) : (
          <Button size="small" disabled={busy} onClick={() => restore.mutate(line)}>{t('requirements.lines.restore')}</Button>
        ))}
      </Box>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
      <SectionLabel info={t('requirements.lines.info')} action={(
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {priorityCode && <Tag tone="purple">{t('requirements.lines.brPriority', { label: prioLabel(priorityCode) })}</Tag>}
          {!disabled && !adding && (
            <Button size="small" startIcon={<AddRounded />} sx={{ color: 'brand.purpleText' }} disabled={busy}
              onClick={() => { setError(''); setAdding({ ...blank, line_kind_code: kinds()[0]?.value ?? '' }); }}>
              {t('requirements.lines.add')}</Button>)}
        </Box>)}>
        {t('requirements.lines.title')}
      </SectionLabel>
      {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }} onClose={() => setError('')}>{error}</Alert>}
      {q.error && <Alert severity="error">{errorText(q.error)}</Alert>}
      {!q.isLoading && !q.error && live.length === 0 && !adding && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.lines.none')}</Typography>)}
      <Box>{live.map(row)}</Box>
      {adding && (
        <LineForm id="line-new" kinds={kinds()} priorities={priorities()} value={adding} onChange={setAdding} busy={busy}
          submitLabel={t('requirements.lines.add')} onCancel={() => setAdding(null)} onSubmit={() => add.mutate(adding)} />)}
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <Button size="small" sx={{ alignSelf: 'flex-start', px: 0 }} onClick={() => setShowRetired((s) => !s)}>
          {showRetired ? t('requirements.lines.hideRetired') : t('requirements.lines.showRetired')}</Button>
        {legacy.length > 0 && (
          <Button size="small" sx={{ alignSelf: 'flex-start', px: 0 }} onClick={() => setLegacyOpen((o) => !o)}>
            {legacyOpen ? t('requirements.lines.hideLegacy') : t('requirements.lines.showLegacy')}</Button>)}
      </Box>
      {showRetired && retired.length > 0 && <Box>{retired.map((l) => row(l, -1))}</Box>}
      {showRetired && !q.isLoading && retired.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('requirements.lines.noRetired')}</Typography>)}
      <Collapse in={legacyOpen} unmountOnExit>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }}>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('requirements.lines.legacyHint')}</Typography>
          {legacy.map(([label, value]) => (
            <Box key={label}>
              <Typography sx={{ fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>{label}</Typography>
              <Typography sx={{ fontSize: 14, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{value}</Typography>
            </Box>
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}
