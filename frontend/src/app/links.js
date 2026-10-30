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
  volume: (p) => `/p/${p}/volume`,                                   // D-67: as-is vs to-be time per area
  access: (p) => `/p/${p}/access`,
  organisation: (p) => `/p/${p}/organisation`,            // D-56: a rail item under Scope (was settings/organisation)
  parties: (p) => `/p/${p}/settings/parties`,
  stakeholders: (p) => `/p/${p}/settings/stakeholders`,              // slice 14
  issues: (p) => `/p/${p}/issues`,
  issue: (p, id) => `/p/${p}/issues/${id}`,
  waves: (p, tab) => (tab ? `/p/${p}/waves?tab=${tab}` : `/p/${p}/waves`),     // slice 15: "Wave" on screen (W-1)
  interfaces: (p) => `/p/${p}/interfaces`,
  reports: (p, tab) => (tab ? `/p/${p}/reports?tab=${tab}` : `/p/${p}/reports`),   // slice 1f
  control: (p) => `/p/${p}/control`,                                  // Control-A: the control panel
  rateCard: (p) => `/p/${p}/settings/rate-card`,
  codeLists: (p) => `/p/${p}/settings/code-lists`,                  // wave 1g
  effort: (p) => `/p/${p}/br-fr/effort`,
  applications: (p) => `/p/${p}/systems`,                // D-56: "Systems" in the rail (was settings/applications)
  application: (p, appId) => `/p/${p}/systems/${appId}`,
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
  memberCandidates: (p) => ['memberCandidates', String(p)],
  program: (g) => ['program', String(g)],
  programMembers: (g) => ['programMembers', String(g)],
  programMemberCandidates: (g) => ['programMemberCandidates', String(g)],
  codeLists: (p) => ['codeLists', String(p ?? 'company')],
  accessChange: (u, kind, admin) => ['accessChange', String(u), kind, String(admin)],
  // slice 16: every removal write invalidates both; a project's own reads are untouched (it is only frozen)
  purgeRequests: () => ['purgeRequests'],
  grantRequests: () => ['grantRequests'],              // slice 17; its writes also invalidate ['users']
  weeklyCheck: () => ['weeklyCheck'],                  // slice 16 U5: read only; the IS job writes
  archiveOverview: () => ['archiveOverview'],
  baselineArchive: (b) => ['baselineArchive', String(b)],
  // The tree read carries each process's DFD light (D-68, slice 13a). DR13-D2, one choice: there is no separate
  // readiness key — every writer of step I/O, external flows, trigger links, BR CRUD, step retire/restore,
  // make-process/demote and component toggles invalidates tree(p).
  tree: (p) => ['bfc-tree', String(p)],
  dfdRule: (p) => ['dfd-rule', String(p)],          // D-70: the chart rules; a save also invalidates tree(p) and flows(p)
  node: (id) => ['bfc-node', String(id)],
  retirePreview: (id) => ['retire-preview', String(id)],     // not under node(id): a retired node has no preview
  brs: (p) => ['brs', String(p)],
  br: (id) => ['br', String(id)],
  brLines: (id) => ['br', String(id), 'lines'],          // D-59: under br(id), so a BR refresh reloads them
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
  volumeSummary: (p) => ['volume-summary', String(p)],
  scopeSummary: (p) => ['scope-summary', String(p)],
  frTrace: () => ['fr-trace'],                                                       // FR panels on solution and BR pages
  brFrs: (brId) => ['fr-trace', 'br', String(brId)],                               // under frTrace(): a BR's FR links (D-52)
  frList: (p, filter = 'all', retired = false) => ['frs', String(p), { retired, filter }],    // under frs(p): one register view
  entities: (p) => ['entities', String(p)],
  entity: (id) => ['entity', String(id)],
  everyEntity: () => ['entity'],                                                     // every entity(id): an import of fields
  erd: (p, area) => ['entities', String(p), 'erd', String(area ?? 'project')],   // under entities(p): field edits refresh it
  parties: (p) => ['parties', String(p)],
  stakeholders: (p) => ['stakeholders', String(p)],
  issues: (p) => ['issues', String(p)],
  issue: (id) => ['issue', String(id)],
  issueBrs: (id) => ['issue', String(id), 'brs'],                                   // under issue(id)
  issueDashboard: (p) => ['issues', String(p), 'dashboard'],                         // under issues(p)
  phases: (p) => ['phases', String(p)],                                             // slice 15: the waves
  phasePlan: (p) => ['phases', String(p), 'plan'],                                  // under phases(p)
  phaseSplit: (solId) => ['phase-split', String(solId)],
  traceability: (p) => ['reports', String(p), 'traceability'],                       // slice 1f
  coverage: (p) => ['reports', String(p), 'coverage'],
  solutionMatrix: (p) => ['reports', String(p), 'solution-matrix'],
  applicationGap: (p, level) => ['reports', String(p), 'application-gap', String(level)],
  volatility: (p) => ['reports', String(p), 'requirement-volatility'],               // Control-B1
  dataMigration: (p) => ['reports', String(p), 'data-migration'],
  orgImpact: (p) => ['reports', String(p), 'org-impact'],                            // Control-B2
  engagement: (p) => ['reports', String(p), 'stakeholder-engagement'],
  changeIntensity: (p) => ['reports', String(p), 'change-intensity'],                // Control-C
  masterData: (p) => ['reports', String(p), 'master-data'],
  houseDefaults: () => ['control', 'house-defaults'],
  resetPreview: (p) => ['control', String(p), 'reset-preview'],
  controlPanel: (p) => ['control', String(p), 'panel'],                              // Control-A; a rule save
  controlRules: (p) => ['control', String(p), 'rules'],                              // invalidates ['control', p]
  solutionDeps: (solId) => ['solution-deps', String(solId)],
  allSolutionDeps: () => ['solution-deps'],                                         // every solutionDeps(id)
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
