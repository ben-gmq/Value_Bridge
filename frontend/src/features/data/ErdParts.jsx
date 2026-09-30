// The ERD's node and edge types for <ModelCanvas kind="erd"> (design §7.14, §14.6; spec §7 3b).
// Every label is JSX text, never innerHTML (§14.5). Colours come from theme tokens only.
import { createContext, memo, useContext } from 'react';
import { BaseEdge, Handle, Position, getSmoothStepPath, useStore } from '@xyflow/react';
import { Box, IconButton, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import KeyRounded from '@mui/icons-material/KeyRounded';
import LinkRounded from '@mui/icons-material/LinkRounded';
import UnfoldLessRounded from '@mui/icons-material/UnfoldLessRounded';
import UnfoldMoreRounded from '@mui/icons-material/UnfoldMoreRounded';
import { LOW_ZOOM } from '../../canvas/layout';
import { MONO } from '../../theme/theme';
import { t } from '../../i18n/t';
import { CARD_W, ENTITY_HANDLE, GHOST, HEADER_H, ROW_H, canCollapse, rowHandle, visibleRows } from './erdModel';
import { requiredText } from './fieldRules';

/** What every card needs but no card owns: type labels, the collapse toggle, edit rights. */
export const ErdContext = createContext({ getLabel: (c) => c, onToggle: () => {}, canEdit: false });

const useLowZoom = () => useStore((s) => s.transform[2] < LOW_ZOOM);
// The ERD is read-only (A-S3-6): handles exist for landing lines, not for drawing them. A line
// ends at the handle's outer edge, so the handle is a point on the border, not a 14px dot.
const HIDDEN = { opacity: 0, pointerEvents: 'none', width: 1, height: 1, minWidth: 0, minHeight: 0, border: 0 };

/** The four fixed handles of one field, {s|t}-{L|R}-{fieldId} (§14.6). */
function FieldHandles({ id }) {
  return (<>
    <Handle type="target" position={Position.Left} id={rowHandle('t', 'L', id)} isConnectable={false} style={HIDDEN} />
    <Handle type="source" position={Position.Left} id={rowHandle('s', 'L', id)} isConnectable={false} style={HIDDEN} />
    <Handle type="target" position={Position.Right} id={rowHandle('t', 'R', id)} isConnectable={false} style={HIDDEN} />
    <Handle type="source" position={Position.Right} id={rowHandle('s', 'R', id)} isConnectable={false} style={HIDDEN} />
  </>);
}

function fieldTip(f, getLabel) {
  return t('data.erd.fieldTip', { name: f.field_name,
    type: f.data_type_code ? getLabel(f.data_type_code) : t('data.erd.typeNone'),
    required: requiredText(f.is_mandatory),
    description: f.description ? t('data.erd.fieldTipDesc', { text: f.description }) : '' });
}

const ROW_SX = { position: 'relative', height: ROW_H, display: 'flex', alignItems: 'center', px: 1,
  borderTop: 1, borderColor: 'divider' };

function FieldRow({ f, low, getLabel }) {
  const icon = { fontSize: 14, flexShrink: 0, color: 'brand.tealText' };
  return (
    <Box sx={ROW_SX} title={fieldTip(f, getLabel)}>
      <FieldHandles id={f.data_field_id} />
      <Box sx={{ visibility: low ? 'hidden' : 'visible', display: 'flex', alignItems: 'center', gap: 0.5, minWidth: 0, width: '100%' }}>
        {/* A PK-and-FK field shows both marks (R2-NEW-3). */}
        {f.is_primary_key && <KeyRounded sx={icon} aria-label={t('data.erd.pk')} />}
        {f.is_foreign_key && <LinkRounded sx={icon} aria-label={t('data.erd.fk')} />}
        {!f.is_primary_key && !f.is_foreign_key && <Box sx={{ width: 14, flexShrink: 0 }} />}
        <Typography noWrap sx={{ fontSize: 12.5, fontWeight: f.is_primary_key ? 700 : 400, flex: 1, minWidth: 0 }}>
          {f.field_name}</Typography>
        {f.is_foreign_key && f.ref_de_name && (
          <Typography noWrap sx={{ fontSize: 11, color: 'text.secondary', maxWidth: 110, flexShrink: 0 }}>
            {t('data.erd.fkTo', { name: f.ref_de_name })}</Typography>)}
      </Box>
    </Box>
  );
}

function EntityCardView({ data }) {
  const { entity, collapsed } = data;
  const { getLabel, onToggle, canEdit } = useContext(ErdContext);
  const low = useLowZoom();
  const { rows, hidden } = visibleRows(entity, collapsed);
  const noKey = entity.warnings.includes('NO_KEY');
  const toggleTip = t(canEdit ? (collapsed ? 'data.erd.expand' : 'data.erd.collapse')
    : (collapsed ? 'data.erd.expandLocal' : 'data.erd.collapseLocal'));
  return (
    <Box sx={(th) => ({ width: CARD_W, borderRadius: 1.5, overflow: 'visible', bgcolor: th.vars.palette.background.paper,
      border: 1.5, borderColor: th.vars.palette.brand.teal })}>
      <Box sx={(th) => ({ position: 'relative', height: HEADER_H, px: 1, display: 'flex', alignItems: 'center', gap: 0.75,
        bgcolor: th.vars.palette.brand.teal, color: th.vars.palette.brand.onTeal,
        borderTopLeftRadius: 4, borderTopRightRadius: 4 })}>
        <Handle type="target" position={Position.Left} id={ENTITY_HANDLE} isConnectable={false} style={HIDDEN} />
        <Box sx={{ visibility: low ? 'hidden' : 'visible', minWidth: 0, flex: 1 }}>
          <Typography sx={{ fontFamily: MONO, fontSize: 11, lineHeight: 1.2 }}>{entity.de_number}</Typography>
          <Typography noWrap sx={{ fontSize: 13.5, fontWeight: 700, lineHeight: 1.3 }}>{entity.de_name}</Typography>
        </Box>
        {noKey && (
          <Box title={t('data.erd.noKeyHelp')} sx={(th) => ({ px: 0.75, py: 0.25, borderRadius: 1, fontSize: 11, fontWeight: 700,
            flexShrink: 0, bgcolor: th.vars.palette.status.cautionBg, color: th.vars.palette.status.caution })}>
            {t('data.erd.noKey')}</Box>)}
        {canCollapse(entity) && (
          <Tooltip title={toggleTip} disableInteractive>
            <IconButton size="small" className="nodrag" aria-label={toggleTip} sx={{ color: 'inherit', flexShrink: 0 }}
              onClick={(e) => { e.stopPropagation(); onToggle(entity.data_entity_id); }}
              onDoubleClick={(e) => e.stopPropagation()}>
              {collapsed ? <UnfoldMoreRounded fontSize="small" /> : <UnfoldLessRounded fontSize="small" />}
            </IconButton>
          </Tooltip>)}
      </Box>
      {rows.map((f) => <FieldRow key={f.data_field_id} f={f} low={low} getLabel={getLabel} />)}
      {!entity.fields.length && (
        <Box sx={ROW_SX}><Typography sx={{ fontSize: 12, color: 'text.secondary', visibility: low ? 'hidden' : 'visible' }}>
          {t('data.erd.noFields')}</Typography></Box>)}
      {hidden.length > 0 && (
        // Hidden attributes keep their handles, stacked here under the same ids (§14.6).
        <Box sx={ROW_SX}>
          {hidden.map((f) => <FieldHandles key={f.data_field_id} id={f.data_field_id} />)}
          <Typography sx={{ fontSize: 12, color: 'text.secondary', fontStyle: 'italic', pl: 2.5, visibility: low ? 'hidden' : 'visible' }}>
            {t('data.erd.more', { n: hidden.length })}</Typography>
        </Box>)}
    </Box>
  );
}

// A drag moves a card many times a second; its rows only change with its data (criterion 17).
export const EntityCard = memo(EntityCardView, (a, b) => a.data === b.data);

function GhostCardView({ data }) {
  const low = useLowZoom();
  const x = data.ghost;
  return (
    <Box sx={(th) => ({ width: GHOST.w, height: GHOST.h, px: 1, py: 0.75, borderRadius: 1.5, position: 'relative',
      border: 1.5, borderStyle: 'dashed', borderColor: th.vars.palette.brand.lineStrong,
      bgcolor: th.vars.palette.background.subtle })}>
      <Handle type="target" position={Position.Left} id={ENTITY_HANDLE} isConnectable={false} style={HIDDEN} />
      <Box sx={{ visibility: low ? 'hidden' : 'visible' }}>
        <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 600 }}>
          <Box component="span" sx={{ fontFamily: MONO, fontSize: 11, color: 'brand.tealText', mr: 0.75 }}>{x.de_number}</Box>
          {x.de_name}</Typography>
        <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
          {t(x.retired ? 'data.erd.retiredParent' : 'data.erd.outside')}</Typography>
      </Box>
    </Box>
  );
}

export const GhostCard = memo(GhostCardView, (a, b) => a.data === b.data);

export const ERD_NODE_TYPES = { entity: EntityCard, ghost: GhostCard };

// ---- crow's-foot lines (the spec's glyph table; A-S3-8: the child end never claims a minimum) ----
const MARK = { one: 'erd-one', zeroOne: 'erd-zero-one', zeroMany: 'erd-zero-many' };
const parentMark = (c) => (c === '1' ? MARK.one : MARK.zeroOne);          // || or |o
const childMark = (c) => (c === '1' ? MARK.zeroOne : MARK.zeroMany);      // o| or o{

function ErdEdgeView({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, data }) {
  const low = useLowZoom();
  const theme = useTheme();
  const p = theme.vars.palette;
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY,
    targetPosition, offset: 30, borderRadius: 6 });
  return (
    <BaseEdge id={id} path={path} interactionWidth={12}
      markerStart={`url(#${childMark(data.child)})`} markerEnd={`url(#${parentMark(data.parent)})`}
      style={{ stroke: p.text.secondary, strokeWidth: 1.5, strokeDasharray: data.identifying ? undefined : '6 4' }}
      label={low ? undefined : label} labelX={labelX} labelY={labelY}
      labelStyle={{ fill: p.text.primary, fontSize: 11.5 }} labelBgStyle={{ fill: p.background.paper }}
      labelBgPadding={[4, 2]} />
  );
}

// Module-level, so ModelCanvas's memo sees one object for the page's life (§14.6).
export const ERD_EDGE_TYPES = { erd: ErdEdgeView };

/**
 * The marker defs, drawn once per page. Each glyph points at its entity along +x, so one marker
 * serves both ends: markerEnd at the parent, markerStart (auto-start-reverse) at the child.
 */
export function ErdMarkers() {
  const theme = useTheme();
  const p = theme.vars.palette;
  const line = { stroke: p.text.secondary, strokeWidth: 1.5, fill: 'none' };
  const ring = { stroke: p.text.secondary, strokeWidth: 1.5, fill: p.background.paper };
  const marker = (markerId, children) => (
    <marker id={markerId} viewBox="0 0 20 20" refX="20" refY="10" markerWidth="20" markerHeight="20"
      markerUnits="userSpaceOnUse" orient="auto-start-reverse">{children}</marker>);
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: 'absolute' }}>
      <defs>
        {marker(MARK.one, <path d="M16 4 V16 M11 4 V16" style={line} />)}
        {marker(MARK.zeroOne, <><path d="M16 4 V16" style={line} /><circle cx="8" cy="10" r="3.5" style={ring} /></>)}
        {marker(MARK.zeroMany, <><path d="M12 10 L20 3 M12 10 L20 17 M12 10 H20" style={line} />
          <circle cx="7" cy="10" r="3.5" style={ring} /></>)}
      </defs>
    </svg>
  );
}

/** "exactly one : zero or many", for the table view. */
export const cardinalityText = (rel) => t('data.erd.cardinality', {
  parent: t(`data.erd.card.${rel.parent_cardinality}`), child: t(`data.erd.card.child.${rel.child_cardinality}`) });
