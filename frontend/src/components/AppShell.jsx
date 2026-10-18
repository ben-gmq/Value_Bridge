import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, ButtonBase, Drawer, IconButton, Menu, MenuItem, Tooltip, Typography, useMediaQuery } from '@mui/material';
import { useColorScheme, useTheme } from '@mui/material/styles';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import AdminPanelSettingsOutlined from '@mui/icons-material/AdminPanelSettingsOutlined';
import ChevronRightRounded from '@mui/icons-material/ChevronRightRounded';
import CorporateFareOutlined from '@mui/icons-material/CorporateFareOutlined';
import DnsOutlined from '@mui/icons-material/DnsOutlined';
import DarkModeOutlined from '@mui/icons-material/DarkModeOutlined';
import DashboardOutlined from '@mui/icons-material/DashboardOutlined';
import GroupOutlined from '@mui/icons-material/GroupOutlined';
import HomeOutlined from '@mui/icons-material/HomeOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';
import LayersOutlined from '@mui/icons-material/LayersOutlined';
import LightModeOutlined from '@mui/icons-material/LightModeOutlined';
import LightbulbOutlined from '@mui/icons-material/LightbulbOutlined';
import ReportProblemOutlined from '@mui/icons-material/ReportProblemOutlined';
import MenuRounded from '@mui/icons-material/MenuRounded';
import SettingsOutlined from '@mui/icons-material/SettingsOutlined';
import StorageOutlined from '@mui/icons-material/StorageOutlined';
import SyncAltOutlined from '@mui/icons-material/SyncAltOutlined';
import TimerOutlined from '@mui/icons-material/TimerOutlined';
import SpeedOutlined from '@mui/icons-material/SpeedOutlined';
import UnfoldMoreRounded from '@mui/icons-material/UnfoldMoreRounded';
import ViewQuiltOutlined from '@mui/icons-material/ViewQuiltOutlined';
import { useAuth } from '../app/AuthContext';
import { useComponents } from '../app/useComponents';
import { useCanAdmin } from '../app/useCanEdit';
import { keys } from '../app/links';
import { api } from '../api/vb';
import { baselineApi } from '../api/scope';
import { t } from '../i18n/t';

const RAIL_WIDTH = 248;

// D-51: the mockups' left rail, grouped Scope / Control / Admin. [i18n key, path under /p/:id, icon,
// components any one of which shows the item (D-37; none = always), admin only]. A path is matched by
// its longest prefix, so /br-fr/frs/12 is Function requirements and /br-fr/7 is Solutions.
export const NAV = [
  { group: 'nav.group.scope', items: [
    ['nav.dashboard', '', DashboardOutlined],
    ['nav.functions', 'processes', AccountTreeOutlined],
    ['nav.dfdLong', 'dfd', HubOutlined, ['TO_BE_DFD', 'AS_IS']],
    ['nav.entities', 'data', StorageOutlined],
    ['nav.solutions', 'br-fr', LightbulbOutlined, ['SOLUTION', 'FUNCTION_REQUIREMENT']],
    ['nav.frs', 'br-fr/frs', ViewQuiltOutlined, ['FUNCTION_REQUIREMENT']],
    ['nav.interfaces', 'interfaces', SyncAltOutlined, ['APPLICATION']],
    // D-56: the client's organisation and its systems, one click from the rail (they were Settings tabs)
    ['nav.organisation', 'organisation', CorporateFareOutlined],
    ['nav.systems', 'systems', DnsOutlined, ['APPLICATION']],
  ] },
  { group: 'nav.group.control', items: [
    ['nav.effort', 'br-fr/effort', TimerOutlined, ['EFFORT']],
    ['nav.volume', 'volume', SpeedOutlined],                              // D-67: as-is vs to-be time
    ['nav.baselines', 'baselines', LayersOutlined],
    ['nav.issues', 'issues', ReportProblemOutlined, ['ISSUE']],           // slice 14
  ] },
  { group: 'nav.group.admin', items: [
    ['nav.settings', 'settings', SettingsOutlined],
    ['nav.access', 'access', GroupOutlined, null, true],
  ] },
];
const ITEMS = NAV.flatMap((g) => g.items.map((i) => ({ group: g.group, key: i[0], path: i[1] })));
// Pages that belong to an item without a rail entry of their own. D-53: a business requirement is part
// of the function chart, so its deep link (requirements/:id) sits under Business functions.
const ALSO = { requirements: 'nav.functions' };

// The current section: the item whose path is the longest prefix of the route under /p/:id.
function sectionOf(rest) {
  const under = (path) => path && (rest === path || rest.startsWith(`${path}/`));
  const hits = ITEMS.filter((i) => under(i.path));
  if (!hits.length) {
    const alias = Object.keys(ALSO).find(under);
    if (alias) return ITEMS.find((i) => i.key === ALSO[alias]);
    return rest === '' ? ITEMS[0] : null;
  }
  return hits.reduce((a, b) => (b.path.length > a.path.length ? b : a));
}

// Pages name their own last crumb (an item's code and name) through <Page crumb=…>.
const CrumbContext = createContext({ crumb: null, setCrumb: () => {} });
export function usePageCrumb(crumb) {
  const { setCrumb } = useContext(CrumbContext);
  useEffect(() => { setCrumb(crumb ?? null); return () => setCrumb(null); }, [crumb, setCrumb]);
}

function RailLink({ to, icon: Icon, label, active, onNavigate }) {
  return (
    <Box component={RouterLink} to={to} onClick={onNavigate} aria-current={active ? 'page' : undefined}
      sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.25, minHeight: 36, borderRadius: 999,
        textDecoration: 'none', fontSize: 13.5, fontWeight: active ? 700 : 500,
        color: active ? th.vars.palette.brand.ftc : th.vars.palette.brand.onFtc2,
        bgcolor: active ? th.vars.palette.brand.onFtcPill : 'transparent',
        '&:hover': { bgcolor: active ? th.vars.palette.brand.onFtcPill : th.vars.palette.brand.onFtcHover },
        '&:focus-visible': { outline: `2px solid ${th.vars.palette.brand.ftcCyan}`, outlineOffset: 2 } })}>
      <Icon sx={(th) => ({ fontSize: 18, color: active ? th.vars.palette.brand.ftcViolet : th.vars.palette.brand.onFtc3 })} />
      {label}
    </Box>
  );
}

function ScopeSelector({ onNavigate }) {
  const { projectId, programId } = useParams();
  const [anchor, setAnchor] = useState(null);
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects });
  const programs = useQuery({ queryKey: ['programs'], queryFn: api.programs });
  const list = projects.data ?? [];
  const current = list.find((p) => String(p.project_id) === projectId);
  const currentProgram = (programs.data ?? []).find((g) => String(g.program_id) === programId);
  const label = current?.project_name ?? currentProgram?.program_name ?? t('scope.choose');
  const single = list.length === 1 && (programs.data ?? []).length === 0;
  const body = (
    <Box sx={{ flexGrow: 1, minWidth: 0, textAlign: 'left' }}>
      <Typography sx={(th) => ({ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', color: th.vars.palette.brand.onFtc3 })}>
        {t('scope.label')}</Typography>
      <Typography noWrap sx={(th) => ({ fontSize: 13.5, fontWeight: 600, color: th.vars.palette.brand.onFtc })}>{label}</Typography>
    </Box>
  );
  const box = (th) => ({ width: '100%', borderRadius: '14px', bgcolor: th.vars.palette.brand.onFtcFill, px: 1.5, py: 1,
    display: 'flex', alignItems: 'center', gap: 1 });
  // A single-project user never sees a menu with one item — just the name (§14.3).
  if (single) return <Box sx={box}>{body}</Box>;
  const close = () => { setAnchor(null); onNavigate?.(); };
  return (
    <>
      <ButtonBase onClick={(e) => setAnchor(e.currentTarget)} aria-haspopup="menu" sx={(th) => ({ ...box(th),
        '&:focus-visible': { outline: `2px solid ${th.vars.palette.brand.ftcCyan}` } })}>
        {body}<UnfoldMoreRounded sx={(th) => ({ fontSize: 18, color: th.vars.palette.brand.onFtc3 })} />
      </ButtonBase>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {(programs.data ?? []).map((g) => (
          <MenuItem key={`g${g.program_id}`} component={RouterLink} to={`/g/${g.program_id}`} onClick={close}
            sx={{ fontWeight: 700 }}>{t('scope.programSuffix', { name: g.program_name })}</MenuItem>
        ))}
        {list.map((p) => (
          <MenuItem key={p.project_id} component={RouterLink} to={`/p/${p.project_id}`}
            selected={String(p.project_id) === projectId} onClick={close}>{p.project_code} · {p.project_name}</MenuItem>
        ))}
        {list.length === 0 && <MenuItem disabled>{t('scope.none')}</MenuItem>}
      </Menu>
    </>
  );
}

function UserBlock() {
  const { me, isAdmin, signOut } = useAuth();
  const { mode, setMode } = useColorScheme();
  const [anchor, setAnchor] = useState(null);
  const name = me?.user?.display_name ?? '';
  const initials = name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  const kind = isAdmin ? t('user.kind.ADMIN') : t(`user.kind.${me?.user?.user_kind ?? 'USER'}`);
  return (
    <>
      <ButtonBase onClick={(e) => setAnchor(e.currentTarget)} aria-haspopup="menu"
        sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 1.25, px: 1, pt: 1.5, width: '100%', justifyContent: 'flex-start',
          borderTop: `1px solid ${th.vars.palette.brand.onFtcLine}`, textAlign: 'left' })}>
        <Box sx={(th) => ({ width: 32, height: 32, borderRadius: '50%', flexShrink: 0, bgcolor: th.vars.palette.brand.ftcViolet,
          color: th.vars.palette.brand.onFtc, fontSize: 12.5, fontWeight: 700, display: 'grid', placeItems: 'center' })}>{initials}</Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography noWrap sx={(th) => ({ fontSize: 13.5, fontWeight: 600, color: th.vars.palette.brand.onFtc })}>{name}</Typography>
          <Typography noWrap sx={(th) => ({ fontSize: 12, color: th.vars.palette.brand.onFtc3 })}>{kind} · FTC</Typography>
        </Box>
      </ButtonBase>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'top', horizontal: 'left' }} transformOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <MenuItem onClick={() => { setMode(mode === 'dark' ? 'light' : 'dark'); setAnchor(null); }}>
          {mode === 'dark' ? t('theme.light') : t('theme.dark')}</MenuItem>
        <MenuItem onClick={signOut}>{t('signout')}</MenuItem>
      </Menu>
    </>
  );
}

function Rail({ onNavigate }) {
  const { isAdmin } = useAuth();
  const canAdmin = useCanAdmin();     // the project's Access item: project admins too (D-71)
  const { projectId } = useParams();
  const { pathname } = useLocation();
  const { anyOn } = useComponents(projectId);
  const base = projectId ? `/p/${projectId}` : null;
  const current = base ? sectionOf(pathname.slice(base.length + 1)) : null;
  return (
    <Box component="nav" aria-label="Main" sx={(th) => ({ width: RAIL_WIDTH, flexShrink: 0, minHeight: '100%',
      bgcolor: th.vars.palette.brand.ftc, display: 'flex', flexDirection: 'column', px: 1.75, py: 2, gap: 2, boxSizing: 'border-box' })}>
      <Box component={RouterLink} to="/" onClick={onNavigate} sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1, textDecoration: 'none' }}>
        <Box sx={(th) => ({ width: 32, height: 32, borderRadius: '10px', bgcolor: th.vars.palette.brand.onFtcPill,
          color: th.vars.palette.brand.ftc, display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 13 })}>VB</Box>
        <Typography sx={(th) => ({ fontWeight: 700, fontSize: 16, color: th.vars.palette.brand.onFtc })}>{t('app.name')}</Typography>
      </Box>
      <ScopeSelector onNavigate={onNavigate} />
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.75, flexGrow: 1 }}>
        {base ? NAV.map((g) => {
          const items = g.items.filter(([, , , need, adminOnly]) => (!need || anyOn(...need)) && (!adminOnly || canAdmin));
          if (!items.length) return null;
          return (
            <Box key={g.group} sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
              <Typography sx={(th) => ({ fontSize: 11.5, fontWeight: 600, letterSpacing: '0.06em', color: th.vars.palette.brand.onFtc3, px: 1.25, pb: 0.5 })}>
                {t(g.group).toUpperCase()}</Typography>
              {items.map(([key, path, icon]) => (
                <RailLink key={key} to={path ? `${base}/${path}` : base} icon={icon} label={t(key)}
                  active={current?.key === key} onNavigate={onNavigate} />
              ))}
            </Box>
          );
        }) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            <RailLink to="/" icon={HomeOutlined} label={t('nav.home')} active={pathname === '/'} onNavigate={onNavigate} />
            {isAdmin && <RailLink to="/admin" icon={AdminPanelSettingsOutlined} label={t('nav.admin')}
              active={pathname.startsWith('/admin')} onNavigate={onNavigate} />}
          </Box>
        )}
      </Box>
      <UserBlock />
    </Box>
  );
}

// "Working · after v1.2" — the open project's position against its latest baseline (D-51, mockups).
function VersionChip() {
  const { projectId, baselineId } = useParams();
  const q = useQuery({ queryKey: keys.baselines(projectId), queryFn: () => baselineApi.list(projectId),
    enabled: Boolean(projectId) });
  if (!projectId || !q.data) return null;
  const viewing = baselineId && q.data.find((b) => String(b.baseline_id) === String(baselineId));
  const label = viewing ? t('shell.viewing', { label: viewing.version_label })
    : q.data[0] ? t('shell.working', { label: q.data[0].version_label }) : t('shell.workingNone');
  return (
    <Box component={RouterLink} to={`/p/${projectId}/baselines`}
      sx={(th) => ({ display: 'inline-flex', alignItems: 'center', gap: 1, height: 30, px: 1.5, borderRadius: 999,
        textDecoration: 'none', whiteSpace: 'nowrap', fontSize: 13, fontWeight: 600,
        bgcolor: th.vars.palette.brand.purpleTint, color: th.vars.palette.brand.purpleText })}>
      <Box component="span" sx={(th) => ({ width: 7, height: 7, borderRadius: '50%', bgcolor: th.vars.palette.brand.purpleText })} />
      {label}
    </Box>
  );
}

function Header({ onMenu, narrow }) {
  const { projectId } = useParams();
  const { pathname } = useLocation();
  const { crumb } = useContext(CrumbContext);
  const { mode, setMode } = useColorScheme();
  const base = projectId ? `/p/${projectId}` : null;
  const current = base ? sectionOf(pathname.slice(base.length + 1)) : null;
  const crumbs = [];
  if (current) {
    crumbs.push({ label: t(current.group) });
    const atSection = pathname === (current.path ? `${base}/${current.path}` : base);
    crumbs.push({ label: t(current.key), to: atSection && !crumb ? null : (current.path ? `${base}/${current.path}` : base) });
  } else if (pathname.startsWith('/admin')) crumbs.push({ label: t('nav.admin') });
  else if (pathname === '/') crumbs.push({ label: t('nav.home') });
  if (crumb) crumbs.push({ label: crumb });
  return (
    <Box component="header" sx={(th) => ({ minHeight: 56, flexShrink: 0, px: { xs: 2, md: 3 }, display: 'flex', alignItems: 'center',
      gap: 2, borderBottom: `1px solid ${th.vars.palette.divider}` })}>
      {narrow && <IconButton onClick={onMenu} aria-label={t('shell.menu')} edge="start"><MenuRounded /></IconButton>}
      <Box component="ol" aria-label={t('shell.breadcrumb')} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, m: 0, p: 0,
        listStyle: 'none', minWidth: 0, flexWrap: 'wrap' }}>
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <Box component="li" key={`${c.label}-${i}`} sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 0.5, fontSize: 13.5,
              color: last ? th.vars.palette.text.primary : th.vars.palette.brand.muted, fontWeight: last ? 600 : 400, minWidth: 0 })}>
              {i > 0 && <ChevronRightRounded sx={(th) => ({ fontSize: 16, color: th.vars.palette.brand.muted })} />}
              {c.to && !last
                ? <Box component={RouterLink} to={c.to} sx={{ color: 'inherit', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}>{c.label}</Box>
                : <Box component="span" aria-current={last ? 'page' : undefined} sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.label}</Box>}
            </Box>
          );
        })}
      </Box>
      <Box sx={{ flexGrow: 1 }} />
      <VersionChip />
      <Tooltip title={mode === 'dark' ? t('theme.light') : t('theme.dark')}>
        <IconButton aria-label={mode === 'dark' ? t('theme.light') : t('theme.dark')} size="small"
          onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')}>
          {mode === 'dark' ? <LightModeOutlined fontSize="small" /> : <DarkModeOutlined fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );
}

function Footer() {
  return (
    <Box component="footer" sx={(th) => ({ minHeight: 34, flexShrink: 0, px: { xs: 2, md: 3 }, display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', borderTop: `1px solid ${th.vars.palette.divider}`,
      fontSize: 12, color: th.vars.palette.brand.muted })}>
      <Box component="span" sx={{ fontWeight: 600, letterSpacing: '0.04em' }}>{t('footer.left')}</Box>
      <Box component="span">{t('footer.copyright', { year: new Date().getFullYear() })}</Box>
    </Box>
  );
}

export function AppShell({ children }) {
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const [open, setOpen] = useState(false);
  const [crumb, setCrumb] = useState(null);
  const ctx = useMemo(() => ({ crumb, setCrumb }), [crumb]);
  return (
    <CrumbContext.Provider value={ctx}>
      <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
        {narrow ? (
          <Drawer open={open} onClose={() => setOpen(false)} slotProps={{ paper: { sx: { border: 0 } } }}>
            <Rail onNavigate={() => setOpen(false)} />
          </Drawer>
        ) : (
          <Box sx={{ position: 'sticky', top: 0, height: '100vh', overflowY: 'auto', flexShrink: 0 }}><Rail /></Box>
        )}
        <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Header narrow={narrow} onMenu={() => setOpen(true)} />
          <Box component="main" sx={{ flexGrow: 1, px: { xs: 2, md: 3 }, pt: 2.5, pb: 3, width: '100%', maxWidth: 1600,
            boxSizing: 'border-box', minWidth: 0 }}>
            {children}
          </Box>
          <Footer />
        </Box>
      </Box>
    </CrumbContext.Provider>
  );
}

// Pages outside the shell (login, setup) still carry the footer (playbook §8).
export function BareShell({ children }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box component="main" sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}>
        {children}
      </Box>
      <Footer />
    </Box>
  );
}
