import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { reportApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useComponents } from '../../app/useComponents';
import { Card, Code, ListRow, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { Loading, Off, Printable } from './reportKit';

// Coverage (spec §3.2, function 56): one card per gap kind, in the server's order, each with the rows it lists. A line
// whose component is off is null (A1) and names the component it waits for — the first one off, FR before SOLUTION.
const NEEDS = {
  br_without_solution: ['SOLUTION'], br_without_fr: ['FUNCTION_REQUIREMENT'],
  fr_without_br: ['FUNCTION_REQUIREMENT'], fr_without_solution: ['FUNCTION_REQUIREMENT', 'SOLUTION'],
  fr_solution_outside_its_brs: ['FUNCTION_REQUIREMENT', 'SOLUTION'],
  solution_reach_without_link: ['FUNCTION_REQUIREMENT', 'SOLUTION'], fr_rejected_tag: ['FUNCTION_REQUIREMENT', 'SOLUTION'],
  tech_solution_without_fr: ['FUNCTION_REQUIREMENT', 'SOLUTION'], flow_uncovered: ['APPLICATION'],
};

function ItemLink({ to, code, tone, text }) {
  return (
    <Link component={RouterLink} to={to} underline="hover"
      sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, color: 'inherit', flex: '1 1 220px' }}>
      <Code tone={tone}>{code}</Code><Typography noWrap sx={{ fontSize: 13.5 }}>{text}</Typography>
    </Link>
  );
}

// A row names whichever items it carries: the BR, the FR, the flow, the solution or the data entity.
function Row({ projectId, r }) {
  return (
    <ListRow sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
      {r.br_id != null && <ItemLink to={links.requirement(projectId, r.br_id)} code={r.br_number} tone="purple" text={r.br_statement} />}
      {r.fr_id != null && <ItemLink to={links.fr(projectId, r.fr_id)} code={r.fr_number} text={r.fr_name} />}
      {r.br_system_flow_id != null && (
        <Stack direction="row" useFlexGap sx={{ gap: 0.75, alignItems: 'center', flexWrap: 'wrap' }}>
          <Code tone="teal">{r.de_number}</Code><Typography sx={{ fontSize: 13 }}>{r.de_name}</Typography>
          <Tag tone="navy">{r.source_code ?? t('reports.cov.retiredSystem')}</Tag>
          <Typography sx={{ fontSize: 13 }}>→</Typography>
          <Tag tone="navy">{r.target_code ?? t('reports.cov.retiredSystem')}</Tag>
        </Stack>
      )}
      {r.solution_id != null
        ? <ItemLink to={links.solution(projectId, r.solution_id)} code={r.solution_number} text={r.solution_name} />
        : r.solution_number && <Tag tone="neutral">{t('reports.cov.tag', { n: r.solution_number })}</Tag>}
      {r.data_entity_id != null && <ItemLink to={links.entity(projectId, r.data_entity_id)} code={r.de_number} tone="teal" text={r.de_name} />}
    </ListRow>
  );
}

function Line({ projectId, line, on }) {
  const warn = line.severity === 'warning';
  const off = line.rows === null && (NEEDS[line.code] || []).find((c) => !on.has(c));
  return (
    <Card title={t(`reports.cov.${line.code}`)} bodySx={{ gap: 0.5 }}
      action={line.rows && (
        <Tag tone={line.rows.length && warn ? 'caution' : 'neutral'}>{t('reports.trace.rows', { n: line.rows.length })}</Tag>
      )}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 0.5 }}>
        <Tag tone={warn ? 'caution' : 'neutral'}>{t(`reports.cov.sev.${line.severity}`)}</Tag>
        <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t(`reports.cov.${line.code}.note`)}</Typography>
      </Box>
      {line.rows === null ? <Off projectId={projectId} component={off || NEEDS[line.code]?.[0]} />
        : line.rows.length === 0 ? <Typography sx={{ fontSize: 13.5 }}>{t('reports.cov.none')}</Typography>
          : line.rows.map((r, i) => <Row key={i} projectId={projectId} r={r} />)}
    </Card>
  );
}

export function Coverage({ projectId }) {
  const q = useQuery({ queryKey: keys.coverage(projectId), queryFn: () => reportApi.coverage(projectId) });
  const { isOn } = useComponents(projectId);
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const on = { has: (c) => isOn(c) };
  return (
    <Printable projectId={projectId} report="coverage" query={q} data={d}>
      <Stack sx={{ gap: 2 }}>
        <Box>
          <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.cov.intro')}</Typography>
        </Box>
        {d.lines.map((line) => <Line key={line.code} projectId={projectId} line={line} on={on} />)}
      </Stack>
    </Printable>
  );
}
