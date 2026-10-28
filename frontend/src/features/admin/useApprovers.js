// AR-28 (migration 0079): how many admins approve on this installation, from the server — never decided here.
// While it is 1 the requester's own Approve shows (sara M1); the database guard still decides. Anything but a clear 1,
// including a failed load, reads as 2.
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/vb';
import { keys } from '../../app/links';

export function useApprovers() {
  const overview = useQuery({ queryKey: keys.archiveOverview(), queryFn: api.archiveOverview });
  const required = overview.data?.approvers_required === 1 ? 1 : 2;
  return { required, alone: required === 1, error: overview.isError };
}
