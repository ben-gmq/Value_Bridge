// The page addresses every screen links to (§14.1: a URL names its scope). Screens link to
// each other only through these, so the three Slice 1 screens agree without knowing each other.
export const links = {
  processes: (p, bfcSet) => (bfcSet === 'AS_IS' ? `/p/${p}/processes?set=AS_IS` : `/p/${p}/processes`),
  node: (p, nodeId, bfcSet) => `/p/${p}/processes?node=${nodeId}${bfcSet === 'AS_IS' ? '&set=AS_IS' : ''}`,
  dfd: (p, nodeId) => `/p/${p}/processes/${nodeId}/dfd`,         // any node's roll-up diagram, opened from the chart
  // D-54: the DFD screen — one diagram per direct parent of processes, the selected one in the URL.
  dfds: (p, nodeId, bfcSet) => {
    const q = new URLSearchParams();
    if (nodeId != null) q.set('node', nodeId);
    if (bfcSet === 'AS_IS') q.set('set', 'AS_IS');
    const qs = q.toString();
    return qs ? `/p/${p}/dfd?${qs}` : `/p/${p}/dfd`;
  },
  // D-53: no requirement list — a BR lives in its process's panel; this deep link stays (FRs, solutions, the diff).
  requirement: (p, brId) => `/p/${p}/requirements/${brId}`,
  solutions: (p) => `/p/${p}/br-fr`,          // the BR–FR map opens on its Solutions tab (S6a-4)
  solution: (p, solId) => `/p/${p}/br-fr/${solId}`,
  frs: (p) => `/p/${p}/br-fr/frs`,
  fr: (p, frId) => `/p/${p}/br-fr/frs/${frId}`,
  data: (p) => `/p/${p}/data`,
  entity: (p, deId) => `/p/${p}/data/${deId}`,
  erd: (p, area) => (area ? `/p/${p}/data/diagram?area=${encodeURIComponent(area)}` : `/p/${p}/data/diagram`),
  settings: (p) => `/p/${p}/settings`,
  components: (p) => `/p/${p}/settings/components`,
  access: (p) => `/p/${p}/access`,
  organisation: (p) => `/p/${p}/settings/organisation`,
  parties: (p) => `/p/${p}/settings/parties`,
  interfaces: (p) => `/p/${p}/interfaces`,
  rateCard: (p) => `/p/${p}/settings/rate-card`,
  effort: (p) => `/p/${p}/br-fr/effort`,
  applications: (p) => `/p/${p}/settings/applications`,
  application: (p, appId) => `/p/${p}/settings/applications/${appId}`,
  baselines: (p, from, to) => (from ? `/p/${p}/baselines?from=${from}&to=${to ?? 'live'}` : `/p/${p}/baselines`),
  baseline: (p, id) => `/p/${p}/baselines/${id}`,
};

// TanStack Query keys, shared so a save on one screen refreshes the others.
export const keys = {
  components: (p) => ['components', String(p)],
  componentCatalogue: () => ['component-catalogue'],
  projectTemplates: () => ['project-templates'],
  project: (p) => ['project', String(p)],
  projectAccess: (p) => ['access', String(p)],
  tree: (p) => ['bfc-tree', String(p)],
  node: (id) => ['bfc-node', String(id)],
  retirePreview: (id) => ['retire-preview', String(id)],     // not under node(id): a retired node has no preview
  brs: (p) => ['brs', String(p)],
  br: (id) => ['br', String(id)],
  solutions: (p) => ['solutions', String(p)],
  solution: (id) => ['solution', String(id)],
  solutionLinks: () => ['solution-links'],                                           // both sides' link lists
  frs: (p) => ['frs', String(p)],
  fr: (id) => ['fr', String(id)],
  applications: (p) => ['applications', String(p)],
  application: (id) => ['application', String(id)],
  appLinks: () => ['app-links'],
  appLinksOf: (kind, id) => ['app-links', kind, String(id)],                                                     // allocations and as-is links, every page
  iface: (frId) => ['fr-interface', String(frId)],
  interfaces: (p) => ['interfaces', String(p)],
  rateCard: (p) => ['rate-card', String(p)],
  effortSummary: (p) => ['effort-summary', String(p)],
  frTrace: () => ['fr-trace'],                                                       // FR panels on solution and BR pages
  entities: (p) => ['entities', String(p)],
  entity: (id) => ['entity', String(id)],
  everyEntity: () => ['entity'],                                                     // every entity(id): an import of fields
  erd: (p, area) => ['entities', String(p), 'erd', String(area ?? 'project')],   // under entities(p): field edits refresh it
  parties: (p) => ['parties', String(p)],
  units: (p) => ['org-units', String(p)],
  roles: (p) => ['org-roles', String(p)],
  flows: (p) => ['process-flows', String(p)],                                       // every DFD of the project
  flowGaps: (p) => ['process-flows', String(p), 'completeness'],                    // under flows(p)
  dfdGraph: (p, nodeId) => ['process-flows', String(p), 'dfd', String(nodeId)],     // under flows(p): step I/O edits refresh it
  triggers: (p) => ['process-triggers', String(p)],
  stepTriggers: (nodeId) => ['bfc-node', String(nodeId), 'triggers'],                // under node(id)
  chartCounts: (p) => ['bfc-sets', String(p)],
  baselines: (p) => ['baselines', String(p)],
  baselineNext: (p, bump) => ['baselines', String(p), 'next', bump],                    // under baselines(p)
  baselineDiff: (p, a, b, priced) => ['baselines', String(p), 'diff', String(a), String(b), Boolean(priced)],
  baseline: (id) => ['baseline', String(id)],
  baselineRows: (id, entity, offset) => ['baseline', String(id), 'rows', entity, offset],  // under baseline(id)
  importBatch: (id) => ['import-batch', String(id)],
  importPreview: (id) => ['import-batch', String(id), 'preview'],                     // under importBatch(id): a commit refreshes it
};
