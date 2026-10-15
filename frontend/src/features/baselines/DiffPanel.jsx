import { Fragment, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, CircularProgress, Collapse, FormControlLabel, IconButton, Stack, Switch,
  Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import { baselineApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile, Segmented, Tile, codeTone } from '../../components/kit';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { CHANGE_KINDS, ChangeTag, areaLabel, entityLabel, fieldLabel, fmtDays, fmtValue, splitLabel } from './baselineKit';
import { detailText } from './FreezeDialog';

function ChangeRow({ r, days }) {
  const [open, setOpen] = useState(false);
  const canOpen = r.fields.length > 0 && r.change !== 'ADDED' && r.change !== 'REMOVED';
  const { code, name } = splitLabel(r.label);
  return (
    <>
      <TableRow hover>
        <TableCell sx={{ width: 36, pl: 1.5, pr: 0 }}>
          {canOpen && (
            <IconButton size="small" onClick={() => setOpen(!open)} aria-label={t('baselines.col.what')} aria-expanded={open}>
              {open ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
            </IconButton>)}
        </TableCell>
        <TableCell><ChangeTag kind={r.change} /></TableCell>
        <TableCell>{code ? <Code tone={codeTone(code)} sx={{ fontSize: 12.5 }}>{code}</Code> : null}</TableCell>
        <TableCell sx={{ minWidth: 200, wordBreak: 'break-word' }}>
          <Typography sx={{ fontWeight: 600, fontSize: 'inherit' }}>{name}</Typography>
          <Typography sx={{ fontSize: 12, color: 'brand.muted' }}>{entityLabel(r.entity)}</Typography>
        </TableCell>
        <TableCell sx={{ color: 'text.secondary', minWidth: 140 }}>
          {r.fields.map((f) => fieldLabel(f).replace('-', '\u2011')).join(', ')}
          {r.moved && r.change === 'CHANGED' && ` · ${t('baselines.alsoMoved')}`}
        </TableCell>
        {days && (
          <TableCell align="right" sx={(th) => ({ pr: 2.5, fontFamily: MONO, whiteSpace: 'nowrap',
            color: r.delta > 0 ? th.vars.palette.brand.purpleText : r.delta < 0 ? th.vars.palette.brand.tealText : th.vars.palette.brand.muted })}>
            {r.delta !== undefined ? fmtDays(r.delta) : ''}</TableCell>)}
      </TableRow>
      {canOpen && (
        <TableRow>
          <TableCell colSpan={days ? 6 : 5} sx={{ py: 0, borderBottom: open ? undefined : 'none' }}>
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
  // Q-22 (slice13_schema §3.7): an entity that gained fields between the two sides is compared on the older list;
  // say which fields were left out, so a quiet comparison is never read as "nothing changed there" (e.g. volume).
  const partly = d ? Object.entries(d.entities).filter(([, e]) => e.not_compared?.length) : [];
  const notUsed = d ? [...new Set(Object.values(d.entities).filter((e) => e.component_on && !e.component_on.a && e.rows.length).map((e) => e.area))] : [];
  const showDays = pricing?.available;
  // D-52: untraced = no BR link (renamed from unlinked; older responses still say unlinked_days).
  const untracedDays = pricing?.totals.untraced_days ?? pricing?.totals.unlinked_days ?? 0;
  // A side frozen before direct links (hash spec 1): its links are derived from its solutions (§5.3).
  // The server names the sides "a"/"b" on the link entity; the labels are the response's from/to.
  const derivedSides = (d?.entities?.br_function_requirement?.derived_sides ?? [])
    .map((s) => (s === 'a' ? d.from : s === 'b' ? d.to : null)).filter(Boolean);
  const total = rows.length;
  const tiles = [
    { k: 'ADDED', days: pricing?.totals.added_days },
    { k: 'REMOVED', days: pricing?.totals.removed_days },
    { k: 'CHANGED', days: pricing?.totals.changed_days },
  ];
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      {q.isLoading && <CircularProgress size={24} />}
      {q.error && <Alert severity="error">{detailText(q.error)}</Alert>}
      {d && (
        <>
          {/* Mockup 09: the purple net change and the three counts in one row; Moved is in the filter. */}
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: showDays
            ? { xs: 'repeat(2, minmax(0, 1fr))', lg: 'minmax(0, 1.35fr) repeat(3, minmax(0, 1fr))' }
            : { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))' } }}>
            {showDays && (
              <PurpleTile label={t('baselines.netSince')} labelSuffix={fromLabel} value={fmtDays(pricing.totals.net_days)}
                unit={t('baselines.days', { n: '' }).trim()} note={t('baselines.netOf', { base: pricing.totals.base_days, label: fromLabel })} />)}
            {tiles.map(({ k, days }) => (
              <Tile key={k} label={t(`baselines.change.${k}`)}
                value={showDays ? fmtDays(days) : d.summary[k]}
                note={showDays ? t('baselines.objects', { n: d.summary[k] }) : null} />))}
          </Box>
          {pricing && !pricing.available && <Alert severity="info">{t('baselines.pricingOff', { labels: pricing.in.join(', ') })}</Alert>}
          {showDays && pricing.totals.effort_exposed_days > 0 && <Alert severity="info">{t('baselines.exposed', { n: pricing.totals.effort_exposed_days })}</Alert>}
          {showDays && pricing.totals.unrated_fr_count > 0 && <Alert severity="warning">{t('baselines.unrated', { n: pricing.totals.unrated_fr_count })}</Alert>}
          {showDays && untracedDays !== 0 && <Alert severity="info">{t('baselines.untraced', { n: fmtDays(untracedDays) })}</Alert>}
          {showDays && (pricing.totals.unassigned_days ?? 0) !== 0 && (
            <Alert severity="info">{t('baselines.unassigned', { n: fmtDays(pricing.totals.unassigned_days) })}</Alert>)}
          {derivedSides.length > 0 && <Alert severity="info">{t('baselines.derivedSides', { labels: derivedSides.join(', ') })}</Alert>}
          {mismatched.map(([e]) => <Alert key={e} severity="warning">{t('baselines.schemaMismatch', { entity: entityLabel(e) })}</Alert>)}
          {partly.map(([e, x]) => (
            <Alert key={`nc-${e}`} severity="info">
              {t('baselines.notCompared', { entity: entityLabel(e),
                fields: x.not_compared.map((c) => t(`baselines.field.${c}`)).join(', ') })}</Alert>))}
          {notUsed.length > 0 && <Alert severity="info">{notUsed.map(areaLabel).join(', ')} — {t('baselines.notUsed', { label: fromLabel })}</Alert>}
          <Card title={t('baselines.changes', { from: fromLabel, to: toLabel })} bodySx={{ px: 0, gap: 1 }}
            action={(
              <Stack direction="row" useFlexGap sx={{ gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
                <FormControlLabel sx={{ mr: 0 }} control={<Switch size="small" checked={priced} onChange={(e) => setPriced(e.target.checked)} />}
                  label={<Typography sx={{ fontSize: 13 }}>{t('baselines.priced')}</Typography>} />
                <Segmented size="sm" label={t('baselines.col.change')} value={kind} onChange={setKind}
                  options={[{ value: 'ALL', label: t('baselines.all', { n: total }) },
                    ...CHANGE_KINDS.map((k) => ({ value: k, label: `${t(`baselines.change.${k}`)} ${d.summary[k]}` }))]} />
              </Stack>)}>
            {shown.length === 0 ? (
              <Typography sx={{ px: 2.5, color: 'text.secondary' }}>{t('baselines.noChanges')}</Typography>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ pl: 1.5 }} />
                      <TableCell sx={{ width: 120 }}>{t('baselines.col.change')}</TableCell>
                      <TableCell sx={{ width: 130 }}>{t('baselines.col.object')}</TableCell>
                      <TableCell>{t('baselines.col.name')}</TableCell>
                      <TableCell>{t('baselines.col.what')}</TableCell>
                      {showDays && <TableCell align="right" sx={{ pr: 2.5, whiteSpace: 'nowrap' }}>{t('baselines.daysShort')}</TableCell>}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {/* A derived (pre-v2) link row has no source_id: key on its (br, fr) pair, else its position */}
                    {shown.map((r, i) => (
                      <Fragment key={`${r.entity}-${r.source_id ?? r.pair?.join('-') ?? `i${i}`}`}><ChangeRow r={r} days={showDays} /></Fragment>))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Card>
        </>
      )}
    </Stack>
  );
}
