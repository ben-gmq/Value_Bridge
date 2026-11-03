// Shared pieces of the change-request screens (slice Change requests, design §4.11, D-16): the baselines a change can
// be raised against, the status tag, day figures and links to the objects a change reaches. Strings: en.changes.json.
import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@mui/material';
import { baselineApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Code, Tag } from '../../components/kit';
import { t } from '../../i18n/t';

export const UNDECIDED = ['OPEN', 'PRICED', 'DEFERRED'];
export const OUTCOMES = ['APPROVED', 'REJECTED', 'DEFERRED'];
const TONE = { OPEN: 'neutral', PRICED: 'navy', DEFERRED: 'caution', APPROVED: 'ok', REJECTED: 'escalate' };

// The server decides what a change may target (criteria 63, 190); this only offers the same set and picks the agreed
// baseline first (DR8-P1: the newest with a client approval), else the newest frozen one.
export function useTargets(projectId) {
  const q = useQuery({ queryKey: keys.baselines(projectId), queryFn: () => baselineApi.list(projectId) });
  const rows = q.data ?? [];
  const agreed = rows.find((b) => b.client_approver_name);
  const ok = rows.filter((b) => b.status_code === 'FROZEN' || b.status_code === 'APPROVED'
    || b.baseline_id === agreed?.baseline_id);
  return {
    error: q.error,
    loading: q.isLoading,
    options: ok.map((b) => ({ value: b.baseline_id,
      label: b.baseline_id === agreed?.baseline_id ? t('changes.agreedLabel', { label: b.version_label }) : b.version_label })),
    preferred: agreed?.baseline_id ?? ok[0]?.baseline_id ?? '',
    labelOf: (id) => rows.find((b) => b.baseline_id === id)?.version_label ?? '',
  };
}

export function StatusTag({ cr, getLabel }) {
  return <Tag tone={TONE[cr.status_behaviour] ?? 'neutral'}>{getLabel(cr.status_code)}</Tag>;
}

// A signed day figure: "+4.00 d", "−3.00 d", "–" when not priced.
export function days(v) {
  if (v === null || v === undefined || v === '') return '–';
  const n = Number(v);
  return t('changes.days', { n: `${n > 0 ? '+' : ''}${v}` });
}

const TO = {
  BR: (p, id) => links.requirement(p, id), FR: (p, id) => links.fr(p, id), SOLUTION: (p, id) => links.solution(p, id),
  APPLICATION: (p, id) => links.application(p, id), DATA_ENTITY: (p, id) => links.entity(p, id),
  WAVE: (p) => links.waves(p), BENEFIT: (p, id) => links.benefit(p, id),
};

export function ObjectLink({ projectId, row }) {
  const to = TO[row.kind]?.(projectId, row.object_id);
  const code = <Code tone={row.object_retired ? 'muted' : 'navy'}>{row.number}</Code>;
  return to ? <Link component={RouterLink} to={to} underline="hover">{code}</Link> : code;
}

export const changeLink = (projectId, id, number) => (
  <Link component={RouterLink} to={links.change(projectId, id)} underline="hover"><Code>{number}</Code></Link>);
