import { useState } from 'react';
import { Alert, Button, Menu, MenuItem, Snackbar } from '@mui/material';
import { IMAGE_FORMATS, saveCanvasImage } from '../canvas/saveImage';
import { t } from '../i18n/t';

/** "Save picture" (function 41): the diagram exactly as shown, in each format canvas/saveImage offers (PNG today). `target` is a
 * ref to the element holding the canvas; `fileName` is made from ids only. A read, so a read-only user can save too.
 * Success is a toast, a failure an error toast (playbook §7). */
export function SavePictureButton({ target, fileName, disabled = false }) {
  const [anchor, setAnchor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const save = async (format) => {
    setAnchor(null);
    setBusy(true);
    try {
      await saveCanvasImage(target.current, format, fileName);
      setNotice({ severity: 'success', text: t('canvas.picture.saved', { format: format.toUpperCase() }) });
    } catch (err) {
      if (import.meta.env.DEV) console.error(err);
      setNotice({ severity: 'error', text: t('canvas.picture.failed') });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button sx={{ whiteSpace: 'nowrap' }} disabled={disabled || busy} aria-haspopup="menu"
        onClick={(e) => setAnchor(e.currentTarget)}>{t('canvas.picture.button')}</Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {IMAGE_FORMATS.map((f) => <MenuItem key={f} onClick={() => save(f)}>{t(`canvas.picture.${f}`)}</MenuItem>)}
      </Menu>
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {notice ? <Alert severity={notice.severity} variant="filled" onClose={() => setNotice(null)}>{notice.text}</Alert> : undefined}
      </Snackbar>
    </>
  );
}
