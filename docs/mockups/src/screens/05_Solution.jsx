import React from 'react';
import { Box, Button, TextField, MenuItem, Typography, IconButton, Table, TableHead, TableBody, TableRow, TableCell } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, Segmented, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const CATS = ['Org & rules', 'People', 'Process', 'Data', 'Technology'];
const AREAS = ['Sales', 'Procure.', 'Finance', 'Data'];
const MATRIX = [[2, 1, 3, 0], [1, 0, 2, 0], [3, 2, 4, 1], [2, 3, 1, 5], [12, 6, 5, 2]];

function heat(v) {
  if (!v) return { bg: SURFACE.raised, fg: SURFACE.textMuted };
  const a = Math.min(0.15 + v * 0.07, 0.95);
  return { bg: `rgba(120,72,220,${a})`, fg: a > 0.5 ? '#FFFFFF' : BRAND.purpleLight };
}

export default function Solution() {
  return (
    <Shell active="sol" crumbs={['Scope', 'Solutions', 'SOL-0004']}>
      <PageHeader
        title={<><Code tone="navy" sx={{ fontSize: 22, mr: 1.5 }}>SOL-0004</Code>Credit automation</>}
        subtitle="How a requirement will be met — organisation, people, process, data or technology"
        actions={<><Button variant="outlined" color="warning">Archive</Button><Button variant="contained">Save solution</Button></>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 380px', gap: 2 }}>
        <Card title="Solution" action={<Status tone="ok" size="sm">Saved · v3</Status>}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <SectionLabel>CATEGORY</SectionLabel>
            <Segmented options={CATS} value="Technology" label="Solution category" />
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <TextField label="Solution name" defaultValue="Credit automation" required fullWidth />
            <TextField label="To-Be system" select defaultValue="n" fullWidth><MenuItem value="n">New sales system (S/4 SD)</MenuItem></TextField>
            <TextField label="What changes" defaultValue="Credit decisions run automatically on every order against a single, current credit limit. Officers only review holds." multiline minRows={2} fullWidth sx={{ gridColumn: '1 / -1' }} />
            <TextField label="Expected benefit" defaultValue="Order-to-confirm time from 1.5 days to same day" fullWidth />
            <TextField label="Solution owner" select defaultValue="t" fullWidth><MenuItem value="t">Takahashi · Finance</MenuItem></TextField>
          </Box>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}><SectionLabel>MEETS THESE REQUIREMENTS</SectionLabel><Box sx={{ flexGrow: 1 }} /><Button size="small" startIcon={<AddRounded />} sx={{ color: BRAND.purpleLight }}>Link requirement</Button></Box>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {[['BR-0043', 'Check credit'], ['BR-0044', 'Confirm order'], ['BR-0052', 'Apply payment']].map(([c, n]) => (
                <Box key={c} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, height: 32, pl: 1.25, pr: 0.5, borderRadius: `${RADIUS.pill}px`, bgcolor: BRAND.purpleTint, border: '1px solid rgba(120,72,220,0.35)' }}>
                  <Code tone="purple" sx={{ fontSize: 12 }}>{c}</Code><Typography sx={{ fontSize: 13.5 }}>{n}</Typography>
                  <IconButton size="small" aria-label={`Unlink ${c}`} sx={{ width: 24, height: 24 }}><CloseRounded sx={{ fontSize: 15 }} /></IconButton>
                </Box>
              ))}
            </Box>
          </Box>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minHeight: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}><SectionLabel>FUNCTIONAL REQUIREMENTS</SectionLabel><Box sx={{ flexGrow: 1 }} /><Button size="small" variant="outlined" startIcon={<AddRounded />}>Add FR</Button></Box>
            <Box sx={{ border: `1px solid ${SURFACE.border}`, borderRadius: `${RADIUS.field + 2}px`, overflow: 'hidden' }}>
              <Table size="small">
                <TableHead><TableRow sx={{ bgcolor: SURFACE.raised }}><TableCell>FR</TableCell><TableCell>Name</TableCell><TableCell>Type</TableCell><TableCell>Complexity</TableCell><TableCell align="right">Effort</TableCell></TableRow></TableHead>
                <TableBody>
                  {[['FR-0012', 'Credit inquiry screen', 'Screen', 'Medium', 8], ['FR-0013', 'Credit decision batch', 'Batch', 'Complex', 15]].map(([c, n, t, cx, d]) => (
                    <TableRow key={c}><TableCell><Code sx={{ fontSize: 12.5 }}>{c}</Code></TableCell><TableCell>{n}</TableCell><TableCell><Tag tone="navy">{t}</Tag></TableCell><TableCell>{cx}</TableCell><TableCell align="right" sx={{ fontFamily: MONO }}>{d} d</TableCell></TableRow>
                  ))}
                  <TableRow sx={{ '& td': { fontWeight: 700, borderBottom: 0 } }}><TableCell colSpan={4}>Solution total</TableCell><TableCell align="right" sx={{ fontFamily: MONO, color: BRAND.purpleLight }}>23 d</TableCell></TableRow>
                </TableBody>
              </Table>
            </Box>
          </Box>
        </Card>

        <Card title="Solution mix by area" action={<Tag tone="neutral">81 solutions</Tag>}>
          <Box sx={{ display: 'grid', gridTemplateColumns: '104px repeat(4, minmax(0,1fr))', gap: 0.75, alignItems: 'center' }}>
            <Box />
            {AREAS.map((a) => <Typography key={a} sx={{ fontSize: 12, fontWeight: 600, color: SURFACE.textMuted, textAlign: 'center' }}>{a}</Typography>)}
            {CATS.map((c, i) => (
              <React.Fragment key={c}>
                <Typography sx={{ fontSize: 13, color: c === 'Technology' ? '#FFFFFF' : SURFACE.textSecondary, fontWeight: c === 'Technology' ? 700 : 400 }}>{c}</Typography>
                {MATRIX[i].map((v, j) => {
                  const h = heat(v);
                  return <Box key={j} sx={{ height: 40, borderRadius: '12px', bgcolor: h.bg, color: h.fg, display: 'grid', placeItems: 'center', fontFamily: MONO, fontSize: 14, fontWeight: 600, outline: i === 4 && j === 0 ? `2px solid ${BRAND.amber}` : 'none' }}>{v || '·'}</Box>;
                })}
              </React.Fragment>
            ))}
          </Box>
          <Box sx={{ p: 1.75, borderRadius: `${RADIUS.field + 2}px`, bgcolor: 'rgba(251,174,64,0.10)', border: '1px solid rgba(251,174,64,0.35)', display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: '#FBC46E' }}>Sales leans on technology</Typography>
            <Typography sx={{ fontSize: 13, color: SURFACE.textSecondary }}>12 of 20 Sales solutions are technology. Check whether rule or process changes are missing before the vendor scope is fixed.</Typography>
          </Box>
          <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted, mt: 'auto' }}>Darker purple means more solutions in that cell.</Typography>
        </Card>
      </Box>
    </Shell>
  );
}
