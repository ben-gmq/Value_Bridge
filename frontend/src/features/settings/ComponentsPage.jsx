import { useEffect, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, FormControlLabel, Radio, RadioGroup, Snackbar, Stack,
  Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { useAuth } from '../../app/AuthContext';
import { keys, links } from '../../app/links';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, ListRow, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { DfdRuleCard } from './DfdRuleCard';
import { FteBasisCard } from './FteBasisCard';

// Settings → Components (D-37, D-39). Everyone sees what the project uses; only a platform admin
// changes it, through a preview that names what a dependency adds and what blocks a switch-off
// (OR-1, OR-2), then a confirm carrying the preview's hash.
export default function ComponentsPage() {
  const { projectId } = useParams();
  const { isAdmin } = useAuth();
  const qc = useQueryClient();
  const comps = useQuery({ queryKey: keys.components(projectId), queryFn: () => api.components(projectId) });
  const project = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const [wanted, setWanted] = useState(null);
  const [depth, setDepth] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const rows = comps.data ?? [];
  const label = (code) => rows.find((c) => c.code === code)?.label ?? code;
  const list = (codes) => codes.map(label).join(', ');

  useEffect(() => { if (comps.data) setWanted(new Set(comps.data.filter((c) => c.enabled).map((c) => c.code))); }, [comps.data]);
  useEffect(() => { if (project.data) setDepth(project.data.data_model_depth); }, [project.data]);

  const send = useMutation({
    mutationFn: (confirm_hash) => api.setComponents(projectId, { component_codes: [...wanted], confirm_hash }),
    onSuccess: (res) => {
      setError('');
      if (res.applied) {
        setPreview(null); setNotice(t('components.saved'));
        qc.invalidateQueries({ queryKey: keys.components(projectId) });
        qc.invalidateQueries({ queryKey: keys.tree(projectId) });      // DR13-D2: a DFD toggle turns the light on or off
      } else setPreview(res);
    },
    onError: (err) => { setPreview(null); setError(errorText(err, t('common.saveFailed'))); },
  });
  const saveDepth = useMutation({
    mutationFn: () => api.setDepth(projectId, { data_model_depth: depth, row_version: project.data.row_version }),
    onSuccess: () => { setError(''); setNotice(t('components.depthSaved'));
      qc.invalidateQueries({ queryKey: keys.project(projectId) });
      qc.invalidateQueries({ queryKey: keys.entities(projectId) }); },
    onError: (err) => setError(errorText(err, t('common.saveFailed'))),
  });

  const toggle = (code) => setWanted((w) => { const n = new Set(w); n.has(code) ? n.delete(code) : n.add(code); return n; });
  const unchanged = preview && !preview.turn_on.length && !preview.turn_off.length && !preview.blockers.length;

  return (
    <Page title={t('components.title')} subtitle={t('components.subtitle')}
      actions={<Button component={RouterLink} to={links.settings(projectId)}>{t('settings.title')}</Button>}>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {!isAdmin && <Alert severity="info" sx={{ mb: 2 }}>{t('components.adminOnly')}</Alert>}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 3fr) minmax(0, 2fr)' }, alignItems: 'start' }}>
        <Card title={t('components.pick')} bodySx={{ gap: 1 }}
          action={isAdmin && (
            <Button variant="contained" size="small" disabled={send.isPending || !wanted} onClick={() => send.mutate(null)}>
              {t('components.save')}</Button>)}>
          {wanted && rows.map((c) => (
            <ListRow key={c.code} selected={wanted.has(c.code)} sx={{ py: 0.5, flexWrap: 'wrap' }}>
              <FormControlLabel label={c.label} disabled={!isAdmin} sx={{ mr: 'auto' }}
                control={<Checkbox checked={wanted.has(c.code)} onChange={() => toggle(c.code)} />} />
              {c.requires.length > 0 && <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {t('components.needs', { list: list(c.requires) })}</Typography>}
              {!c.available && <Tag tone="neutral">{t('components.notYet')}</Tag>}
            </ListRow>
          ))}
        </Card>

        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Card title={t('components.depthTitle')} bodySx={{ gap: 1 }}>
            <Typography sx={{ color: 'text.secondary', fontSize: 13.5 }}>{t('components.depthWhat')}</Typography>
            {depth && (
              <RadioGroup value={depth} onChange={(e) => setDepth(e.target.value)} aria-label={t('components.depthTitle')}>
                {['KEYS_ONLY', 'FULL'].map((v) => (
                  <FormControlLabel key={v} value={v} disabled={!isAdmin} control={<Radio />} label={t(`components.depth.${v}`)} />
                ))}
              </RadioGroup>
            )}
            {isAdmin && (
              <Box>
                <Button variant="contained" onClick={() => saveDepth.mutate()}
                  disabled={saveDepth.isPending || !project.data || depth === project.data.data_model_depth}>
                  {t('components.saveDepth')}</Button>
              </Box>
            )}
          </Card>
          {/* D-70: the project's DFD rule, per chart — next to the other "how complete" setting, the depth */}
          <DfdRuleCard projectId={projectId} isAdmin={isAdmin} onNotice={setNotice} />
          {/* D-67: the FTE basis every process's hours divide by */}
          <FteBasisCard projectId={projectId} isAdmin={isAdmin} onNotice={setNotice} />
        </Stack>
      </Box>

      <ConfirmDialog open={Boolean(preview)} title={t('components.reviewTitle')} confirmLabel={t('components.apply')}
        body={unchanged ? t('components.nothing') : ''}
        busy={send.isPending || unchanged || !preview?.turn_on.length && !preview?.turn_off.length
          || (preview?.blockers ?? []).length > 0}
        onClose={() => setPreview(null)} onConfirm={() => send.mutate(preview.confirm_hash)}>
        {preview && (
          <Stack spacing={1}>
            {preview.turn_on.length > 0 && <Typography>{t('components.turnOn', { list: list(preview.turn_on) })}</Typography>}
            {preview.added_by_dependency.length > 0 && (
              <Alert severity="info">{t('components.addedByDependency', { list: list(preview.added_by_dependency) })}</Alert>)}
            {preview.turn_off.length > 0 && <Typography>{t('components.turnOff', { list: list(preview.turn_off) })}</Typography>}
            {preview.blockers.length > 0 && (
              <Alert severity="error">
                <Typography sx={{ mb: 0.5 }}>{t('components.blocked')}</Typography>
                {preview.blockers.map((b, i) => <Typography key={`${b.component}-${b.reason}-${i}`} variant="body2">{b.message}</Typography>)}
              </Alert>
            )}
          </Stack>
        )}
      </ConfirmDialog>
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
