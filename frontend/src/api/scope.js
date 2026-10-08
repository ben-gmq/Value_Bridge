// Slice 1 resources (§9). One function per route; screens never build URLs themselves.
// Deletes send row_version as a query parameter; derived values are never sent (VB law 6).
import { http } from './client';

const d = (p) => p.then((r) => r.data);
const P = (projectId) => `/api/v1/projects/${projectId}`;
const V = '/api/v1';
// A text/plain export arrives as text; an error body (JSON) is still parsed, so errorText works.
const asText = { responseType: 'text',
  transformResponse: (data, headers) => (String(headers?.['content-type'] ?? '').includes('json') ? JSON.parse(data) : data) };
const del = (url, rowVersion) => d(http.delete(url, { params: { row_version: rowVersion } }));

export const bfcApi = {
  tree: (projectId, includeRetired = false) =>
    d(http.get(`${P(projectId)}/bfc-tree`, { params: { include_retired: includeRetired } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/bfc-nodes`, body)),
  get: (id) => d(http.get(`${V}/bfc-nodes/${id}`)),
  update: (id, body) => d(http.patch(`${V}/bfc-nodes/${id}`, body)),
  reorder: (id, body) => d(http.patch(`${V}/bfc-nodes/${id}/reorder`, body)),
  markProcess: (id, body) => d(http.patch(`${V}/bfc-nodes/${id}/process`, body)),
  retire: (id, rowVersion) => del(`${V}/bfc-nodes/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/bfc-nodes/${id}/restore`)),
  // A process step retires with its requirement and flows, and comes back the same way
  // (docs/step_retire_spec.md §9). The hash is the preview's staleness check.
  retirePreview: (id) => d(http.get(`${V}/bfc-nodes/${id}/retire-preview`)),
  retireWithDependents: (id, confirmHash) => d(http.post(`${V}/bfc-nodes/${id}/retire-with-dependents`, { confirm_hash: confirmHash })),
  restoreWithDependents: (id) => d(http.post(`${V}/bfc-nodes/${id}/restore-with-dependents`)),
  stepData: (id) => d(http.get(`${V}/bfc-nodes/${id}/data-entities`)),
  linkStepData: (id, body) => d(http.post(`${V}/bfc-nodes/${id}/data-entities`, body)),
  unlinkStepData: (id, linkId, rowVersion) => del(`${V}/bfc-nodes/${id}/data-entities/${linkId}`, rowVersion),
  roles: (id) => d(http.get(`${V}/bfc-nodes/${id}/org-roles`)),
  linkRole: (id, body) => d(http.post(`${V}/bfc-nodes/${id}/org-roles`, body)),
  unlinkRole: (id, linkId, rowVersion) => del(`${V}/bfc-nodes/${id}/org-roles/${linkId}`, rowVersion),
  flows: (id) => d(http.get(`${V}/bfc-nodes/${id}/external-flows`)),
  linkFlow: (id, body) => d(http.post(`${V}/bfc-nodes/${id}/external-flows`, body)),
  unlinkFlow: (id, linkId, rowVersion) => del(`${V}/bfc-nodes/${id}/external-flows/${linkId}`, rowVersion),
};

// There is no "create requirement": a BR appears with its process step (D-2).
export const brApi = {
  list: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/business-requirements`, { params: { include_retired: includeRetired } })),
  get: (id) => d(http.get(`${V}/business-requirements/${id}`)),
  update: (id, body) => d(http.patch(`${V}/business-requirements/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/business-requirements/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/business-requirements/${id}/restore`)),
  data: (id) => d(http.get(`${V}/business-requirements/${id}/data-entities`)),
  linkData: (id, body) => d(http.post(`${V}/business-requirements/${id}/data-entities`, body)),
  unlinkData: (id, linkId, rowVersion) => del(`${V}/business-requirements/${id}/data-entities/${linkId}`, rowVersion),
  roles: (id) => d(http.get(`${V}/business-requirements/${id}/org-roles`)),
  linkRole: (id, body) => d(http.post(`${V}/business-requirements/${id}/org-roles`, body)),
  unlinkRole: (id, linkId, rowVersion) => del(`${V}/business-requirements/${id}/org-roles/${linkId}`, rowVersion),
};

export const dataApi = {
  list: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/data-entities`, { params: { include_retired: includeRetired } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/data-entities`, body)),
  get: (id) => d(http.get(`${V}/data-entities/${id}`)),
  update: (id, body) => d(http.patch(`${V}/data-entities/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/data-entities/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/data-entities/${id}/restore`)),
  usedBy: (id) => d(http.get(`${V}/data-entities/${id}/business-requirements`)),
  fields: (id, includeRetired = false) => d(http.get(`${V}/data-entities/${id}/fields`, { params: { include_retired: includeRetired } })),
  createField: (id, body) => d(http.post(`${V}/data-entities/${id}/fields`, body)),
  updateField: (fieldId, body) => d(http.patch(`${V}/data-fields/${fieldId}`, body)),
  retireField: (fieldId, rowVersion) => del(`${V}/data-fields/${fieldId}`, rowVersion),
  restoreField: (fieldId) => d(http.patch(`${V}/data-fields/${fieldId}/restore`)),
};

export const partyApi = {
  list: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/external-entities`, { params: { include_retired: includeRetired } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/external-entities`, body)),
  update: (id, body) => d(http.patch(`${V}/external-entities/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/external-entities/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/external-entities/${id}/restore`)),
};

export const orgApi = {
  units: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/org-units`, { params: { include_retired: includeRetired } })),
  createUnit: (projectId, body) => d(http.post(`${P(projectId)}/org-units`, body)),
  updateUnit: (id, body) => d(http.patch(`${V}/org-units/${id}`, body)),
  retireUnit: (id, rowVersion) => del(`${V}/org-units/${id}`, rowVersion),
  restoreUnit: (id) => d(http.patch(`${V}/org-units/${id}/restore`)),
  roles: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/org-roles`, { params: { include_retired: includeRetired } })),
  createRole: (projectId, body) => d(http.post(`${P(projectId)}/org-roles`, body)),
  updateRole: (id, body) => d(http.patch(`${V}/org-roles/${id}`, body)),
  retireRole: (id, rowVersion) => del(`${V}/org-roles/${id}`, rowVersion),
  restoreRole: (id) => d(http.patch(`${V}/org-roles/${id}/restore`)),
};

// Slice 2 — process flow edges (§9, S2-2: the ends are create-only).
export const flowApi = {
  list: (projectId, nodeId) => d(http.get(`${P(projectId)}/process-flows`, { params: nodeId ? { bfc_node_id: nodeId } : {} })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/process-flows`, body)),
  update: (id, body) => d(http.patch(`${V}/process-flows/${id}`, body)),
  remove: (id, rowVersion) => del(`${V}/process-flows/${id}`, rowVersion),
  completeness: (projectId) => d(http.get(`${P(projectId)}/flow-completeness`)),
  graph: (nodeId, variant = 'AS_IS') => d(http.get(`${V}/bfc-nodes/${nodeId}/process-flow`, { params: { variant } })),
  // Slice 3c — the same graph as Mermaid text (R2-S7).
  mermaid: (nodeId, variant = 'AS_IS') => d(http.get(`${V}/bfc-nodes/${nodeId}/process-flow/export`,
    { params: { format: 'mermaid', variant }, ...asText })),
  // A suggested chain in chart order: nothing is stored until keep (docs/draft_arrows_spec.md §9).
  suggest: (nodeId) => d(http.get(`${V}/bfc-nodes/${nodeId}/process-flow/suggest`)),
  keep: (nodeId, confirmHash) => d(http.post(`${V}/bfc-nodes/${nodeId}/process-flow/suggest/keep`,
    { confirm_hash: confirmHash })),
};

// Slice 3a — the DFD of one parent node (D-31).
export const dfdApi = {
  graph: (nodeId) => d(http.get(`${V}/bfc-nodes/${nodeId}/dfd`)),
  mermaid: (nodeId) => d(http.get(`${V}/bfc-nodes/${nodeId}/dfd/export`, { params: { format: 'mermaid' }, ...asText })),
};

// Saved diagram positions (D-30). PUT upserts only what it lists; DELETE resets one diagram.
const L = (projectId, type, scopeKey) => `${P(projectId)}/diagram-layouts/${type}/${scopeKey}`;

export const layoutApi = {
  get: (projectId, type, scopeKey) => d(http.get(L(projectId, type, scopeKey))),
  save: (projectId, type, scopeKey, items) => d(http.put(L(projectId, type, scopeKey), items)),
  reset: (projectId, type, scopeKey) => d(http.delete(L(projectId, type, scopeKey))),
};

// Slice 3b — the logical ERD (§7.4 generate_erd). `area` is a chart node id, or empty for the
// whole project. Positions go through layoutApi with type ERD and the graph's scope_key.
export const erdApi = {
  graph: (projectId, area) => d(http.get(`${P(projectId)}/erd`, { params: area ? { subject_area: area } : {} })),
  mermaid: (projectId, area) => d(http.get(`${P(projectId)}/erd/export`,
    { params: { format: 'mermaid', ...(area ? { subject_area: area } : {}) }, ...asText })),
};

// Slice 4a — the one import pipeline (docs/slice4a_spec.md §9). `target` is the route slug
// (`data-entities`; 4a-2 adds `data-fields`). The upload is the raw .xlsx body, never multipart
// (A-4a-7), with the display name percent-encoded in X-VB-File-Name (4a-R8).
export const XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

// A blob response's error body is JSON underneath: parse it back so errorText can read detail.
async function readBlobError(err) {
  const data = err?.response?.data;
  if (data instanceof Blob) {
    try { err.response.data = JSON.parse(await data.text()); } catch { /* not JSON: keep the fallback */ }
  }
  return err;
}

// The server names the file (§7.11); never from user text. Saved via a throwaway object URL.
const dispositionName = (headers, fallback) =>
  /filename="([^"]+)"/.exec(String(headers?.['content-disposition'] ?? ''))?.[1] ?? fallback;

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function download(url, fallback) {
  try {
    const r = await http.get(url, { responseType: 'blob' });
    const name = dispositionName(r.headers, fallback);
    saveBlob(r.data, name);
    return name;
  } catch (err) {
    throw await readBlobError(err);
  }
}

export const importApi = {
  template: (projectId, target) => download(`${P(projectId)}/bulk/templates/${target}`, `vb-${target}-template.xlsx`),
  export: (projectId, target) => download(`${P(projectId)}/bulk/${target}/export`, `vb-${target}-export.xlsx`),
  // `buffer` is the ArrayBuffer read once when the file was picked (4a-R16). 201 → the preview.
  validate: (projectId, target, buffer, fileName) => d(http.post(`${P(projectId)}/bulk/${target}/validate`, buffer,
    { headers: { 'Content-Type': XLSX_TYPE, 'X-VB-File-Name': encodeURIComponent(fileName) } })),
  batch: (batchId) => d(http.get(`${V}/bulk/batches/${batchId}`)),
  preview: (batchId) => d(http.get(`${V}/bulk/batches/${batchId}/preview`)),
  // acknowledged_inserts is the count the user typed; the server re-validates and compares (R2-P2).
  commit: (batchId, { row_version, acknowledged_inserts }) =>
    d(http.post(`${V}/bulk/batches/${batchId}/commit`, { row_version, acknowledged_inserts })),
};
