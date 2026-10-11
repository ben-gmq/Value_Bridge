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
import SolutionsPage from '../features/solutions/SolutionsPage';
import SolutionPage from '../features/solutions/SolutionPage';
import FrsPage from '../features/frs/FrsPage';
import FrPage from '../features/frs/FrPage';
import InterfacesPage from '../features/interfaces/InterfacesPage';
import EffortPage from '../features/effort/EffortPage';
import RateCardPage from '../features/effort/RateCardPage';
import OrganisationPage from '../features/settings/OrganisationPage';
import PartiesPage from '../features/settings/PartiesPage';
import ComponentsPage from '../features/settings/ComponentsPage';
import ComponentOff from '../features/common/ComponentOff';
import { useComponents } from './useComponents';
import ApplicationsPage from '../features/applications/ApplicationsPage';
import ApplicationPage from '../features/applications/ApplicationPage';

// Routes name their scope (§14.1): /p/:projectId for a project, /g/:programId for a program,
// so the backend guard always receives it.
const SECTIONS = [   // [path, i18n section key, build slice] — sections not built yet
];

// Slice 1 pages (addresses in app/links.js). "Processes" opens the function chart; the
// process flow arrives later as a view of it (Ben, 2026-09-29, S1-9).
const PAGES = [
  ['processes', ProcessesPage], ['processes/:nodeId/flow', FlowPage], ['processes/:nodeId/dfd', DfdPage], ['requirements', RequirementsPage],
  ['requirements/:brId', RequirementPage], ['data', DataEntitiesPage], ['data/diagram', ErdPage], ['data/:deId', DataEntityPage],
  ['interfaces', InterfacesPage], ['br-fr', SolutionsPage], ['br-fr/frs', FrsPage], ['br-fr/effort', EffortPage], ['br-fr/frs/:frId', FrPage], ['br-fr/:solutionId', SolutionPage],
  ['settings', SettingsPage], ['settings/organisation', OrganisationPage], ['settings/parties', PartiesPage],
  ['settings/components', ComponentsPage],
  ['settings/applications', ApplicationsPage], ['settings/rate-card', RateCardPage], ['settings/applications/:appId', ApplicationPage],
];

// D-37: a screen of a component that is off shows why instead of its content. Any one listed
// component being on opens it (the BR–FR map shows solutions or FRs). Presentation only.
const NEEDS = {
  'br-fr': ['SOLUTION', 'FUNCTION_REQUIREMENT'], 'br-fr/:solutionId': ['SOLUTION'],
  'br-fr/frs': ['FUNCTION_REQUIREMENT'], 'br-fr/frs/:frId': ['FUNCTION_REQUIREMENT'],
  'br-fr/effort': ['EFFORT'], 'settings/rate-card': ['EFFORT'], interfaces: ['APPLICATION'],
  'settings/applications': ['APPLICATION'], 'settings/applications/:appId': ['APPLICATION'],
  'processes/:nodeId/flow': ['TO_BE_DFD'], 'processes/:nodeId/dfd': ['TO_BE_DFD', 'AS_IS'],
};

function Gated({ path, Screen }) {
  const { projectId } = useParams();
  const { anyOn, rows, ready } = useComponents(projectId);
  const need = NEEDS[path];
  if (need && !ready) return <Spinner />;
  if (need && !anyOn(...need)) {
    return <ComponentOff name={rows.find((c) => c.code === need[0])?.label ?? need[0]} />;
  }
  return <Screen />;
}

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
        <Route key={path} path={`/p/:projectId/${path}`} element={<RequireAuth><Gated path={path} Screen={Screen} /></RequireAuth>} />
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
