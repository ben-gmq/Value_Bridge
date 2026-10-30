import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, FormControl, FormControlLabel, InputLabel, MenuItem, Select, Snackbar,
  Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { api } from '../../api/vb';
import { keys, links } from '../../app/links';
import { errorText } from '../../api/client';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card } from '../../components/kit';
import { Page } from '../../components/Page';
import { ControlDefaultsTab } from '../control/ControlDefaultsTab';
import { CodeListsView } from '../settings/CodeListsPage';
import { RemovalsTab } from './RemovalsTab';
import { PendingGrants, RequestGrantDialog } from './GrantRequests';
import { t } from '../../i18n/t';

function useSave(fn, keys, onOk) {
  const qc = useQueryClient();
  const [error, setError] = useState('');
  const m = useMutation({ mutationFn: fn,
    onSuccess: (res) => { keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] })); setError(''); onOk?.(res); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))) });
  return { m, error, setError };
}

// D-71 (design-auditor M1): what a change of kind or admin flag brings back into force. The server recomputes it
// under a lock and refuses the change unless the hash matches what was shown here.
function useComesBack(user, kind, admin) {
  return useQuery({ queryKey: keys.accessChange(user?.app_user_id, kind, admin),
    queryFn: () => api.accessChangePreview(user.app_user_id, { user_kind: kind, is_platform_admin: admin }),
    enabled: Boolean(user && kind), staleTime: 0, gcTime: 0 });
}

function ComesBack({ q }) {
  if (!q.data) return null;
  const level = (l) => (l ? t(`access.level.${l}`) : t('admin.comesBackUnread'));
  if (q.data.comes_back.length === 0) return <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('admin.comesBackNone')}</Typography>;
  return (
    <Alert severity="warning" sx={{ mt: 1 }}>
      <Typography sx={{ fontSize: 13.5, mb: 0.5 }}>{t('admin.comesBack')}</Typography>
      {q.data.comes_back.map((r) => (
        <Typography key={r.project_id} sx={{ fontSize: 13.5 }}>
          {t('admin.comesBackRow', { code: r.project_code, name: r.project_name, before: level(r.level_before), after: level(r.level_after) })}
        </Typography>))}
    </Alert>
  );
}

const grid = { autoHeight: true, disableRowSelectionOnClick: true, sx: { bgcolor: 'background.paper', border: 0, borderRadius: 0 } };

// D-51 kit look: the create form and the list each sit in a card.
function FormRow({ children }) {
  return (
    <Card sx={{ mb: 2, mt: 2 }} bodySx={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>{children}</Card>
  );
}

function GridCard(props) {
  return <Card bodySx={{ px: 0, pb: 0, pt: 0.5 }}><DataGrid {...props} /></Card>;
}

function ClientSelect({ id, value, onChange, clients }) {
  return (
    <FormControl size="small" sx={{ minWidth: 200 }}>
      <InputLabel id={`${id}-label`}>{t('admin.client')}</InputLabel>
      <Select labelId={`${id}-label`} id={id} label={t('admin.client')}
        value={clients.some((c) => c.client_id === value) ? value : ''} onChange={(e) => onChange(e.target.value)}>
        {clients.map((c) => <MenuItem key={c.client_id} value={c.client_id}>{c.client_name}</MenuItem>)}
      </Select>
    </FormControl>
  );
}

function Users({ notify }) {
  const users = useQuery({ queryKey: ['users'], queryFn: api.users });
  const empty = { email: '', display_name: '', initial_password: '', user_kind: '' };
  const [f, setF] = useState(empty);
  const [deact, setDeact] = useState(null);
  const [adminChange, setAdminChange] = useState(null);
  const [reason, setReason] = useState('');
  const [fallbackKind, setFallbackKind] = useState('VIEWER');
  const create = useSave(() => api.createUser(f), ['users'], () => { setF(empty); notify(t('admin.userCreated')); });
  const deactivate = useSave((id) => api.deactivateUser(id), ['users'], () => { setDeact(null); notify(t('admin.deactivated')); });
  const removing = Boolean(adminChange?.is_platform_admin);
  const adminBack = useComesBack(removing ? adminChange : null, fallbackKind, false);
  const setAdmin = useSave((u) => api.setPlatformAdmin(u.app_user_id, {
    is_platform_admin: !u.is_platform_admin, rationale: reason, row_version: u.row_version,
    user_kind: u.is_platform_admin ? fallbackKind : null, confirm_hash: adminBack.data?.confirm_hash ?? null }),
  ['users'], () => { setAdminChange(null); setReason(''); notify(t('admin.adminChanged')); });
  const [grantFor, setGrantFor] = useState(null);
  const [kindChange, setKindChange] = useState(null);
  const kindBack = useComesBack(kindChange, 'USER', false);
  const setKind = useSave((u) => api.setUserKind(u.app_user_id, {
    user_kind: u.user_kind === 'USER' ? 'VIEWER' : 'USER', row_version: u.row_version,
    confirm_hash: u === kindChange ? kindBack.data?.confirm_hash ?? null : null }),
  ['users'], () => { setKindChange(null); notify(t('admin.kindChanged')); });
  const error = create.error || deactivate.error || setAdmin.error || setKind.error;
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <FormRow>
        <TextField id="u-name" label={t('admin.name')} value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} />
        <TextField id="u-email" label={t('admin.email')} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <TextField id="u-pw" label={t('admin.initialPassword')} type="password" value={f.initial_password}
          onChange={(e) => setF({ ...f, initial_password: e.target.value })} />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="u-kind-label">{t('admin.kind')}</InputLabel>
          <Select labelId="u-kind-label" id="u-kind" label={t('admin.kind')} value={f.user_kind}
            onChange={(e) => setF({ ...f, user_kind: e.target.value })}>
            {['USER', 'VIEWER'].map((k) => <MenuItem key={k} value={k}>{t(`admin.kind.${k}`)}</MenuItem>)}
          </Select>
        </FormControl>
        <Button variant="contained" disabled={create.m.isPending || !f.user_kind} onClick={() => create.m.mutate()}>{t('admin.createUser')}</Button>
      </FormRow>
      <PendingGrants notify={notify} />
      <RequestGrantDialog key={grantFor?.app_user_id ?? 'none'} user={grantFor} onClose={() => setGrantFor(null)}
        notify={notify} />
      <GridCard {...grid} rows={users.data ?? []} getRowId={(r) => r.app_user_id}
        columns={[
          { field: 'app_user_id', headerName: t('admin.id'), width: 70 },
          { field: 'display_name', headerName: t('admin.name'), flex: 1 },
          { field: 'email', headerName: t('admin.email'), flex: 1 },
          { field: 'is_platform_admin', headerName: t('admin.isAdmin'), width: 90, type: 'boolean' },
          { field: 'user_kind', headerName: t('admin.kind'), width: 110,
            valueGetter: (v, row) => (row.is_platform_admin ? t('admin.kind.ADMIN') : t(`admin.kind.${v}`)) },
          { field: 'is_active', headerName: t('admin.active'), width: 90, type: 'boolean' },
          { field: 'x', headerName: '', width: 360, sortable: false, renderCell: ({ row }) => row.is_active && (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', height: '100%' }}>
              {!row.is_platform_admin && (
                <Button size="small" disabled={setKind.m.isPending}
                  onClick={() => (row.user_kind === 'USER' ? setKind.m.mutate(row) : setKindChange(row))}>
                  {row.user_kind === 'USER' ? t('admin.makeViewer') : t('admin.makeUser')}</Button>)}
              {row.is_platform_admin ? (
                <Button size="small" onClick={() => { setAdmin.setError(''); setAdminChange(row); }}>
                  {t('admin.removeAdmin')}</Button>
              ) : (                                              // slice 17: a request a second admin decides
                <Button size="small" onClick={() => setGrantFor(row)}>{t('grants.request')}</Button>)}
              <Button size="small" color="warning" onClick={() => setDeact(row)}>{t('admin.deactivate')}</Button>
            </Stack>) },
        ]} />
      <ConfirmDialog open={Boolean(deact)} title={t('admin.deactivateTitle')}
        body={t('admin.deactivateBody', { name: deact?.display_name })} confirmLabel={t('admin.deactivate')}
        busy={deactivate.m.isPending} onClose={() => setDeact(null)} onConfirm={() => deactivate.m.mutate(deact.app_user_id)} />
      {/* sara 7b L10: VIEWER → USER grants edit on every project open to all staff — confirm it. */}
      <ConfirmDialog open={Boolean(kindChange)} title={t('admin.makeUserTitle')}
        body={t('admin.makeUserBody', { name: kindChange?.display_name })} confirmLabel={t('admin.makeUser')}
        busy={setKind.m.isPending || !kindBack.data} onClose={() => setKindChange(null)}
        onConfirm={() => setKind.m.mutate(kindChange)}>
        <ComesBack q={kindBack} />
      </ConfirmDialog>
      <ConfirmDialog open={Boolean(adminChange)} title={t('admin.adminTitle')}
        body={t(adminChange?.is_platform_admin ? 'admin.adminBodyRemove' : 'admin.adminBodyGrant', { name: adminChange?.display_name })}
        confirmLabel={adminChange?.is_platform_admin ? t('admin.removeAdmin') : t('admin.makeAdmin')}
        busy={setAdmin.m.isPending || !reason.trim() || (removing && !adminBack.data)}
        onClose={() => { setAdminChange(null); setReason(''); }}
        onConfirm={() => setAdmin.m.mutate(adminChange)}>
        <TextField id="admin-reason" label={t('admin.reason')} value={reason} onChange={(e) => setReason(e.target.value)}
          fullWidth multiline minRows={2} />
        {adminChange?.is_platform_admin && (
          <FormControl size="small" fullWidth sx={{ mt: 2 }}>
            <InputLabel id="admin-fallback-label">{t('admin.becomes')}</InputLabel>
            <Select labelId="admin-fallback-label" id="admin-fallback" label={t('admin.becomes')} value={fallbackKind}
              onChange={(e) => setFallbackKind(e.target.value)}>
              {['USER', 'VIEWER'].map((k) => <MenuItem key={k} value={k}>{t(`admin.kind.${k}`)}</MenuItem>)}
            </Select>
          </FormControl>)}
        {removing && <Box sx={{ mt: 2 }}><ComesBack q={adminBack} /></Box>}
      </ConfirmDialog>
    </>
  );
}

function Clients({ notify }) {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const empty = { client_code: '', client_name: '', industry: '' };
  const [f, setF] = useState(empty);
  const { m, error } = useSave(() => api.createClient(f), ['clients'], () => { setF(empty); notify(t('admin.clientCreated')); });
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <FormRow>
        <TextField id="c-code" label={t('admin.clientCode')} value={f.client_code} onChange={(e) => setF({ ...f, client_code: e.target.value })} />
        <TextField id="c-name" label={t('admin.clientName')} value={f.client_name} onChange={(e) => setF({ ...f, client_name: e.target.value })} />
        <TextField id="c-ind" label={t('admin.industry')} value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} />
        <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('admin.createClient')}</Button>
      </FormRow>
      <GridCard {...grid} rows={clients.data ?? []} getRowId={(r) => r.client_id}
        columns={[{ field: 'client_code', headerName: t('admin.code'), width: 140 },
                  { field: 'client_name', headerName: t('admin.name'), flex: 1 },
                  { field: 'industry', headerName: t('admin.industry'), flex: 1 }]} />
    </>
  );
}

function Programs({ notify }) {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const empty = { client_id: '', program_code: '', program_name: '' };
  const [f, setF] = useState(empty);
  const { m, error } = useSave(() => api.createProgram(f), ['programs'], () => { setF(empty); notify(t('admin.programCreated')); });
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <FormRow>
        <ClientSelect id="g-client" value={f.client_id} onChange={(v) => setF({ ...f, client_id: v })} clients={clients.data ?? []} />
        <TextField id="g-code" label={t('admin.programCode')} value={f.program_code} onChange={(e) => setF({ ...f, program_code: e.target.value })} />
        <TextField id="g-name" label={t('admin.programName')} value={f.program_name} onChange={(e) => setF({ ...f, program_name: e.target.value })} />
        <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('admin.createProgram')}</Button>
      </FormRow>
      <GridCard {...grid} rows={programs.data ?? []} getRowId={(r) => r.program_id}
        columns={[{ field: 'program_code', headerName: t('admin.code'), width: 140 },
                  { field: 'program_name', headerName: t('admin.name'), flex: 1 }]} />
    </>
  );
}

// Everything a chosen component needs, transitively (OR-2). The server refuses a list that is not
// closed, so the form sends the closure and says what it added — nothing is added silently.
function closure(codes, catalogue) {
  const needs = Object.fromEntries(catalogue.map((c) => [c.code, c.requires]));
  const out = new Set();
  const todo = [...codes];
  while (todo.length) {
    const c = todo.pop();
    if (!out.has(c)) { out.add(c); todo.push(...(needs[c] ?? [])); }
  }
  return out;
}

// D-37 / OR-3: a template pre-fills the components; any combination may follow.
function ComponentPicker({ f, setF, catalogue, templates }) {
  const chosen = new Set(f.component_codes);
  const added = [...closure(chosen, catalogue)].filter((c) => !chosen.has(c));
  const label = (code) => catalogue.find((c) => c.code === code)?.label ?? code;
  const toggle = (code) => setF({ ...f, component_codes: chosen.has(code)
    ? f.component_codes.filter((c) => c !== code) : [...f.component_codes, code] });
  return (
    <Box sx={{ width: '100%' }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'center', mb: 1 }}>
        <FormControl size="small" sx={{ minWidth: 240 }}>
          <InputLabel id="p-tpl-label">{t('components.template')}</InputLabel>
          <Select labelId="p-tpl-label" id="p-tpl" label={t('components.template')} value={f.template_code}
            onChange={(e) => { const code = e.target.value;
              const tpl = templates.find((x) => x.code === code);
              setF({ ...f, template_code: code, component_codes: tpl ? [...tpl.components] : f.component_codes }); }}>
            <MenuItem value="">{t('components.templateNone')}</MenuItem>
            {templates.map((x) => <MenuItem key={x.code} value={x.code}>{x.label}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 280 }}>
          <InputLabel id="p-depth-label">{t('components.depthTitle')}</InputLabel>
          <Select labelId="p-depth-label" id="p-depth" label={t('components.depthTitle')} value={f.data_model_depth}
            onChange={(e) => setF({ ...f, data_model_depth: e.target.value })}>
            {['FULL', 'KEYS_ONLY'].map((v) => <MenuItem key={v} value={v}>{t(`components.depth.${v}`)}</MenuItem>)}
          </Select>
        </FormControl>
      </Stack>
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>{t('components.pick')}</Typography>
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap' }}>
        {catalogue.map((c) => (
          <FormControlLabel key={c.code} label={c.label}
            control={<Checkbox size="small" checked={chosen.has(c.code) || added.includes(c.code)}
              disabled={added.includes(c.code)} onChange={() => toggle(c.code)} />} />
        ))}
      </Stack>
      {added.length > 0 && <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('components.added', { list: added.map(label).join(', ') })}</Typography>}
    </Box>
  );
}

function Projects({ notify }) {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects });
  const catalogue = useQuery({ queryKey: keys.componentCatalogue(), queryFn: api.componentCatalogue });
  const templates = useQuery({ queryKey: keys.projectTemplates(), queryFn: api.projectTemplates });
  const empty = { client_id: '', project_code: '', project_name: '', program_id: '', template_code: '',
    component_codes: [], data_model_depth: 'FULL', is_restricted: 'yes' };   // D-62: assigned consultants only
  const [f, setF] = useState(empty);
  const [retiring, setRetiring] = useState(null);
  const navigate = useNavigate();
  const { m, error } = useSave(() => api.createProject({ ...f, program_id: f.program_id || null,
    is_restricted: f.is_restricted === 'yes',
    template_code: f.template_code || null,
    component_codes: [...closure(f.component_codes, catalogue.data ?? [])] }), ['projects'],
  // DR10c-P3: a restricted project starts with no members, so the admin lands on its Access screen to add them.
  (res) => { setF(empty); notify(t('admin.projectCreated'));
    if (res?.project_id) navigate(links.access(res.project_id), { state: { created: true } }); });
  const progs = (programs.data ?? []).filter((g) => g.client_id === f.client_id);
  const programCode = (id) => (programs.data ?? []).find((g) => g.program_id === id)?.program_code ?? '';
  return (
    <>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <FormRow>
        <ClientSelect id="p-client" value={f.client_id} onChange={(v) => setF({ ...f, client_id: v, program_id: '' })} clients={clients.data ?? []} />
        <TextField id="p-code" label={t('admin.projectCode')} value={f.project_code} onChange={(e) => setF({ ...f, project_code: e.target.value })} />
        <TextField id="p-name" label={t('admin.projectName')} value={f.project_name} onChange={(e) => setF({ ...f, project_name: e.target.value })} />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="p-prog-label">{t('admin.programOptional')}</InputLabel>
          <Select labelId="p-prog-label" id="p-prog" label={t('admin.programOptional')}
            value={progs.some((g) => g.program_id === f.program_id) ? f.program_id : ''}
            onChange={(e) => setF({ ...f, program_id: e.target.value })}>
            <MenuItem value="">{t('common.none')}</MenuItem>
            {progs.map((g) => <MenuItem key={g.program_id} value={g.program_id}>{g.program_name}</MenuItem>)}
          </Select>
        </FormControl>
        <ComponentPicker f={f} setF={setF} catalogue={catalogue.data ?? []} templates={templates.data ?? []} />
        {/* D-62: preselected "Assigned consultants only"; the API still requires the choice explicitly (§8.10 risk 1). */}
        <FormControl size="small" sx={{ minWidth: 260 }}>
          <InputLabel id="p-restricted-label">{t('admin.restricted')}</InputLabel>
          <Select labelId="p-restricted-label" id="p-restricted" label={t('admin.restricted')} value={f.is_restricted}
            onChange={(e) => setF({ ...f, is_restricted: e.target.value })}>
            <MenuItem value="yes">{t('admin.restricted.yes')}</MenuItem>
            <MenuItem value="no">{t('admin.restricted.no')}</MenuItem>
          </Select>
        </FormControl>
        <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate()}>{t('admin.createProject')}</Button>
      </FormRow>
      <GridCard {...grid} rows={projects.data ?? []} getRowId={(r) => r.project_id}
        columns={[{ field: 'project_code', headerName: t('admin.code'), width: 140 },
                  { field: 'project_name', headerName: t('admin.name'), flex: 1 },
                  { field: 'program_id', headerName: t('admin.program'), width: 140, valueGetter: (v) => programCode(v) },
                  { field: 'closed_on', headerName: t('admin.closedOn'), width: 130, valueGetter: (v) => v ?? '' },
                  { field: 'x', headerName: '', width: 110, sortable: false, renderCell: ({ row }) => (
                    <Button size="small" color="warning" onClick={() => setRetiring(row)}>{t('admin.retire')}</Button>) }]} />
      <RetireProject project={retiring} onClose={() => setRetiring(null)} notify={notify} />
    </>
  );
}

// Slice 16 (AR-10, Q-90): retiring closes the project first (its archive clock starts), then retires it.
function RetireProject({ project, onClose, notify }) {
  const [typed, setTyped] = useState('');
  const { m, error, setError } = useSave((p) => api.retireProject(p.project_id, {
    confirm_text: typed.trim(), row_version: p.row_version }), ['projects'],
  () => { setTyped(''); onClose(); notify(t('admin.retired')); });
  if (!project) return null;
  return (
    <ConfirmDialog open title={t('admin.retireTitle', { code: project.project_code })}
      body={t(project.closed_on ? 'admin.retireBodyClosed' : 'admin.retireBodyOpen', { date: project.closed_on })}
      confirmLabel={t('admin.retire')} busy={m.isPending || typed.trim() !== project.project_code}
      onClose={() => { setTyped(''); setError(''); onClose(); }} onConfirm={() => m.mutate(project)}>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TextField id="retire-confirm" label={t('admin.retireConfirm', { code: project.project_code })} value={typed}
        onChange={(e) => setTyped(e.target.value)} fullWidth />
    </ConfirmDialog>
  );
}

function CompanyCodeLists() {
  return <Box sx={{ mt: 2 }}><CodeListsView /></Box>;
}

const TABS = [['admin.users', Users], ['admin.clients', Clients], ['admin.programs', Programs], ['admin.projects', Projects],
  ['admin.codeLists', CompanyCodeLists], ['control.house.tab', ControlDefaultsTab], ['removals.tab', RemovalsTab]];

// 0079 (Ben 2026-10-24): while this installation lets one admin approve alone, every admin page says so.
function SingleOwnerBanner() {
  const overview = useQuery({ queryKey: keys.archiveOverview(), queryFn: api.archiveOverview });
  if (overview.data?.approvers_required !== 1) return null;
  return <Alert severity="warning" sx={{ mb: 2 }}>{t('admin.singleOwner')}</Alert>;
}

export default function AdminPage() {
  const [tab, setTab] = useState(0);
  const [notice, setNotice] = useState('');
  const Body = TABS[tab][1];
  return (
    <Page title={t('admin.title')} subtitle={t('admin.subtitle')}>
      <SingleOwnerBanner />
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 1 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label={t('admin.tabs')}>
          {TABS.map(([key]) => <Tab key={key} label={t(key)} />)}
        </Tabs>
      </Box>
      <Body notify={setNotice} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
