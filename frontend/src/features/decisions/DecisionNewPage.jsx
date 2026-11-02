import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, Stack, TextField } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi, decisionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';

// YYYY-MM-DD in ICT — the day the server checks against (D2-2, sara L1), whatever the browser's own time zone
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Bangkok' });
const EMPTY = { title: '', decision_text: '', alternative_rejected: '', dimension_code: '', analysis_code: '',
  decided_on: today() };

// Record a decision (§4.11 record_decision), or correct one (?supersedes=id, DC-2). Nothing here is editable after
// saving (A-41): the save is guarded against a second click while the first is in flight (review D1-7).
export default function DecisionNewPage() {
  const { projectId } = useParams();
  const [search] = useSearchParams();
  const supersedes = search.get('supersedes');
  const navigate = useNavigate();
  const qc = useQueryClient();
  const dim = useCodes(projectId, 'PM_DIMENSION');
  const rules = useQuery({ queryKey: keys.controlRules(projectId), queryFn: () => controlApi.rules(projectId) });
  const old = useQuery({ queryKey: keys.decision(supersedes), queryFn: () => decisionApi.get(supersedes),
    enabled: Boolean(supersedes) });
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState('');
  const sent = useRef(false);
  const set = (k, v) => setF((cur) => ({ ...cur, [k]: v }));

  useEffect(() => {                                                     // a correction starts from what it corrects
    if (old.data) {
      setF({ title: old.data.title, decision_text: old.data.decision_text,
        alternative_rejected: old.data.alternative_rejected, dimension_code: old.data.dimension_code,
        analysis_code: old.data.analysis_code ?? '', decided_on: today() });
    }
  }, [old.data]);

  const m = useMutation({
    mutationFn: () => decisionApi.create(projectId, {
      title: f.title.trim(), decision_text: f.decision_text.trim(), alternative_rejected: f.alternative_rejected.trim(),
      dimension_code: f.dimension_code, analysis_code: f.analysis_code || null, decided_on: f.decided_on || null,
      supersedes_decision_id: supersedes ? Number(supersedes) : null }),
    onSuccess: (row) => {
      qc.invalidateQueries({ queryKey: keys.decisions(projectId) });
      if (supersedes) qc.invalidateQueries({ queryKey: keys.decision(supersedes) });
      navigate(links.decision(projectId, row.decision_id), { replace: true, state: { recorded: row.decision_number } });
    },
    onError: (err) => { sent.current = false; setError(errorText(err, t('common.saveFailed'))); },
  });
  const ready = f.title.trim() && f.decision_text.trim() && f.alternative_rejected.trim() && f.dimension_code;
  const submit = () => {
    if (sent.current) return;
    sent.current = true;
    setError('');
    m.mutate();
  };
  const ruleOptions = (rules.data ?? []).map((r) => ({ value: r.analysis_code, label: t(`control.analysis.${r.analysis_code}`) }));

  return (
    <Page title={supersedes && old.data ? t('decisions.correctTitle', { number: old.data.decision_number })
      : t('decisions.recordTitle')} crumb={supersedes && old.data ? old.data.decision_number : undefined}
      error={(old.error || rules.error) && errorText(old.error || rules.error)}
      actions={(
        <>
          <Button onClick={() => navigate(-1)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={m.isPending || !ready} onClick={submit}>{t('decisions.save')}</Button>
        </>)}>
      <Card>
        <Alert severity="info" sx={{ mb: 2 }}>{t('decisions.permanent')}</Alert>
        {supersedes && old.data && (
          <Alert severity="warning" sx={{ mb: 2 }}>{t('decisions.correcting', { number: old.data.decision_number })}</Alert>)}
        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        <Stack spacing={2}>
          <TextField id="dec-title" size="small" label={t('decisions.field.title')} value={f.title} required
            slotProps={{ htmlInput: { maxLength: 200 } }} onChange={(e) => set('title', e.target.value)} />
          <TextField id="dec-text" size="small" multiline minRows={3} required label={t('decisions.field.decision_text')}
            value={f.decision_text} onChange={(e) => set('decision_text', e.target.value)} />
          <TextField id="dec-alternative" size="small" multiline minRows={2} required
            label={t('decisions.field.alternative_rejected')} value={f.alternative_rejected}
            onChange={(e) => set('alternative_rejected', e.target.value)} />
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0,1fr))' } }}>
            <SimpleSelect id="dec-dimension" label={t('decisions.field.dimension_code')} value={f.dimension_code}
              onChange={(v) => set('dimension_code', v)}
              options={dim.options(f.dimension_code).map((c) => ({ value: c.code, label: c.label }))} />
            <SimpleSelect id="dec-analysis" label={t('decisions.field.analysis_code')} value={f.analysis_code} allowEmpty
              emptyLabel={t('decisions.noAnalysis')} onChange={(v) => set('analysis_code', v)} options={ruleOptions} />
            <TextField id="dec-decided-on" type="date" size="small" label={t('decisions.field.decided_on')}
              value={f.decided_on} onChange={(e) => set('decided_on', e.target.value)}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: today() } }} />
          </Box>
        </Stack>
      </Card>
    </Page>
  );
}
