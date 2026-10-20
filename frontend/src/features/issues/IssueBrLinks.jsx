import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, IconButton, Tooltip, Typography } from '@mui/material';
import LinkOffRounded from '@mui/icons-material/LinkOffRounded';
import { errorText, isStale } from '../../api/client';
import { bfcApi, brApi, issueApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, ListRow, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { SimpleSelect } from '../processes/chartKit';

// The requirements an issue is raised against (§4.5 link_issue_br, many-to-many). Zero links is valid: the issue is
// project-level. A requirement retired with its step takes its links along (I-3); the issue stays.
export function IssueBrLinks({ projectId, issue, canEdit }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: keys.issueBrs(issue.issue_id), queryFn: () => issueApi.brs(issue.issue_id) });
  const brs = useQuery({ queryKey: keys.brs(projectId), queryFn: () => brApi.list(projectId), enabled: canEdit });
  // A requirement with no statement yet is named by its process (browser check 2026-10-20): never a bare number.
  const tree = useQuery({ queryKey: [...keys.tree(projectId), { retired: true }],
    queryFn: () => bfcApi.tree(projectId, true) });
  const nodes = new Map((tree.data ?? []).map((n) => [n.bfc_node_id, n]));
  const describe = (b) => b.br_statement?.trim() || nodes.get(b.bfc_node_id)?.node_name || '';
  const [pick, setPick] = useState('');
  const [error, setError] = useState('');
  const rows = q.data ?? [];
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.issueBrs(issue.issue_id) });
    qc.invalidateQueries({ queryKey: keys.issues(projectId) }); qc.invalidateQueries({ queryKey: keys.scopeSummary(projectId) });
  };
  const fail = (err) => { refresh(); setError(isStale(err) ? t('issues.stale') : errorText(err, t('common.saveFailed'))); };
  const add = useMutation({
    mutationFn: () => issueApi.link(issue.issue_id, pick),
    onSuccess: () => { setPick(''); setError(''); refresh(); },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (row) => issueApi.unlink(issue.issue_id, row.issue_br_id, row.row_version),
    onSuccess: () => { setError(''); refresh(); },
    onError: fail,
  });
  const linked = new Set(rows.map((r) => r.br_id));
  const options = (brs.data ?? []).filter((b) => b.is_active && !linked.has(b.br_id))
    .map((b) => ({ value: b.br_id, label: `${b.br_number} ${describe(b)}`.trim() }));
  const editable = canEdit && issue.is_active;

  return (
    <Card title={t('issues.links.title')} action={<Tag tone="neutral">{rows.length}</Tag>} bodySx={{ gap: 1 }}>
      {(error || q.error) && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error || errorText(q.error)}</Alert>}
      {!q.isLoading && rows.length === 0 && (
        <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('issues.links.none')}</Typography>)}
      {rows.map((r) => (
        <ListRow key={r.issue_br_id}>
          <Box component={RouterLink} to={links.requirement(projectId, r.br_id)}
            sx={{ display: 'flex', gap: 1, alignItems: 'center', minWidth: 0, flex: 1, color: 'inherit', textDecoration: 'none' }}>
            <Code tone="purple">{r.br_number}</Code>
            <Typography noWrap sx={{ fontSize: 13.5 }}>{describe(r)}</Typography>
          </Box>
          {editable && (
            <Tooltip title={t('issues.links.remove')}>
              <IconButton size="small" aria-label={t('issues.links.remove')} disabled={remove.isPending}
                onClick={() => remove.mutate(r)}><LinkOffRounded fontSize="small" /></IconButton>
            </Tooltip>)}
        </ListRow>
      ))}
      {editable && (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 1 }}>
          <SimpleSelect id="iss-link-br" label={t('issues.links.pick')} value={pick} onChange={setPick} options={options} />
          <Button variant="outlined" disabled={!pick || add.isPending} onClick={() => add.mutate()}>{t('issues.links.add')}</Button>
        </Box>)}
    </Card>
  );
}
