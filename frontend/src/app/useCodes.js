import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/vb';

// code_master in the UI (scaffold §4): send codes, show labels. One hook, resolved by the
// backend's two-tier rule, cached per project and category.
// `codes` is every code a record may hold, so labels never go blank. A picker offers `options(current)`: the codes
// the project has not hidden, plus the record's own current value, so a hidden code still shows and saves (wave 1g, R5).
export function useCodes(projectId, category) {
  const q = useQuery({ queryKey: ['codes', String(projectId), category],
    queryFn: () => api.codes(projectId, category), enabled: Boolean(projectId), staleTime: 300_000 });
  const codes = useMemo(() => q.data ?? [], [q.data]);
  const getLabel = useCallback((code) => codes.find((c) => c.code === code)?.label ?? code, [codes]);
  const options = useCallback((current) => codes.filter((c) => !c.is_hidden || c.code === current), [codes]);
  return { codes, options, getLabel, loading: q.isLoading };
}
