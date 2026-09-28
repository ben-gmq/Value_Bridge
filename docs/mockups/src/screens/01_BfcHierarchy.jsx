import React from 'react';
import { Box, Button, TextField, MenuItem, IconButton, Typography, Divider } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import ChevronRightRounded from '@mui/icons-material/ChevronRightRounded';
import DragIndicatorRounded from '@mui/icons-material/DragIndicatorRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import FileDownloadOutlined from '@mui/icons-material/FileDownloadOutlined';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, LevelBadge, Raci, KV, Status, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const TREE = [
  { l: 1, code: '01', name: 'Sales', open: true, n: 142 },
  { l: 2, code: '01.02', name: 'Order management', open: true, n: 38 },
  { l: 3, code: '01.02.01', name: 'Order intake', open: true, n: 12 },
  { l: 4, code: '01.02.01.01', name: 'Receive order', open: false, n: 2 },
  { l: 4, code: '01.02.01.02', name: 'Credit check', open: true, n: 2 },
  { l: 5, code: '01.02.01.02.01', name: 'Check credit', sel: true },
  { l: 5, code: '01.02.01.02.02', name: 'Confirm order' },
  { l: 4, code: '01.02.01.03', name: 'Stock preparation', open: false, n: 2 },
  { l: 3, code: '01.02.02', name: 'Shipping', open: false, n: 9 },
  { l: 2, code: '01.03', name: 'Billing & receivables', open: false, n: 21 },
  { l: 1, code: '02', name: 'Procurement', open: false, n: 96 },
  { l: 1, code: '03', name: 'Production', open: false, n: 40 },
  { l: 1, code: '04', name: 'Finance', open: false, n: 90 },
];

function TreeRow({ r }) {
  const Chevron = r.open ? ExpandMoreRounded : ChevronRightRounded;
  return (
    <Box role="treeitem" aria-selected={!!r.sel} aria-level={r.l}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, height: 36, pl: 1 + (r.l - 1) * 2, pr: 1.25, borderRadius: `${RADIUS.field}px`,
        bgcolor: r.sel ? BRAND.purpleTint : 'transparent', outline: r.sel ? `1px solid rgba(120,72,220,0.45)` : 'none' }}>
      {r.l < 5 ? <Chevron sx={{ fontSize: 18, color: SURFACE.textMuted }} /> : <Box sx={{ width: 18 }} />}
      <LevelBadge level={r.l} />
      <Code tone={r.sel ? 'purple' : 'muted'} sx={{ fontSize: 12 }}>{r.code}</Code>
      <Typography noWrap sx={{ fontSize: 13.5, fontWeight: r.l <= 2 || r.sel ? 700 : 500, color: r.sel ? '#FFFFFF' : SURFACE.text, minWidth: 0 }}>{r.name}</Typography>
      <Box sx={{ flexGrow: 1 }} />
      {r.n && <Typography sx={{ fontSize: 12, color: SURFACE.textMuted, fontFamily: MONO }}>{r.n}</Typography>}
    </Box>
  );
}

function EntityChip({ code, name, crud }) {
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, height: 32, pl: 1.25, pr: 0.5, borderRadius: `${RADIUS.pill}px`, bgcolor: BRAND.tealTint, border: '1px solid rgba(42,155,176,0.35)' }}>
      <Code tone="teal" sx={{ fontSize: 12 }}>{code}</Code>
      <Typography sx={{ fontSize: 13.5, color: SURFACE.text }}>{name}</Typography>
      <Box sx={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: BRAND.tealText, px: 0.75 }}>{crud}</Box>
      <IconButton size="small" aria-label={`Remove ${name}`} sx={{ width: 24, height: 24 }}><CloseRounded sx={{ fontSize: 15 }} /></IconButton>
    </Box>
  );
}

export default function BfcHierarchy() {
  return (
    <Shell active="bfc" crumbs={['Scope', 'Business functions', '01.02.01.02.01 Check credit']}>
      <PageHeader title="Business function chart"
        subtitle="Five levels, coded automatically · each level-5 function owns exactly one business requirement"
        actions={<>
          <Button variant="outlined" startIcon={<FileDownloadOutlined />}>Export</Button>
          <Button variant="contained" startIcon={<AddRounded />}>Add level-1 function</Button>
        </>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '400px minmax(0,1fr)', gap: 2 }}>
        <Card title="Hierarchy" action={<Box sx={{ display: 'flex', gap: 0.5 }}>{[1, 2, 3, 4, 5].map((l) => <LevelBadge key={l} level={l} />)}</Box>} bodySx={{ gap: 1, px: 1.5 }}>
          <TextField size="small" placeholder="Filter by code or name" sx={{ mx: 1 }} inputProps={{ 'aria-label': 'Filter hierarchy' }} />
          <Box role="tree" aria-label="Business function chart" sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            {TREE.map((r) => <TreeRow key={r.code} r={r} />)}
          </Box>
          <Box sx={{ mt: 'auto', mx: 1, display: 'flex', alignItems: 'center', gap: 1, color: SURFACE.textMuted, fontSize: 12.5 }}>
            <DragIndicatorRounded sx={{ fontSize: 16 }} />Drag to reorder — codes below are renumbered in one save
          </Box>
        </Card>

        <Card title="Level-5 function · Check credit" action={<Box sx={{ display: 'flex', gap: 1 }}><Tag tone="purple">Changed since v1.2</Tag><Status tone="ok" size="sm">Saved · v4 · K. Yamada 09-24</Status></Box>}>
          <Box sx={{ borderRadius: `${RADIUS.field + 4}px`, bgcolor: SURFACE.rail, px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <AutoAwesomeOutlined sx={{ fontSize: 20, color: BRAND.purpleLight }} />
            <Box sx={{ minWidth: 0, flexGrow: 1 }}>
              <Typography sx={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', color: '#CFC6F5' }}>REQUIREMENT CREATED WITH THIS FUNCTION</Typography>
              <Typography noWrap sx={{ fontSize: 14.5, fontWeight: 600, color: '#FFFFFF' }}><Code tone="purple" sx={{ fontSize: 13.5, mr: 1 }}>BR-0043</Code>Decide acceptance against the remaining credit limit</Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 0.75 }}><Tag tone="navy">SOL-0004</Tag><Tag tone="neutral">SOL-0019</Tag></Box>
            <Button variant="contained" size="small" sx={{ bgcolor: '#FFFFFF', color: SURFACE.rail, '&:hover': { bgcolor: '#EDEAF8' } }}>Open requirement</Button>
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <TextField label="Parent (level 4)" select defaultValue="p" fullWidth>
              <MenuItem value="p">01.02.01.02 Credit check</MenuItem>
            </TextField>
            <TextField label="Code" value="01.02.01.02.01" fullWidth InputProps={{ readOnly: true, sx: { fontFamily: MONO, color: BRAND.purpleLight } }} helperText="Generated from the parent chain on save" />
            <TextField label="Function name" defaultValue="Check credit" fullWidth required />
            <TextField label="Current system (As-Is)" select defaultValue="s" fullWidth>
              <MenuItem value="s">SalesPro v8 (legacy order system)</MenuItem>
            </TextField>
            <TextField label="Description" defaultValue="Compare the order amount with the customer's remaining credit limit and record the result on the order. Orders over the limit are put on hold and returned to Sales." fullWidth multiline minRows={2} sx={{ gridColumn: '1 / -1' }} />
          </Box>

          <Divider />
          <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.15fr)', gap: 3 }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
              <SectionLabel>DATA IN</SectionLabel>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                <EntityChip code="DE-0011" name="Order" crud="R" />
                <EntityChip code="DE-0007" name="Credit limit" crud="R" />
              </Box>
              <SectionLabel sx={{ mt: 1 }}>DATA OUT</SectionLabel>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                <EntityChip code="DE-0011" name="Order" crud="U" />
                <Button size="small" variant="outlined" startIcon={<AddRounded />}>Add entity</Button>
              </Box>
            </Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
              <SectionLabel>ROLES (RACI) · ONE ACCOUNTABLE</SectionLabel>
              {[['Credit officer', 'Finance · Credit Control', 'R'], ['Credit manager', 'Finance · Credit Control', 'A'], ['Sales rep', 'Sales · Order desk', 'I']].map(([r, o, v]) => (
                <Box key={r} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{r}</Typography>
                    <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>{o}</Typography>
                  </Box>
                  <Raci value={v} label={`RACI for ${r}`} />
                </Box>
              ))}
              <Button size="small" startIcon={<AddRounded />} sx={{ alignSelf: 'flex-start', color: BRAND.purpleLight }}>Add role</Button>
            </Box>
          </Box>

          <Box sx={{ mt: 'auto', display: 'flex', gap: 1.25, justifyContent: 'flex-end' }}>
            <Button variant="outlined" color="warning">Discard changes</Button>
            <Button variant="contained">Save function</Button>
          </Box>
        </Card>

      </Box>
    </Shell>
  );
}
