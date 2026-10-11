// The diagrams' shared look (D-51, mockup 02): node frames, the header strip with counts and legend,
// and the small flags a box can carry. The DFD and the ERD (and any later diagram on <ModelCanvas>)
// draw their boxes from these, so every diagram reads alike. Theme tokens only.
import { Box, Typography } from '@mui/material';
import { RADIUS } from '../theme/brand';
import { MONO } from '../theme/theme';

/**
 * The tone of a box on a diagram: purple = a process, teal = a data entity or store,
 * navy = a system or an outside party. Returns [border, header tint, code text].
 */
const TONES = {
  purple: (p) => [p.brand.level4, p.brand.purpleTint, p.brand.purpleText],
  teal: (p) => [p.brand.teal, p.brand.tealTint, p.brand.tealText],
  navy: (p) => [p.primary.main, p.brand.navyTint, p.brand.link],
};

export const toneColors = (th, tone) => TONES[tone](th.vars.palette);

/** The sx of a diagram box: radius 18, a 1.5px tone border; selected → violet with a soft ring;
 * `warn` → amber (a gap that blocks the freeze). */
export function nodeFrame(th, tone, { selected = false, warn = false, dashed = false, radius = RADIUS.diagram } = {}) {
  const p = th.vars.palette;
  const [border] = toneColors(th, tone);
  return {
    position: 'relative', borderRadius: `${radius}px`, bgcolor: p.background.paper,
    border: `1.5px ${dashed ? 'dashed' : 'solid'} ${selected ? p.brand.ftcViolet : warn ? p.warning.main : border}`,
    boxShadow: selected ? `0 0 0 4px ${p.brand.purpleTint}` : 'none',
    transition: 'box-shadow 120ms, border-color 120ms',
  };
}

/** The coloured header strip of a box (its code row), inside a frame from nodeFrame. */
export function nodeHeader(th, tone, { selected = false, radius = RADIUS.diagram } = {}) {
  const [border, tint] = toneColors(th, tone);
  return {
    bgcolor: selected ? th.vars.palette.brand.selected : tint,
    borderBottom: `1px solid ${selected ? th.vars.palette.brand.ftcViolet : border}`,
    borderTopLeftRadius: `${radius - 2}px`, borderTopRightRadius: `${radius - 2}px`,
  };
}

/** A small pill pinned to a box's top-right corner: "gap", "Cross-area", "No key". */
export function NodeFlag({ children, tone = 'caution', title }) {
  return (
    <Box component="span" title={title} sx={(th) => {
      const c = { caution: th.vars.palette.warning.main, teal: th.vars.palette.brand.tealText }[tone];
      return { position: 'absolute', top: -11, right: 12, px: 0.9, height: 20, display: 'inline-flex', alignItems: 'center',
        borderRadius: `${RADIUS.pill}px`, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', color: c,
        bgcolor: th.vars.palette.background.paper, border: `1.5px solid ${c}`, zIndex: 1 };
    }}>{children}</Box>
  );
}

/** One legend entry: a tiny swatch in the shape the diagram draws, and its name. */
export function LegendSwatch({ shape, label }) {
  const swatch = (th) => {
    const p = th.vars.palette;
    const base = { width: 18, height: 12, flexShrink: 0, borderStyle: 'solid', borderWidth: '1.5px' };
    return {
      process: { ...base, borderColor: p.brand.level4, borderRadius: '4px' },
      entity: { ...base, borderColor: p.brand.teal, borderRadius: '4px' },
      store: { ...base, borderColor: p.brand.teal, borderRightWidth: 0, bgcolor: p.brand.tealTint },
      party: { ...base, borderColor: p.primary.main, borderWidth: '2.5px' },
      trigger: { ...base, width: 12, borderColor: p.text.secondary, borderRadius: '50%' },
      ghost: { ...base, borderColor: p.brand.lineStrong, borderStyle: 'dashed', borderRadius: '4px' },
      line: { ...base, height: 0, borderWidth: 0, borderTop: `1.5px solid ${p.brand.muted}` },
      dashed: { ...base, height: 0, borderWidth: 0, borderTop: `1.5px dashed ${p.brand.muted}` },
      order: { ...base, height: 0, borderWidth: 0, borderTop: `1.5px dashed ${p.primary.main}` },
    }[shape];
  };
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, fontSize: 12.5, color: 'text.secondary', whiteSpace: 'nowrap' }}>
      <Box aria-hidden sx={swatch} />{label}
    </Box>
  );
}

/** The strip across the top of a diagram card: mono counts at the left, legend and controls at the right. */
export function CanvasHeader({ summary, legend, children }) {
  return (
    <Box sx={(th) => ({ px: 2.5, py: 1.5, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap',
      borderBottom: `1px solid ${th.vars.palette.divider}` })}>
      {summary && (
        <Typography sx={(th) => ({ fontFamily: MONO, fontSize: 12.5, color: th.vars.palette.brand.muted })}>{summary}</Typography>)}
      <Box sx={{ flexGrow: 1 }} />
      {legend && <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>{legend}</Box>}
      {children}
    </Box>
  );
}

/** The two-column body of a diagram screen: the canvas card and a 320px side panel (stacks when narrow). */
export function DiagramGrid({ children }) {
  return (
    <Box sx={{ display: 'grid', gap: 2, alignItems: 'start',
      gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1fr) 320px' } }}>
      {children}
    </Box>
  );
}
