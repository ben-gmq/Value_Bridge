import { useQuery } from '@tanstack/react-query';
import { api } from '../api/vb';
import { keys } from './links';

// The project's components (D-37), read from the server. Presentation only: hiding a screen is a
// convenience, the guard still refuses a write to a component that is off (409 COMPONENT_OFF).
// Until the list arrives nothing gated counts as on, and gated screens wait (`ready`), so a
// component that is off never flashes into view (UAT 7a observation A).
export function useComponents(projectId) {
  const q = useQuery({ queryKey: keys.components(projectId), queryFn: () => api.components(projectId),
    enabled: Boolean(projectId), staleTime: 60_000 });
  const rows = q.data ?? [];
  const on = new Set(rows.filter((c) => c.enabled).map((c) => c.code));
  const isOn = (...codes) => Boolean(q.data) && codes.every((c) => on.has(c));
  const anyOn = (...codes) => Boolean(q.data) && codes.some((c) => on.has(c));
  return { rows, isOn, anyOn, ready: Boolean(q.data) || q.isError, loading: q.isLoading };
}
