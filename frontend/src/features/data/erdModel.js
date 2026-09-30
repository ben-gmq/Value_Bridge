// The ERD's pure half (spec §7 3b, design §7.14 / §14.6): card geometry, the collapse rule, and
// graph → React Flow nodes and edges. No React here, so the page rebuilds these only when the
// data, the layout, a collapse or the selection changes — never per drag frame (criterion 17).
import { LAYERED_RIGHT, elkLayout, pushClear } from '../../canvas/layout';

export const CARD_W = 264;
export const HEADER_H = 46;
export const ROW_H = 24;
export const GHOST = { w: 200, h: 56 };
export const SHOWN_ATTRS = 8;                 // more than this collapse to "+N more" (§7.14)
const PAD = 6;

export const entityNodeId = (deId) => `e${deId}`;
export const ghostNodeId = (deId) => `x${deId}`;
export const ENTITY_HANDLE = 't-L-entity';    // every card has it; stubs always land here (R2-NEW-2)
export const rowHandle = (st, side, fieldId) => `${st}-${side}-${fieldId}`;   // never changes (§14.6)

/** Key rows (PK, then FK) always show; attributes are the rest, in the service's order. */
export function splitFields(entity) {
  const keys = entity.fields.filter((f) => f.is_primary_key || f.is_foreign_key);
  const attrs = entity.fields.filter((f) => !f.is_primary_key && !f.is_foreign_key);
  return { keys, attrs };
}

export const canCollapse = (entity) => splitFields(entity).attrs.length > SHOWN_ATTRS;

/**
 * R2-NEW-1: no stored row → default by size (collapsed when more than 8 attributes); a stored
 * row → its flag, false included, so an expanded card stays expanded after reload.
 */
export function initialCollapsed(g) {
  const stored = new Map(g.layout.filter((p) => p.object_type === 'ENTITY').map((p) => [p.object_id, p.collapsed]));
  return new Map(g.entities.map((e) => [e.data_entity_id,
    stored.has(e.data_entity_id) ? stored.get(e.data_entity_id) : canCollapse(e)]));
}

/** The rows a card renders, and the attributes whose handles stack on the summary row. */
export function visibleRows(entity, collapsed) {
  const { keys, attrs } = splitFields(entity);
  const folded = collapsed && attrs.length > SHOWN_ATTRS;
  return { rows: [...keys, ...(folded ? attrs.slice(0, SHOWN_ATTRS) : attrs)],
    hidden: folded ? attrs.slice(SHOWN_ATTRS) : [] };
}

export function cardHeight(entity, collapsed) {
  const { rows, hidden } = visibleRows(entity, collapsed);
  return HEADER_H + Math.max(rows.length, 1) * ROW_H + (hidden.length ? ROW_H : 0) + PAD;
}

/** One ghost per parent outside the area (or retired), keyed by its entity id. */
export function ghostsOf(g) {
  const out = new Map();
  for (const r of g.outside_refs) {
    if (!out.has(r.parent_data_entity_id)) {
      out.set(r.parent_data_entity_id, { data_entity_id: r.parent_data_entity_id, de_number: r.parent_de_number,
        de_name: r.parent_de_name, retired: r.retired });
    }
  }
  return [...out.values()];
}

/**
 * Edge landing (spec §7 3b): a via field lands on its parent's row handle only when it names a
 * parent field AND that field is a key row, which stays rendered when the card collapses;
 * otherwise on the card's entity handle. No relationship is dropped for want of a handle.
 */
export const targetHandle = (v) => (v.ref_data_field_id != null && v.ref_is_key
  ? rowHandle('t', 'L', v.ref_data_field_id) : ENTITY_HANDLE);

/** Relationships → one edge per via field (a composite FK draws one line per field, §7.14). */
export function buildEdges(g) {
  const edges = [];
  const add = (rel, stub) => rel.via_fields.forEach((v, i) => {
    edges.push({
      id: `r${rel.child_data_entity_id}-${rel.parent_data_entity_id}-${rel.fk_group_no}-${v.data_field_id}`,
      type: 'erd',
      source: entityNodeId(rel.child_data_entity_id), sourceHandle: rowHandle('s', 'R', v.data_field_id),
      target: stub ? ghostNodeId(rel.parent_data_entity_id) : entityNodeId(rel.parent_data_entity_id),
      targetHandle: stub ? ENTITY_HANDLE : targetHandle(v),
      label: i === 0 ? rel.label : undefined,           // one label per relationship
      focusable: false, selectable: false,
      data: { parent: rel.parent_cardinality, child: rel.child_cardinality, identifying: rel.identifying, stub },
    });
  });
  g.relationships.forEach((r) => add(r, false));
  g.outside_refs.forEach((r) => add(r, true));
  return edges;
}

/** Card ids that share a relationship with `id` (itself included), for highlight-and-dim. */
export function neighbours(edges, id) {
  const out = new Set([id]);
  for (const e of edges) {
    if (e.source === id) out.add(e.target);
    if (e.target === id) out.add(e.source);
  }
  return out;
}

/**
 * Auto-layout (ELK, off the main thread), then saved positions win (D-30), then every unpinned
 * card is pushed down clear of the pinned ones (§14.6, sara L7). Arranging saves nothing.
 */
export async function arrange(g, collapsed, edges) {
  const ghosts = ghostsOf(g);
  const items = [
    ...g.entities.map((e) => ({ id: entityNodeId(e.data_entity_id), w: CARD_W,
      h: cardHeight(e, collapsed.get(e.data_entity_id)), deId: e.data_entity_id })),
    ...ghosts.map((x) => ({ id: ghostNodeId(x.data_entity_id), w: GHOST.w, h: GHOST.h })),
  ];
  const pairs = new Map();
  for (const e of edges) pairs.set(`${e.source}>${e.target}`, { id: `l${pairs.size}`, sources: [e.source], targets: [e.target] });
  const laid = await elkLayout({ id: 'root', layoutOptions: LAYERED_RIGHT,
    children: items.map((i) => ({ id: i.id, width: i.w, height: i.h })), edges: [...pairs.values()] });
  const at = new Map(laid.children.map((c) => [c.id, { x: c.x, y: c.y }]));
  const saved = new Map(g.layout.filter((p) => p.object_type === 'ENTITY').map((p) => [p.object_id, p]));
  const boxes = items.map((i) => {
    const p = i.deId != null ? saved.get(i.deId) : null;
    return { id: i.id, ...(p ? { x: p.x, y: p.y } : at.get(i.id)), w: i.w, h: i.h, pinned: Boolean(p) };
  });
  return pushClear(boxes, { axis: 'y' });
}

export function buildNodes(g, collapsed, positions) {
  return [
    ...g.entities.map((e) => ({ id: entityNodeId(e.data_entity_id), type: 'entity',
      position: positions.get(entityNodeId(e.data_entity_id)),
      data: { entity: e, collapsed: Boolean(collapsed.get(e.data_entity_id)) } })),
    ...ghostsOf(g).map((x) => ({ id: ghostNodeId(x.data_entity_id), type: 'ghost', draggable: false,
      position: positions.get(ghostNodeId(x.data_entity_id)), data: { ghost: x } })),
  ];
}
