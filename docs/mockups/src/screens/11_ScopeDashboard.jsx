import React from 'react';
import { Box, Button, Typography, Table, TableHead, TableBody, TableRow, TableCell, LinearProgress } from '@mui/material';
import { Shell, PageHeader, Card, Code, Tag, Status, PurpleTile, Tile, Segmented, BRAND, SURFACE, STATUS_COLOR_MAP, RADIUS, MONO } from '../kit.jsx';

// Slice 12 target (docs/slice12_kpis.md, S12-1): the built dashboard S1–S6 + M1, plus S7–S11 — DFD readiness,
// entities without fields, open freeze warnings, effort by solution and the business-area switch.
// Figures match the showcase project (seeds/demo_showcase.py), so it sits beside the live screenshots.
const AREAS = [
  ['01', 'Sales', 7, 7, 7, 7, 86, 37],
  ['02', 'Procurement', 5, 5, 5, 4, 80, 19],
  ['03', 'Logistics', 6, 6, 6, 4, 67, 18],
  ['04', 'Finance', 7, 7, 6, 7, 71, 40],
];
const BY_SOLUTION = [
  ['SOL-0001', 'Order-to-cash on S/4HANA', 32], ['SOL-0005', 'Procure-to-pay on S/4HANA', 25],
  ['SOL-0007', 'Warehouse on WMS', 18], ['SOL-0002', 'Credit automation', 16], ['SOL-0003', 'EDI order intake', 12],
];
const num = { fontFamily: MONO, fontSize: 13.5 };

function Bar({ value, tone = 'ok' }) {
  return <LinearProgress variant="determinate" value={value} aria-label={`${value}%`}
    sx={{ height: 6, borderRadius: 3, bgcolor: SURFACE.raised, '& .MuiLinearProgress-bar': { bgcolor: STATUS_COLOR_MAP[tone].dot, borderRadius: 3 } }} />;
}

export default function ScopeDashboard() {
  return (
    <Shell current active="home" crumbs={['Scope', 'Dashboard']}>
      <PageHeader eyebrow={<Code tone="muted">CSR27</Code>} title="2027 Core Systems Renewal"
        subtitle="4 business areas · scope, requirement coverage and baselines · as of 16 Oct 2026"
        actions={<>
          <Segmented label="Business area" value="All areas" options={['All areas', 'Sales', 'Procurement', 'Logistics', 'Finance']} size="sm" />
          <Button variant="contained">Open baselines</Button>
        </>} />

      <Box sx={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 1fr 1fr', gap: 1.5, flexShrink: 0 }}>
        <PurpleTile label="REQUIREMENTS IN BASELINE V1.1" value="24" unit="of 25 today" note="1 added · 1 changed since v1.1" />
        <Tile label="Requirements that reach an FR" value="76%" note="19 of 25 · 22 functional requirements" />
        <Tile label="No solution yet" value="2" tone="caution" note="0 FRs without a requirement" />
        <Tile label="Effort in scope" value="114 days" note="22 FRs rated · 0 not yet" />
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1.5, flexShrink: 0 }}>
        <Tile label="Processes not ready for the DFD rule" value="1" tone="escalate" note="04.01.04 Issue credit note · 0 amber · 24 ready" />
        <Tile label="Open freeze warnings" value="4" tone="caution" note="All on one process · resolve before freezing v1.2" />
        <Tile label="Data entities without fields" value="0" tone="ok" note="of 17 entities · 0 with keys only" />
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 1.5, flexGrow: 1, minHeight: 0 }}>
        <Card title="Requirements by business area" action={<Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Reach = requirements with at least one FR</Typography>}>
          <Table size="small" aria-label="Requirements by business area" sx={{ '& td, & th': { px: 1.25 } }}>
            <TableHead><TableRow>
              <TableCell>Area</TableCell><TableCell align="right">Processes</TableCell><TableCell align="right">Requirements</TableCell>
              <TableCell align="right">Confirmed</TableCell><TableCell align="right">FRs</TableCell><TableCell>Reach</TableCell><TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>Effort (d)</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {AREAS.map(([c, n, p, r, cf, f, reach, e]) => (
                <TableRow key={c}>
                  <TableCell><Code tone="muted" sx={{ mr: 1 }}>{c}</Code><b>{n}</b></TableCell>
                  <TableCell align="right" sx={num}>{p}</TableCell><TableCell align="right" sx={num}>{r}</TableCell>
                  <TableCell align="right" sx={num}>{cf}</TableCell><TableCell align="right" sx={num}>{f}</TableCell>
                  <TableCell><Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Box sx={{ width: 64 }}><Bar value={reach} /></Box><Box sx={{ ...num, fontSize: 12.5, width: 34, textAlign: 'right' }}>{reach}%</Box></Box></TableCell>
                  <TableCell align="right" sx={num}>{e}</TableCell>
                </TableRow>
              ))}
              <TableRow sx={{ '& td': { fontWeight: 700, borderBottom: 0 } }}>
                <TableCell>Project total</TableCell><TableCell align="right" sx={num}>25</TableCell><TableCell align="right" sx={num}>25</TableCell>
                <TableCell align="right" sx={num}>24</TableCell><TableCell align="right" sx={num}>22</TableCell>
                <TableCell><Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Box sx={{ width: 64 }}><Bar value={76} /></Box><Box sx={{ ...num, fontSize: 12.5, width: 34, textAlign: 'right' }}>76%</Box></Box></TableCell>
                <TableCell align="right" sx={num}>114</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, minHeight: 0 }}>
          <Card title="Effort by solution" action={<Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>man-days · top 5 of 8</Typography>} bodySx={{ gap: 1.1 }}>
            {BY_SOLUTION.map(([code, name, d]) => (
              <Box key={code} sx={{ display: 'grid', gridTemplateColumns: '1fr 120px 28px', alignItems: 'center', gap: 1.5 }}>
                <Typography noWrap sx={{ fontSize: 13.5 }}><Code sx={{ mr: 1 }}>{code}</Code>{name}</Typography>
                <Box sx={{ height: 8, borderRadius: 4, bgcolor: SURFACE.raised }}><Box sx={{ width: `${(d / 32) * 100}%`, height: '100%', borderRadius: 4, bgcolor: BRAND.purpleMid }} /></Box>
                <Box sx={{ ...num, textAlign: 'right', fontWeight: 600 }}>{d}</Box>
              </Box>
            ))}
          </Card>
          <Card title="Baselines" action={<Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Sign-off = the client's approval</Typography>} bodySx={{ gap: 1 }}>
            {[['v1.1', '16 Oct 2026 · Awaiting sign-off', 'Frozen', 'navy'], ['v1.0', 'Approved by T. Kato (Kaito CIO)', 'Agreed', 'ok']].map(([v, note, s, tone]) => (
              <Box key={v} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 1.5, py: 1, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.raised }}>
                <Code sx={{ fontSize: 14, fontWeight: 600 }}>{v}</Code>
                <Typography sx={{ fontSize: 13, color: SURFACE.textSecondary, flexGrow: 1 }}>{note}</Typography>
                {tone === 'ok' ? <Status tone="ok" size="sm">{s}</Status> : <Tag tone="navy">{s}</Tag>}
              </Box>
            ))}
          </Card>
        </Box>
      </Box>
    </Shell>
  );
}
