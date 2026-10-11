import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/vb';
import { useAuth } from './AuthContext';
import { keys } from './links';

// Whether the signed-in user may change the open project (sara LOW-3, L5). It reads the level the
// server resolved for this project (GET /projects/{id} → my_access_level, D-40): a restricted
// project may cap a USER to VIEW. Never computed from memberships in the browser. Presentation
// only: the server refuses a VIEW-level write whatever this returns.
export function useCanEdit() {
  const { projectId } = useParams();
  const { isAdmin } = useAuth();
  const q = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId),
    enabled: Boolean(projectId) });
  if (!projectId) return isAdmin;
  return ['EDIT', 'ADMIN'].includes(q.data?.my_access_level);
}
