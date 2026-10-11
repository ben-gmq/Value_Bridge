import { useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Card, CardContent, FormControl, InputLabel, Link, MenuItem, Select, Snackbar, Stack,
  Typography } from '@mui/material';
import LayersOutlinedIcon from '@mui/icons-material/LayersOutlined';
import { errorText } from '../../api/client';
import { baselineApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { Mono } from '../processes/chartKit';
import { AgreedChip, StatusChip, fmtDate } from './baselineKit';
import { DiffPanel } from './DiffPanel';
import { FreezeDialog } from './FreezeDialog';

const LIVE = 'live';

function VersionRow({ projectId, b }) {
  return (
    <Box sx={(th) => ({ p: 1.25, borderRadius: 1, bgcolor: th.vars.palette.background.subtle, border: 1, borderColor: 'divider' })}>
      <Stack direction="row" useFlexGap sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
        <Link component={RouterLink} to={links.baseline(projectId, b.baseline_id)} underline="hover">
          <Mono sx={{ fontSize: 15, fontWeight: 700 }}>{b.version_label}</Mono>
        </Link>
        <StatusChip code={b.status_code} label={b.status_label} />
        {b.is_agreed && <AgreedChip />}
      </Stack>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 0.5 }}>
        {t('baselines.frozenOn', { date: fmtDate(b.frozen_at), who: b.frozen_by ?? '' })}
      </Typography>
      {b.client_approver_name
        ? <Typography sx={{ fontSize: 12.5 }}>{t('baselines.signedBy', { name: b.client_approver_name, date: fmtDate(b.client_approved_on) })}</Typography>
        : <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('baselines.awaitingSignOff')}</Typography>}
      {b.note && <Typography sx={{ fontSize: 12.5, mt: 0.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{b.note}</Typography>}
    </Box>
  );
}

// Mockup 09: versions on the left, the comparison on the right; the freeze is a header action.
export default function BaselinesPage() {
  const { projectId } = useParams();
  const canEdit = useCanEdit();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState('');
  const q = useQuery({ queryKey: keys.baselines(projectId), queryFn: () => baselineApi.list(projectId) });
  const list = q.data ?? [];
  const from = params.get('from') ?? (list[0] ? String(list[0].baseline_id) : null);
  const to = params.get('to') ?? LIVE;
  const labelOf = (id) => (id === LIVE ? t('baselines.working') : list.find((b) => String(b.baseline_id) === id)?.version_label ?? '');
  const pick = (which, v) => setParams({ from, to, [which]: v }, { replace: true });
  const next = list[0] ? `v${list[0].major_no}.${list[0].minor_no + 1}` : 'v1.0';     // the dialog offers MAJOR too
  return (
    <Page title={t('baselines.title')} subtitle={t('baselines.subtitle')} error={q.error && errorText(q.error)}
      actions={canEdit && (
        <Button variant="contained" startIcon={<LayersOutlinedIcon />} onClick={() => setOpen(true)}>
          {t('baselines.freeze', { label: next })}
        </Button>)}>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '300px minmax(0, 1fr)' } }}>
        <Card sx={{ alignSelf: 'start' }}>
          <CardContent>
            <Typography component="h2" sx={{ fontWeight: 700, mb: 1 }}>{t('baselines.versions')}</Typography>
            <Stack spacing={1}>
              <Box sx={(th) => ({ p: 1.25, borderRadius: 1, border: 1, borderColor: th.vars.palette.brand.ftcViolet })}>
                <Typography sx={{ fontWeight: 700 }}>{t('baselines.working')}</Typography>
                <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('baselines.workingNote')}</Typography>
              </Box>
              {list.map((b) => <VersionRow key={b.baseline_id} projectId={projectId} b={b} />)}
              {q.isSuccess && list.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('baselines.none')}</Typography>}
            </Stack>
          </CardContent>
        </Card>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          {list.length === 0 ? (q.isSuccess && <Alert severity="info">{t('baselines.pickTwo')}</Alert>) : (
            <>
              <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
                <Typography sx={{ fontWeight: 700 }}>{t('baselines.compare')}</Typography>
                <FormControl size="small" sx={{ minWidth: 160 }}>
                  <InputLabel id="bl-from">{t('baselines.from')}</InputLabel>
                  <Select labelId="bl-from" label={t('baselines.from')} value={from ?? ''} onChange={(e) => pick('from', e.target.value)}>
                    {list.map((b) => <MenuItem key={b.baseline_id} value={String(b.baseline_id)}>{b.version_label}</MenuItem>)}
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 180 }}>
                  <InputLabel id="bl-to">{t('baselines.to')}</InputLabel>
                  <Select labelId="bl-to" label={t('baselines.to')} value={to} onChange={(e) => pick('to', e.target.value)}>
                    <MenuItem value={LIVE}>{t('baselines.working')}</MenuItem>
                    {list.filter((b) => String(b.baseline_id) !== from).map((b) => (
                      <MenuItem key={b.baseline_id} value={String(b.baseline_id)}>{b.version_label}</MenuItem>))}
                  </Select>
                </FormControl>
              </Stack>
              <DiffPanel projectId={projectId} from={from} to={to} fromLabel={labelOf(from)} toLabel={labelOf(to)} />
            </>
          )}
        </Stack>
      </Box>
      <FreezeDialog projectId={projectId} open={open} onClose={() => setOpen(false)}
        onFrozen={(out) => { setOpen(false); setToast(t('baselines.dlg.done', { label: out.baseline.version_label }));
          setParams({ from: String(out.baseline.baseline_id), to: LIVE }, { replace: true }); }} />
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast('')} message={toast} />
    </Page>
  );
}
