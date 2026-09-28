import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import { t } from '../i18n/t';

// One confirmation for every regret-able action (sara M11). The confirm button is amber —
// `warning` is reserved for exactly these (playbook §6).
export function ConfirmDialog({ open, title, body, confirmLabel, busy, onConfirm, onClose, children }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Typography sx={{ mb: children ? 2 : 0 }}>{body}</Typography>
        {children}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" color="warning" disabled={busy} onClick={onConfirm}>{confirmLabel}</Button>
      </DialogActions>
    </Dialog>
  );
}
