import { useMemo, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Link, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { bfcApi, brApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, Code, LevelBadge, ListRow, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { ShowRetired } from '../processes/chartKit';
import { BrStatusTag } from './reqKit';

// Business requirements (§7.3), as a kit card list (D-51). There is no "add requirement": a BR
// appears with its process step (D-2), so the empty state points at the chart.
function EmptyState({ projectId }) {
  return (
    <Stack sx={{ alignItems: 'center', justifyContent: 'center', py: 5, px: 2, textAlign: 'center' }} spacing={1}>
      <Typography sx={{ color: 'text.secondary' }}>{t('requirements.empty')}</Typography>
      <Link component={RouterLink} to={links.processes(projectId)}>{t('requirements.goProcesses')}</Link>
    </Stack>
  );
}

export default function RequirementsPage() {
  const { projectId } = useParams();
  const [showRetired, setShowRetired] = useState(false);
  const brsQ = useQuery({ queryKey: [...keys.brs(projectId), { retired: showRetired }],
    queryFn: () => brApi.list(projectId, showRetired) });
  // Retired nodes too, so a retired requirement still shows where it sat.
  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: true }], queryFn: () => bfcApi.tree(projectId, true) });
  const { getLabel } = useCodes(projectId, 'BR_STATUS');
  const nodeById = useMemo(() => new Map((treeQ.data ?? []).map((n) => [n.bfc_node_id, n])), [treeQ.data]);
  const rows = useMemo(() => [...(brsQ.data ?? [])].sort((a, b) => a.br_number.localeCompare(b.br_number)), [brsQ.data]);

  return (
    <Page title={t('requirements.title')} subtitle={t('requirements.subtitle')}
      error={(brsQ.error && errorText(brsQ.error)) || (treeQ.error && errorText(treeQ.error))}>
      <Card title={t('requirements.count', { n: rows.length })}
        action={<ShowRetired id="br-show-retired" checked={showRetired} onChange={setShowRetired} />}
        bodySx={{ gap: 1 }}>
        {brsQ.isLoading && <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>}
        {!brsQ.isLoading && !brsQ.error && rows.length === 0 && <EmptyState projectId={projectId} />}
        {rows.map((row) => {
          const node = nodeById.get(row.bfc_node_id);
          const statement = (row.br_statement ?? '').split('\n')[0];
          return (
            <ListRow key={row.br_id} component={RouterLink} to={links.requirement(projectId, row.br_id)}
              sx={{ flexWrap: 'wrap', rowGap: 0.5, opacity: row.is_active ? 1 : 0.7 }}>
              <Code tone="purple" sx={{ width: 76, flexShrink: 0 }}>{row.br_number}</Code>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: '1 1 260px', minWidth: 0 }}>
                {node && <LevelBadge level={node.level_no} label={t('processes.levelN', { n: node.level_no })} />}
                {node && <Code tone="muted" sx={{ fontSize: 12 }}>{node.hier_code}</Code>}
                <Box sx={{ minWidth: 0 }}>
                  <Typography noWrap sx={{ fontSize: 14, fontWeight: 600 }}>{node?.node_name}</Typography>
                  {statement && <Typography noWrap sx={{ fontSize: 12.5, color: 'text.secondary' }}>{statement}</Typography>}
                </Box>
              </Box>
              <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexShrink: 0, ml: 'auto' }}>
                {!row.is_active && <Tag tone="neutral">{t('processes.retiredChip')}</Tag>}
                <BrStatusTag code={row.status_code} label={getLabel(row.status_code)} />
              </Box>
            </ListRow>
          );
        })}
      </Card>
    </Page>
  );
}
