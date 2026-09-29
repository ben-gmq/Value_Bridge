import { errorText, isConflict } from '../../api/client';
import { t } from '../../i18n/t';

// A 409 means one of two things: someone else saved first (stale row_version → ConflictDialog,
// §14.7), or the server refused and named why ("Retire these first: …", a duplicate name). The
// record itself tells them apart: re-read it and compare versions, never parse the message.
export async function explainError(err, sentVersion, reread) {
  if (isConflict(err) && sentVersion != null && reread) {
    try {
      const fresh = await reread();
      if (fresh && fresh.row_version !== sentVersion) return { stale: true, fresh };
    } catch { /* could not re-read: show the server's own words */ }
  }
  return { stale: false, text: errorText(err, t('common.saveFailed')) };
}
