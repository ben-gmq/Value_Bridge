// Auto-layout through the ELK web worker (§14.6). Settings are the spike's: layered, orthogonal,
// BRANDES_KOEPF placement — never NETWORK_SIMPLEX (35 s at 200 entities).
let worker = null;
let seq = 0;
const pending = new Map();

function getWorker() {
  if (!worker) {
    worker = new Worker(new URL('./elk.worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = (e) => {
      const p = pending.get(e.data.id);
      if (!p) return;
      pending.delete(e.data.id);
      if (e.data.error) p.reject(new Error(e.data.error));
      else p.resolve(e.data.graph);
    };
  }
  return worker;
}

export function elkLayout(graph) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    getWorker().postMessage({ id, graph });
  });
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
