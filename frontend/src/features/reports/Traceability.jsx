import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { reportApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code, ListRow, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading, Off, Printable } from './reportKit';

// Traceability (spec §3.1, function 68): one row per step × BR × linked FR, grouped by FR type. An FR reached only
// through a solution is not traced (D-52) and sits in the untraced list. A part whose component is off is null (A1).
function FrCell({ projectId, r }) {
  return (
    <Link component={RouterLink} to={links.fr(projectId, r.fr_id)} underline="hover"
      sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, color: 'inherit' }}>
      <Code>{r.fr_number}</Code><Typography noWrap sx={{ fontSize: 13.5 }}>{r.fr_name}</Typography>
    </Link>
  );
}

function TagCell({ r, getCategory }) {
  if (r.rejected_solution === null) return null;                                       // SOLUTION off (A1)
  if (!r.solution) return <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('reports.trace.noTag')}</Typography>;
  return (
    <Stack direction="row" useFlexGap sx={{ gap: 0.75, alignItems: 'center', flexWrap: 'wrap', minWidth: 0 }}>
      <Code>{r.solution.solution_number}</Code>
      <Typography noWrap sx={{ fontSize: 13 }}>{r.solution.solution_name}</Typography>
      <Tag tone="neutral">{getCategory(r.solution.category_code)}</Tag>
      {r.rejected_solution && <Tag tone="escalate">{t('reports.trace.rejected')}</Tag>}
      {!r.rejected_solution && r.tag_answers_br === false && <Tag tone="caution">{t('reports.trace.notThisBr')}</Tag>}
      {(r.applications || []).map((a) => <Tag key={a.application_code} tone="navy">{a.application_code}</Tag>)}
    </Stack>
  );
}

const GRID = { display: 'grid', gap: 1.5, alignItems: 'center',
  gridTemplateColumns: { xs: 'minmax(0,1fr)', md: 'minmax(0,1.1fr) minmax(0,1.6fr) minmax(0,1.3fr) minmax(0,1.4fr) auto' } };

function Header() {
  return (
    <Box sx={{ ...GRID, display: { xs: 'none', md: 'grid' }, px: 1.5, pb: 0.5 }}>
      {['step', 'br', 'fr', 'solution'].map((k) => (
        <Typography key={k} sx={{ fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>{t(`reports.trace.${k}`)}</Typography>
      ))}
      <span />
    </Box>
  );
}

function Row({ projectId, r, getStatus, getCategory }) {
  return (
    <ListRow sx={GRID}>
      <Box sx={{ display: 'flex', gap: 1, minWidth: 0 }}>
        <Code tone="muted">{r.hier_code}</Code><Typography noWrap sx={{ fontSize: 13.5 }}>{r.step_name}</Typography>
      </Box>
      <Link component={RouterLink} to={links.requirement(projectId, r.br_id)} underline="hover"
        sx={{ display: 'flex', gap: 1, minWidth: 0, color: 'inherit' }}>
        <Code tone="purple">{r.br_number}</Code>
        <Typography noWrap sx={{ fontSize: 13.5 }}>{r.br_statement}</Typography>
      </Link>
      <FrCell projectId={projectId} r={r} />
      <TagCell r={r} getCategory={getCategory} />
      <Tag tone="neutral">{getStatus(r.fulfilment_status_code)}</Tag>
    </ListRow>
  );
}

export function Traceability({ projectId }) {
  const q = useQuery({ queryKey: keys.traceability(projectId), queryFn: () => reportApi.traceability(projectId) });
  const { getLabel: getStatus } = useCodes(projectId, 'FR_FULFILMENT_STATUS');
  const { getLabel: getCategory } = useCodes(projectId, 'SOLUTION_CATEGORY');
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  if (d.groups === null) return <><Generated at={d.generated_at} /><Off projectId={projectId} component="FUNCTION_REQUIREMENT" /></>;
  return (
    <Printable projectId={projectId} report="traceability" query={q} data={d}>
      <Stack sx={{ gap: 2 }}>
        <Box>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.trace.intro')}</Typography>
        </Box>
        {d.groups.length === 0 && <Alert severity="info">{t('reports.trace.empty')}</Alert>}
        {d.groups.map((g) => (
          <Card key={g.fr_type_code} title={g.fr_type_label}
            action={<Tag tone="neutral">{t('reports.trace.rows', { n: g.rows.length })}</Tag>} bodySx={{ gap: 0.5 }}>
            <Header />
            {g.rows.map((r) => (
              <Row key={`${r.br_id}-${r.fr_id}`} projectId={projectId} r={r} getStatus={getStatus} getCategory={getCategory} />
            ))}
          </Card>
        ))}
        <Card title={t('reports.trace.untraced')} bodySx={{ gap: 0.5 }}
          action={d.untraced.length > 0 && <Tag tone="caution">{t('reports.trace.rows', { n: d.untraced.length })}</Tag>}>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 0.5 }}>{t('reports.trace.untracedNote')}</Typography>
          {d.untraced.length === 0 && <Typography sx={{ fontSize: 13.5 }}>{t('reports.trace.untracedEmpty')}</Typography>}
          {d.untraced.map((r) => (
            <ListRow key={r.fr_id} sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
              <Box sx={{ flex: '1 1 240px', minWidth: 0 }}><FrCell projectId={projectId} r={r} /></Box>
              <Box sx={{ flex: '1 1 240px', minWidth: 0 }}><TagCell r={r} getCategory={getCategory} /></Box>
              <Tag tone="neutral">{getStatus(r.fulfilment_status_code)}</Tag>
            </ListRow>
          ))}
        </Card>
        <Card title={t('reports.trace.without')} bodySx={{ gap: 0.5 }}>
          {d.answered_without_software === null ? <Off projectId={projectId} component="SOLUTION" /> : <>
            <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 0.5 }}>{t('reports.trace.withoutNote')}</Typography>
            {d.answered_without_software.length === 0
              && <Typography sx={{ fontSize: 13.5 }}>{t('reports.trace.withoutEmpty')}</Typography>}
            {d.answered_without_software.map((s) => (
              <ListRow key={s.solution_id} component={RouterLink} to={links.solution(projectId, s.solution_id)}
                sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                <Code>{s.solution_number}</Code>
                <Typography sx={{ fontSize: 13.5, flex: '1 1 200px' }}>{s.solution_name}</Typography>
                <Tag tone="neutral">{getCategory(s.category_code)}</Tag>
                {s.br_numbers.map((n) => <Tag key={n} tone="purple">{n}</Tag>)}
              </ListRow>
            ))}
          </>}
        </Card>
      </Stack>
    </Printable>
  );
}
