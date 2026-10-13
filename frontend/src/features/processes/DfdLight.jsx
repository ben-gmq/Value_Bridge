import { Box, Tooltip } from '@mui/material';
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded';
import WarningAmberRounded from '@mui/icons-material/WarningAmberRounded';
import CancelRounded from '@mui/icons-material/CancelRounded';
import CheckRounded from '@mui/icons-material/CheckRounded';
import { Tag } from '../../components/kit';
import { t } from '../../i18n/t';

// D-68 / D-69 (slice 13a): the DFD readiness light and the "DFD" marks. Both read only what the server says —
// the tree row's dfd_light and dfd_missing element codes (services/process_flow.readiness) — never whether a tile
// looks empty (DR13-D1). The light is always colour + icon + text (D-50), the colours are STATUS_COLOR_MAP tokens.
const LOOK = {
  READY: { tone: 'ok', Icon: CheckCircleRounded },
  PARTIAL: { tone: 'caution', Icon: WarningAmberRounded },
  NOT_READY: { tone: 'escalate', Icon: CancelRounded },
};

/** The light's tooltip: what is still needed. Under the fixed rule every gap blocks the freeze (DR13-P2, until Q-13). */
export function lightTip(light, missing = []) {
  if (light === 'READY') return t('processes.dfdLight.tipReady');
  return [t('processes.dfdLight.stillNeeded'), ...missing.map((code) => `• ${t(`processes.dfdLight.element.${code}`)}`),
    t('processes.dfdLight.blocks')].join('\n');
}

/** A process's light: an icon and a word in a tone tag, its gaps in the tooltip. Nothing when the rule does not apply. */
export function DfdLight({ light, missing, size = 'md', sx }) {
  const look = LOOK[light];
  if (!look) return null;
  const small = size === 'sm';
  return (
    <Tooltip title={<Box component="span" sx={{ whiteSpace: 'pre-line' }}>{lightTip(light, missing)}</Box>}>
      <Box component="span" tabIndex={small ? undefined : 0} aria-label={`${t('processes.dfdLight.label')}: ${t(`processes.dfdLight.${light}`)}. ${lightTip(light, missing)}`}
        sx={{ display: 'inline-flex', flex: 'none', borderRadius: 999, '&:focus-visible': { outline: '2px solid', outlineOffset: 1 }, ...sx }}>
        <Tag tone={look.tone} icon={<look.Icon aria-hidden sx={{ fontSize: small ? 14 : 16 }} />}
          sx={small ? { height: 20, px: 0.75, fontSize: 11.5 } : undefined}>
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
 * D-69: a small "DFD" mark on a field the rule needs — a tick when the server says the element is met, the amber
 * dot (10d's "not set" dot) when it is missing. `dfd` is { missing } from the tree row, or null when the rule does
 * not apply to this chart (no mark at all).
 */
export function DfdMark({ dfd, element }) {
  if (!dfd) return null;
  const met = !dfd.missing.includes(element);
  const tip = `${t('processes.dfdMark.note')} — ${t(`processes.dfdMark.element.${element}`)}. ${t(met ? 'processes.dfdMark.met' : 'processes.dfdMark.missing')}`;
  return (
    <Tooltip title={tip}>
      <Box component="span" role="img" aria-label={tip} sx={(th) => ({ display: 'inline-flex', alignItems: 'center', gap: 0.4, flex: 'none',
        height: 18, px: 0.6, borderRadius: 999, border: `1px solid ${th.vars.palette.divider}`, fontSize: 10.5, fontWeight: 700,
        letterSpacing: 0.3, color: th.vars.palette.brand.muted, verticalAlign: 'middle' })}>
        {t('processes.dfdMark.label')}
        {met ? <CheckRounded aria-hidden sx={(th) => ({ fontSize: 13, color: th.vars.palette.status.ok })} />
          : <Box component="span" aria-hidden sx={(th) => ({ width: 6, height: 6, borderRadius: '50%', bgcolor: th.vars.palette.status.caution })} />}
      </Box>
    </Tooltip>
  );
}
