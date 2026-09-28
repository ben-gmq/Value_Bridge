import React from 'react';
import { Box, Button, TextField, MenuItem, Typography, IconButton, Avatar } from '@mui/material';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, Status, Segmented, Steps, BRAND, SURFACE, RADIUS } from '../kit.jsx';

const ACTIVITY = [
  ['09-24 16:10', 'K. Yamada', 'Linked BR-0044 Confirm order'],
  ['09-22 11:32', 'K. Yamada', 'Moved to In progress · workshop booked 09-26'],
  ['09-19 15:05', 'K. Yamada', 'Severity raised to High'],
  ['09-18 10:20', 'K. Yamada', 'Recorded, raised by Suzuki in the credit workshop'],
];

export default function Issue() {
  return (
    <Shell active="issue" crumbs={['Control', 'Issues', 'ISS-0012']}>
      <PageHeader
        title={<><Code tone="muted" sx={{ fontSize: 22, mr: 1.5 }}>ISS-0012</Code>Credit criteria differ by department</>}
        subtitle="Raised by the client, recorded by the consultant — both are kept"
        actions={<Steps steps={['Open', 'In progress', 'Resolved']} current={1} />} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 340px', gap: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Card title="Issue" action={<Status tone="escalate" size="sm">High</Status>}>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 2 }}>
              <TextField label="Title" defaultValue="Credit criteria differ by department" required fullWidth sx={{ gridColumn: 'span 2' }} />
              <TextField label="Type" select defaultValue="r" fullWidth><MenuItem value="r">Business rule</MenuItem></TextField>
              <TextField label="Raised by (client)" select defaultValue="s" fullWidth><MenuItem value="s">Suzuki · Credit Control</MenuItem></TextField>
              <TextField label="Recorded by (FTC)" value="K. Yamada" fullWidth InputProps={{ readOnly: true }} />
              <TextField label="Raised on" defaultValue="2026-09-18" fullWidth />
              <TextField label="Description" defaultValue="Sales and Finance apply different thresholds when an order exceeds the limit. Sales allows 10% over for key accounts; Finance does not. The same order can be accepted or held depending on who checks it." multiline minRows={3} fullWidth sx={{ gridColumn: '1 / -1' }} />
            </Box>
            <Box sx={{ display: 'flex', gap: 4, alignItems: 'flex-start' }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}><SectionLabel>SEVERITY</SectionLabel><Segmented options={['Low', 'Medium', 'High']} value="High" label="Severity" /></Box>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                <SectionLabel>AFFECTS REQUIREMENTS</SectionLabel>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {[['BR-0043', 'Check credit'], ['BR-0044', 'Confirm order']].map(([c, n]) => (
                    <Box key={c} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, height: 32, pl: 1.25, pr: 0.5, borderRadius: `${RADIUS.pill}px`, bgcolor: BRAND.purpleTint, border: '1px solid rgba(120,72,220,0.35)' }}>
                      <Code tone="purple" sx={{ fontSize: 12 }}>{c}</Code><Typography sx={{ fontSize: 13.5 }}>{n}</Typography>
                      <IconButton size="small" aria-label={`Unlink ${c}`} sx={{ width: 24, height: 24 }}><CloseRounded sx={{ fontSize: 15 }} /></IconButton>
                    </Box>
                  ))}
                  <Button size="small" variant="outlined" startIcon={<AddRounded />}>Link</Button>
                </Box>
              </Box>
            </Box>
          </Card>
          <Card title="Resolution" action={<Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Required to resolve</Typography>}>
            <TextField label="How it was resolved" placeholder="e.g. One credit rule agreed for all departments, recorded as SOL-0019" multiline minRows={2} fullWidth />
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1.25 }}>
              <Button variant="outlined">Save</Button>
              <Button variant="contained" disabled>Resolve issue</Button>
            </Box>
          </Card>
        </Box>

        <Card title="Activity">
          <Box component="ol" sx={{ m: 0, p: 0, listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
            {ACTIVITY.map(([t, who, what], i) => (
              <Box component="li" key={t} sx={{ display: 'flex', gap: 1.5 }}>
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', mt: 0.5, bgcolor: i === 0 ? BRAND.purpleMid : 'transparent', border: `2px solid ${i === 0 ? BRAND.purpleMid : SURFACE.borderStrong}` }} />
                  {i < ACTIVITY.length - 1 && <Box sx={{ width: 2, flexGrow: 1, bgcolor: SURFACE.border, my: 0.5 }} />}
                </Box>
                <Box sx={{ pb: 2.25 }}>
                  <Typography sx={{ fontSize: 14 }}>{what}</Typography>
                  <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>{who} · {t}</Typography>
                </Box>
              </Box>
            ))}
          </Box>
          <Box sx={{ mt: 'auto', display: 'flex', alignItems: 'center', gap: 1.25, p: 1.5, borderRadius: `${RADIUS.field + 2}px`, bgcolor: SURFACE.raised }}>
            <Avatar sx={{ width: 32, height: 32, bgcolor: BRAND.purple, color: BRAND.purpleLight, fontSize: 12.5, fontWeight: 700 }}>SZ</Avatar>
            <Box><Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>Suzuki</Typography><Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>Client stakeholder · no login</Typography></Box>
          </Box>
        </Card>
      </Box>
    </Shell>
  );
}
