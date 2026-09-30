import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, CircularProgress } from '@mui/material';
import { api } from '../api/vb';
import { useAuth } from './AuthContext';
import { links } from './links';
import { AppShell } from '../components/AppShell';
import LoginPage from '../features/auth/LoginPage';
import SetupPage from '../features/auth/SetupPage';
import HomePage from '../features/projects/HomePage';
import ProjectHome from '../features/projects/ProjectHome';
import AccessPage from '../features/projects/AccessPage';
import ProgramHome from '../features/programs/ProgramHome';
import AdminPage from '../features/admin/AdminPage';
import SectionPlaceholder from '../features/common/SectionPlaceholder';
import ProcessesPage from '../features/processes/ProcessesPage';
import FlowPage from '../features/processes/FlowPage';
import DfdPage from '../features/processes/DfdPage';
import RequirementsPage from '../features/requirements/RequirementsPage';
import RequirementPage from '../features/requirements/RequirementPage';
import DataEntitiesPage from '../features/data/DataEntitiesPage';
import DataEntityPage from '../features/data/DataEntityPage';
import ErdPage from '../features/data/ErdPage';
import SettingsPage from '../features/settings/SettingsPage';
import OrganisationPage from '../features/settings/OrganisationPage';
import PartiesPage from '../features/settings/PartiesPage';

// Routes name their scope (§14.1): /p/:projectId for a project, /g/:programId for a program,
// so the backend guard always receives it.
const SECTIONS = [   // [path, i18n section key, build slice] — sections not built yet
  ['br-fr', 'brfr', 3], ['interfaces', 'interfaces', 3],
];

// Slice 1 pages (addresses in app/links.js). "Processes" opens the function chart; the
// process flow arrives later as a view of it (Ben, 2026-09-29, S1-9).
const PAGES = [
  ['processes', ProcessesPage], ['processes/:nodeId/flow', FlowPage], ['processes/:nodeId/dfd', DfdPage], ['requirements', RequirementsPage],
  ['requirements/:brId', RequirementPage], ['data', DataEntitiesPage], ['data/diagram', ErdPage], ['data/:deId', DataEntityPage],
  ['settings', SettingsPage], ['settings/organisation', OrganisationPage], ['settings/parties', PartiesPage],
];

/** The shell's "DFD" item: a DFD is drawn for one branch of the chart, so it opens the chart
 * with a hint to pick one (Ben, 2026-09-30, sara M2). */
function PickDfd() {
  const { projectId } = useParams();
  return <Navigate to={`${links.processes(projectId)}?pick=dfd`} replace />;
}

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
      {PAGES.map(([path, Screen]) => (
        <Route key={path} path={`/p/:projectId/${path}`} element={<RequireAuth><Screen /></RequireAuth>} />
      ))}
      <Route path="/p/:projectId/dfd" element={<RequireAuth><PickDfd /></RequireAuth>} />
      {SECTIONS.map(([path, section, slice]) => (
        <Route key={path} path={`/p/:projectId/${path}`}
          element={<RequireAuth><SectionPlaceholder section={section} slice={slice} /></RequireAuth>} />
      ))}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
