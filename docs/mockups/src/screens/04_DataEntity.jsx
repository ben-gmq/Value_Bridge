import React from 'react';
import { Box, Button, TextField, MenuItem, Typography, Checkbox, Switch, FormControlLabel, Table, TableHead, TableBody, TableRow, TableCell, Select, InputBase } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import FileDownloadOutlined from '@mui/icons-material/FileDownloadOutlined';
import DragIndicatorRounded from '@mui/icons-material/DragIndicatorRounded';
import KeyRounded from '@mui/icons-material/KeyRounded';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const FIELDS = [
  ['Order no.', 'STRING', '12', true, true, ''],
  ['Order date', 'DATE', '', true, false, ''],
  ['Customer code', 'STRING', '10', true, false, 'DE-0004 Customer'],
  ['Order amount', 'DECIMAL', '13,0', true, false, ''],
  ['Credit result', 'CODE', '2', false, false, ''],
  ['Order status', 'CODE', '2', true, false, ''],
  ['Requested date', 'DATE', '', false, false, ''],
  ['Created at', 'DATETIME', '', true, false, ''],
];

const cellInput = { fontSize: 13.5, height: 34, px: 1.25, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.field, border: `1px solid ${SURFACE.border}`, width: '100%' };

export default function DataEntity() {
  return (
    <Shell active="de" crumbs={['Scope', 'Data entities', 'DE-0011 Order']}>
      <PageHeader
        title={<><Code tone="teal" sx={{ fontSize: 22, mr: 1.5 }}>DE-0011</Code>Order</>}
        subtitle="A data store in the DFD · 24 fields · used by 11 requirements"
        actions={<>
          <Button variant="outlined" startIcon={<FileDownloadOutlined />}>Excel template</Button>
          <Button variant="contained">Save entity</Button>
        </>} />

      <Card sx={{ flexShrink: 0 }} bodySx={{ py: 2.25, flexDirection: 'row', alignItems: 'center', gap: 2 }}>
        <TextField label="Entity name" defaultValue="Order" sx={{ width: 220 }} required />
        <TextField label="Owning area" select defaultValue="s" sx={{ width: 200 }}><MenuItem value="s">01 Sales</MenuItem></TextField>
        <TextField label="Description" defaultValue="One customer order. Its lines are held in DE-0012 Order line." sx={{ flexGrow: 1 }} />
        <FormControlLabel control={<Switch defaultChecked color="secondary" />} label={<Typography sx={{ fontSize: 14 }}>Master candidate</Typography>} />
      </Card>

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 330px', gap: 2 }}>
        <Card title="Fields" action={<Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}><Typography sx={{ fontSize: 13, color: SURFACE.textMuted }}>8 of 24</Typography><Button size="small" variant="outlined" startIcon={<AddRounded />}>Add field</Button></Box>} bodySx={{ px: 1.5 }}>
          <Table size="small" sx={{ tableLayout: 'fixed', '& td': { borderBottom: `1px solid ${SURFACE.border}`, py: 0.75 } }}>
            <TableHead><TableRow>
              <TableCell sx={{ width: 28 }} /><TableCell>Field name</TableCell><TableCell sx={{ width: 150 }}>Data type</TableCell><TableCell sx={{ width: 96 }}>Length</TableCell>
              <TableCell align="center" sx={{ width: 76 }}>Required</TableCell><TableCell align="center" sx={{ width: 50 }}>PK</TableCell><TableCell sx={{ width: 180 }}>Foreign key →</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {FIELDS.map(([n, t, len, req, pk, fk]) => (
                <TableRow key={n}>
                  <TableCell sx={{ px: 0.5 }}><DragIndicatorRounded sx={{ fontSize: 18, color: SURFACE.textMuted }} /></TableCell>
                  <TableCell><InputBase defaultValue={n} inputProps={{ 'aria-label': 'Field name' }} sx={{ ...cellInput, fontWeight: pk ? 700 : 400 }} /></TableCell>
                  <TableCell>
                    <Select value={t} size="small" inputProps={{ 'aria-label': 'Data type' }} sx={{ width: '100%', height: 34, fontFamily: MONO, fontSize: 13 }}>
                      <MenuItem value={t}>{t}</MenuItem>
                    </Select>
                  </TableCell>
                  <TableCell><InputBase defaultValue={len} placeholder="—" inputProps={{ 'aria-label': 'Length' }} sx={{ ...cellInput, fontFamily: MONO }} /></TableCell>
                  <TableCell align="center"><Checkbox checked={req} inputProps={{ 'aria-label': 'Required' }} sx={{ '&.Mui-checked': { color: BRAND.purpleMid } }} /></TableCell>
                  <TableCell align="center">{pk ? <KeyRounded aria-label="Primary key" sx={{ fontSize: 18, color: BRAND.amber }} /> : <Checkbox inputProps={{ 'aria-label': 'Primary key' }} />}</TableCell>
                  <TableCell>{fk ? <Tag tone="teal">→ {fk}</Tag> : <Typography sx={{ fontSize: 13, color: SURFACE.textMuted }}>—</Typography>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Card title="Model checks">
            <Status tone="ok" size="sm">Primary key set · Order no.</Status>
            <Status tone="ok" size="sm">FK target DE-0004 has a primary key</Status>
            <Status tone="caution" size="sm">Credit result has no code list yet</Status>
          </Card>
          <Card title="Used by requirements" action={<Code tone="muted">11</Code>} bodySx={{ gap: 1 }}>
            {[['BR-0041', 'Enter order', 'C'], ['BR-0042', 'Amend order', 'R U'], ['BR-0043', 'Check credit', 'R U'], ['BR-0044', 'Confirm order', 'R U'], ['BR-0045', 'Allocate stock', 'R']].map(([c, n, crud]) => (
              <Box key={c} sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.5, height: 38, borderRadius: `${RADIUS.field}px`, bgcolor: c === 'BR-0043' ? BRAND.purpleTint : SURFACE.raised }}>
                <Code tone="purple" sx={{ fontSize: 12 }}>{c}</Code><Typography sx={{ fontSize: 13.5, flexGrow: 1 }}>{n}</Typography>
                <Box sx={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: BRAND.purpleLight }}>{crud}</Box>
              </Box>
            ))}
            <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted, px: 0.5 }}>6 more · used by 2 business areas</Typography>
          </Card>
        </Box>
      </Box>
    </Shell>
  );
}
