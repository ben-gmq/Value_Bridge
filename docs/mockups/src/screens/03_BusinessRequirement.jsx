import React from 'react';
import { Box, Button, TextField, MenuItem, Typography, Checkbox, Table, TableHead, TableBody, TableRow, TableCell, Divider, IconButton } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import HistoryRounded from '@mui/icons-material/HistoryRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import LockOutlined from '@mui/icons-material/LockOutlined';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, LevelBadge, Raci, KV, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const USAGE = [
  ['DE-0011', 'Order', [false, true, true, false], 'In · Out'],
  ['DE-0007', 'Credit limit', [false, true, false, false], 'In'],
  ['DE-0004', 'Customer', [false, true, false, false], 'In'],
];

export default function BusinessRequirement() {
  return (
    <Shell active="br" crumbs={['Scope', 'Business requirements', 'BR-0043']}>
      <PageHeader
        eyebrow={<Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><LevelBadge level={5} /><Code tone="purple">01.02.01.02.01</Code><Typography sx={{ fontSize: 13, color: SURFACE.textMuted }}>Order intake › Credit check</Typography></Box>}
        title={<><Code tone="purple" sx={{ fontSize: 22, mr: 1.5 }}>BR-0043</Code>Check credit</>}
        subtitle="One requirement per level-5 function · created with the function, edited here"
        actions={<>
          <Button variant="outlined" startIcon={<HistoryRounded />}>History</Button>
          <Button variant="contained">Save requirement</Button>
        </>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 340px', gap: 2 }}>
        <Card title="Requirement" action={<Status tone="ok" size="sm">Saved · v7</Status>}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 2 }}>
            <TextField label="Requirement statement" defaultValue="Decide acceptance against the remaining credit limit" required fullWidth sx={{ gridColumn: 'span 4' }} />
            <TextField label="Business logic" defaultValue="Remaining limit = credit limit − open receivables − open orders. If the order amount exceeds the remaining limit, set credit result to HOLD and return the order to Sales with the shortfall." multiline minRows={2} fullWidth sx={{ gridColumn: 'span 4' }} />
            <TextField label="Trigger" defaultValue="Order registered" fullWidth />
            <TextField label="Frequency" select defaultValue="d" fullWidth><MenuItem value="d">Per order</MenuItem></TextField>
            <TextField label="Priority" select defaultValue="m" fullWidth><MenuItem value="m">Must</MenuItem></TextField>
            <TextField label="Business area" select defaultValue="s" fullWidth><MenuItem value="s">01 Sales</MenuItem></TextField>
          </Box>

          <Divider />
          <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.25fr) minmax(0,1fr)', gap: 3, minHeight: 0 }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <SectionLabel>DATA USAGE · CRUD</SectionLabel><Box sx={{ flexGrow: 1 }} />
                <Button size="small" startIcon={<AddRounded />} sx={{ color: BRAND.purpleLight }}>Add entity</Button>
              </Box>
              <Box sx={{ border: `1px solid ${SURFACE.border}`, borderRadius: `${RADIUS.field + 2}px`, overflow: 'hidden' }}>
                <Table size="small">
                  <TableHead><TableRow sx={{ bgcolor: SURFACE.raised }}>
                    <TableCell>Entity</TableCell>{['C', 'R', 'U', 'D'].map((c) => <TableCell key={c} align="center" sx={{ width: 44, fontFamily: MONO }}>{c}</TableCell>)}<TableCell>Derived</TableCell>
                  </TableRow></TableHead>
                  <TableBody>
                    {USAGE.map(([code, name, crud, io]) => (
                      <TableRow key={code}>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}><Code tone="teal" sx={{ fontSize: 12, mr: 1 }}>{code}</Code>{name}</TableCell>
                        {crud.map((on, i) => <TableCell key={i} align="center" sx={{ p: 0 }}><Checkbox checked={on} inputProps={{ 'aria-label': `${name} ${'CRUD'[i]}` }} sx={{ '&.Mui-checked': { color: BRAND.purpleMid } }} /></TableCell>)}
                        <TableCell><Tag tone={io.includes('Out') ? 'purple' : 'neutral'}>{io}</Tag></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
              <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Input and output are derived from CRUD — R is input, C and U are output.</Typography>
            </Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
              <SectionLabel>ACCOUNTABILITY (RACI)</SectionLabel>
              {[['Credit manager', 'A'], ['Credit officer', 'R'], ['Sales manager', 'C']].map(([r, v]) => (
                <Box key={r} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 600, flexGrow: 1 }}>{r}</Typography><Raci value={v} label={`RACI for ${r}`} />
                </Box>
              ))}
              <SectionLabel sx={{ mt: 1 }}>SOLUTIONS</SectionLabel>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {[['SOL-0004', 'Credit automation', 'navy'], ['SOL-0019', 'Rule standards', 'purple']].map(([c, n, t]) => (
                  <Box key={c} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, height: 32, pl: 1.25, pr: 0.5, borderRadius: `${RADIUS.pill}px`, bgcolor: SURFACE.raised, border: `1px solid ${SURFACE.border}` }}>
                    <Code tone={t} sx={{ fontSize: 12 }}>{c}</Code><Typography sx={{ fontSize: 13.5 }}>{n}</Typography>
                    <IconButton size="small" aria-label={`Unlink ${c}`} sx={{ width: 24, height: 24 }}><CloseRounded sx={{ fontSize: 15 }} /></IconButton>
                  </Box>
                ))}
                <Button size="small" variant="outlined" startIcon={<AddRounded />}>Link</Button>
              </Box>
            </Box>
          </Box>
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Box component="section" sx={{ borderRadius: `${RADIUS.card}px`, bgcolor: SURFACE.rail, p: 2.5, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
            <Typography sx={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', color: '#CFC6F5' }}>COVERAGE</Typography>
            <Typography sx={{ fontSize: 17, fontWeight: 700, color: '#FFFFFF' }}>Reaches 2 functional requirements</Typography>
            {[['FR-0012', 'Credit inquiry screen', '8 d'], ['FR-0013', 'Credit decision batch', '15 d']].map(([c, n, d]) => (
              <Box key={c} sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, height: 38, borderRadius: `${RADIUS.field}px`, bgcolor: 'rgba(255,255,255,0.07)' }}>
                <Code tone="purple" sx={{ fontSize: 12 }}>{c}</Code><Typography noWrap sx={{ fontSize: 13.5, color: '#FFFFFF', flexGrow: 1 }}>{n}</Typography><Code sx={{ color: '#CFC6F5', fontSize: 12 }}>{d}</Code>
              </Box>
            ))}
          </Box>
          <Card title="Issues" action={<Status tone="escalate" size="sm">1 high</Status>}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}><Code tone="muted" sx={{ fontSize: 12 }}>ISS-0012</Code> · raised by Suzuki, Credit Control</Typography>
              <Typography sx={{ fontSize: 14 }}>Credit criteria differ by department, so decisions depend on who makes them</Typography>
            </Box>
          </Card>
          <Card title="Record">
            <KV k="Version" v="7 · K. Yamada, 09-24 16:02" />
            <KV k="Baseline" v={<Tag tone="purple">Changed since v1.2</Tag>} />
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', p: 1.5, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.raised }}>
              <LockOutlined sx={{ fontSize: 18, color: SURFACE.textMuted, mt: '1px' }} />
              <Typography sx={{ fontSize: 12.5, color: SURFACE.textSecondary }}>If someone else saves first, your save is stopped and you are asked to refresh — nothing is overwritten.</Typography>
            </Box>
          </Card>
        </Box>
      </Box>
    </Shell>
  );
}
