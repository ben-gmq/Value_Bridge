import { Status, Tag } from '../../components/kit';

// Shared bits of the issue screens. Open / closed is the status's behaviour, never its code (law 5).
export function IssueStatus({ issue, label, size }) {
  return <Status tone={issue.status_behaviour === 'CLOSED' ? 'ok' : 'neutral'} size={size}>{label}</Status>;
}

// CRITICAL is pinned (I-13): the one severity the app looks up by value; it is the escalation colour.
export function SeverityTag({ code, label }) {
  return <Tag tone={code === 'CRITICAL' ? 'escalate' : 'neutral'}>{label}</Tag>;
}
