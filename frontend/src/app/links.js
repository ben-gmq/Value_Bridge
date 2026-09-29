// The page addresses every screen links to (§14.1: a URL names its scope). Screens link to
// each other only through these, so the three Slice 1 screens agree without knowing each other.
export const links = {
  processes: (p) => `/p/${p}/processes`,
  node: (p, nodeId) => `/p/${p}/processes?node=${nodeId}`,
  requirements: (p) => `/p/${p}/requirements`,
  requirement: (p, brId) => `/p/${p}/requirements/${brId}`,
  data: (p) => `/p/${p}/data`,
  entity: (p, deId) => `/p/${p}/data/${deId}`,
  settings: (p) => `/p/${p}/settings`,
  access: (p) => `/p/${p}/access`,
  organisation: (p) => `/p/${p}/settings/organisation`,
  parties: (p) => `/p/${p}/settings/parties`,
};

// TanStack Query keys, shared so a save on one screen refreshes the others.
export const keys = {
  tree: (p) => ['bfc-tree', String(p)],
  node: (id) => ['bfc-node', String(id)],
  brs: (p) => ['brs', String(p)],
  br: (id) => ['br', String(id)],
  entities: (p) => ['entities', String(p)],
  entity: (id) => ['entity', String(id)],
  parties: (p) => ['parties', String(p)],
  units: (p) => ['org-units', String(p)],
  roles: (p) => ['org-roles', String(p)],
};
