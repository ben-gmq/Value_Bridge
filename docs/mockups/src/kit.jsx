import React from 'react';
import { Box, Typography, Avatar, InputBase, Chip, ToggleButton, ToggleButtonGroup } from '@mui/material';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';
import AssignmentOutlined from '@mui/icons-material/AssignmentOutlined';
import StorageOutlined from '@mui/icons-material/StorageOutlined';
import LightbulbOutlined from '@mui/icons-material/LightbulbOutlined';
import ViewQuiltOutlined from '@mui/icons-material/ViewQuiltOutlined';
import ReportProblemOutlined from '@mui/icons-material/ReportProblemOutlined';
import UploadFileOutlined from '@mui/icons-material/UploadFileOutlined';
import LayersOutlined from '@mui/icons-material/LayersOutlined';
import GroupOutlined from '@mui/icons-material/GroupOutlined';
import SearchRounded from '@mui/icons-material/SearchRounded';
import UnfoldMoreRounded from '@mui/icons-material/UnfoldMoreRounded';
import ChevronRightRounded from '@mui/icons-material/ChevronRightRounded';
import { BRAND, SURFACE, STATUS_COLOR_MAP, RADIUS, MONO } from './tokens.js';

const RAIL_TEXT = '#DCD7F2';
const RAIL_MUTED = '#A79FD4';

const NAV = [
  { group: 'Scope', items: [
    ['bfc', 'Business functions', AccountTreeOutlined],
    ['dfd', 'Data flow diagram', HubOutlined],
    ['br', 'Business requirements', AssignmentOutlined],
    ['de', 'Data entities', StorageOutlined],
    ['sol', 'Solutions', LightbulbOutlined],
    ['fr', 'Functional requirements', ViewQuiltOutlined],
  ]},
  { group: 'Control', items: [
    ['issue', 'Issues', ReportProblemOutlined],
    ['import', 'Bulk import', UploadFileOutlined],
    ['baseline', 'Baselines', LayersOutlined],
  ]},
  { group: 'Admin', items: [['project', 'Project & access', GroupOutlined]] },
];

function Rail({ active }) {
  return (
    <Box component="nav" aria-label="Main" sx={{ width: 248, flexShrink: 0, bgcolor: SURFACE.rail, display: 'flex', flexDirection: 'column', px: 1.75, py: 2, gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1 }}>
        <Box sx={{ width: 32, height: 32, borderRadius: '10px', bgcolor: '#FFFFFF', color: SURFACE.rail, display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 13 }}>VB</Box>
        <Typography sx={{ fontWeight: 700, fontSize: 16, color: '#FFFFFF' }}>Value Bridge</Typography>
      </Box>
      <Box component="button" type="button" sx={{ all: 'unset', cursor: 'pointer', borderRadius: `${RADIUS.field}px`, bgcolor: 'rgba(255,255,255,0.08)', px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', color: RAIL_MUTED }}>ENGAGEMENT</Typography>
          <Typography noWrap sx={{ fontSize: 13.5, fontWeight: 600, color: '#FFFFFF' }}>2027 Core Systems Renewal</Typography>
        </Box>
        <UnfoldMoreRounded sx={{ fontSize: 18, color: RAIL_MUTED }} />
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.75, flexGrow: 1 }}>
        {NAV.map((g) => (
          <Box key={g.group} sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            <Typography sx={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '0.06em', color: RAIL_MUTED, px: 1.25, pb: 0.5 }}>{g.group.toUpperCase()}</Typography>
            {g.items.map(([key, label, Icon]) => {
              const on = key === active;
              return (
                <Box key={key} component="a" href="#" aria-current={on ? 'page' : undefined}
                  sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.25, height: 36, borderRadius: `${RADIUS.pill}px`, textDecoration: 'none',
                    color: on ? SURFACE.rail : RAIL_TEXT, bgcolor: on ? '#FFFFFF' : 'transparent', fontSize: 13.5, fontWeight: on ? 700 : 500 }}>
                  <Icon sx={{ fontSize: 18, color: on ? BRAND.purpleMid : RAIL_MUTED }} />{label}
                </Box>
              );
            })}
          </Box>
        ))}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, px: 1, pt: 1.5, borderTop: '1px solid rgba(255,255,255,0.10)' }}>
        <Avatar sx={{ width: 32, height: 32, fontSize: 12.5, fontWeight: 700, bgcolor: BRAND.purpleMid, color: '#FFFFFF' }}>KY</Avatar>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: '#FFFFFF' }}>K. Yamada</Typography>
          <Typography sx={{ fontSize: 12, color: RAIL_MUTED }}>Owner · FTC</Typography>
        </Box>
      </Box>
    </Box>
  );
}

export function Shell({ active, crumbs = [], children }) {
  return (
    <Box sx={{ width: 1440, height: 900, display: 'flex', bgcolor: SURFACE.page, color: SURFACE.text }}>
      <Rail active={active} />
      <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Box component="header" sx={{ height: 56, flexShrink: 0, px: 3, display: 'flex', alignItems: 'center', gap: 2, borderBottom: `1px solid ${SURFACE.border}` }}>
          <Box component="ol" aria-label="Breadcrumb" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, m: 0, p: 0, listStyle: 'none' }}>
            {crumbs.map((c, i) => (
              <Box component="li" key={c} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, fontSize: 13.5, color: i === crumbs.length - 1 ? SURFACE.text : SURFACE.textMuted, fontWeight: i === crumbs.length - 1 ? 600 : 400 }}>
                {i > 0 && <ChevronRightRounded sx={{ fontSize: 16, color: SURFACE.textMuted }} />}{c}
              </Box>
            ))}
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: 300, height: 36, px: 1.5, borderRadius: `${RADIUS.field}px`, bgcolor: SURFACE.field, border: `1px solid ${SURFACE.border}` }}>
            <SearchRounded sx={{ fontSize: 18, color: SURFACE.textMuted }} />
            <InputBase placeholder="Search codes, requirements, entities" inputProps={{ 'aria-label': 'Search' }} sx={{ fontSize: 13.5, flexGrow: 1 }} />
            <Box sx={{ fontFamily: MONO, fontSize: 11.5, color: SURFACE.textMuted, border: `1px solid ${SURFACE.border}`, borderRadius: '6px', px: 0.75 }}>/</Box>
          </Box>
          <Chip size="small" label="Working · after v1.2" sx={{ bgcolor: BRAND.purpleTint, color: BRAND.purpleLight, height: 30, px: 0.5 }}
            icon={<Box component="span" sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: BRAND.purpleLight, ml: '10px !important' }} />} />
        </Box>
        <Box component="main" sx={{ flexGrow: 1, minHeight: 0, display: 'flex', flexDirection: 'column', px: 3, pt: 2.5, pb: 1.5, gap: 2 }}>
          {children}
        </Box>
        <Box component="footer" sx={{ height: 34, flexShrink: 0, px: 3, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', borderTop: `1px solid ${SURFACE.border}`, fontSize: 12, color: SURFACE.textMuted }}>
          © 2026 Fortience Consulting Inc. All rights reserved.
        </Box>
      </Box>
    </Box>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 2, flexShrink: 0 }}>
      <Box sx={{ minWidth: 0 }}>
        {eyebrow && <Box sx={{ mb: 0.5 }}>{eyebrow}</Box>}
        <Typography variant="h1" component="h1">{title}</Typography>
        {subtitle && <Typography sx={{ fontSize: 13.5, color: SURFACE.textSecondary, mt: 0.5 }}>{subtitle}</Typography>}
      </Box>
      <Box sx={{ flexGrow: 1 }} />
      <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'center' }}>{actions}</Box>
    </Box>
  );
}

export function Card({ title, action, children, sx, bodySx, component = 'section' }) {
  return (
    <Box component={component} sx={{ bgcolor: SURFACE.card, border: `1px solid ${SURFACE.border}`, borderRadius: `${RADIUS.card}px`, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', ...sx }}>
      {title && (
        <Box sx={{ px: 2.5, pt: 2, pb: 1.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography variant="h2" component="h2" sx={{ fontSize: 15 }}>{title}</Typography>
          <Box sx={{ flexGrow: 1 }} />
          {action}
        </Box>
      )}
      <Box sx={{ px: 2.5, pb: 2.5, pt: title ? 0 : 2.5, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0, flexGrow: 1, ...bodySx }}>{children}</Box>
    </Box>
  );
}

export function SectionLabel({ children, sx }) {
  return <Typography sx={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', color: SURFACE.textMuted, ...sx }}>{children}</Typography>;
}

export function Code({ children, tone = 'navy', sx }) {
  const c = tone === 'purple' ? BRAND.purpleLight : tone === 'teal' ? BRAND.tealText : tone === 'muted' ? SURFACE.textMuted : BRAND.primaryLight;
  return <Box component="span" sx={{ fontFamily: MONO, fontSize: 13, color: c, whiteSpace: 'nowrap', ...sx }}>{children}</Box>;
}

export function Status({ tone = 'neutral', children, size = 'md' }) {
  const s = STATUS_COLOR_MAP[tone];
  return (
    <Box component="span" sx={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 0.75, px: size === 'sm' ? 1 : 1.25, height: size === 'sm' ? 24 : 28, borderRadius: `${RADIUS.pill}px`, bgcolor: s.bg, color: s.fg, fontSize: size === 'sm' ? 12 : 12.5, fontWeight: 600, whiteSpace: 'nowrap' }}>
      <Box component="span" sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: s.dot }} />{children}
    </Box>
  );
}

export function Tag({ children, tone = 'purple', sx }) {
  const map = {
    purple: [BRAND.purpleTint, BRAND.purpleLight],
    navy: ['rgba(74,115,168,0.18)', BRAND.primaryLight],
    teal: [BRAND.tealTint, BRAND.tealText],
    neutral: ['rgba(183,180,196,0.10)', SURFACE.textSecondary],
  }[tone];
  return <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, px: 1.1, height: 24, borderRadius: `${RADIUS.pill}px`, bgcolor: map[0], color: map[1], fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', ...sx }}>{children}</Box>;
}

// Level 1–5 of the business function chart, stepped in the FTC purple scale.
export const LEVEL_COLORS = ['#E3DCFA', '#C9B9F5', '#B09AEE', '#9679E5', '#7848DC'];
export function LevelBadge({ level }) {
  return <Box component="span" aria-label={`Level ${level}`} sx={{ display: 'inline-grid', placeItems: 'center', width: 22, height: 22, borderRadius: '8px', fontSize: 11.5, fontWeight: 700, fontFamily: MONO, bgcolor: level >= 4 ? LEVEL_COLORS[level - 1] : 'transparent', color: level >= 4 ? SURFACE.rail : LEVEL_COLORS[level - 1], border: `1.5px solid ${LEVEL_COLORS[level - 1]}` }}>{level}</Box>;
}

export function Raci({ value, label }) {
  return (
    <ToggleButtonGroup exclusive value={value} size="small" aria-label={label}
      sx={{ bgcolor: SURFACE.field, borderRadius: `${RADIUS.pill}px`, p: '3px', gap: '2px', border: `1px solid ${SURFACE.border}`,
        '& .MuiToggleButton-root': { border: 0, borderRadius: `${RADIUS.pill}px !important`, width: 30, height: 26, fontSize: 12.5, fontWeight: 700, color: SURFACE.textMuted, p: 0 },
        '& .Mui-selected': { bgcolor: `${BRAND.purpleMid} !important`, color: '#FFFFFF !important' } }}>
      {['R', 'A', 'C', 'I'].map((k) => <ToggleButton key={k} value={k} aria-label={k}>{k}</ToggleButton>)}
    </ToggleButtonGroup>
  );
}

export function KV({ k, v, mono }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, fontSize: 13.5 }}>
      <Box sx={{ width: 120, flexShrink: 0, color: SURFACE.textMuted }}>{k}</Box>
      <Box sx={{ color: SURFACE.text, fontFamily: mono ? MONO : undefined, minWidth: 0 }}>{v}</Box>
    </Box>
  );
}

export function Segmented({ options, value, label, size = 'md' }) {
  return (
    <ToggleButtonGroup exclusive value={value} aria-label={label}
      sx={{ bgcolor: SURFACE.field, borderRadius: `${RADIUS.pill}px`, p: '3px', gap: '2px', border: `1px solid ${SURFACE.border}`, alignSelf: 'flex-start',
        '& .MuiToggleButton-root': { border: 0, borderRadius: `${RADIUS.pill}px !important`, px: size === 'sm' ? 1.5 : 2, height: size === 'sm' ? 28 : 32, fontSize: 13.5, fontWeight: 600, color: SURFACE.textSecondary, textTransform: 'none', whiteSpace: 'nowrap' },
        '& .Mui-selected': { bgcolor: `${BRAND.purpleMid} !important`, color: '#FFFFFF !important' } }}>
      {options.map((o) => <ToggleButton key={o} value={o}>{o}</ToggleButton>)}
    </ToggleButtonGroup>
  );
}

export function Steps({ steps, current }) {
  return (
    <Box component="ol" aria-label="Progress" sx={{ display: 'flex', alignItems: 'center', gap: 1, m: 0, p: 0, listStyle: 'none' }}>
      {steps.map((st, i) => {
        const done = i < current, on = i === current;
        return (
          <Box component="li" key={st} aria-current={on ? 'step' : undefined} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {i > 0 && <Box sx={{ width: 28, height: 2, borderRadius: 1, bgcolor: done || on ? BRAND.purpleMid : SURFACE.borderStrong }} />}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, height: 32, pl: 0.5, pr: 1.5, borderRadius: `${RADIUS.pill}px`, bgcolor: on ? BRAND.purpleTint : 'transparent', border: on ? '1px solid rgba(120,72,220,0.5)' : '1px solid transparent' }}>
              <Box sx={{ width: 24, height: 24, borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 700,
                bgcolor: done ? BRAND.purpleMid : on ? '#FFFFFF' : 'transparent', color: done ? '#FFFFFF' : on ? SURFACE.rail : SURFACE.textMuted, border: done || on ? 0 : `1.5px solid ${SURFACE.borderStrong}` }}>{done ? '✓' : i + 1}</Box>
              <Typography sx={{ fontSize: 13.5, fontWeight: on ? 700 : 500, color: on ? '#FFFFFF' : done ? SURFACE.textSecondary : SURFACE.textMuted, whiteSpace: 'nowrap' }}>{st}</Typography>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

// Highlight tile in FTC Dark Purple — used once per screen for the key figure.
export function PurpleTile({ label, value, unit, note, sx }) {
  return (
    <Box sx={{ borderRadius: `${RADIUS.card}px`, bgcolor: SURFACE.rail, p: 2.25, display: 'flex', flexDirection: 'column', gap: 0.5, ...sx }}>
      <Typography sx={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', color: '#CFC6F5' }}>{label}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
        <Typography sx={{ fontFamily: MONO, fontSize: 30, fontWeight: 500, color: '#FFFFFF', lineHeight: 1.1 }}>{value}</Typography>
        {unit && <Typography sx={{ fontSize: 14, color: '#CFC6F5', whiteSpace: 'nowrap' }}>{unit}</Typography>}
      </Box>
      {note && <Typography sx={{ fontSize: 12.5, color: '#CFC6F5' }}>{note}</Typography>}
    </Box>
  );
}

export function Tile({ label, value, tone, note }) {
  const c = tone ? STATUS_COLOR_MAP[tone].fg : SURFACE.text;
  return (
    <Box sx={{ borderRadius: `${RADIUS.card}px`, bgcolor: SURFACE.card, border: `1px solid ${SURFACE.border}`, p: 2.25, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: SURFACE.textMuted }}>{label}</Typography>
      <Typography sx={{ fontFamily: MONO, fontSize: 28, fontWeight: 500, color: c, lineHeight: 1.1 }}>{value}</Typography>
      {note && <Typography sx={{ fontSize: 12.5, color: SURFACE.textMuted }}>{note}</Typography>}
    </Box>
  );
}

export { BRAND, SURFACE, STATUS_COLOR_MAP, RADIUS, MONO };
