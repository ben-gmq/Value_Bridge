import { useMemo, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Snackbar, Typography } from '@mui/material';
import LockOutlined from '@mui/icons-material/LockOutlined';
import { errorText } from '../../api/client';
import { bfcApi } from '../../api/scope';
import { keys, links } from '../../app/links';
import { Card, Code, KV, LevelBadge, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { useBrEditor } from './BrEditor';
import { BrStatusTag } from './reqKit';
import { DfdMark } from '../processes/DfdLight';

// Business requirement page — mockup 03 (D-51). D-53: a BR is part of the function chart and is
// edited in its process's panel there; this page stays as the deep link (from FRs, solutions, the
// baseline diff), crumbed under Business functions. Both use one editor (BrEditor.useBrEditor).
// Left: the Requirement card; right: Coverage (FRs reached through solutions) and the Record card.
export default function RequirementPage() {
  const { projectId, brId } = useParams();
  const [notice, setNotice] = useState('');
  // The parent path in the eyebrow; retired nodes too, so a retired step still shows where it sat.
  const treeQ = useQuery({ queryKey: [...keys.tree(projectId), { retired: true }], queryFn: () => bfcApi.tree(projectId, true) });
  // D-69: the CRUD grid makes the step's output, so its header carries the DATA_OUT mark (server codes only, DR13-D1).
  const crudMark = (nodeId) => {
    const row = (treeQ.data ?? []).find((n) => n.bfc_node_id === nodeId);
    return row?.dfd_light ? <DfdMark dfd={{ missing: row.dfd_missing ?? [] }} element="DATA_OUT" /> : null;
  };
  const ed = useBrEditor({ projectId, brId, onNotice: setNotice, crudMark });
  const br = ed.br;
  const nodeQ = useQuery({ queryKey: keys.node(br?.bfc_node_id), queryFn: () => bfcApi.get(br.bfc_node_id),
    enabled: Boolean(br) });
  const node = nodeQ.data;
  const path = useMemo(() => {
    const byId = new Map((treeQ.data ?? []).map((n) => [n.bfc_node_id, n]));
    const out = [];
    for (let p = byId.get(node?.parent_bfc_node_id); p && out.length < 10; p = byId.get(p.parent_bfc_node_id)) out.unshift(p.node_name);
    return out;
  }, [treeQ.data, node]);

  if (ed.error) return <Page title={t('requirements.title')} error={errorText(ed.error)} />;
  if (!br) {
    return (
      <Page title={t('requirements.title')}>
        <Typography sx={{ color: 'text.secondary' }}>{t('processes.loading')}</Typography>
      </Page>
    );
  }

  const eyebrow = node && (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
      <LevelBadge level={node.level_no} label={t('processes.levelN', { n: node.level_no })} />
      <Link component={RouterLink} to={links.node(projectId, node.bfc_node_id, node.bfc_set_code)} underline="hover"
        title={t('requirements.backToNode')}>
        <Code tone="purple">{node.hier_code}</Code></Link>
      {path.length > 0 && (
        <Typography noWrap sx={{ fontSize: 13, color: 'text.secondary', minWidth: 0 }}>{path.join(' › ')}</Typography>)}
    </Box>
  );

  return (
    <Page eyebrow={eyebrow} crumb={br.br_number} subtitle={t('requirements.detailSubtitle')} actions={ed.actions}
      title={<><Code tone="purple" sx={{ fontSize: 22, mr: 1.5 }}>{br.br_number}</Code>{node?.node_name}</>}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 2, '&:empty': { display: 'none' } }}>
        {ed.alerts}
        {nodeQ.error && <Alert severity="error">{errorText(nodeQ.error)}</Alert>}
      </Box>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', lg: 'minmax(0,1fr) 340px' }, alignItems: 'start' }}>
        <Card title={t('requirements.requirement')} action={ed.saveState} bodySx={{ containerType: 'inline-size', gap: 2.5 }}>
          {ed.fields}
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          {ed.coverage}
          <Card title={t('requirements.record')}>
            <KV k={t('requirements.recordVersion')} v={<Code tone="muted" sx={{ color: 'text.primary' }}>{br.row_version}</Code>} />
            <KV k={t('requirements.recordStatus')} v={<BrStatusTag code={br.status_code} label={ed.getLabel(br.status_code)} />} />
            {!ed.live && <KV k={t('requirements.recordState')} v={<Tag tone="neutral">{t('processes.retiredChip')}</Tag>} />}
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', p: 1.5, borderRadius: '14px', bgcolor: 'background.subtle' }}>
              <LockOutlined sx={{ fontSize: 18, color: 'brand.muted', mt: '1px' }} />
              <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t('requirements.recordLock')}</Typography>
            </Box>
          </Card>
        </Box>
      </Box>

      {ed.dialogs}
      <Snackbar open={Boolean(notice)} autoHideDuration={3000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
