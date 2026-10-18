import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Link, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { errorText } from '../../api/client';
import { issueApi } from '../../api/scope';
import { keys } from '../../app/links';
import { useCodes } from '../../app/useCodes';
import { Card, PurpleTile, Tile } from '../../components/kit';
import { t } from '../../i18n/t';
import { TileRow } from '../frs/frKit';

// The issue dashboard (§4.5 issue_dashboard): open issues by severity × type, by area, by raiser, and overdue. An issue
// counts once in every area it touches, so area rows do not add up to the total (R4, I-12). A count opens the register
// filtered the same way.
export function IssueDashboard({ projectId, onFilter }) {
  const q = useQuery({ queryKey: keys.issueDashboard(projectId), queryFn: () => issueApi.dashboard(projectId) });
  const sev = useCodes(projectId, 'ISSUE_SEVERITY');
  const typ = useCodes(projectId, 'ISSUE_TYPE');
  if (q.error) return <Alert severity="error">{errorText(q.error)}</Alert>;
  const d = q.data;
  if (!d) return null;
  const count = (n, filter) => (n ? (
    <Link component="button" underline="hover" onClick={() => onFilter(filter)} sx={{ fontWeight: 600 }}>{n}</Link>
  ) : <Box component="span" sx={{ color: 'text.disabled' }}>0</Box>);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <TileRow>
        <PurpleTile label={t('issues.dash.open')} value={d.open} />
        <Tile label={t('issues.dash.critical')} value={d.critical} note={t('issues.dash.criticalNote')} />
        <Tile label={t('issues.dash.overdue')} value={d.overdue} note={t('issues.dash.overdueNote')} />
      </TileRow>
      <Card title={t('issues.dash.bySeverityType')} bodySx={{ px: 0, overflowX: 'auto' }}>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>{t('issues.field.severity')}</TableCell>
            {d.types.map((ty) => <TableCell key={ty} align="right">{typ.getLabel(ty)}</TableCell>)}
          </TableRow></TableHead>
          <TableBody>
            {d.by_severity_type.map((r) => (
              <TableRow key={r.severity_code}>
                <TableCell>{sev.getLabel(r.severity_code)}</TableCell>
                {d.types.map((ty) => (
                  <TableCell key={ty} align="right">
                    {count(r.counts[ty] ?? 0, { severity: r.severity_code, issue_type: ty })}</TableCell>))}
              </TableRow>))}
          </TableBody>
        </Table>
      </Card>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0,1fr)', md: 'repeat(2, minmax(0,1fr))' } }}>
        <Card title={t('issues.dash.byArea')} bodySx={{ px: 0 }}>
          <Table size="small">
            <TableBody>
              {d.by_area.map((r) => (
                <TableRow key={r.area_id}>
                  <TableCell>{r.bfc_set_code === 'AS_IS' ? t('issues.dash.asIs') : ''}{r.hier_code} {r.name}</TableCell>
                  <TableCell align="right">{count(r.open, { area: String(r.area_id) })}</TableCell>
                </TableRow>))}
              <TableRow>
                <TableCell sx={{ color: 'text.secondary' }}>{t('issues.dash.noArea')}</TableCell>
                <TableCell align="right">{count(d.no_area, { area: 'none' })}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <Typography sx={{ fontSize: 12, color: 'text.secondary', px: 2, pt: 1 }}>{t('issues.dash.areaNote')}</Typography>
        </Card>
        <Card title={t('issues.dash.byRaiser')} bodySx={{ px: 0 }}>
          <Table size="small">
            <TableBody>
              {d.by_raiser.length === 0 && (
                <TableRow><TableCell sx={{ color: 'text.secondary' }}>{t('issues.dash.noneOpen')}</TableCell></TableRow>)}
              {d.by_raiser.map((r) => (
                <TableRow key={r.stakeholder_id}>
                  <TableCell>{r.name}</TableCell>
                  <TableCell align="right">{count(r.open, { raiser: r.stakeholder_id })}</TableCell>
                </TableRow>))}
            </TableBody>
          </Table>
        </Card>
      </Box>
    </Box>
  );
}
