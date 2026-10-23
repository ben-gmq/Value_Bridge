// Slice 16 U5 / AR-23, slice 17 VB-012: the weekly archive check's card on the Removals tab. It shows when the check
// last ran (and warns if never, or over 8 days ago), what that run counted, any held project archive whose last check
// failed (U1), and the platform-admin lines read live. The check itself is Fortience IS's weekly job
// (scripts.weekly_check); nothing on this card writes.
import { useQuery } from '@tanstack/react-query';
import { Alert, Stack, Typography } from '@mui/material';
import { api } from '../../api/vb';
import { keys } from '../../app/links';
import { Card } from '../../components/kit';
import { t } from '../../i18n/t';

const when = (iso) => (iso ? new Date(iso).toLocaleString() : '');

export function WeeklyCheckCard() {
  const q = useQuery({ queryKey: keys.weeklyCheck(), queryFn: api.weeklyCheck });
  if (!q.data) return null;
  const { last_run: run, held_failing: held, admin } = q.data;
  const s = run.summary;
  return (
    <Card title={t('removals.weekly.title')} sx={{ mb: 2 }}>
      {run.stale && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {run.ran_at ? t('removals.weekly.stale', { when: when(run.ran_at) }) : t('removals.weekly.never')}
        </Alert>)}
      {run.ran_at && s && (
        <Typography variant="body2">{t('removals.weekly.line', { when: when(run.ran_at), due: s.due ?? 0,
          reopened: s.reopened ?? 0, owed: s.owed_files ?? 0, failed: s.failed_files ?? 0,
          held: s.held_archives ?? 0, heldFailing: s.held_failing ?? 0, removals: s.unfinished_removals ?? 0 })}
        </Typography>)}
      <Stack spacing={0.5} sx={{ mt: 1 }}>
        {held.map((h) => (
          <Alert key={h.project_purge_id} severity="error">
            {t('removals.weekly.heldFailing', { code: h.project_code, error: h.error, when: when(h.checked_at) })}
          </Alert>))}
        {admin.live_admins_below_two && <Alert severity="warning">{t('removals.weekly.adminsBelowTwo')}</Alert>}
        {admin.admins_without_a_grant.length > 0 && (
          <Alert severity="warning">{t('removals.weekly.noGrant', { n: admin.admins_without_a_grant.length })}</Alert>)}
        {admin.open_over_7_days.length > 0 && (
          <Typography variant="body2">{t('removals.weekly.oldRequests', { n: admin.open_over_7_days.length })}</Typography>)}
        {admin.approved_last_7_days.length > 0 && (
          <Typography variant="body2">{t('removals.weekly.recentGrants', { n: admin.approved_last_7_days.length })}</Typography>)}
        {admin.owner_grants_last_7_days.length > 0 && (
          <Typography variant="body2">{t('removals.weekly.ownerGrants', { n: admin.owner_grants_last_7_days.length,
            backdated: admin.owner_grants_last_7_days.filter((g) => g.backdated).length })}</Typography>)}
        {admin.legacy_without_asker.length > 0 && (
          <Typography variant="body2">{t('removals.weekly.noAsker', { n: admin.legacy_without_asker.length })}</Typography>)}
        {(admin.admins_removed_last_7_days.length > 0 || admin.admins_deactivated_last_7_days.length > 0) && (
          <Typography variant="body2">{t('removals.weekly.removedAdmins', {
            removed: admin.admins_removed_last_7_days.length,
            deactivated: admin.admins_deactivated_last_7_days.length })}</Typography>)}
      </Stack>
    </Card>
  );
}
