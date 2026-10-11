import { useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Card, CardContent, Chip, Snackbar, Stack, Table, TableBody, TableCell, TableHead,
  TableRow, TextField, Typography } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import { baselineApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useComponents } from '../../app/useComponents';
import { ConfirmDialog } from '../../components/ConfirmDialog';
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
  if (d.total === 0) return <Typography sx={{ color: 'text.secondary', p: 2 }}>{t('baselines.view.empty')}</Typography>;
  // ids are shown through the row's label; a code shows as its label beside it (UAT 8 D3)
  const cols = d.columns.filter((c) => !c.endsWith('_id')
    && !(c.endsWith('_code') && d.columns.includes(`${c.slice(0, -5)}_label`)));
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{t('baselines.col.item')}</TableCell>
            {cols.map((c) => <TableCell key={c} sx={{ whiteSpace: 'nowrap' }}>{fieldLabel(c)}</TableCell>)}
          </TableRow>
        </TableHead>
        <TableBody>
          {d.rows.map((r) => (
            <TableRow key={r.source_id}>
              <TableCell sx={{ fontWeight: 600, minWidth: 180, wordBreak: 'break-word' }}>{r.label}</TableCell>
              {cols.map((c) => <TableCell key={c} sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxWidth: 360 }}>{c === 'bfc_set_code' ? t(`baselines.chart.${r[c]}`) : fmtValue(r[c])}</TableCell>)}
            </TableRow>))}
        </TableBody>
      </Table>
      {d.total > d.rows.length && <Button sx={{ m: 1 }} onClick={() => setLimit(limit + PAGE)}>{t('baselines.view.more')}</Button>}
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
  const entities = b ? Object.entries(b.counts) : [];
  const [entity, setEntity] = useState('bfc_node');
  return (
    <Page title={b ? `${t('baselines.title')} · ${b.version_label}` : t('baselines.title')} error={q.error && detailText(q.error)}
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
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
            <Card>
              <CardContent>
                <Stack direction="row" useFlexGap sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
                  <Typography sx={{ fontWeight: 700 }}>{t('baselines.view.status')}</Typography>
                  <StatusChip code={b.status_code} label={b.status_label} />{b.is_agreed && <AgreedChip />}
                </Stack>
                <Typography sx={{ fontSize: 13.5 }}>{t('baselines.frozenOn', { date: fmtDateTime(b.frozen_at), who: b.frozen_by ?? '' })}</Typography>
                {b.note && <Typography sx={{ fontSize: 13.5, mt: 1, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{b.note}</Typography>}
                <Typography sx={{ fontSize: 13, color: 'text.secondary', mt: 1 }}>
                  {t('baselines.view.depth')}: {t(`baselines.view.depth.${b.data_model_depth}`)}
                </Typography>
                <Typography sx={{ fontSize: 13, fontWeight: 600, mt: 1 }}>{t('baselines.view.components')}</Typography>
                <Stack direction="row" useFlexGap sx={{ gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {b.components.map((c) => <Chip key={c} size="small" label={catalogue.find((x) => x.code === c)?.label ?? c} />)}
                </Stack>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <Typography sx={{ fontWeight: 700, mb: 1 }}>{t('baselines.view.approval')}</Typography>
                {b.client_approver_name ? (
                  <>
                    <Typography sx={{ fontSize: 13.5 }}>{t('baselines.signedBy', { name: b.client_approver_name, date: fmtDate(b.client_approved_on) })}</Typography>
                    {b.approval_reference && <Typography sx={{ fontSize: 13.5 }}>{t('baselines.view.reference', { ref: b.approval_reference })}</Typography>}
                    {b.approval_note && <Typography sx={{ fontSize: 13.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{b.approval_note}</Typography>}
                    <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 0.5 }}>
                      {t('baselines.view.recordedBy', { who: b.approved_by ?? '', date: fmtDateTime(b.approved_at) })}</Typography>
                  </>
                ) : <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('baselines.view.noApproval')}</Typography>}
              </CardContent>
            </Card>
          </Box>
          <Card>
            <CardContent sx={{ px: 0 }}>
              <Typography component="h2" sx={{ fontWeight: 700, px: 2, mb: 1 }}>{t('baselines.view.contents')}</Typography>
              <Stack direction="row" useFlexGap sx={{ gap: 0.75, flexWrap: 'wrap', px: 2, mb: 1 }}>
                {entities.filter(([, n]) => n > 0).map(([e, n]) => (
                  <Chip key={e} label={`${entityLabel(e)} · ${n}`} onClick={() => setEntity(e)}
                    color={e === entity ? 'primary' : 'default'} variant={e === entity ? 'filled' : 'outlined'} />))}
              </Stack>
              {b.intact && <Rows key={entity} b={b} entity={entity} />}
            </CardContent>
          </Card>
        </Stack>
      )}
      {b && <ApproveDialog b={b} open={approving} onClose={() => setApproving(false)}
        onDone={() => { setApproving(false); setToast(t('baselines.approve.done')); }} />}
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast('')} message={toast} />
    </Page>
  );
}
