import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Stack, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { controlApi } from '../../api/scope';
import { keys } from '../../app/links';
import { Card, Code, PurpleTile, Status } from '../../components/kit';
import { t } from '../../i18n/t';
import { Generated, Loading, Off } from './reportKit';

// Data migration map (docs/slice_control_b_spec.md §2.4, CB-4): every data entity the future state uses, the systems
// holding it today and the systems it goes to. Entities needing a data-ownership decision come first. New data and
// retiring entities are listed apart and not counted. The server decides each state.
const cellSx = { px: 1.25, py: 1, fontSize: 13.5, borderBottom: 1, borderColor: 'divider', textAlign: 'left' };
const TONE = { NO_SOURCE: 'caution', CONFLICTING: 'caution', OK: 'ok' };
const ORDER = { NO_SOURCE: 0, CONFLICTING: 1, OK: 2 };
const apps = (list) => (list.length ? list.map((a) => a.application_code).join(', ') : '–');

function Names({ title, rows, note }) {
  if (!rows.length) return null;
  return (
    <Card title={title}>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 1 }}>{note}</Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {rows.map((e) => (
          <Typography component="li" key={e.data_entity_id} sx={{ fontSize: 13.5 }}>
            <Code tone="muted">{e.de_number}</Code> {e.de_name}
          </Typography>))}
      </Box>
    </Card>
  );
}

export function DataMigration({ projectId }) {
  const q = useQuery({ queryKey: keys.dataMigration(projectId), queryFn: () => controlApi.dataMigration(projectId) });
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return <Loading />;
  const h = d.headline;
  if (h.reason === 'AS_IS_OFF' || h.reason === 'APPLICATION_OFF') {
    return <><Generated at={d.generated_at} /><Off projectId={projectId} component={h.reason.replace('_OFF', '')} /></>;
  }
  const rows = [...(d.entities ?? [])].sort((a, b) => ORDER[a.state] - ORDER[b.state]);
  return (
    <Stack sx={{ gap: 2 }}>
      <Generated at={d.generated_at} />
      <Typography sx={{ fontSize: 13.5, color: 'text.secondary' }}>{t('reports.migration.intro')}</Typography>
      {h.reason && <Alert severity="info">{t(`control.reason.${h.reason}`, { n: h.in_scope })}</Alert>}
      {!h.reason && (
        <Stack direction="row" useFlexGap sx={{ gap: 2, flexWrap: 'wrap' }}>
          <PurpleTile label={t('reports.migration.decisions')} value={Number(h.measured)}
            note={t('control.migration', { none: h.no_source, two: h.conflicting, n: h.in_scope })} />
          {h.not_seen_on_as_is > 0 && (
            <PurpleTile label={t('reports.migration.notSeen')} value={h.not_seen_on_as_is} note={t('reports.migration.notSeenNote')} />)}
        </Stack>)}
      {rows.length > 0 && (
        <Card title={t('reports.tab.data_migration')} bodySx={{ overflowX: 'auto' }}>
          <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                {['entity', 'state', 'sources', 'targets'].map((k) => (
                  <Box component="th" key={k} scope="col" sx={{ ...cellSx, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
                    {t(`reports.migration.${k}`)}
                  </Box>))}
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.data_entity_id}>
                  <Box component="th" scope="row" sx={{ ...cellSx, fontWeight: 400 }}>
                    <Code tone="muted">{e.de_number}</Code> {e.de_name}
                  </Box>
                  <Box component="td" sx={cellSx}><Status tone={TONE[e.state]} size="sm">{t(`reports.migration.state.${e.state}`)}</Status></Box>
                  <Box component="td" sx={cellSx}>{apps(e.sources)}</Box>
                  <Box component="td" sx={cellSx}>{e.targets === null ? t('reports.migration.noSolution') : apps(e.targets)}</Box>
                </tr>))}
            </tbody>
          </Box>
        </Card>)}
      <Names title={t('reports.migration.newData')} rows={d.new_data ?? []} note={t('reports.migration.newDataNote')} />
      <Names title={t('reports.migration.retiring')} rows={d.retiring ?? []} note={t('reports.migration.retiringNote')} />
    </Stack>
  );
}
