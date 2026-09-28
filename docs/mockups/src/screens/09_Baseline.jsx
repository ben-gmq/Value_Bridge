import React from 'react';
import { Box, Button, TextField, Typography, Table, TableHead, TableBody, TableRow, TableCell } from '@mui/material';
import LayersOutlined from '@mui/icons-material/LayersOutlined';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, Segmented, PurpleTile, Tile, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const VERSIONS = [
  ['Working', 'Not frozen · 57 changes', null, true],
  ['v1.2', 'Frozen 08-29 · client approved', 'ok'],
  ['v1.1', 'Frozen 07-31', 'ok'],
  ['v1.0', 'Frozen 06-30 · first baseline', 'ok'],
];
const CHANGES = [
  ['Added', 'FR-0031', 'Credit hold notification', 'Interface · Simple', '+4'],
  ['Added', 'BR-0061', 'Issue credit note', 'New level-5 function', '+18'],
  ['Changed', 'FR-0013', 'Credit decision batch', 'Medium → Complex', '+5'],
  ['Changed', 'BR-0043', 'Check credit', 'Business logic', '0'],
  ['Moved', '01.02.02.03', 'Pack order', '01.02.02 → 01.02.03', '0'],
  ['Deleted', 'FR-0019', 'Manual credit form', 'Replaced by FR-0012', '−10'],
  ['Added', 'SOL-0019', 'Rule standards', 'Org & rules', '0'],
];
const KIND = { Added: 'purple', Changed: 'navy', Moved: 'neutral', Deleted: 'teal' };

export default function Baseline() {
  return (
    <Shell active="baseline" crumbs={['Control', 'Baselines', 'v1.2 → Working']}>
      <PageHeader title="Baselines" subtitle="Freeze scope, then show every change since as person-days"
        actions={<><Button variant="outlined">Compare versions</Button><Button variant="contained" startIcon={<LayersOutlined />}>Freeze v1.3</Button></>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '320px minmax(0,1fr)', gap: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Card title="Versions" bodySx={{ gap: 1 }}>
            {VERSIONS.map(([v, note, st, cur]) => (
              <Box key={v} sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.5, height: 52, borderRadius: `${RADIUS.field}px`, bgcolor: cur ? BRAND.purpleTint : SURFACE.raised, outline: cur ? '1px solid rgba(120,72,220,0.45)' : 'none' }}>
                <Code tone={cur ? 'purple' : 'navy'} sx={{ fontSize: 14, fontWeight: 600, width: 64 }}>{v}</Code>
                <Typography sx={{ fontSize: 13, color: SURFACE.textSecondary, flexGrow: 1 }}>{note}</Typography>
              </Box>
            ))}
          </Card>
          <Card title="Before freezing v1.3" bodySx={{ gap: 1.25 }}>
            <TextField label="Baseline note" defaultValue="After credit workshop — scope for vendor RFP" size="small" fullWidth />
            <SectionLabel>CONSISTENCY CHECK</SectionLabel>
            <Status tone="ok" size="sm">Hierarchy codes consistent</Status>
            <Status tone="ok" size="sm">Every level-5 function has a BR</Status>
            <Status tone="caution" size="sm">2 BRs have no solution</Status>
            <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Only an owner can freeze. 25 tables are frozen in one step.</Typography>
          </Card>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.35fr) repeat(3, minmax(0,1fr))', gap: 2, flexShrink: 0 }}>
            <PurpleTile label="NET CHANGE SINCE v1.2" value="+280" unit="person-days" note="+15% on 1,860 in v1.2" />
            <Tile label="Added" value="+340" note="31 objects" />
            <Tile label="Removed" value="−60" note="5 objects" />
            <Tile label="Changes needing a CR" value="4" tone="caution" note="Above the 20-day threshold" />
          </Box>
          <Card title="Changes · v1.2 → Working" action={<Segmented size="sm" options={['All 57', 'Added 31', 'Changed 18', 'Deleted 5', 'Moved 3']} value="All 57" label="Filter changes" />} bodySx={{ px: 0 }}>
            <Table size="small">
              <TableHead><TableRow><TableCell sx={{ pl: 2.5, width: 110 }}>Change</TableCell><TableCell sx={{ width: 130 }}>Object</TableCell><TableCell>Name</TableCell><TableCell>What changed</TableCell><TableCell align="right" sx={{ pr: 2.5, width: 130 }}>Person-days</TableCell></TableRow></TableHead>
              <TableBody>
                {CHANGES.map(([k, code, name, what, d]) => (
                  <TableRow key={code}>
                    <TableCell sx={{ pl: 2.5 }}><Tag tone={KIND[k]}>{k}</Tag></TableCell>
                    <TableCell><Code tone={code.startsWith('BR') ? 'purple' : code.startsWith('0') ? 'muted' : 'navy'} sx={{ fontSize: 12.5 }}>{code}</Code></TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>{name}</TableCell>
                    <TableCell sx={{ color: SURFACE.textSecondary }}>{what}</TableCell>
                    <TableCell align="right" sx={{ pr: 2.5, fontFamily: MONO, color: d.startsWith('+') ? BRAND.purpleLight : d.startsWith('−') ? BRAND.tealText : SURFACE.textMuted }}>{d}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </Box>
      </Box>
    </Shell>
  );
}
