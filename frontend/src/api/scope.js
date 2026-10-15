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
  tree: (projectId, includeRetired = false, bfcSet = 'TO_BE') =>
    d(http.get(`${P(projectId)}/bfc-tree`, { params: { include_retired: includeRetired, bfc_set: bfcSet } })),
  // D-46: one performer per process, sent by code (or an AI's name), never by id.
  setPerformer: (id, body) => d(http.put(`${V}/bfc-nodes/${id}/performer`, body)),
  // D-49: the triggers that start a step.
  triggers: (id) => d(http.get(`${V}/bfc-nodes/${id}/triggers`)),
  linkTrigger: (id, body) => d(http.post(`${V}/bfc-nodes/${id}/triggers`, body)),
  unlinkTrigger: (id, linkId, rowVersion) => del(`${V}/bfc-nodes/${id}/triggers/${linkId}`, rowVersion),
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
  apps: (id) => d(http.get(`${V}/bfc-nodes/${id}/applications`)),
  linkApp: (id, body) => d(http.post(`${V}/bfc-nodes/${id}/applications`, body)),
  editAppLink: (id, linkId, body) => d(http.patch(`${V}/bfc-nodes/${id}/applications/${linkId}`, body)),
  unlinkApp: (id, linkId, rowVersion) => del(`${V}/bfc-nodes/${id}/applications/${linkId}`, rowVersion),
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
  solutions: (id) => d(http.get(`${V}/business-requirements/${id}/solutions`)),
  linkSolution: (id, body) => d(http.post(`${V}/business-requirements/${id}/solutions`, body)),
  editSolutionLink: (id, linkId, body) => d(http.patch(`${V}/business-requirements/${id}/solutions/${linkId}`, body)),
  unlinkSolution: (id, linkId, rowVersion) => del(`${V}/business-requirements/${id}/solutions/${linkId}`, rowVersion),
};

// Slice 5 (docs/slice5_spec.md). A link is always made through its BR's route, from either page.
export const solutionApi = {
  list: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/solutions`, { params: { include_retired: includeRetired } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/solutions`, body)),
  get: (id) => d(http.get(`${V}/solutions/${id}`)),
  update: (id, body) => d(http.patch(`${V}/solutions/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/solutions/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/solutions/${id}/restore`)),
  brs: (id) => d(http.get(`${V}/solutions/${id}/business-requirements`)),
  frs: (id) => d(http.get(`${V}/solutions/${id}/function-requirements`)),
  apps: (id) => d(http.get(`${V}/solutions/${id}/applications`)),
  allocate: (id, body) => d(http.post(`${V}/solutions/${id}/applications`, body)),
  editAllocation: (id, linkId, body) => d(http.patch(`${V}/solutions/${id}/applications/${linkId}`, body)),
  unallocate: (id, linkId, rowVersion) => del(`${V}/solutions/${id}/applications/${linkId}`, rowVersion),
};

// Slice 6a (docs/slice6a_spec.md), re-based by D-52 (docs/slice10b_schema.md §1.2): a BR maps to FRs through a
// stored link, made from the BR screen; the FR's solution is an optional tag. `unlinked` = no live BR link,
// `unassigned` = no solution. `create` takes an optional br_id: create and link in one step.
export const frApi = {
  list: (projectId, { includeRetired = false, unlinked = false, unassigned = false } = {}) =>
    d(http.get(`${P(projectId)}/function-requirements`, { params: { include_retired: includeRetired, unlinked, unassigned } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/function-requirements`, body)),
  get: (id) => d(http.get(`${V}/function-requirements/${id}`)),
  update: (id, body) => d(http.patch(`${V}/function-requirements/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/function-requirements/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/function-requirements/${id}/restore`)),
  // The BR's links, one row per link (D-52). Writes are on the BR's route, whichever page is open.
  ofBr: (brId) => d(http.get(`${V}/business-requirements/${brId}/function-requirements`)),
  linkToBr: (brId, body) => d(http.post(`${V}/business-requirements/${brId}/function-requirements`, body)),
  editBrLink: (brId, linkId, body) => d(http.patch(`${V}/business-requirements/${brId}/function-requirements/${linkId}`, body)),
  unlinkFromBr: (brId, linkId, rowVersion) => del(`${V}/business-requirements/${brId}/function-requirements/${linkId}`, rowVersion),
  // The FR's solution tag, set from this BR's row: only one of this BR's live solutions, or null (422 otherwise).
  setSolutionFromBr: (brId, linkId, body) =>
    d(http.put(`${V}/business-requirements/${brId}/function-requirements/${linkId}/solution`, body)),
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

// 7c — the two charts (D-47), the trigger catalogue (D-49) and completeness (D-38).
export const chartApi = {
  counts: (projectId) => d(http.get(`${P(projectId)}/bfc-sets`)),
  copy: (projectId, toSet, fromSet, confirmHash = null) =>
    d(http.post(`${P(projectId)}/bfc-sets/${toSet}/copy-from/${fromSet}`, { confirm_hash: confirmHash })),
  completeness: (projectId, bfcSet = 'TO_BE') =>
    d(http.get(`${P(projectId)}/process-completeness`, { params: { bfc_set: bfcSet } })),
};

export const triggerApi = {
  list: (projectId, includeRetired = false) =>
    d(http.get(`${P(projectId)}/process-triggers`, { params: { include_retired: includeRetired } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/process-triggers`, body)),
  update: (id, body) => d(http.patch(`${V}/process-triggers/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/process-triggers/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/process-triggers/${id}/restore`)),
};

// The project's DFD rule (D-70): per chart, the elements a process needs before a freeze. Everyone reads it; a
// platform admin previews a change (no write) and saves it with the preview's digest and the project's row_version.
export const dfdRuleApi = {
  get: (projectId) => d(http.get(`${P(projectId)}/dfd-rule`)),
  preview: (projectId, body) => d(http.post(`${P(projectId)}/dfd-rule/preview`, body)),
  save: (projectId, body) => d(http.put(`${P(projectId)}/dfd-rule`, body)),
};

// The DFD of one parent node — the one process diagram (D-38): lanes are performers, order is derived.
export const dfdApi = {
  graph: (nodeId) => d(http.get(`${V}/bfc-nodes/${nodeId}/dfd`)),
  mermaid: (nodeId, order = false) => d(http.get(`${V}/bfc-nodes/${nodeId}/dfd/export`,
    { params: { format: 'mermaid', order }, ...asText })),
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
// (`data-entities`, `data-fields`); template and export also take `data-model` (both sheets, S4-12). The upload is the raw .xlsx body, never multipart
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
  // The file-level checks alone, nothing staged (the data-model wizard runs it on the fields sheet
  // before step 1 commits): { target, sheet_name, row_count, file_warnings, other_sheets: [{sheet, target}] }.
  check: (projectId, target, buffer, fileName) => d(http.post(`${P(projectId)}/bulk/${target}/check`, buffer,
    { headers: { 'Content-Type': XLSX_TYPE, 'X-VB-File-Name': encodeURIComponent(fileName) } })),
  batch: (batchId) => d(http.get(`${V}/bulk/batches/${batchId}`)),
  preview: (batchId) => d(http.get(`${V}/bulk/batches/${batchId}/preview`)),
  // acknowledged_inserts is the count the user typed; the server re-validates and compares (R2-P2).
  commit: (batchId, { row_version, acknowledged_inserts }) =>
    d(http.post(`${V}/bulk/batches/${batchId}/commit`, { row_version, acknowledged_inserts })),
};

// Slice 6b-1 (docs/slice6b1_spec.md). Allocations are written through the solution's routes and
// as-is links through the step's, whichever page the user is on.
export const appApi = {
  list: (projectId, includeRetired = false) => d(http.get(`${P(projectId)}/applications`, { params: { include_retired: includeRetired } })),
  create: (projectId, body) => d(http.post(`${P(projectId)}/applications`, body)),
  get: (id) => d(http.get(`${V}/applications/${id}`)),
  update: (id, body) => d(http.patch(`${V}/applications/${id}`, body)),
  retire: (id, rowVersion) => del(`${V}/applications/${id}`, rowVersion),
  restore: (id) => d(http.patch(`${V}/applications/${id}/restore`)),
  solutions: (id) => d(http.get(`${V}/applications/${id}/solutions`)),
  steps: (id) => d(http.get(`${V}/applications/${id}/bfc-nodes`)),
};

// Slice 6b-2 (docs/slice6b2_spec.md). The detail is one PUT (the whole carried set) per FR.
export const ifaceApi = {
  get: (frId) => d(http.get(`${V}/function-requirements/${frId}/interface`)),
  put: (frId, body) => d(http.put(`${V}/function-requirements/${frId}/interface`, body)),
  remove: (frId, rowVersion) => del(`${V}/function-requirements/${frId}/interface`, rowVersion),
  list: (projectId, params = {}) => d(http.get(`${P(projectId)}/interfaces`, { params })),
};

// Slice 6c (docs/slice6c_spec.md). Effort days are derived from the card, never sent (VB law 6).
export const effortApi = {
  card: (projectId) => d(http.get(`${P(projectId)}/rate-card`)),
  saveCard: (projectId, body) => d(http.put(`${P(projectId)}/rate-card`, body)),
  rate: (frId, body) => d(http.patch(`${V}/function-requirements/${frId}/complexity`, body)),
  summary: (projectId) => d(http.get(`${P(projectId)}/effort-summary`)),
};

// Slice 8 (docs/slice8_schema.md §5). Read-only apart from freeze and approve; the version, status and
// digest of the stored baseline are the server's (VB law 6). The freeze sends back the preview's digest, so
// it freezes exactly what the person reviewed (DR8-P2).
export const baselineApi = {
  list: (projectId) => d(http.get(`${P(projectId)}/baselines`)),
  next: (projectId, bump) => d(http.get(`${P(projectId)}/baselines/next`, { params: { bump } })),
  freeze: (projectId, body) => d(http.post(`${P(projectId)}/baselines/freeze`, body)),
  diff: (projectId, from, to, priced) =>
    d(http.get(`${P(projectId)}/baselines/diff`, { params: { from, to, priced } })),
  get: (id) => d(http.get(`${V}/baselines/${id}`)),
  rows: (id, entity, offset, limit) => d(http.get(`${V}/baselines/${id}/rows/${entity}`, { params: { offset, limit } })),
  approve: (id, body) => d(http.post(`${V}/baselines/${id}/approve`, body)),
};
