// Edge types every diagram shares (§14.6). The canvas owns them so the flow, the DFD and the
// ERD agree on how a labelled line behaves when zoomed out.
import { BezierEdge, SmoothStepEdge, useStore } from '@xyflow/react';
import { LOW_ZOOM } from './layout';

/** A smoothstep line whose label hides in the low-zoom view, as box text does (sara L8). */
export function LabelledEdge(props) {
  const low = useStore((s) => s.transform[2] < LOW_ZOOM);
  return <SmoothStepEdge {...props} label={low ? undefined : props.label} />;
}

/** The same, drawn as a soft curve — the DFD's line in mockup 02. */
export function CurvedEdge(props) {
  const low = useStore((s) => s.transform[2] < LOW_ZOOM);
  return <BezierEdge {...props} label={low ? undefined : props.label} />;
}

export const EDGE_TYPES = { labelled: LabelledEdge, curved: CurvedEdge };

/**
 * The mockups' line look (D-51), one place for every diagram: a quiet muted line with its label in
 * a small pill; `hot` (a line touching the selected box) in FTC violet, a little heavier.
 * `palette` is theme.vars.palette, so every value is a theme token.
 */
export function edgeLook(palette, hot = false) {
  const stroke = hot ? palette.brand.ftcViolet : palette.brand.muted;
  return {
    style: { stroke, strokeWidth: hot ? 2 : 1.5 },
    markerColor: stroke,
    labelStyle: { fill: hot ? palette.brand.purpleText : palette.text.secondary, fontSize: 11.5, fontWeight: 500 },
    labelBgStyle: { fill: palette.background.paper, stroke: palette.brand.lineStrong, strokeWidth: 1 },
    labelBgPadding: [8, 4],
    labelBgBorderRadius: 11,
  };
}
