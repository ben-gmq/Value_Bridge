import { useAuth } from './AuthContext';

// Whether the signed-in user may change the open project (sara LOW-3, L5). It reads the role the
// server already resolved for /auth/me — never matches grant ids to the project in the browser.
// A user holds one grant (D-32), so that one role applies to every project they can open.
// Presentation only: the server refuses a REVIEWER's write whatever this returns.
const EDIT_ROLES = new Set(['OWNER', 'EDITOR']);

export function useCanEdit() {
  const { me } = useAuth();
  if (!me) return false;
  if (me.scope === 'PLATFORM_ADMIN') return true;
  return EDIT_ROLES.has(me.project_role_code);
}
