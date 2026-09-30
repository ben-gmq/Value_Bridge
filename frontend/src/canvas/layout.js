// Auto-layout through the ELK web worker (§14.6). Settings are the spike's: layered, orthogonal,
// BRANDES_KOEPF placement — never NETWORK_SIMPLEX (35 s at 200 entities).
import ELK from 'elkjs/lib/elk-api.js';

let elk = null;

export function elkLayout(graph) {
  if (!elk) {
    elk = new ELK({ workerFactory: () => new Worker(new URL('./elk.worker.js', import.meta.url), { type: 'module' }) });
  }
  return elk.layout(graph);
}

export const LAYERED_RIGHT = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.spacing.nodeNode': '40',
  'elk.layered.spacing.nodeNodeBetweenLayers': '70',
};

/** Where the canvas stops showing text (§14.6): below this zoom, a simplified view. */
export const LOW_ZOOM = 0.45;

const overlaps = (a, b, gap) => a.x < b.x + b.w + gap && b.x < a.x + a.w + gap
  && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap;

/**
 * Pinned boxes keep their saved place; every other box is pushed clear of every box already
 * placed (§14.6, sara L7). `boxes` is [{id, x, y, w, h, pinned}]; returns a Map id → {x, y}.
 * `axis` 'x' pushes right (the flow: a step never leaves its lane band, or it would read as
 * another role's step); 'y' pushes down the column (DFD, ERD). Arranging saves nothing —
 * only a drag end does — so an arrange never pins a box.
 */
export function pushClear(boxes, { axis = 'y', gap = 24 } = {}) {
  const placed = boxes.filter((b) => b.pinned).map((b) => ({ ...b }));
  const free = boxes.filter((b) => !b.pinned).map((b) => ({ ...b }))
    .sort((a, b) => (axis === 'x' ? a.x - b.x || a.y - b.y : a.y - b.y || a.x - b.x));
  for (const b of free) {
    // Each move clears one placed box and never moves back, so this ends within |placed| moves.
    for (let guard = 0; guard <= placed.length; guard += 1) {
      const hit = placed.find((p) => overlaps(b, p, gap));
      if (!hit) break;
      if (axis === 'x') b.x = hit.x + hit.w + gap;
      else b.y = hit.y + hit.h + gap;
    }
    placed.push(b);
  }
  return new Map(placed.map((b) => [b.id, { x: b.x, y: b.y }]));
}
