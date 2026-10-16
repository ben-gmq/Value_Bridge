import React from 'react';
import { Box, Button, Typography, Table, TableHead, TableBody, TableRow, TableCell } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded';
import EastRounded from '@mui/icons-material/EastRounded';
import { Shell, PageHeader, Card, Code, Tag, Status, LevelBadge, Segmented, SectionLabel, BRAND, SURFACE, STATUS_COLOR_MAP, RADIUS, MONO } from '../kit.jsx';

// Slice 11 target (docs/slice11_schema.md, D-59 / D-60b / D-61, S11-5): a BR in its process panel with numbered
// requirement lines, the attributes it uses with C / R / U, and the data it needs copied between systems — each flow
// covered by an Interface or Migration FR, or offered as one. Names follow the showcase project.
const TREE = [
  [1, '01', 'Sales'], [2, '01.01', 'Order management'], [3, '01.01.01', 'Receive order'], [3, '01.01.02', 'Check credit', true],
  [3, '01.01.03', 'Confirm order'], [3, '01.01.04', 'Amend order'], [3, '01.01.05', 'Cancel order'], [2, '01.02', 'Pricing'],
  [3, '01.02.01', 'Maintain price list'], [3, '01.02.02', 'Approve discount'], [1, '02', 'Procurement'], [2, '02.01', 'Purchasing'],
  [3, '02.01.01', 'Raise purchase request'], [3, '02.01.02', 'Approve purchase request'],
];
const LINES = [
  ['1', 'Rule', 'Must', 'Only customers with an active account may be granted credit.'],
  ['2', 'Calculation', 'Must', 'Remaining limit = credit limit − open receivables − open orders.'],
  ['3', 'Validation', 'Must', 'If the order amount exceeds the remaining limit, the credit result is HOLD.'],
  ['4', 'Control', 'Should', "Key accounts may exceed the limit by 10% with the credit manager's approval."],
  ['5', 'Output', 'Must', 'The credit result and any shortfall go back to Sales.'],
];
const USES = [
  ['DE-0002', 'Credit limit', 'R', ['customer_id', 'limit_amount', 'currency']],
  ['DE-0003', 'Sales order', 'R', ['order_id', 'customer_id', 'total_amount']],
  ['DE-0003', 'Sales order', 'U', ['status']],
];
const FLOWS = [
  ['DE-0003', 'Sales order', 'EDI hub', 'SAP S/4HANA', 'On every inbound order', ['FR-0010', 'Interface']],
  ['DE-0002', 'Credit limit', 'SalesPro v8', 'SAP S/4HANA', 'Once, at cut-over', null],
];

function Crud({ k }) {
  return <Box component="span" sx={{ display: 'inline-grid', placeItems: 'center', width: 22, height: 22, borderRadius: '7px', fontFamily: MONO, fontSize: 12, fontWeight: 700, bgcolor: BRAND.purpleMid, color: '#FFFFFF' }}>{k}</Box>;
}

export default function StructuredRequirement() {
  return (
    <Shell current active="bfc" crumbs={['Scope', 'Business functions', '01.01.02 Check credit']}>
      <PageHeader title="Business function chart" subtitle="Five levels, coded automatically · each process step owns exactly one business requirement"
        actions={<Segmented label="Chart" value="To-be chart" options={['To-be chart', 'As-is chart']} size="sm" />} />

      <Box sx={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 1.5, flexGrow: 1, minHeight: 0 }}>
        <Card title="Hierarchy" bodySx={{ gap: 0.25, pt: 0.5 }}>
          {TREE.map(([lvl, code, name, on]) => (
            <Box key={code} sx={{ display: 'flex', alignItems: 'center', gap: 1, height: 33, pl: (lvl - 1) * 1.75 + 0.75, pr: 1, borderRadius: `${RADIUS.field}px`,
              bgcolor: on ? BRAND.purpleTint : 'transparent', border: on ? `1px solid ${BRAND.purpleMid}` : '1px solid transparent' }}>
              <LevelBadge level={lvl} />
              <Code tone="muted" sx={{ fontSize: 12 }}>{code}</Code>
              <Typography noWrap sx={{ fontSize: 13.5, fontWeight: lvl < 3 || on ? 700 : 500, flexGrow: 1 }}>{name}</Typography>
              {lvl === 3 && <CheckCircleRounded sx={{ fontSize: 18, color: STATUS_COLOR_MAP.ok.dot }} />}
            </Box>
          ))}
        </Card>

        <Card bodySx={{ gap: 1.75, overflow: 'hidden' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
            <LevelBadge level={3} /><Code tone="muted">01.01.02</Code>
            <Typography sx={{ fontSize: 13, color: SURFACE.textMuted }}>Sales › Order management</Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Status tone="ok" size="sm">Ready</Status><Tag tone="navy">BR-0002</Tag><Tag>Confirmed</Tag>
          </Box>
          <Box>
            <Typography sx={{ fontSize: 22, fontWeight: 700 }}>Check credit</Typography>
            <Typography sx={{ fontSize: 14.5, color: SURFACE.textSecondary, mt: 0.25 }}>Decide acceptance against the customer's remaining credit limit</Typography>
          </Box>

          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
              <SectionLabel>REQUIREMENT LINES · 5</SectionLabel><Box sx={{ flexGrow: 1 }} />
              <Button size="small" startIcon={<AddRounded />}>Add line</Button>
            </Box>
            <Table size="small" aria-label="Requirement lines">
              <TableHead><TableRow><TableCell sx={{ width: 100 }}>#</TableCell><TableCell sx={{ width: 120 }}>Kind</TableCell><TableCell sx={{ width: 90 }}>Priority</TableCell><TableCell>Requirement</TableCell></TableRow></TableHead>
              <TableBody>
                {LINES.map(([n, kind, prio, text]) => (
                  <TableRow key={n}>
                    <TableCell><Code>BR-0002.{n}</Code></TableCell>
                    <TableCell><Tag tone="neutral">{kind}</Tag></TableCell>
                    <TableCell><Tag tone={prio === 'Must' ? 'purple' : 'teal'}>{prio}</Tag></TableCell>
                    <TableCell sx={{ color: SURFACE.text }}>{text}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1.25fr', gap: 1.5, minHeight: 0 }}>
            <Box sx={{ borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.raised, p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.1 }}>
              <SectionLabel>DATA IT USES · BY ATTRIBUTE</SectionLabel>
              {USES.map(([de, name, crud, fields]) => (
                <Box key={de + crud} sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.6 }}>
                  <Crud k={crud} />
                  <Typography sx={{ fontSize: 13.5, fontWeight: 600, mx: 0.5 }}>{name}</Typography>
                  {fields.map((f) => <Tag key={f} tone="teal" sx={{ fontFamily: MONO, fontWeight: 500, height: 22, fontSize: 11.5 }}>{f}</Tag>)}
                </Box>
              ))}
            </Box>

            <Box sx={{ borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.raised, p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.1 }}>
              <SectionLabel>DATA BETWEEN SYSTEMS</SectionLabel>
              {FLOWS.map(([de, name, from, to, when, fr]) => (
                <Box key={de} sx={{ borderRadius: `${RADIUS.field}px`, border: `1px solid ${SURFACE.border}`, bgcolor: SURFACE.card, px: 1.5, py: 1.1, display: 'flex', flexDirection: 'column', gap: 0.6 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Code tone="teal">{de}</Code><Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{name}</Typography>
                    <Box sx={{ flexGrow: 1 }} /><Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>{when}</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Tag tone="navy">{from}</Tag><EastRounded sx={{ fontSize: 16, color: SURFACE.textMuted }} /><Tag tone="navy">{to}</Tag>
                    <Box sx={{ flexGrow: 1 }} />
                    {fr ? <Status tone="ok" size="sm">Covered by {fr[0]} · {fr[1]}</Status>
                      : <><Status tone="caution" size="sm">No FR yet</Status><Button size="small" variant="outlined">Create Migration FR</Button></>}
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        </Card>
      </Box>
    </Shell>
  );
}
