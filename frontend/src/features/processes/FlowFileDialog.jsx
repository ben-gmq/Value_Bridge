import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar, Typography } from '@mui/material';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import { errorText } from '../../api/client';
import { flowFileApi } from '../../api/scope';
import { t } from '../../i18n/t';

// The flow as a file (slice 1e-b, D-25): export this parent node's steps as vb-process-flow/2.0, and download the
// format and the AI prompt pack. The AI rules come first, before any download (VB-013, FI-6, FI-10): Claude
// Enterprise under FTC's account only, personal data removed by the consultant. Importing a file is piece (a2).
export function FlowFileButton({ nodeId, hasSteps }) {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState(null);          // an error, shown in the dialog
  const [done, setDone] = useState(null);              // a success, as a toast (playbook §7)
  const run = useMutation({
    mutationFn: ({ fn }) => fn(),
    onSuccess: (_r, { done: key }) => setDone(t(key)),
    onError: (err) => setNotice(errorText(err, t('processes.flowFile.failed'))),
  });
  const close = () => { setOpen(false); setNotice(null); };
  const go = (fn, done) => { setNotice(null); run.mutate({ fn, done }); };

  return (
    <>
      <Button variant="outlined" sx={{ whiteSpace: 'nowrap' }} onClick={() => setOpen(true)}>
        {t('processes.flowFile.button')}</Button>
      <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
        <DialogTitle>{t('processes.flowFile.title')}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>{t('processes.flowFile.aiRuleTitle')}</Typography>
            <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
              <li>{t('processes.flowFile.aiRuleService')}</li>
              <li>{t('processes.flowFile.aiRulePersonal')}</li>
              <li>{t('processes.flowFile.aiRuleConfidential')}</li>
            </Box>
          </Alert>
          <Typography variant="body2" sx={{ mb: 2 }}>{t('processes.flowFile.intro')}</Typography>
          {!hasSteps && <Alert severity="info" sx={{ mb: 2 }}>{t('processes.flowFile.noSteps')}</Alert>}
          {notice && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setNotice(null)}>{notice}</Alert>}
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button variant="contained" startIcon={<DownloadRounded />} disabled={!hasSteps || run.isPending}
              onClick={() => go(() => flowFileApi.export(nodeId), 'processes.flowFile.exported')}>
              {t('processes.flowFile.export')}</Button>
            <Button variant="outlined" startIcon={<DownloadRounded />} disabled={run.isPending}
              onClick={() => go(flowFileApi.promptPack, 'processes.flowFile.packSaved')}>
              {t('processes.flowFile.pack')}</Button>
            <Button variant="outlined" startIcon={<DownloadRounded />} disabled={run.isPending}
              onClick={() => go(flowFileApi.schema, 'processes.flowFile.schemaSaved')}>
              {t('processes.flowFile.schema')}</Button>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>{t('processes.flowFile.close')}</Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={Boolean(done)} autoHideDuration={4000} onClose={() => setDone(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {done ? <Alert severity="success" variant="filled" onClose={() => setDone(null)}>{done}</Alert> : undefined}
      </Snackbar>
    </>
  );
}
