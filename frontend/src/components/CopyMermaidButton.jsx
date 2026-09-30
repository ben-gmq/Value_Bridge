import { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar, TextField, Tooltip,
  Typography } from '@mui/material';
import { errorText } from '../api/client';
import { t } from '../i18n/t';
import { MONO } from '../theme/theme';

/** "Copy as Mermaid" (slice 3c) on the flow, DFD and ERD pages. It fetches the server's export
 * (every label already escaped, R2-S7) and writes it to the clipboard. Where the browser allows
 * no clipboard, the text opens in a read-only box to copy by hand — shown as a field value, so it
 * is always text, never markup. A read, so a REVIEWER can copy too.
 * `area` is the string-key prefix of the page's own i18n file (`processes` or `data.erd`). */
export function CopyMermaidButton({ fetchText, area, disabled = false }) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [manual, setManual] = useState(null);

  const copy = async () => {
    setBusy(true);
    let text;
    try {
      text = await fetchText();
    } catch (err) {
      setNotice({ severity: 'error', text: errorText(err, t(`${area}.mermaidFailed`)) });
      setBusy(false);
      return;
    }
    try {
      if (!navigator.clipboard?.writeText) throw new Error('no clipboard');
      await navigator.clipboard.writeText(text);
      setNotice({ severity: 'success', text: t(`${area}.mermaidCopied`) });
    } catch {
      setManual(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Tooltip title={t(`${area}.mermaidHelp`)}>
        <span><Button sx={{ whiteSpace: 'nowrap' }} disabled={disabled || busy} onClick={copy}>
          {t(`${area}.mermaidCopy`)}</Button></span>
      </Tooltip>
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {notice ? <Alert severity={notice.severity} variant="filled" onClose={() => setNotice(null)}
          sx={{ whiteSpace: 'pre-wrap' }}>{notice.text}</Alert> : undefined}
      </Snackbar>
      <Dialog open={manual != null} onClose={() => setManual(null)} maxWidth="md" fullWidth>
        <DialogTitle>{t(`${area}.mermaidManualTitle`)}</DialogTitle>
        <DialogContent>
          <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 2 }}>{t(`${area}.mermaidManualHelp`)}</Typography>
          <TextField id="mermaid-text" label={t(`${area}.mermaidText`)} value={manual ?? ''} fullWidth multiline
            minRows={8} maxRows={20} autoFocus onFocus={(e) => e.target.select()}
            slotProps={{ htmlInput: { readOnly: true, spellCheck: false, style: { fontFamily: MONO, fontSize: 12.5 } } }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setManual(null)}>{t(`${area}.mermaidClose`)}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
