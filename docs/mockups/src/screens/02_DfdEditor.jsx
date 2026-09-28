import React from 'react';
import { Box, Button, Typography, ToggleButton, ToggleButtonGroup, IconButton, Divider } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import RemoveRounded from '@mui/icons-material/RemoveRounded';
import FileDownloadOutlined from '@mui/icons-material/FileDownloadOutlined';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, LevelBadge, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

// Canvas geometry (px inside the diagram area, 780 x 570)
const W = 176, H = 84, DW = 168, DH = 44;
const P = { // x, y, no, name, BR, role, selected, warning
  p11: [10, 120, '1.1', 'Enter order', 'BR-0041', 'Order clerk'],
  p12: [10, 300, '1.2', 'Amend order', 'BR-0042', 'Order clerk'],
  p31: [10, 474, '3.1', 'Allocate stock', 'BR-0045', 'Stock clerk'],
  p21: [580, 70, '2.1', 'Check credit', 'BR-0043', 'Credit officer', true],
  p22: [580, 300, '2.2', 'Confirm order', 'BR-0044', 'Order clerk'],
  p32: [580, 474, '3.2', 'Notify shortage', 'BR-0046', 'Stock clerk', false, true],
};
const D = { // x, y, no, name, DE
  d4: [300, 30, 'D4', 'Customer', 'DE-0004'],
  d1: [300, 250, 'D1', 'Order', 'DE-0011'],
  d2: [300, 140, 'D2', 'Credit limit', 'DE-0007'],
  d3: [300, 420, 'D3', 'Stock', 'DE-0015'],
};
const EXT = [10, 10, 176, 56];
function box(id) {
  if (id === 'ext') return EXT;
  if (P[id]) return [P[id][0], P[id][1], W, H];
  return [D[id][0], D[id][1], DW, DH];
}
function anchor(id, side, off = 0) {
  const [x, y, w, h] = box(id);
  return { l: [x, y + h / 2 + off], r: [x + w, y + h / 2 + off], t: [x + w / 2 + off, y], b: [x + w / 2 + off, y + h] }[side];
}
// from, side, to, side, label, CRUD, highlighted, offset
const EDGES = [
  ['ext', 'b', 'p11', 't', 'Order request', null, false],
  ['d4', 'l', 'p11', 'r', 'Customer', 'R', false, -18],
  ['p11', 'r', 'd1', 'l', 'Order', 'C', false, 12],
  ['p12', 'r', 'd1', 'l', 'Order', 'U', false, 0],
  ['d1', 'b', 'p31', 't', 'Order', 'R', false, -40],
  ['p31', 'r', 'd3', 'l', 'Stock', 'U', false, 0],
  ['d3', 'r', 'p32', 'l', 'Stock', 'R', false, 0],
  ['d1', 'r', 'p21', 'l', 'Order', 'R U', true, -8],
  ['d2', 'r', 'p21', 'l', 'Credit limit', 'R', true, 14],
  ['d1', 'r', 'p22', 'l', 'Order', 'R', false, 8],
];
function curve(e) {
  const [f, fs, t, ts, , , , off = 0] = e;
  const [x1, y1] = anchor(f, fs, fs === 'l' || fs === 'r' ? off / 2 : off);
  const [x2, y2] = anchor(t, ts, ts === 'l' || ts === 'r' ? off : 0);
  const horiz = fs === 'l' || fs === 'r';
  const c1 = horiz ? [(x1 + x2) / 2, y1] : [x1, (y1 + y2) / 2];
  const c2 = ts === 'l' || ts === 'r' ? [(x1 + x2) / 2, y2] : [x2, (y1 + y2) / 2];
  const mid = [0.125 * x1 + 0.375 * c1[0] + 0.375 * c2[0] + 0.125 * x2, 0.125 * y1 + 0.375 * c1[1] + 0.375 * c2[1] + 0.125 * y2];
  return { d: `M${x1} ${y1} C ${c1[0]} ${c1[1]}, ${c2[0]} ${c2[1]}, ${x2} ${y2}`, mid };
}

function Process({ id }) {
  const [x, y, no, name, br, role, sel, warn] = P[id];
  return (
    <Box sx={{ position: 'absolute', left: x, top: y, width: W, height: H, borderRadius: `${RADIUS.diagram}px`, bgcolor: sel ? '#2A2350' : SURFACE.raised,
      border: `1.5px solid ${sel ? BRAND.purpleMid : warn ? BRAND.amber : '#4A4660'}`, boxShadow: sel ? '0 0 0 4px rgba(120,72,220,0.22)' : 'none', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ height: 26, px: 1.25, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${sel ? 'rgba(120,72,220,0.45)' : SURFACE.border}` }}>
        <Code tone={sel ? 'purple' : 'navy'} sx={{ fontSize: 12, fontWeight: 600 }}>{no}</Code>
        {warn ? <Typography sx={{ fontSize: 11, fontWeight: 700, color: BRAND.amber }}>No output</Typography> : <Code tone="muted" sx={{ fontSize: 11.5 }}>{br}</Code>}
      </Box>
      <Box sx={{ px: 1.25, py: 0.75 }}>
        <Typography sx={{ fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>{name}</Typography>
        <Typography sx={{ fontSize: 12, color: SURFACE.textMuted }}>R · {role}</Typography>
      </Box>
    </Box>
  );
}

function Store({ id }) {
  const [x, y, no, name, de] = D[id];
  return (
    <Box sx={{ position: 'absolute', left: x, top: y, width: DW, height: DH, display: 'flex', alignItems: 'stretch', bgcolor: 'rgba(2,120,142,0.10)',
      borderTop: `1.5px solid ${BRAND.teal}`, borderBottom: `1.5px solid ${BRAND.teal}`, borderLeft: `1.5px solid ${BRAND.teal}` }}>
      <Box sx={{ width: 36, display: 'grid', placeItems: 'center', borderRight: `1.5px solid ${BRAND.teal}`, fontFamily: MONO, fontSize: 12, fontWeight: 600, color: BRAND.tealText }}>{no}</Box>
      <Box sx={{ px: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: '#FFFFFF', lineHeight: 1.2 }}>{name}</Typography>
        <Code tone="teal" sx={{ fontSize: 11 }}>{de}</Code>
      </Box>
    </Box>
  );
}

function Label({ x, y, text, crud }) {
  return (
    <Box sx={{ position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)', px: 1, height: 22, display: 'flex', alignItems: 'center', gap: 0.5, borderRadius: `${RADIUS.pill}px`, bgcolor: SURFACE.card, border: `1px solid ${SURFACE.borderStrong}`, fontSize: 11.5, color: SURFACE.textSecondary, whiteSpace: 'nowrap' }}>
      {text}{crud && <Box component="span" sx={{ fontFamily: MONO, fontWeight: 700, color: crud.startsWith('R') && crud.length === 1 ? BRAND.primaryLight : BRAND.purpleLight }}>{crud}</Box>}
    </Box>
  );
}

export default function DfdEditor() {
  return (
    <Shell active="dfd" crumbs={['Scope', 'Data flow diagram', '01.02.01 Order intake']}>
      <PageHeader
        eyebrow={<Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><LevelBadge level={3} /><Code tone="purple">01.02.01</Code><Typography sx={{ fontSize: 13, color: SURFACE.textMuted }}>Sales › Order management</Typography></Box>}
        title="Order intake — data flow diagram"
        subtitle="Generated from level-5 functions, data entities and CRUD usage. Editing the diagram updates the requirements."
        actions={<>
          <ToggleButtonGroup exclusive value="5" size="small" aria-label="Expand to level"
            sx={{ bgcolor: SURFACE.field, borderRadius: `${RADIUS.pill}px`, p: '3px', border: `1px solid ${SURFACE.border}`, '& .MuiToggleButton-root': { border: 0, borderRadius: `${RADIUS.pill}px !important`, px: 1.75, height: 32, fontSize: 13, color: SURFACE.textSecondary, textTransform: 'none' }, '& .Mui-selected': { bgcolor: `${BRAND.purpleMid} !important`, color: '#FFFFFF !important' } }}>
            <ToggleButton value="4">Level 4 · view only</ToggleButton>
            <ToggleButton value="5">Level 5 · edit</ToggleButton>
          </ToggleButtonGroup>
          <Button variant="outlined" startIcon={<FileDownloadOutlined />}>Export Mermaid</Button>
        </>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 320px', gap: 2 }}>
        <Card sx={{ position: 'relative' }} bodySx={{ p: 0, position: 'relative' }}>
          <Box sx={{ position: 'absolute', inset: 0, backgroundImage: `radial-gradient(${SURFACE.borderStrong} 1px, transparent 1px)`, backgroundSize: '22px 22px', opacity: 0.7 }} />
          <Box sx={{ position: 'absolute', top: 16, left: 20, right: 20, display: 'flex', alignItems: 'center', gap: 2, zIndex: 2 }}>
            <Typography sx={{ fontSize: 13, color: SURFACE.textMuted, fontFamily: MONO }}>6 processes · 4 stores · 1 external · 14 flows</Typography>
            <Box sx={{ flexGrow: 1 }} />
            {[['Process', '#4A4660', 18], ['Data store', BRAND.teal, 0], ['External entity', SURFACE.textSecondary, 4]].map(([t, c, r]) => (
              <Box key={t} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: 12.5, color: SURFACE.textSecondary }}>
                <Box sx={{ width: 18, height: 12, border: `1.5px solid ${c}`, borderRadius: `${r / 3}px`, borderRight: t === 'Data store' ? 0 : undefined }} />{t}
              </Box>
            ))}
          </Box>

          <Box sx={{ position: 'absolute', left: 20, top: 56, width: 780, height: 570 }}>
            <svg width="780" height="570" style={{ position: 'absolute', inset: 0 }} aria-hidden="true">
              <defs>
                <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8E8A9E" /></marker>
                <marker id="ahp" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={BRAND.purpleMid} /></marker>
              </defs>
              {EDGES.map((e, i) => {
                const hot = e[6];
                return <path key={i} d={curve(e).d} fill="none" stroke={hot ? BRAND.purpleMid : '#5A566E'} strokeWidth={hot ? 2 : 1.5} markerEnd={`url(#${hot ? 'ahp' : 'ah'})`} />;
              })}
            </svg>
            <Box sx={{ position: 'absolute', left: EXT[0], top: EXT[1], width: EXT[2], height: EXT[3], bgcolor: SURFACE.raised, border: `1.5px solid ${SURFACE.textSecondary}`, borderRadius: '4px', display: 'grid', placeItems: 'center', textAlign: 'center' }}>
              <Box><Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', color: SURFACE.textMuted }}>EXTERNAL</Typography><Typography sx={{ fontSize: 14, fontWeight: 700 }}>Customer</Typography></Box>
            </Box>
            {Object.keys(P).map((k) => <Process key={k} id={k} />)}
            {Object.keys(D).map((k) => <Store key={k} id={k} />)}
            {EDGES.map((e, i) => { const m = curve(e).mid; return <Label key={i} x={m[0]} y={m[1]} text={e[4]} crud={e[5]} />; })}
            <Box sx={{ position: 'absolute', left: 580, top: 398, px: 1.5, py: 1, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.rail, border: '1px solid rgba(120,72,220,0.5)' }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: '#FFFFFF' }}>Drop on a store to connect</Typography>
              <Typography sx={{ fontSize: 12, color: '#CFC6F5' }}>Then pick C / R / U / D</Typography>
            </Box>
          </Box>

          <Box sx={{ position: 'absolute', left: 20, bottom: 16, zIndex: 2, display: 'flex', alignItems: 'center', gap: 1, p: 0.75, borderRadius: `${RADIUS.pill}px`, bgcolor: SURFACE.card, border: `1px solid ${SURFACE.border}` }}>
            <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted, px: 1 }}>Add</Typography>
            <Button size="small" variant="outlined" startIcon={<AddRounded />}>Process</Button>
            <Button size="small" variant="outlined" startIcon={<AddRounded />} sx={{ borderColor: BRAND.teal, color: BRAND.tealText }}>Data store</Button>
            <Button size="small" variant="outlined" startIcon={<AddRounded />}>External</Button>
          </Box>
          <Box sx={{ position: 'absolute', right: 20, bottom: 16, zIndex: 2, display: 'flex', alignItems: 'center', gap: 0.5, p: 0.5, borderRadius: `${RADIUS.pill}px`, bgcolor: SURFACE.card, border: `1px solid ${SURFACE.border}` }}>
            <IconButton size="small" aria-label="Zoom out"><RemoveRounded fontSize="small" /></IconButton>
            <Typography sx={{ fontFamily: MONO, fontSize: 13, px: 0.5 }}>100%</Typography>
            <IconButton size="small" aria-label="Zoom in"><AddRounded fontSize="small" /></IconButton>
            <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
            <Button size="small" startIcon={<AccountTreeOutlined />} sx={{ color: SURFACE.textSecondary }}>Auto layout</Button>
          </Box>
        </Card>

        <Card title="Process 2.1" action={<IconButton size="small" aria-label="Close inspector"><CloseRounded fontSize="small" /></IconButton>}>
          <Box>
            <Code tone="purple">01.02.01.02.01 · BR-0043</Code>
            <Typography sx={{ fontSize: 20, fontWeight: 700, mt: 0.5 }}>Check credit</Typography>
            <Typography sx={{ fontSize: 13.5, color: SURFACE.textSecondary, mt: 0.5 }}>Compare the order amount with the remaining credit limit. Over the limit, the order goes on hold and back to Sales.</Typography>
          </Box>
          <Divider />
          <SectionLabel>DATA USAGE</SectionLabel>
          {[['DE-0011', 'Order', 'R U'], ['DE-0007', 'Credit limit', 'R']].map(([c, n, crud]) => (
            <Box key={c} sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.5, height: 40, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.raised }}>
              <Code tone="teal" sx={{ fontSize: 12 }}>{c}</Code><Typography sx={{ fontSize: 14, flexGrow: 1 }}>{n}</Typography>
              <Box sx={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: BRAND.purpleLight }}>{crud}</Box>
            </Box>
          ))}
          <SectionLabel>ROLES</SectionLabel>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}><Tag tone="purple">R</Tag><Typography sx={{ fontSize: 14 }}>Credit officer</Typography></Box>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}><Tag tone="purple" sx={{ bgcolor: BRAND.purpleMid, color: '#FFFFFF' }}>A</Tag><Typography sx={{ fontSize: 14 }}>Credit manager</Typography></Box>
          </Box>
          <SectionLabel>CHECKS</SectionLabel>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Status tone="ok" size="sm">Has input and output</Status>
            <Status tone="escalate" size="sm">ISS-0012 · rules differ by department</Status>
          </Box>
          <Button variant="contained" fullWidth sx={{ mt: 'auto' }}>Open BR-0043</Button>
        </Card>
      </Box>
    </Shell>
  );
}
