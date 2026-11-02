import { useState } from 'react';
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Link, Snackbar, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { decisionApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCanEdit } from '../../app/useCanEdit';
import { useCodes } from '../../app/useCodes';
import { Card, Code } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { CodeTitle, TwoCol } from '../frs/frKit';

function Field({ label, children }) {
  return (
    <Box>
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 0.25 }}>{label}</Typography>
      <Typography component="div" sx={{ fontSize: 14, whiteSpace: 'pre-wrap' }}>{children || '–'}</Typography>
    </Box>
  );
}

// One decision, read-only (A-41), with the decision it corrects and the one that corrects it. "Correct this decision"
// is offered only on the latest in a chain (DC-2).
export default function DecisionPage() {
  const { projectId, decisionId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const canEdit = useCanEdit();
  const dim = useCodes(projectId, 'PM_DIMENSION');
  const q = useQuery({ queryKey: keys.decision(decisionId), queryFn: () => decisionApi.get(decisionId) });
  const [notice, setNotice] = useState(location.state?.recorded
    ? t('decisions.recorded', { number: location.state.recorded }) : '');
  const d = q.data;

  if (q.error) return <Page title={t('decisions.title')} error={errorText(q.error)} />;
  if (!d) return <Page title={t('decisions.loading')} />;

  const home = d.project_id;                                  // the decision's own project, not the URL's (sara L2)
  const chainLink = (id, number) => (
    <Link component={RouterLink} to={links.decision(home, id)} underline="hover"><Code>{number}</Code></Link>);

  const main = (
    <Card title={t('decisions.cardTitle')} bodySx={{ gap: 2 }}>
      <Field label={t('decisions.field.decision_text')}>{d.decision_text}</Field>
      <Field label={t('decisions.field.alternative_rejected')}>{d.alternative_rejected}</Field>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0,1fr))' } }}>
        <Field label={t('decisions.field.dimension_code')}>{dim.getLabel(d.dimension_code)}</Field>
        <Field label={t('decisions.field.analysis_code')}>
          {d.analysis_code ? t(`control.analysis.${d.analysis_code}`) : t('decisions.noAnalysis')}</Field>
        <Field label={t('decisions.field.decided_on')}>{d.decided_on}</Field>
        <Field label={t('decisions.field.decided_by')}>{d.decided_by_name}</Field>
      </Box>
    </Card>
  );
  const side = (
    <Card title={t('decisions.chainTitle')} bodySx={{ gap: 1 }}>
      {d.supersedes_decision_id && (
        <Typography sx={{ fontSize: 13.5 }}>{t('decisions.supersedes')} {chainLink(d.supersedes_decision_id, d.supersedes_number)}</Typography>)}
      {d.superseded_by_id && (
        <Typography sx={{ fontSize: 13.5 }}>{t('decisions.supersededByLabel')} {chainLink(d.superseded_by_id, d.superseded_by_number)}</Typography>)}
      {!d.supersedes_decision_id && !d.superseded_by_id && (
        <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('decisions.noChain')}</Typography>)}
    </Card>
  );

  return (
    <Page title={<CodeTitle code={d.decision_number} name={d.title} tone={d.superseded_by_id ? 'muted' : 'navy'} />}
      subtitle={t('decisions.detailSubtitle')} crumb={d.decision_number}
      actions={canEdit && !d.superseded_by_id && (
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => navigate(links.decisionNew(home, d.decision_id))}>
            {t('decisions.correct')}</Button>
        </Stack>)}>
      <TwoCol main={main} side={side} />
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
