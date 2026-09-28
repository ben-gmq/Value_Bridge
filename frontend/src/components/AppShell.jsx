import { useState } from 'react';
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, IconButton, Menu, MenuItem, Tooltip, Typography } from '@mui/material';
import { useColorScheme } from '@mui/material/styles';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import TuneIcon from '@mui/icons-material/Tune';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import { useAuth } from '../app/AuthContext';
import { api } from '../api/vb';
import { t } from '../i18n/t';

// §14.3: the seven-item navigation of the v9 boards. Sections not built yet land on a
// "coming in slice N" page, so the shell is final from day one.
export const NAV = [
  ['nav.dashboard', ''], ['nav.processes', 'processes'], ['nav.dfd', 'dfd'],
  ['nav.requirements', 'requirements'], ['nav.brfr', 'br-fr'], ['nav.interfaces', 'interfaces'],
  ['nav.data', 'data'],
];

const onFtc = (theme) => ({
  color: theme.vars.palette.brand.onFtc2,
  borderColor: theme.vars.palette.brand.onFtcLine,
});

function ScopeSelector() {
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
    <Box component="span" sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
      <Box component="span" sx={(th) => ({ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em',
        color: th.vars.palette.brand.onFtc3, lineHeight: 1.2 })}>{t('scope.label')}</Box>
      <Box component="span" sx={{ fontSize: 13.5, fontWeight: 700, color: 'brand.onFtc', lineHeight: 1.3 }}>{label}</Box>
    </Box>
  );
  // A single-project user never sees a menu with one item — just the name (§14.3).
  if (single) return <Box sx={{ px: 1.5 }}>{body}</Box>;
  return (
    <>
      <Button onClick={(e) => setAnchor(e.currentTarget)} aria-haspopup="menu"
        endIcon={<KeyboardArrowDownIcon sx={(th) => ({ color: th.vars.palette.brand.onFtc2 })} />}
        sx={(th) => ({ ...onFtc(th), border: '1px solid', borderRadius: '14px', px: 1.5, height: 40,
          bgcolor: th.vars.palette.brand.onFtcFill })}>{body}</Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {(programs.data ?? []).map((g) => (
          <MenuItem key={`g${g.program_id}`} component={RouterLink} to={`/g/${g.program_id}`}
            onClick={() => setAnchor(null)} sx={{ fontWeight: 700 }}>{t('scope.programSuffix', { name: g.program_name })}</MenuItem>
        ))}
        {list.map((p) => (
          <MenuItem key={p.project_id} component={RouterLink} to={`/p/${p.project_id}`}
            selected={String(p.project_id) === projectId} onClick={() => setAnchor(null)}>
            {p.project_code} · {p.project_name}
          </MenuItem>
        ))}
        {list.length === 0 && <MenuItem disabled>{t('scope.none')}</MenuItem>}
      </Menu>
    </>
  );
}

function Header() {
  const { me, isAdmin, signOut } = useAuth();
  const { projectId } = useParams();
  const { pathname } = useLocation();
  const { mode, setMode } = useColorScheme();
  const [anchor, setAnchor] = useState(null);
  const name = me?.user?.display_name ?? '';
  const initials = name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  const base = projectId ? `/p/${projectId}` : null;
  const section = base ? pathname.slice(base.length + 1).split('/')[0] : null;

  return (
    <Box component="header" sx={(th) => ({ height: 56, flexShrink: 0, px: 2.5, display: 'flex',
      alignItems: 'center', gap: 2.25, bgcolor: th.vars.palette.brand.ftc,
      borderBottom: `3px solid ${th.vars.palette.brand.ftcCyan}` })}>
      <Box component={RouterLink} to="/" sx={{ display: 'flex', alignItems: 'center', gap: 1.25, textDecoration: 'none' }}>
        <Box sx={(th) => ({ width: 28, height: 28, borderRadius: '14px', bgcolor: th.vars.palette.brand.onFtcPill,
          color: th.vars.palette.brand.ftc, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontWeight: 700, fontSize: 13.5 })}>VB</Box>
        <Typography sx={{ fontWeight: 700, fontSize: 16.5, color: 'brand.onFtc' }}>{t('app.name')}</Typography>
      </Box>
      <ScopeSelector />
      <Box component="nav" aria-label="Main" sx={{ display: 'flex', gap: 0.25 }}>
        {base && NAV.map(([key, path]) => {
          const active = section === path;
          return (
            <Box key={key} component={RouterLink} to={path ? `${base}/${path}` : base}
              aria-current={active ? 'page' : undefined}
              sx={(th) => ({ textDecoration: 'none', px: 1.5, py: 0.875, borderRadius: 999, fontSize: 14.5,
                fontWeight: active ? 600 : 500,
                color: active ? th.vars.palette.brand.ftc : th.vars.palette.brand.onFtc2,
                bgcolor: active ? th.vars.palette.brand.onFtcPill : 'transparent',
                '&:hover': { bgcolor: active ? th.vars.palette.brand.onFtcPill : th.vars.palette.brand.onFtcHover } })}>{t(key)}</Box>
          );
        })}
        {!base && isAdmin && (
          <Box component={RouterLink} to="/admin" aria-current={pathname.startsWith('/admin') ? 'page' : undefined}
            sx={(th) => ({ textDecoration: 'none', px: 1.5, py: 0.875, borderRadius: 999, fontSize: 14.5,
              fontWeight: 600, color: pathname.startsWith('/admin') ? th.vars.palette.brand.ftc : th.vars.palette.brand.onFtc2,
              bgcolor: pathname.startsWith('/admin') ? th.vars.palette.brand.onFtcPill : 'transparent' })}>{t('nav.admin')}</Box>
        )}
      </Box>
      <Box sx={{ flexGrow: 1 }} />
      <Tooltip title={mode === 'dark' ? t('theme.light') : t('theme.dark')}>
        <IconButton aria-label={mode === 'dark' ? t('theme.light') : t('theme.dark')}
          onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')}
          sx={(th) => ({ ...onFtc(th), border: '1px solid', width: 36, height: 36 })}>
          {mode === 'dark' ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
      {base && (
        <Tooltip title={t('nav.access')}>
          <IconButton component={RouterLink} to={`${base}/access`} aria-label={t('nav.access')}
            aria-current={section === 'access' ? 'page' : undefined}
            sx={(th) => ({ ...onFtc(th), border: '1px solid', width: 36, height: 36,
              bgcolor: section === 'access' ? th.vars.palette.brand.onFtcPill : th.vars.palette.brand.onFtcFill,
              color: section === 'access' ? th.vars.palette.brand.ftc : th.vars.palette.brand.onFtc })}>
            <TuneIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
      <Button onClick={(e) => setAnchor(e.currentTarget)} aria-haspopup="menu"
        sx={(th) => ({ color: th.vars.palette.brand.onFtc2, gap: 1, borderRadius: 999, px: 1 })}>
        <Box component="span" sx={(th) => ({ width: 28, height: 28, borderRadius: '50%',
          bgcolor: th.vars.palette.brand.ftcViolet, color: th.vars.palette.brand.onFtc, fontSize: 12.5, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center' })}>{initials}</Box>
        <Box component="span" sx={{ fontSize: 13.5, fontWeight: 500 }}>{name}</Box>
      </Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={signOut}>{t('signout')}</MenuItem>
      </Menu>
    </Box>
  );
}

function Footer() {
  return (
    <Box component="footer" sx={(th) => ({ height: 28, flexShrink: 0, px: 3, mt: 'auto',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      bgcolor: th.vars.palette.brand.ftc })}>
      <Typography sx={(th) => ({ fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', color: th.vars.palette.brand.onFtc3 })}>
        {t('footer.left')}</Typography>
      <Typography sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.onFtc2 })}>
        {t('footer.copyright', { year: new Date().getFullYear() })}</Typography>
    </Box>
  );
}

export function AppShell({ children }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Header />
      <Box component="main" sx={{ flexGrow: 1, px: 3, py: 3, maxWidth: 1440, width: '100%', mx: 'auto', boxSizing: 'border-box' }}>
        {children}
      </Box>
      <Footer />
    </Box>
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
