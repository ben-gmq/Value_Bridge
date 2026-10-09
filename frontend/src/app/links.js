// The page addresses every screen links to (§14.1: a URL names its scope). Screens link to
// each other only through these, so the three Slice 1 screens agree without knowing each other.
export const links = {
  processes: (p) => `/p/${p}/processes`,
  node: (p, nodeId) => `/p/${p}/processes?node=${nodeId}`,
  flow: (p, nodeId) => `/p/${p}/processes/${nodeId}/flow`,
  dfd: (p, nodeId) => `/p/${p}/processes/${nodeId}/dfd`,
  requirements: (p) => `/p/${p}/requirements`,
  requirement: (p, brId) => `/p/${p}/requirements/${brId}`,
  data: (p) => `/p/${p}/data`,
  entity: (p, deId) => `/p/${p}/data/${deId}`,
  erd: (p, area) => (area ? `/p/${p}/data/diagram?area=${encodeURIComponent(area)}` : `/p/${p}/data/diagram`),
  settings: (p) => `/p/${p}/settings`,
  access: (p) => `/p/${p}/access`,
  organisation: (p) => `/p/${p}/settings/organisation`,
  parties: (p) => `/p/${p}/settings/parties`,
};

// TanStack Query keys, shared so a save on one screen refreshes the others.
export const keys = {
  tree: (p) => ['bfc-tree', String(p)],
  node: (id) => ['bfc-node', String(id)],
  retirePreview: (id) => ['retire-preview', String(id)],     // not under node(id): a retired node has no preview
  brs: (p) => ['brs', String(p)],
  br: (id) => ['br', String(id)],
  entities: (p) => ['entities', String(p)],
  entity: (id) => ['entity', String(id)],
  everyEntity: () => ['entity'],                                                     // every entity(id): an import of fields
  erd: (p, area) => ['entities', String(p), 'erd', String(area ?? 'project')],   // under entities(p): field edits refresh it
  parties: (p) => ['parties', String(p)],
  units: (p) => ['org-units', String(p)],
  roles: (p) => ['org-roles', String(p)],
  flows: (p) => ['process-flows', String(p)],
  flowGaps: (p) => ['flow-completeness', String(p)],
  flowGraph: (p, nodeId) => ['process-flows', String(p), 'graph', String(nodeId)],   // under flows(p): edge edits refresh it
  dfdGraph: (p, nodeId) => ['process-flows', String(p), 'dfd', String(nodeId)],     // under flows(p): step I/O edits refresh it
  importBatch: (id) => ['import-batch', String(id)],
  importPreview: (id) => ['import-batch', String(id), 'preview'],                     // under importBatch(id): a commit refreshes it
};
