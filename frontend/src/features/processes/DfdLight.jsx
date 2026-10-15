import { useQuery } from '@tanstack/react-query';
import { Box, Tooltip } from '@mui/material';
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded';
import WarningAmberRounded from '@mui/icons-material/WarningAmberRounded';
import CancelRounded from '@mui/icons-material/CancelRounded';
import CheckRounded from '@mui/icons-material/CheckRounded';
import { dfdRuleApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Tag } from '../../components/kit';
import { t } from '../../i18n/t';

// D-68 / D-69 / D-70: the DFD readiness light and the "DFD" marks. Both read only what the server says — the tree
// row's dfd_light, dfd_missing (rule elements missing) and dfd_advised (recommended elements missing) codes
// (services/process_flow.readiness) and the chart's rule — never whether a tile looks empty (DR13-D1). Q-13: red =
// a rule element is missing and the process blocks the freeze; yellow = the rule is met but a recommended element
// is missing. The light is always colour + icon + text (D-50), the colours are STATUS_COLOR_MAP tokens.
const LOOK = {
  READY: { tone: 'ok', Icon: CheckCircleRounded },
  PARTIAL: { tone: 'caution', Icon: WarningAmberRounded },
  NOT_READY: { tone: 'escalate', Icon: CancelRounded },
};

/** The chart rules of a project (D-70): `ruleFor(set)` is the chart's element codes, or null until loaded. */
export function useDfdRule(projectId) {
  const q = useQuery({ queryKey: keys.dfdRule(projectId), queryFn: () => dfdRuleApi.get(projectId),
    enabled: Boolean(projectId) });
  return { ruleFor: (bfcSet) => q.data?.charts.find((c) => c.bfc_set_code === bfcSet)?.codes ?? null, data: q.data,
    error: q.error, isLoading: q.isLoading };
}

const bullets = (codes) => codes.map((code) => `• ${t(`processes.dfdLight.element.${code}`)}`);

/** The light's tooltip (Q-13, S13-2): red names the rule's missing elements and blocks the freeze; yellow names the
 * recommended ones it misses and says the freeze is not blocked. */
export function lightTip(light, missing = [], advised = []) {
  if (light === 'READY') return t('processes.dfdLight.tipReady');
  if (light === 'NOT_READY') {
    return [t('processes.dfdLight.stillNeeded'), ...bullets(missing), t('processes.dfdLight.blocks'),
      ...(advised.length ? [t('processes.dfdLight.alsoRecommended'), ...bullets(advised)] : [])].join('\n');
  }
  return [t('processes.dfdLight.recommendedMissing'), ...bullets(advised), t('processes.dfdLight.passes')].join('\n');
}

/** A process's light: an icon and a word in a tone tag, its gaps in the tooltip. Nothing when the rule does not apply.
 * `size="icon"` is the tree row's form (10e): the icon alone in a round tone badge, so the process name keeps the
 * width; its word and gaps stay in the aria-label and the tooltip (D-50: icon + colour + text, the text named). */
export function DfdLight({ light, missing, advised, size = 'md', sx }) {
  const look = LOOK[light];
  if (!look) return null;
  const label = `${t('processes.dfdLight.label')}: ${t(`processes.dfdLight.${light}`)}. ${lightTip(light, missing, advised)}`;
  const tip = <Box component="span" sx={{ whiteSpace: 'pre-line' }}>{`${t(`processes.dfdLight.${light}`)}\n${lightTip(light, missing, advised)}`}</Box>;
  if (size === 'icon') {
    return (
      <Tooltip title={tip}>
        <Box component="span" role="img" aria-label={label} sx={(th) => ({ display: 'inline-grid', placeItems: 'center', flex: 'none',
          width: 22, height: 22, borderRadius: '50%', bgcolor: th.vars.palette.status[`${look.tone}Bg`],
          color: th.vars.palette.status[look.tone], ...sx })}>
          <look.Icon aria-hidden sx={{ fontSize: 15 }} />
        </Box>
      </Tooltip>
    );
  }
  return (
    <Tooltip title={<Box component="span" sx={{ whiteSpace: 'pre-line' }}>{lightTip(light, missing, advised)}</Box>}>
      <Box component="span" tabIndex={0} aria-label={label}
        sx={{ display: 'inline-flex', flex: 'none', borderRadius: 999, '&:focus-visible': { outline: '2px solid', outlineOffset: 1 }, ...sx }}>
        <Tag tone={look.tone} size="lg" icon={<look.Icon aria-hidden sx={{ fontSize: 16 }} />}>
          {t(`processes.dfdLight.${light}`)}</Tag>
      </Box>
    </Tooltip>
  );
}

/** Ready / partly / not counts of one diagram's processes — the DFD list's line (A7). */
export function LightCounts({ counts }) {
  return (
    <Box component="span" sx={{ display: 'inline-flex', flexWrap: 'wrap', columnGap: 1, rowGap: 0.25, fontSize: 12 }}>
      {Object.entries(LOOK).map(([light, { tone, Icon }]) => (
        <Box component="span" key={light} sx={(th) => ({ display: 'inline-flex', alignItems: 'center', gap: 0.4,
          color: counts[light] ? th.vars.palette.status[tone] : th.vars.palette.brand.muted })}>
          <Icon aria-hidden sx={{ fontSize: 13 }} />{t(`processes.dfdLight.count.${light}`, { n: counts[light] })}
        </Box>
      ))}
    </Box>
  );
}

/**
 * D-69: a small "DFD" mark on a field the chart's rule needs — a tick when the server says the element is met, the
 * amber dot (10d's "not set" dot) when it is missing. `dfd` is { missing, rule } (the tree row's codes and the
 * chart's rule), or null when the rule does not apply to this chart. An element outside the rule has no mark (B7).
 */
export function DfdMark({ dfd, element }) {
  if (!dfd || !(dfd.rule ?? []).includes(element)) return null;
  const met = !dfd.missing.includes(element);
  const tip = `${t('processes.dfdMark.note')} — ${t(`processes.dfdMark.element.${element}`)}. ${t(met ? 'processes.dfdMark.met' : 'processes.dfdMark.missing')}`;
  return (
    <Tooltip title={tip}>
      <Box component="span" role="img" aria-label={tip} sx={(th) => ({ display: 'inline-flex', alignItems: 'center', gap: 0.4, flex: 'none',
        height: 20, px: 0.75, borderRadius: 999, border: `1px solid ${th.vars.palette.divider}`, fontSize: 12.5, fontWeight: 700,
        letterSpacing: 0.3, color: th.vars.palette.brand.muted, verticalAlign: 'middle' })}>
        {t('processes.dfdMark.label')}
        {met ? <CheckRounded aria-hidden sx={(th) => ({ fontSize: 14, color: th.vars.palette.status.ok })} />
          : <Box component="span" aria-hidden sx={(th) => ({ width: 6, height: 6, borderRadius: '50%', bgcolor: th.vars.palette.status.caution })} />}
      </Box>
    </Tooltip>
  );
}
