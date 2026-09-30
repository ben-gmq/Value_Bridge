// ELK runs off the main thread (§14.6). One request in, one laid-out graph (or an error) out.
import ELK from 'elkjs/lib/elk.bundled.js';

const elk = new ELK();

self.onmessage = async (e) => {
  const { id, graph } = e.data;
  try {
    self.postMessage({ id, graph: await elk.layout(graph) });
  } catch (err) {
    self.postMessage({ id, error: String(err?.message ?? err) });
  }
};
