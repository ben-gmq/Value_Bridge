import React from 'react';
import { Box, Button, Typography, Table, TableHead, TableBody, TableRow, TableCell, Tabs, Tab } from '@mui/material';
import FileDownloadOutlined from '@mui/icons-material/FileDownloadOutlined';
import PersonAddAltOutlined from '@mui/icons-material/PersonAddAltOutlined';
import ArrowRightAltRounded from '@mui/icons-material/ArrowRightAltRounded';
import { Shell, PageHeader, Card, Code, Tag, Status, Steps, Tile, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const ROWS = [
  [4, 'BR-0043', 'update', 'Business logic', 'limit − open AR', 'limit − open AR − open orders'],
  [5, 'BR-0044', 'update', 'Accountable', 'Sales manager', 'Order manager'],
  [9, 'BR-0061', 'new', 'Requirement', '—', 'Issue credit note'],
  [10, 'BR-0062', 'new', 'Requirement', '—', 'Approve write-off'],
  [12, 'BR-0048', 'error', 'Business function', '01.02.02.01.02', '01.02.09.01.02 — code not found'],
  [17, 'BR-0052', 'update', 'Frequency', 'Daily', 'Per receipt'],
  [21, 'BR-0070', 'error', 'Accountable', '—', 'Two accountable roles — only one allowed'],
  [24, 'BR-0063', 'new', 'Requirement', '—', 'Reconcile bank statement'],
];
const TONE = { new: ['purple', 'New'], update: ['navy', 'Update'], error: ['escalate', 'Error'] };

export default function ImportPreview() {
  return (
    <Shell active="import" crumbs={['Control', 'Bulk import', 'business_requirements_0924.xlsx']}>
      <PageHeader title="Bulk import — business requirements"
        subtitle="Validated and held apart — nothing is written until you commit"
        actions={<Steps steps={['Upload', 'Validate', 'Preview', 'Commit']} current={2} />} />

      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))', gap: 2, flexShrink: 0 }}>
        <Tile label="Rows in file" value="142" />
        <Tile label="New" value="12" note="Created on commit" />
        <Tile label="Update" value="27" note="Before → after shown" />
        <Tile label="Unchanged" value="101" note="Skipped" />
        <Tile label="Errors" value="2" tone="escalate" note="Fix before commit" />
      </Box>

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 330px', gap: 2 }}>
        <Card bodySx={{ px: 0, pt: 0.5 }}>
          <Tabs value={0} sx={{ px: 2, borderBottom: `1px solid ${SURFACE.border}`, '& .MuiTabs-indicator': { bgcolor: BRAND.purpleMid, height: 3, borderRadius: 2 }, '& .Mui-selected': { color: '#FFFFFF !important' } }}>
            <Tab label="Changes 41" /><Tab label="Errors 2" /><Tab label="Unchanged 101" />
          </Tabs>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell sx={{ pl: 2.5, width: 60 }}>Row</TableCell><TableCell sx={{ width: 100 }}>Key</TableCell><TableCell sx={{ width: 96 }}>Action</TableCell><TableCell sx={{ width: 150 }}>Field</TableCell><TableCell>Before → after</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {ROWS.map(([row, key, act, field, before, after]) => (
                <TableRow key={row} sx={{ bgcolor: act === 'error' ? 'rgba(224,105,90,0.06)' : 'transparent' }}>
                  <TableCell sx={{ pl: 2.5, fontFamily: MONO, color: SURFACE.textMuted }}>{row}</TableCell>
                  <TableCell><Code tone="purple" sx={{ fontSize: 12.5 }}>{key}</Code></TableCell>
                  <TableCell>{act === 'error' ? <Status tone="escalate" size="sm">Error</Status> : <Tag tone={TONE[act][0]}>{TONE[act][1]}</Tag>}</TableCell>
                  <TableCell sx={{ color: SURFACE.textSecondary, whiteSpace: 'nowrap' }}>{field}</TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                      {before !== '—' && <Typography noWrap sx={{ fontSize: 13.5, color: SURFACE.textMuted, textDecoration: act === 'update' ? 'line-through' : 'none', maxWidth: 240 }}>{before}</Typography>}
                      {before !== '—' && <ArrowRightAltRounded sx={{ fontSize: 18, color: SURFACE.textMuted }} />}
                      <Typography noWrap sx={{ fontSize: 13.5, color: act === 'error' ? '#F08A7D' : SURFACE.text, fontWeight: act === 'error' ? 400 : 500 }}>{after}</Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Card title="New stakeholders" action={<Code tone="muted">2</Code>} bodySx={{ gap: 1 }}>
            {[['Ono', 'Finance · AR'], ['Hayashi', 'Treasury']].map(([n, o]) => (
              <Box key={n} sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.5, height: 44, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.raised }}>
                <PersonAddAltOutlined sx={{ fontSize: 18, color: BRAND.purpleLight }} />
                <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{n}</Typography><Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>{o}</Typography>
              </Box>
            ))}
            <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Created as client stakeholders. They get no login.</Typography>
          </Card>
          <Box component="section" sx={{ borderRadius: `${RADIUS.card}px`, bgcolor: SURFACE.rail, p: 2.5, display: 'flex', flexDirection: 'column', gap: 1.25, mt: 'auto' }}>
            <Typography sx={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', color: '#CFC6F5' }}>ALL ROWS OR NONE</Typography>
            <Typography sx={{ fontSize: 15, fontWeight: 700, color: '#FFFFFF' }}>Fix 2 errors to commit</Typography>
            <Typography sx={{ fontSize: 13, color: '#CFC6F5' }}>Every row is checked again at commit and saved in one transaction.</Typography>
            <Button variant="outlined" startIcon={<FileDownloadOutlined />} sx={{ borderColor: 'rgba(255,255,255,0.35)', color: '#FFFFFF' }}>Download error report</Button>
            <Button variant="contained" disabled sx={{ '&.Mui-disabled': { bgcolor: 'rgba(255,255,255,0.10)', color: '#A79FD4' } }}>Commit 39 changes</Button>
          </Box>
        </Box>
      </Box>
    </Shell>
  );
}
