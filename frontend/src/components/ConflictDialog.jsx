import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import { t } from '../i18n/t';

// §14.7: one conflict dialog for every 409 on an edit. The user's unsaved values stay
// visible so a reload never loses what they typed.
export function ConflictDialog({ open, unsaved, onReload, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('conflict.title')}</DialogTitle>
      <DialogContent>
        <Typography sx={{ mb: 2 }}>{t('conflict.body')}</Typography>
        {unsaved && (
          <Box component="dl" sx={{ m: 0, p: 2, bgcolor: 'background.subtle', borderRadius: 1, border: 1, borderColor: 'divider' }}>
            {Object.entries(unsaved).map(([k, v]) => (
              <Box key={k} sx={{ display: 'flex', gap: 2, py: 0.5 }}>
                <Box component="dt" sx={{ minWidth: 140, color: 'text.secondary' }}>{k}</Box>
                <Box component="dd" sx={{ m: 0, whiteSpace: 'pre-wrap' }}>{String(v ?? '')}</Box>
              </Box>
            ))}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" onClick={onReload}>{t('conflict.reload')}</Button>
      </DialogActions>
    </Dialog>
  );
}
