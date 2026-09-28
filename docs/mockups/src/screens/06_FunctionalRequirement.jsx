import React from 'react';
import { Box, Button, TextField, MenuItem, Typography, Table, TableBody, TableRow, TableCell, TableHead } from '@mui/material';
import LockOutlined from '@mui/icons-material/LockOutlined';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, Segmented, PurpleTile, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const RATES = [['Simple', 5], ['Medium', 10], ['Complex', 15], ['Very complex', 25]];

export default function FunctionalRequirement() {
  return (
    <Shell active="fr" crumbs={['Scope', 'Functional requirements', 'FR-0013']}>
      <PageHeader
        title={<><Code tone="navy" sx={{ fontSize: 22, mr: 1.5 }}>FR-0013</Code>Credit decision batch</>}
        subtitle="What the vendor builds · always sits under one solution"
        actions={<><Button variant="outlined">Cancel</Button><Button variant="contained">Save FR</Button></>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 360px', gap: 2 }}>
        <Card title="Functional requirement" action={<Status tone="ok" size="sm">Saved · v2</Status>}>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <TextField label="Parent solution" select defaultValue="s" required fullWidth><MenuItem value="s">SOL-0004 · Credit automation</MenuItem></TextField>
            <TextField label="To-Be system" select defaultValue="n" fullWidth><MenuItem value="n">New sales system (S/4 SD)</MenuItem></TextField>
            <TextField label="FR name" defaultValue="Credit decision batch" required fullWidth sx={{ gridColumn: '1 / -1' }} />
          </Box>
          <Box sx={{ display: 'flex', gap: 4 }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}><SectionLabel>TYPE</SectionLabel><Segmented options={['Screen', 'Batch', 'Interface', 'Report']} value="Batch" label="FR type" /></Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}><SectionLabel>COMPLEXITY</SectionLabel><Segmented options={['Simple', 'Medium', 'Complex', 'Very complex']} value="Complex" label="Complexity" /></Box>
          </Box>
          <TextField label="Description" defaultValue="Runs every 10 minutes. For each new order, calculates the remaining credit limit and sets the credit result (OK / HOLD). Held orders are routed to the credit officer's queue." multiline minRows={3} fullWidth />
          <TextField label="Acceptance criteria" defaultValue={'1. Orders within the limit are confirmed with no manual step.\n2. Orders over the limit are held and the shortfall is shown.\n3. A run of 5,000 orders completes within 3 minutes.'} multiline minRows={3} fullWidth />
          <TextField label="Direct link to a business function (optional)" select defaultValue="" fullWidth SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
            helperText="Only when no business requirement covers it — normally the link runs through BR-0043.">
            <MenuItem value="">None — linked through the requirement</MenuItem>
          </TextField>
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <PurpleTile label="EFFORT" value="15" unit="person-days" note="Batch × Complex · rate card v3" />
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', p: 1.75, borderRadius: `${RADIUS.field + 2}px`, bgcolor: SURFACE.card, border: `1px solid ${SURFACE.border}` }}>
            <LockOutlined sx={{ fontSize: 18, color: BRAND.purpleLight, mt: '1px' }} />
            <Typography sx={{ fontSize: 13, color: SURFACE.textSecondary }}>Fixed when saved. A later rate-card change does not move scope that is already agreed.</Typography>
          </Box>
          <Card title="Rate card · Batch">
            <Table size="small">
              <TableHead><TableRow><TableCell>Complexity</TableCell><TableCell align="right">Person-days</TableCell></TableRow></TableHead>
              <TableBody>
                {RATES.map(([c, d]) => {
                  const on = c === 'Complex';
                  return (
                    <TableRow key={c} sx={{ bgcolor: on ? BRAND.purpleTint : 'transparent' }}>
                      <TableCell sx={{ fontWeight: on ? 700 : 400, color: on ? '#FFFFFF' : undefined }}>{c}</TableCell>
                      <TableCell align="right" sx={{ fontFamily: MONO, color: on ? BRAND.purpleLight : undefined }}>{d}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', color: SURFACE.textMuted }}><InfoOutlined sx={{ fontSize: 16 }} /><Typography sx={{ fontSize: 12.5 }}>Adjusted for this engagement: +0%</Typography></Box>
          </Card>
          <Card title="Traceability" bodySx={{ gap: 1 }}>
            {[['BFC', '01.02.01.02.01', 'purple'], ['BR', 'BR-0043', 'purple'], ['Solution', 'SOL-0004', 'navy'], ['System', 'New sales system', 'teal']].map(([k, v, t]) => (
              <Box key={k} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Typography sx={{ width: 72, fontSize: 13, color: SURFACE.textMuted }}>{k}</Typography><Tag tone={t}>{v}</Tag>
              </Box>
            ))}
          </Card>
        </Box>
      </Box>
    </Shell>
  );
}
