// The mockups' component kit (docs/mockups/src/kit.jsx, D-51), rebuilt on theme tokens so it works in
// both colour schemes. Every screen composes these; no screen restyles them locally.
import { Box, ButtonBase, IconButton, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import { MONO } from '../theme/theme';

const R = { card: '24px', field: '14px', pill: 999 };

/** A titled surface: 24px radius, hairline border, title row with an optional action at the right. */
export function Card({ title, action, children, sx, bodySx, component = 'section', tone }) {
  return (
    <Box component={component} sx={(th) => ({
      bgcolor: tone === 'purple' ? th.vars.palette.brand.ftc : th.vars.palette.background.paper,
      color: tone === 'purple' ? th.vars.palette.brand.onFtc : undefined,
      border: `1px solid ${tone === 'purple' ? 'transparent' : th.vars.palette.divider}`, borderRadius: R.card,
      display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden', ...(typeof sx === 'function' ? sx(th) : sx) })}>
      {(title || action) && (
        <Box sx={{ px: 2.5, pt: 2, pb: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          {title && <Typography variant="h6" component="h2" sx={{ fontSize: 15 }}>{title}</Typography>}
          <Box sx={{ flexGrow: 1 }} />
          {action}
        </Box>
      )}
      <Box sx={{ px: 2.5, pb: 2.5, pt: title || action ? 0 : 2.5, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0,
        flexGrow: 1, ...bodySx }}>{children}</Box>
    </Box>
  );
}

/** Small-caps section label: "DATA USAGE · CRUD". */
export function SectionLabel({ children, sx, action, info }) {
  const titled = children != null && children !== false;       // untitled: the row carries only its info and action
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ...sx }}>
      {titled && <Typography component="h3" sx={(th) => ({ fontSize: 12.5, fontWeight: 600, letterSpacing: '0.06em', color: th.vars.palette.brand.muted,
        textTransform: 'uppercase' })}>{children}</Typography>}
      {info && <InfoTip title={info} sx={titled ? { ml: -0.75 } : undefined} />}
      {action && <><Box sx={{ flexGrow: 1 }} />{action}</>}
    </Box>
  );
}

/** A group header inside a panel: 14/600, sentence case — one step above SectionLabel's small caps.
 * `info` puts the explanation behind an (i) tooltip instead of an always-on paragraph (10d). */
export function GroupHeader({ children, info, action, id, sx }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, minHeight: 28, ...sx }}>
      <Typography component="h3" id={id} sx={{ fontSize: 14, fontWeight: 600, color: 'text.primary' }}>{children}</Typography>
      {info && <InfoTip title={info} />}
      {action && <><Box sx={{ flexGrow: 1 }} />{action}</>}
    </Box>
  );
}

/** An (i) that explains on hover or focus. The text is the label too, so a screen reader hears it. */
export function InfoTip({ title, sx }) {
  return (
    <Tooltip title={title} enterTouchDelay={0}>
      <IconButton size="small" aria-label={title} sx={(th) => ({ p: 0.5, color: th.vars.palette.brand.muted, ...sx })}>
        <InfoOutlined sx={{ fontSize: 16 }} />
      </IconButton>
    </Tooltip>
  );
}

/**
 * One fact at a glance that opens its editor (10d "How it runs" tiles): a 12.5/600 label, the value
 * at 14/600, an optional muted note. Empty → muted `emptyText` and a small amber dot on the label;
 * no alert box. `selected` marks the tile whose editor is open below.
 */
export function FactTile({ label, value, note, empty, emptyText, onClick, selected, controls, sx }) {
  return (
    <ButtonBase onClick={onClick} aria-expanded={selected} aria-controls={controls} focusRipple
      sx={(th) => ({ display: 'flex', flexDirection: 'column', alignItems: 'stretch', textAlign: 'left', gap: 0.5,
        minWidth: 0, minHeight: 76, px: 1.75, py: 1.5, borderRadius: R.field, font: 'inherit', color: 'inherit',
        bgcolor: selected ? th.vars.palette.brand.purpleTint : th.vars.palette.background.subtle,
        outline: selected ? `1px solid ${th.vars.palette.brand.ftcViolet}` : `1px solid ${th.vars.palette.divider}`,
        transition: 'background-color 120ms ease-out',
        '&:hover': { bgcolor: selected ? th.vars.palette.brand.purpleTint : th.vars.palette.brand.selected },
        '&.Mui-focusVisible': { outline: `2px solid ${th.vars.palette.brand.ftcViolet}`, outlineOffset: 1 }, ...sx })}>
      <Box component="span" sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: 12.5, fontWeight: 600,
        color: th.vars.palette.brand.muted })}>
        {label}
        {empty && <Box component="span" aria-hidden sx={(th) => ({ width: 6, height: 6, borderRadius: '50%',
          bgcolor: th.vars.palette.status.caution, flex: 'none' })} />}
      </Box>
      {empty ? (
        <Box component="span" sx={{ fontSize: 14, color: 'text.secondary' }}>{emptyText}</Box>
      ) : (
        <Box component="span" sx={{ fontSize: 14, fontWeight: 600, color: 'text.primary', minWidth: 0, overflow: 'hidden',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', wordBreak: 'break-word' }}>{value}</Box>
      )}
      {note && <Box component="span" sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.muted, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' })}>{note}</Box>}
    </ButtonBase>
  );
}

/** A monospace code: BR-0043 (purple), FR-0012 / SOL-0004 (navy), DE-0011 (teal), hierarchy codes (muted). */
export function Code({ children, tone = 'navy', sx }) {
  return (
    <Box component="span" sx={(th) => ({ fontFamily: MONO, fontSize: 13, whiteSpace: 'nowrap',
      color: { purple: th.vars.palette.brand.purpleText, teal: th.vars.palette.brand.tealText, muted: th.vars.palette.brand.muted,
        navy: th.vars.palette.brand.link }[tone], ...sx })}>{children}</Box>
  );
}

/** The tone of an object code by its prefix — one place, so every screen colours codes alike. */
export const codeTone = (code = '') => (/^BR-/.test(code) ? 'purple' : /^DE-/.test(code) ? 'teal'
  : /^\d/.test(code) ? 'muted' : 'navy');

/** Status pill with a dot: ok / caution / escalate / neutral. */
export function Status({ tone = 'neutral', children, size = 'md', sx }) {
  return (
    <Box component="span" sx={(th) => ({ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 0.75,
      px: size === 'sm' ? 1 : 1.25, height: size === 'sm' ? 24 : 28, borderRadius: R.pill, whiteSpace: 'nowrap',
      bgcolor: th.vars.palette.status[`${tone}Bg`], color: th.vars.palette.status[tone], fontSize: size === 'sm' ? 12 : 12.5,
      fontWeight: 600, ...sx })}>
      <Box component="span" aria-hidden sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: 'currentColor' }} />{children}
    </Box>
  );
}

/** A soft tag: purple (BR, selection), navy (actions/data), teal (data entities), neutral.
 * `size="lg"` is the 12.5 px label the process screen holds to (10e); the default stays 12 elsewhere. */
export function Tag({ children, tone = 'purple', sx, icon, size = 'md' }) {
  return (
    <Box component="span" sx={(th) => {
      const map = {
        purple: [th.vars.palette.brand.purpleTint, th.vars.palette.brand.purpleText],
        navy: [th.vars.palette.brand.navyTint, th.vars.palette.brand.link],
        teal: [th.vars.palette.brand.tealTint, th.vars.palette.brand.tealText],
        neutral: [th.vars.palette.status.neutralBg, th.vars.palette.status.neutral],
        ok: [th.vars.palette.status.okBg, th.vars.palette.status.ok],
        caution: [th.vars.palette.status.cautionBg, th.vars.palette.status.caution],
        escalate: [th.vars.palette.status.escalateBg, th.vars.palette.status.escalate],
      }[tone];
      return { display: 'inline-flex', alignItems: 'center', gap: 0.5, px: 1.1, height: 24, borderRadius: R.pill, bgcolor: map[0],
        color: map[1], fontSize: size === 'lg' ? 12.5 : 12, fontWeight: 600, whiteSpace: 'nowrap', ...sx };
    }}>{icon}{children}</Box>
  );
}

/** Level 1–5 of the business function chart, stepped in the FTC purple scale; 4–5 filled. */
export function LevelBadge({ level, label }) {
  const lv = Math.min(Math.max(Number(level) || 1, 1), 5);
  return (
    <Box component="span" aria-label={label ?? `Level ${lv}`} sx={(th) => {
      const c = th.vars.palette.brand[`level${lv}`];
      return { display: 'inline-grid', placeItems: 'center', width: 22, height: 22, borderRadius: '8px', flexShrink: 0, fontSize: 12.5,
        fontWeight: 700, fontFamily: MONO, bgcolor: lv >= 4 ? c : 'transparent', color: lv >= 4 ? th.vars.palette.brand.ftc : c,
        border: `1.5px solid ${c}` };
    }}>{lv}</Box>
  );
}

/** Label / value row for record panels. */
export function KV({ k, v, mono }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, fontSize: 13.5 }}>
      <Box sx={(th) => ({ width: 120, flexShrink: 0, color: th.vars.palette.brand.muted })}>{k}</Box>
      <Box sx={{ fontFamily: mono ? MONO : undefined, minWidth: 0, wordBreak: 'break-word' }}>{v}</Box>
    </Box>
  );
}

/** Pill segmented control. `options` = [{ value, label }] or strings. */
export function Segmented({ options, value, onChange, label, size = 'md', sx }) {
  const opts = options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o));
  return (
    <ToggleButtonGroup exclusive value={value} onChange={(_, v) => v !== null && onChange?.(v)} aria-label={label}
      sx={(th) => ({ bgcolor: th.vars.palette.background.field, borderRadius: R.pill, p: '3px', gap: '2px', flexWrap: 'wrap',
        border: `1px solid ${th.vars.palette.divider}`, alignSelf: 'flex-start',
        '& .MuiToggleButton-root': { border: 0, borderRadius: `${R.pill}px !important`, px: size === 'sm' ? 1.5 : 2,
          height: size === 'sm' ? 28 : 32, fontSize: 13.5, fontWeight: 600, color: th.vars.palette.text.secondary, whiteSpace: 'nowrap' },
        '& .Mui-selected': { bgcolor: `${th.vars.palette.brand.ftcViolet} !important`, color: `${th.vars.palette.brand.onFtc} !important` },
        ...sx })}>
      {opts.map((o) => <ToggleButton key={o.value} value={o.value} aria-label={o.aria}>{o.label}</ToggleButton>)}
    </ToggleButtonGroup>
  );
}

/** The one key figure per screen, in FTC Dark Purple. */
export function PurpleTile({ label, labelSuffix, value, unit, note, sx }) {
  return (
    <Box sx={(th) => ({ borderRadius: R.card, bgcolor: th.vars.palette.brand.ftc, p: 2.25, display: 'flex', flexDirection: 'column',
      gap: 0.5, minWidth: 0, ...sx })}>
      <Typography sx={(th) => ({ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', color: th.vars.palette.brand.onFtcTile,
        textTransform: 'uppercase' })}>{label}
        {labelSuffix && <Box component="span" sx={{ textTransform: 'none' }}> {labelSuffix}</Box>}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, flexWrap: 'wrap' }}>
        <Typography sx={(th) => ({ fontFamily: MONO, fontSize: 30, fontWeight: 500, color: th.vars.palette.brand.onFtc, lineHeight: 1.1 })}>{value}</Typography>
        {unit && <Typography sx={(th) => ({ fontSize: 14, color: th.vars.palette.brand.onFtcTile })}>{unit}</Typography>}
      </Box>
      {note && <Typography sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.onFtcTile })}>{note}</Typography>}
    </Box>
  );
}

/** A figure tile; `tone` colours the value by status. */
export function Tile({ label, value, tone, note, icon }) {
  return (
    <Box sx={(th) => ({ borderRadius: R.card, bgcolor: th.vars.palette.background.paper, border: `1px solid ${th.vars.palette.divider}`,
      p: 2.25, display: 'flex', flexDirection: 'column', gap: 0.5, minWidth: 0 })}>
      <Typography sx={(th) => ({ fontSize: 12.5, fontWeight: 600, color: th.vars.palette.brand.muted, display: 'flex', alignItems: 'center', gap: 0.5 })}>
        {icon}{label}</Typography>
      <Typography sx={(th) => ({ fontFamily: MONO, fontSize: 28, fontWeight: 500, lineHeight: 1.1,
        color: tone ? th.vars.palette.status[tone] : th.vars.palette.text.primary })}>{value}</Typography>
      {note && <Typography sx={(th) => ({ fontSize: 12.5, color: th.vars.palette.brand.muted })}>{note}</Typography>}
    </Box>
  );
}

/** A selectable row inside a card list (versions, steps, nodes). */
export function ListRow({ selected, children, onClick, component, to, sx, ...rest }) {
  return (
    <Box component={component} to={to} onClick={onClick} {...rest} sx={(th) => ({ display: 'flex', alignItems: 'center', gap: 1.25, px: 1.5, py: 1.25,
      borderRadius: R.field, textDecoration: 'none', color: 'inherit', cursor: onClick || to ? 'pointer' : 'default',
      bgcolor: selected ? th.vars.palette.brand.purpleTint : th.vars.palette.background.subtle,
      outline: selected ? `1px solid ${th.vars.palette.brand.ftcViolet}` : 'none',
      '&:hover': onClick || to ? { bgcolor: th.vars.palette.brand.selected } : undefined, ...sx })}>
      {children}
    </Box>
  );
}

/** Inline monospace "In · Out" / derived chips used by CRUD and I/O tables. */
export function MonoChip({ children, tone = 'neutral', size = 'md' }) {
  return <Tag tone={tone} sx={{ fontFamily: MONO, fontSize: size === 'lg' ? 12.5 : 11.5, height: 22, px: 0.9 }}>{children}</Tag>;
}
