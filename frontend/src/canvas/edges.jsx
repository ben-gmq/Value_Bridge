// Edge types every diagram shares (§14.6). The canvas owns them so the flow, the DFD and the
// ERD agree on how a labelled line behaves when zoomed out.
import { SmoothStepEdge, useStore } from '@xyflow/react';
import { LOW_ZOOM } from './layout';

/** A smoothstep line whose label hides in the low-zoom view, as box text does (sara L8). */
export function LabelledEdge(props) {
  const low = useStore((s) => s.transform[2] < LOW_ZOOM);
  return <SmoothStepEdge {...props} label={low ? undefined : props.label} />;
}

export const EDGE_TYPES = { labelled: LabelledEdge };
