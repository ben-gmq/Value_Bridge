import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Snackbar, Stack, Table, TableBody, TableCell, TableHead,
  TableRow, TextField, Typography } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import { baselineApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Code, KV, Segmented, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { AgreedChip, StatusChip, entityLabel, fieldLabel, fmtDate, fmtDateTime, fmtValue } from './baselineKit';
import { detailText } from './FreezeDialog';

const PAGE = 100;

function ApproveDialog({ b, open, onClose, onDone }) {
  const qc = useQueryClient();
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Bangkok' });
  const [form, setForm] = useState({ name: '', date: today, reference: '', note: '' });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = useMutation({
    mutationFn: () => baselineApi.approve(b.baseline_id, { client_approver_name: form.name.trim(),
      client_approved_on: form.date, approval_reference: form.reference || null, approval_note: form.note || null,
      row_version: b.row_version }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.baseline(b.baseline_id) });
      qc.invalidateQueries({ queryKey: keys.baselines(b.project_id) });
      onDone();
    },
  });
  return (
    <ConfirmDialog open={open} title={t('baselines.approve.title', { label: b.version_label })} body={t('baselines.approve.body')}
      confirmLabel={t('baselines.approve.confirm')} busy={save.isPending || !form.name.trim() || !form.date}
      onConfirm={() => save.mutate()} onClose={() => { save.reset(); onClose(); }}>
      <Stack spacing={2}>
        <TextField label={t('baselines.approve.name')} value={form.name} onChange={set('name')} size="small" required
          slotProps={{ htmlInput: { maxLength: 200 } }} />
        <TextField label={t('baselines.approve.date')} type="date" value={form.date} onChange={set('date')} size="small" required
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: today } }} />
        <TextField label={t('baselines.approve.reference')} helperText={t('baselines.approve.referenceHelp')} value={form.reference}
          onChange={set('reference')} size="small" slotProps={{ htmlInput: { maxLength: 200 } }} />
        <TextField label={t('baselines.approve.note')} value={form.note} onChange={set('note')} size="small" multiline maxRows={4}
          slotProps={{ htmlInput: { maxLength: 4000 } }} />
        {save.error && <Alert severity="error">{detailText(save.error)}</Alert>}
      </Stack>
    </ConfirmDialog>
  );
}

function Rows({ b, entity }) {
  const [limit, setLimit] = useState(PAGE);
  const q = useQuery({ queryKey: keys.baselineRows(b.baseline_id, entity, limit),
    queryFn: () => baselineApi.rows(b.baseline_id, entity, 0, limit) });
  const d = q.data;
  if (q.error) return <Alert severity="error">{detailText(q.error)}</Alert>;
  if (!d) return null;
  if (d.total === 0) return <Typography sx={{ color: 'text.secondary', px: 2.5 }}>{t('baselines.view.empty')}</Typography>;
  // ids are shown through the row's label; a code shows as its label beside it (UAT 8 D3)
  const cols = d.columns.filter((c) => !c.endsWith('_id')
    && !(c.endsWith('_code') && d.columns.includes(`${c.slice(0, -5)}_label`)));
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ pl: 2.5 }}>{t('baselines.col.item')}</TableCell>
            {cols.map((c) => <TableCell key={c} sx={{ whiteSpace: 'nowrap' }}>{fieldLabel(c)}</TableCell>)}
          </TableRow>
        </TableHead>
        <TableBody>
          {d.rows.map((r) => (
            <TableRow key={r.source_id}>
              <TableCell sx={{ pl: 2.5, fontWeight: 600, minWidth: 180, wordBreak: 'break-word' }}>{r.label}</TableCell>
              {cols.map((c) => <TableCell key={c} sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxWidth: 360 }}>{c === 'bfc_set_code' ? t(`baselines.chart.${r[c]}`) : fmtValue(r[c])}</TableCell>)}
            </TableRow>))}
        </TableBody>
      </Table>
      {d.total > d.rows.length && <Button sx={{ m: 1, ml: 2 }} onClick={() => setLimit(limit + PAGE)}>{t('baselines.view.more')}</Button>}
    </Box>
  );
}

// §14.4: a baseline opens read only — a banner says so, no edit control exists, and every request is a
// snapshot read. The one write is recording the client's sign-off (§5.2, DR8-P1).
export default function BaselinePage() {
  const { projectId, baselineId } = useParams();
  const canEdit = useCanEdit();
  const { rows: catalogue } = useComponents(projectId);
  const [approving, setApproving] = useState(false);
  const [toast, setToast] = useState('');
  const q = useQuery({ queryKey: keys.baseline(baselineId), queryFn: () => baselineApi.get(baselineId) });
  const b = q.data;
  const files = useQuery({ queryKey: keys.baselineArchive(baselineId), queryFn: () => baselineApi.archive(baselineId),
    enabled: Boolean(b) });                               // slice 16: the archive files this baseline owes
  const entities = b ? Object.entries(b.counts) : [];
  const [entity, setEntity] = useState('bfc_node');
  return (
    <Page title={b ? `${t('baselines.title')} · ${b.version_label}` : t('baselines.title')} error={q.error && detailText(q.error)}
      crumb={b?.version_label}
      actions={b && (
        <>
          <Button variant="outlined" component={RouterLink} to={links.baselines(projectId, b.baseline_id, 'live')}>
            {t('baselines.view.compareLive')}</Button>
          {canEdit && !b.client_approver_name && ['FROZEN', 'SUPERSEDED'].includes(b.status_code) && (
            <Button variant="contained" onClick={() => setApproving(true)}>{t('baselines.approve')}</Button>)}
        </>)}>
      {b && (
        <Stack spacing={2}>
          <Alert severity="info" icon={<LockOutlinedIcon />}
            action={<Button color="inherit" size="small" startIcon={<ArrowBackIcon />} component={RouterLink} to={links.baselines(projectId)}>{t('baselines.view.back')}</Button>}>
            {t('baselines.view.banner', { label: b.version_label, date: fmtDate(b.frozen_at) })}
          </Alert>
          {!b.intact && <Alert severity="error">{t('baselines.view.intactBad')}</Alert>}
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' } }}>
            <Card title={t('baselines.view.status')} action={(
              <Stack direction="row" useFlexGap sx={{ gap: 0.75, flexWrap: 'wrap' }}>
                <StatusChip code={b.status_code} label={b.status_label} />{b.is_agreed && <AgreedChip />}
              </Stack>)} bodySx={{ gap: 1 }}>
              <KV k={t('baselines.field.version_label')} v={<Code>{b.version_label}</Code>} />
              <KV k={t('baselines.view.frozen')} v={t('baselines.frozenOn', { date: fmtDateTime(b.frozen_at), who: b.frozen_by ?? '' })} />
              {b.note && <KV k={t('baselines.view.note')} v={<Box component="span" sx={{ whiteSpace: 'pre-wrap' }}>{b.note}</Box>} />}
              <KV k={t('baselines.view.depth')} v={t(`baselines.view.depth.${b.data_model_depth}`)} />
              {(files.data ?? []).length > 0 && (
                <KV k={t('removals.archive.label')} v={(
                  <Stack direction="row" useFlexGap sx={{ gap: 0.5, flexWrap: 'wrap' }}>
                    {files.data.map((f) => (
                      <Tag key={f.archive_part} tone={{ WRITTEN: 'teal', OWED: 'neutral' }[f.status] ?? 'escalate'}>
                        {`${t(`removals.archive.${f.archive_part}`)} · ${t(`removals.archive.${f.status}`)}`}</Tag>))}
                  </Stack>)} />
              )}
              {/* D-70 [Q-19]: the DFD rule each chart passed; a baseline frozen before 13b carries none — the D-38 rule */}
              {['TO_BE', 'AS_IS'].map((set) => {
                const codes = set === 'TO_BE' ? b.dfd_rule_to_be : b.dfd_rule_as_is;
                return (
                  <KV key={set} k={t(`baselines.view.dfdRule.${set}`)} v={codes ? (
                    <Stack direction="row" useFlexGap sx={{ gap: 0.5, flexWrap: 'wrap' }}>
                      {codes.map((c) => <Tag key={c} tone="neutral">{t(`baselines.view.dfdRule.element.${c}`)}</Tag>)}
                    </Stack>) : t('baselines.view.dfdRule.d38')} />
                );
              })}
              <KV k={t('baselines.view.components')} v={(
                <Stack direction="row" useFlexGap sx={{ gap: 0.5, flexWrap: 'wrap' }}>
                  {b.components.map((c) => <Tag key={c} tone="neutral">{catalogue.find((x) => x.code === c)?.label ?? c}</Tag>)}
                </Stack>)} />
            </Card>
            <Card title={t('baselines.view.approval')} bodySx={{ gap: 1 }}>
              {b.client_approver_name ? (
                <>
                  <Typography sx={{ fontSize: 13.5 }}>{t('baselines.signedBy', { name: b.client_approver_name, date: fmtDate(b.client_approved_on) })}</Typography>
                  {b.approval_reference && <Typography sx={{ fontSize: 13.5 }}>{t('baselines.view.reference', { ref: b.approval_reference })}</Typography>}
                  {b.approval_note && <Typography sx={{ fontSize: 13.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{b.approval_note}</Typography>}
                  <Typography sx={{ fontSize: 12.5, color: 'brand.muted' }}>
                    {t('baselines.view.recordedBy', { who: b.approved_by ?? '', date: fmtDateTime(b.approved_at) })}</Typography>
                </>
              ) : <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('baselines.view.noApproval')}</Typography>}
            </Card>
          </Box>
          <Card title={t('baselines.view.contents')} bodySx={{ px: 0, gap: 1.5 }}>
            <Box sx={{ px: 2.5 }}>
              <Segmented size="sm" label={t('baselines.view.contents')} value={entity} onChange={setEntity}
                options={entities.filter(([, n]) => n > 0).map(([e, n]) => ({ value: e, label: `${entityLabel(e)} · ${n}` }))} />
            </Box>
            {b.intact && <Rows key={entity} b={b} entity={entity} />}
          </Card>
        </Stack>
      )}
      {b && <ApproveDialog b={b} open={approving} onClose={() => setApproving(false)}
        onDone={() => { setApproving(false); setToast(t('baselines.approve.done')); }} />}
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast('')} message={toast} />
    </Page>
  );
}
