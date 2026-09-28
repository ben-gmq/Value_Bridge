import React from 'react';
import { Box, Button, TextField, MenuItem, Typography, Switch, FormControlLabel, Table, TableHead, TableBody, TableRow, TableCell, Avatar, Select, IconButton } from '@mui/material';
import PersonAddAltOutlined from '@mui/icons-material/PersonAddAltOutlined';
import MoreVertRounded from '@mui/icons-material/MoreVertRounded';
import { Shell, PageHeader, Card, SectionLabel, Code, Tag, BRAND, SURFACE, RADIUS, MONO } from '../kit.jsx';

const MEMBERS = [
  ['KY', 'K. Yamada', 'k.yamada@fortience.co.jp', 'OWNER', '06-02'],
  ['MI', 'M. Ito', 'm.ito@fortience.co.jp', 'EDITOR', '06-02'],
  ['TS', 'T. Sato', 't.sato@fortience.co.jp', 'EDITOR', '06-15'],
  ['AW', 'A. Watanabe', 'a.watanabe@fortience.co.jp', 'EDITOR', '07-01'],
  ['RN', 'R. Nakamura', 'r.nakamura@fortience.co.jp', 'REVIEWER', '08-20'],
];
const ROLE_TONE = { OWNER: [BRAND.purpleMid, '#FFFFFF'], EDITOR: ['rgba(74,115,168,0.22)', BRAND.primaryLight], REVIEWER: ['rgba(183,180,196,0.12)', SURFACE.textSecondary] };

export default function ProjectAccess() {
  return (
    <Shell active="project" crumbs={['Admin', 'Project & access']}>
      <PageHeader title="Project & access" subtitle="One engagement per project · people see only projects they are granted"
        actions={<Button variant="contained">Save project</Button>} />

      <Box sx={{ flexGrow: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '460px minmax(0,1fr)', gap: 2 }}>
        <Card title="Project">
          <TextField label="Project name" defaultValue="2027 Core Systems Renewal" required fullWidth />
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <TextField label="Client" defaultValue="Kanto Industrial Co." fullWidth />
            <TextField label="Code prefix" defaultValue="CSR" fullWidth InputProps={{ sx: { fontFamily: MONO } }} helperText="Used in exports" />
            <TextField label="Start date" defaultValue="2026-04-01" fullWidth />
            <TextField label="Phase" select defaultValue="r" fullWidth><MenuItem value="r">Requirements</MenuItem></TextField>
          </Box>
          <SectionLabel sx={{ mt: 0.5 }}>SCOPE CONTROL THRESHOLDS</SectionLabel>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <TextField label="Caution at net change" defaultValue="10" fullWidth InputProps={{ endAdornment: <Typography sx={{ color: SURFACE.textMuted, fontSize: 13.5 }}>%</Typography> }} />
            <TextField label="Escalate at net change" defaultValue="20" fullWidth InputProps={{ endAdornment: <Typography sx={{ color: SURFACE.textMuted, fontSize: 13.5 }}>%</Typography> }} />
            <TextField label="CR needed above" defaultValue="20" fullWidth sx={{ gridColumn: '1 / -1' }} InputProps={{ endAdornment: <Typography sx={{ color: SURFACE.textMuted, fontSize: 13.5, whiteSpace: 'nowrap' }}>person-days</Typography> }} />
          </Box>
          <FormControlLabel control={<Switch defaultChecked color="secondary" />} label={<Typography sx={{ fontSize: 14 }}>Baselines need client approval before they count</Typography>} />
        </Card>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Card title="Members" action={<Tag tone="neutral">5 people</Tag>} bodySx={{ px: 0, pb: 1.5 }}>
            <Box sx={{ px: 2.5, display: 'flex', gap: 1.25 }}>
              <TextField size="small" placeholder="Invite by email — FTC staff only" fullWidth inputProps={{ 'aria-label': 'Invite by email' }} />
              <Select size="small" value="EDITOR" inputProps={{ 'aria-label': 'Role for invite' }} sx={{ width: 140 }}><MenuItem value="EDITOR">Editor</MenuItem></Select>
              <Button variant="contained" startIcon={<PersonAddAltOutlined />}>Invite</Button>
            </Box>
            <Table size="small">
              <TableHead><TableRow><TableCell sx={{ pl: 2.5 }}>Person</TableCell><TableCell>Role</TableCell><TableCell>Added</TableCell><TableCell sx={{ width: 48 }} /></TableRow></TableHead>
              <TableBody>
                {MEMBERS.map(([ini, n, mail, role, added]) => (
                  <TableRow key={n}>
                    <TableCell sx={{ pl: 2.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                        <Avatar sx={{ width: 32, height: 32, fontSize: 12, fontWeight: 700, bgcolor: role === 'OWNER' ? BRAND.purpleMid : SURFACE.raised, color: role === 'OWNER' ? '#FFFFFF' : SURFACE.textSecondary }}>{ini}</Avatar>
                        <Box><Typography sx={{ fontSize: 14, fontWeight: 600 }}>{n}</Typography><Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>{mail}</Typography></Box>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', px: 1.25, height: 26, borderRadius: `${RADIUS.pill}px`, bgcolor: ROLE_TONE[role][0], color: ROLE_TONE[role][1], fontSize: 12, fontWeight: 700, letterSpacing: '0.04em' }}>{role}</Box>
                    </TableCell>
                    <TableCell sx={{ fontFamily: MONO, color: SURFACE.textMuted }}>{added}</TableCell>
                    <TableCell><IconButton size="small" aria-label={`Options for ${n}`}><MoreVertRounded fontSize="small" /></IconButton></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 2, flexShrink: 0 }}>
            {[['OWNER', 'Everything, including freezing baselines and managing access'], ['EDITOR', 'Create and change scope; cannot freeze or grant access'], ['REVIEWER', 'Read and comment; approves baselines for the client']].map(([r, d]) => (
              <Box key={r} sx={{ p: 2, borderRadius: `${RADIUS.card}px`, bgcolor: r === 'OWNER' ? SURFACE.rail : SURFACE.card, border: r === 'OWNER' ? 0 : `1px solid ${SURFACE.border}` }}>
                <Typography sx={{ fontSize: 12.5, fontWeight: 700, letterSpacing: '0.06em', color: r === 'OWNER' ? '#CFC6F5' : SURFACE.textMuted }}>{r}</Typography>
                <Typography sx={{ fontSize: 13.5, mt: 0.5, color: r === 'OWNER' ? '#FFFFFF' : SURFACE.textSecondary }}>{d}</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </Shell>
  );
}
