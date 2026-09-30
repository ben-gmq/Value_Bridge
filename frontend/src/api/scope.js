// Slice 1 resources (§9). One function per route; screens never build URLs themselves.
// Deletes send row_version as a query parameter; derived values are never sent (VB law 6).
import { http } from './client';

const d = (p) => p.then((r) => r.data);
const P = (projectId) => `/api/v1/projects/${projectId}`;
const V = '/api/v1';
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
};

// Slice 3a — the DFD of one parent node (D-31).
export const dfdApi = {
  graph: (nodeId) => d(http.get(`${V}/bfc-nodes/${nodeId}/dfd`)),
};

// Saved diagram positions (D-30). PUT upserts only what it lists; DELETE resets one diagram.
const L = (projectId, type, scopeKey) => `${P(projectId)}/diagram-layouts/${type}/${scopeKey}`;

export const layoutApi = {
  get: (projectId, type, scopeKey) => d(http.get(L(projectId, type, scopeKey))),
  save: (projectId, type, scopeKey, items) => d(http.put(L(projectId, type, scopeKey), items)),
  reset: (projectId, type, scopeKey) => d(http.delete(L(projectId, type, scopeKey))),
};
