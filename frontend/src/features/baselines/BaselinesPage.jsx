import { useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, CircularProgress, FormControl, InputLabel, MenuItem, Select, Snackbar, Stack,
  Typography } from '@mui/material';
import LayersOutlinedIcon from '@mui/icons-material/LayersOutlined';
import { errorText } from '../../api/client';
import { baselineApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { Card, Code, ListRow, SectionLabel, Status } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { AgreedChip, StatusChip, fmtDate, lineLabel } from './baselineKit';
import { DiffPanel } from './DiffPanel';
import { FreezeDialog, detailText, itemText } from './FreezeDialog';

const LIVE = 'live';

function VersionRow({ projectId, b }) {
  return (
    <ListRow component={RouterLink} to={links.baseline(projectId, b.baseline_id)} sx={{ alignItems: 'flex-start', py: 1.5 }}>
      <Code sx={{ fontSize: 14, fontWeight: 600, width: 52, flexShrink: 0, pt: 0.25 }}>{b.version_label}</Code>
      <Box sx={{ minWidth: 0, flexGrow: 1 }}>
        <Stack direction="row" useFlexGap sx={{ gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}>
          <StatusChip code={b.status_code} label={b.status_label} />
          {b.is_agreed && <AgreedChip />}
        </Stack>
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mt: 0.5 }}>
          {t('baselines.frozenOn', { date: fmtDate(b.frozen_at), who: b.frozen_by ?? '' })}
        </Typography>
        <Typography sx={{ fontSize: 12.5, color: b.client_approver_name ? 'text.primary' : 'brand.muted' }}>
          {b.client_approver_name
            ? t('baselines.signedBy', { name: b.client_approver_name, date: fmtDate(b.client_approved_on) })
            : t('baselines.awaitingSignOff')}
        </Typography>
        {b.note && <Typography sx={{ fontSize: 12.5, mt: 0.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{b.note}</Typography>}
      </Box>
    </ListRow>
  );
}

// One consistency line: a status pill with its count, and the first few items it names.
function CheckLine({ tone, k, items }) {
  return (
    <Box>
      <Status tone={tone} size="sm" sx={{ whiteSpace: 'normal', height: 'auto', minHeight: 24, py: 0.25 }}>
        {t('baselines.line.count', { line: lineLabel(k), n: items.length })}
      </Status>
      <Typography sx={{ fontSize: 12, color: 'brand.muted', mt: 0.25, pl: 1, wordBreak: 'break-word' }}>
        {items.slice(0, 5).map(itemText).join(', ')}{items.length > 5 ? ' …' : ''}
      </Typography>
    </Box>
  );
}

// Mockup 09 "Before freezing": the next freeze's own preview (the same check the dialog runs), read only here.
function BeforeFreezing({ projectId, nextLabel }) {
  const pv = useQuery({ queryKey: keys.baselineNext(projectId, 'MINOR'), queryFn: () => baselineApi.next(projectId, 'MINOR') });
  const p = pv.data;
  const lines = (obj, tone) => Object.entries(obj ?? {}).map(([k, v]) => <CheckLine key={`${tone}-${k}`} tone={tone} k={k} items={v} />);
  const blocked = p && (Object.keys(p.errors).length > 0 || Object.keys(p.freeze_blocking).length > 0);
  const total = p ? Object.values(p.counts_by_entity).reduce((a, b) => a + b, 0) : 0;
  const areas = p ? Object.values(p.counts_by_entity).filter((n) => n > 0).length : 0;
  return (
    <Card title={t('baselines.before', { label: p?.next_label ?? nextLabel })} bodySx={{ gap: 1.25 }}>
      <SectionLabel>{t('baselines.check')}</SectionLabel>
      {pv.isLoading && <CircularProgress size={20} />}
      {pv.error && <Alert severity="error">{detailText(pv.error)}</Alert>}
      {p && (
        <>
          {!blocked && <Status tone="ok" size="sm">{t('baselines.checkReady')}</Status>}
          {lines(p.errors, 'escalate')}
          {lines(p.freeze_blocking, 'escalate')}
          {lines(p.warnings, 'caution')}
          <Typography sx={{ fontSize: 12.5, color: 'brand.muted' }}>{t('baselines.checkCounts', { n: total, m: areas })}</Typography>
        </>
      )}
    </Card>
  );
}

// Mockup 09: versions and the freeze check on the left, the comparison on the right; the freeze is a header action.
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
      crumb={list.length > 0 ? `${labelOf(from)} → ${labelOf(to)}` : undefined}
      actions={(
        <>
          {list.length > 0 && (
            <>
              <FormControl size="small" sx={{ minWidth: 130 }}>
                <InputLabel id="bl-from">{t('baselines.from')}</InputLabel>
                <Select labelId="bl-from" label={t('baselines.from')} value={from ?? ''} onChange={(e) => pick('from', e.target.value)}>
                  {list.map((b) => <MenuItem key={b.baseline_id} value={String(b.baseline_id)}>{b.version_label}</MenuItem>)}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 150 }}>
                <InputLabel id="bl-to">{t('baselines.to')}</InputLabel>
                <Select labelId="bl-to" label={t('baselines.to')} value={to} onChange={(e) => pick('to', e.target.value)}>
                  <MenuItem value={LIVE}>{t('baselines.working')}</MenuItem>
                  {list.filter((b) => String(b.baseline_id) !== from).map((b) => (
                    <MenuItem key={b.baseline_id} value={String(b.baseline_id)}>{b.version_label}</MenuItem>))}
                </Select>
              </FormControl>
            </>
          )}
          {canEdit && (
            <Button variant="contained" startIcon={<LayersOutlinedIcon />} onClick={() => setOpen(true)}>
              {t('baselines.freeze', { label: next })}
            </Button>)}
        </>
      )}>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: '320px minmax(0, 1fr)' } }}>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Card title={t('baselines.versions')} bodySx={{ gap: 1 }}>
            <ListRow selected={to === LIVE} onClick={to === LIVE || !from ? undefined : () => pick('to', LIVE)}>
              <Code tone="purple" sx={{ fontSize: 14, fontWeight: 600 }}>{t('baselines.working')}</Code>
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary', flexGrow: 1, minWidth: 0 }}>{t('baselines.workingNote')}</Typography>
            </ListRow>
            {list.map((b) => <VersionRow key={b.baseline_id} projectId={projectId} b={b} />)}
            {q.isSuccess && list.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('baselines.none')}</Typography>}
          </Card>
          <BeforeFreezing projectId={projectId} nextLabel={next} />
        </Stack>
        <Box sx={{ minWidth: 0 }}>
          {list.length === 0
            ? (q.isSuccess && <Alert severity="info">{t('baselines.pickTwo')}</Alert>)
            : <DiffPanel projectId={projectId} from={from} to={to} fromLabel={labelOf(from)} toLabel={labelOf(to)} />}
        </Box>
      </Box>
      <FreezeDialog projectId={projectId} open={open} onClose={() => setOpen(false)}
        onFrozen={(out) => { setOpen(false); setToast(t('baselines.dlg.done', { label: out.baseline.version_label }));
          setParams({ from: String(out.baseline.baseline_id), to: LIVE }, { replace: true }); }} />
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast('')} message={toast} />
    </Page>
  );
}
