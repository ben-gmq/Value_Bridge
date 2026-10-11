import { Fragment, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Card, CardContent, CircularProgress, Collapse, FormControlLabel, IconButton, Stack, Switch,
  Table, TableBody, TableCell, TableHead, TableRow, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import { baselineApi } from '../../api/scope';
import { keys } from '../../app/links';
import { t } from '../../i18n/t';
import { CHANGE_KINDS, ChangeTag, areaLabel, entityLabel, fieldLabel, fmtDays, fmtValue } from './baselineKit';
import { detailText } from './FreezeDialog';

function Tile({ label, value, note, strong }) {
  return (
    <Card sx={(th) => ({ flex: '1 1 150px', minWidth: 0, ...(strong ? { bgcolor: th.vars.palette.brand.ftc, color: th.vars.palette.brand.onFtc } : {}) })}>
      <CardContent>
        <Typography sx={{ fontSize: 12.5, fontWeight: 600, opacity: 0.85 }}>{label}</Typography>
        <Typography sx={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
        {note && <Typography sx={{ fontSize: 12.5, opacity: 0.85 }}>{note}</Typography>}
      </CardContent>
    </Card>
  );
}

function ChangeRow({ r, days }) {
  const [open, setOpen] = useState(false);
  const canOpen = r.fields.length > 0 && r.change !== 'ADDED' && r.change !== 'REMOVED';
  return (
    <>
      <TableRow hover>
        <TableCell sx={{ width: 36, pr: 0 }}>
          {canOpen && (
            <IconButton size="small" onClick={() => setOpen(!open)} aria-label={t('baselines.col.what')} aria-expanded={open}>
              {open ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
            </IconButton>)}
        </TableCell>
        <TableCell><ChangeTag kind={r.change} /></TableCell>
        <TableCell sx={{ minWidth: 220, wordBreak: 'break-word' }}>
          <Typography sx={{ fontWeight: 600, fontSize: 'inherit' }}>{r.label}</Typography>
          <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{entityLabel(r.entity)}</Typography>
        </TableCell>
        <TableCell sx={{ color: 'text.secondary', minWidth: 140 }}>
          {r.fields.map((f) => fieldLabel(f).replace('-', '\u2011')).join(', ')}
          {r.moved && r.change === 'CHANGED' && ` · ${t('baselines.alsoMoved')}`}
        </TableCell>
        {days && <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{r.delta !== undefined ? fmtDays(r.delta) : ''}</TableCell>}
      </TableRow>
      {canOpen && (
        <TableRow>
          <TableCell colSpan={days ? 5 : 4} sx={{ py: 0, borderBottom: open ? undefined : 'none' }}>
            <Collapse in={open} unmountOnExit>
              <Table size="small" sx={{ my: 1 }}>
                <TableHead><TableRow><TableCell /><TableCell>{t('baselines.col.before')}</TableCell><TableCell>{t('baselines.col.after')}</TableCell></TableRow></TableHead>
                <TableBody>
                  {r.fields.map((f) => (
                    <TableRow key={f}>
                      <TableCell sx={{ color: 'text.secondary', width: 180 }}>{fieldLabel(f)}</TableCell>
                      <TableCell sx={{ textDecoration: 'line-through', color: 'text.secondary', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{fmtValue(r.before[f])}</TableCell>
                      <TableCell sx={(th) => ({ bgcolor: th.vars.palette.status.cautionBg, whiteSpace: 'pre-wrap', wordBreak: 'break-word' })}>{fmtValue(r.after[f])}</TableCell>
                    </TableRow>))}
                </TableBody>
              </Table>
            </Collapse>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

// §5.3 / D-50 (the engine's first screen): a baseline against the working set or another baseline — counts
// per change, the priced delta when effort is used in both, and every changed row with a before/after.
export function DiffPanel({ projectId, from, to, fromLabel, toLabel }) {
  const [priced, setPriced] = useState(true);
  const [kind, setKind] = useState('ALL');
  const q = useQuery({ queryKey: keys.baselineDiff(projectId, from, to, priced),
    queryFn: () => baselineApi.diff(projectId, from, to, priced), enabled: Boolean(from && to) });
  const d = q.data;
  const pricing = d?.pricing;
  const delta = useMemo(() => Object.fromEntries((pricing?.lines ?? []).map((l) => [l.source_id, l.delta_days])), [pricing]);
  const rows = useMemo(() => {
    if (!d) return [];
    const out = [];
    for (const [entity, e] of Object.entries(d.entities)) {
      for (const r of e.rows) {
        out.push({ ...r, entity, area: e.area, delta: entity === 'function_requirement' ? delta[r.source_id] : undefined });
      }
    }
    return out;
  }, [d, delta]);
  const shown = kind === 'ALL' ? rows : rows.filter((r) => r.change === kind);
  const mismatched = d ? Object.entries(d.entities).filter(([, e]) => e.status === 'SCHEMA_VERSION_MISMATCH') : [];
  const notUsed = d ? [...new Set(Object.values(d.entities).filter((e) => e.component_on && !e.component_on.a && e.rows.length).map((e) => e.area))] : [];
  const showDays = pricing?.available;
  const total = rows.length;
  return (
    <Stack spacing={2}>
      {q.isLoading && <CircularProgress size={24} />}
      {q.error && <Alert severity="error">{detailText(q.error)}</Alert>}
      {d && (
        <>
          <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
            {showDays && (
              <Tile strong label={t('baselines.net')} value={fmtDays(pricing.totals.net_days)}
                note={`${t('baselines.days', { n: '' }).trim()} · ${t('baselines.netOf', { base: pricing.totals.base_days, label: fromLabel })}`} />)}
            {CHANGE_KINDS.map((k) => (
              <Tile key={k} label={t(`baselines.change.${k}`)} value={d.summary[k]}
                note={showDays && k === 'ADDED' ? t('baselines.days', { n: fmtDays(pricing.totals.added_days) })
                  : showDays && k === 'REMOVED' ? t('baselines.days', { n: fmtDays(pricing.totals.removed_days) }) : null} />))}
          </Stack>
          {pricing && !pricing.available && <Alert severity="info">{t('baselines.pricingOff', { labels: pricing.in.join(', ') })}</Alert>}
          {showDays && pricing.totals.effort_exposed_days > 0 && <Alert severity="info">{t('baselines.exposed', { n: pricing.totals.effort_exposed_days })}</Alert>}
          {showDays && pricing.totals.unrated_fr_count > 0 && <Alert severity="warning">{t('baselines.unrated', { n: pricing.totals.unrated_fr_count })}</Alert>}
          {showDays && pricing.totals.unlinked_days !== 0 && <Alert severity="info">{t('baselines.unlinked', { n: fmtDays(pricing.totals.unlinked_days) })}</Alert>}
          {mismatched.map(([e]) => <Alert key={e} severity="warning">{t('baselines.schemaMismatch', { entity: entityLabel(e) })}</Alert>)}
          {notUsed.length > 0 && <Alert severity="info">{notUsed.map(areaLabel).join(', ')} — {t('baselines.notUsed', { label: fromLabel })}</Alert>}
          <Card>
            <CardContent sx={{ px: 0 }}>
              <Stack direction="row" useFlexGap sx={{ px: 2, gap: 1, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                <Typography component="h2" sx={{ fontWeight: 700 }}>{t('baselines.changes', { from: fromLabel, to: toLabel })}</Typography>
                <Stack direction="row" useFlexGap sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <FormControlLabel control={<Switch size="small" checked={priced} onChange={(e) => setPriced(e.target.checked)} />}
                    label={<Typography sx={{ fontSize: 13 }}>{t('baselines.priced')}</Typography>} />
                  <ToggleButtonGroup exclusive size="small" value={kind} onChange={(_, v) => v && setKind(v)} aria-label={t('baselines.col.change')}
                    sx={{ flexWrap: 'wrap' }}>
                    <ToggleButton value="ALL">{t('baselines.all', { n: total })}</ToggleButton>
                    {CHANGE_KINDS.map((k) => <ToggleButton key={k} value={k}>{`${t(`baselines.change.${k}`)} ${d.summary[k]}`}</ToggleButton>)}
                  </ToggleButtonGroup>
                </Stack>
              </Stack>
              {shown.length === 0 ? (
                <Typography sx={{ px: 2, pt: 2, color: 'text.secondary' }}>{t('baselines.noChanges')}</Typography>
              ) : (
                <Box sx={{ overflowX: 'auto', mt: 1 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell />
                        <TableCell>{t('baselines.col.change')}</TableCell>
                        <TableCell>{t('baselines.col.item')}</TableCell><TableCell>{t('baselines.col.what')}</TableCell>
                        {showDays && <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{t('baselines.daysShort')}</TableCell>}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {shown.map((r) => <Fragment key={`${r.entity}-${r.source_id}`}><ChangeRow r={r} days={showDays} /></Fragment>)}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </Stack>
  );
}
