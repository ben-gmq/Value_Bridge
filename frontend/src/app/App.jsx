import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, CircularProgress } from '@mui/material';
import { api } from '../api/vb';
import { useAuth } from './AuthContext';
import { AppShell } from '../components/AppShell';
import LoginPage from '../features/auth/LoginPage';
import SetupPage from '../features/auth/SetupPage';
import HomePage from '../features/projects/HomePage';
import ProjectHome from '../features/projects/ProjectHome';
import AccessPage from '../features/projects/AccessPage';
import ProgramHome from '../features/programs/ProgramHome';
import AdminPage from '../features/admin/AdminPage';
import SectionPlaceholder from '../features/common/SectionPlaceholder';

// Routes name their scope (§14.1): /p/:projectId for a project, /g/:programId for a program,
// so the backend guard always receives it.
const SECTIONS = [   // [path, i18n section key, build slice]
  ['processes', 'processes', 2], ['dfd', 'dfd', 2], ['requirements', 'requirements', 1],
  ['br-fr', 'brfr', 3], ['interfaces', 'interfaces', 3], ['data', 'data', 1],
];

function Spinner() {
  return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}><CircularProgress /></Box>;
}

function RequireAuth({ children, admin = false }) {
  const { signedIn, loading, isAdmin } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  if (!signedIn) return <Navigate to="/login" replace state={{ from: location }} />;
  if (admin && !isAdmin) return <Navigate to="/" replace />;
  return <AppShell>{children}</AppShell>;
}

function LoginOrSetup() {
  const setup = useQuery({ queryKey: ['setup'], queryFn: api.setupStatus });
  if (setup.isLoading) return <Spinner />;
  return setup.data?.setup_required ? <Navigate to="/setup" replace /> : <LoginPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginOrSetup />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route path="/" element={<RequireAuth><HomePage /></RequireAuth>} />
      <Route path="/admin" element={<RequireAuth admin><AdminPage /></RequireAuth>} />
      <Route path="/g/:programId" element={<RequireAuth><ProgramHome /></RequireAuth>} />
      <Route path="/p/:projectId" element={<RequireAuth><ProjectHome /></RequireAuth>} />
      <Route path="/p/:projectId/access" element={<RequireAuth><AccessPage /></RequireAuth>} />
      {SECTIONS.map(([path, section, slice]) => (
        <Route key={path} path={`/p/:projectId/${path}`}
          element={<RequireAuth><SectionPlaceholder section={section} slice={slice} /></RequireAuth>} />
      ))}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
