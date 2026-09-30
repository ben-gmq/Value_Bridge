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
