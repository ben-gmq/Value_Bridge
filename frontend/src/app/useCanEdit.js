import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/vb';
import { useAuth } from './AuthContext';
import { keys } from './links';

// The server's level ranks (services/access.LEVEL_RANK, D-71): PLATFORM is a platform admin.
const RANK = { VIEW: 1, EDIT: 2, ADMIN: 3, PLATFORM: 4 };

// The level the server resolved for the open project (GET /projects/{id} → my_access_level, D-40, D-71): a
// restricted project may cap a USER to VIEW; a project member may be ADMIN. Never computed from memberships in the
// browser. Presentation only: the server refuses whatever this returns.
function useLevelAtLeast(min) {
  const { projectId } = useParams();
  const { isAdmin } = useAuth();
  const q = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId),
    enabled: Boolean(projectId) });
  if (!projectId) return isAdmin;
  return (RANK[q.data?.my_access_level] ?? 0) >= RANK[min];
}

// Whether the signed-in user may change the open project (sara LOW-3, L5).
export function useCanEdit() {
  return useLevelAtLeast('EDIT');
}

// Whether they may manage its members and read its access list — a project admin or a platform admin (D-71).
export function useCanAdmin() {
  return useLevelAtLeast('ADMIN');
}
