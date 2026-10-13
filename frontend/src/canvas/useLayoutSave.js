// Saving diagram positions — the ONE copy for the flow, the DFD and the ERD (sara M1, §14.6).
// A box that stops moving is queued; one debounced PUT sends the queue; a queue still pending
// when the page or the scope changes is sent, not dropped; Reset discards it first, so a late
// save cannot re-pin a box the reset just cleared (sara L3). Last write wins per object (A-52).
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { layoutApi } from '../api/scope';

const SAVE_DELAY = 600;

/**
 * `toItem(node)` turns a canvas node into a saved item ({object_type, object_id, x, y, …}) or
 * null for anything that is not placed (lanes, ghosts). It is read when the box is queued, so
 * the item always belongs to the scope it moved in. `onSaved(layout, scopeKey)` receives the
 * scope's saved positions; `onError(err)` a failed save.
 */
export function useLayoutSave({ projectId, diagramType, scopeKey, canEdit, getNode, toItem, onSaved, onError }) {
  const pending = useRef(new Map());
  const timer = useRef(null);
  const latest = useRef(null);
  latest.current = { projectId, diagramType, scopeKey, getNode, toItem, onSaved, onError };

  const send = useCallback((sk, items, quiet) => {
    const { projectId: p, diagramType: type, onSaved: ok, onError: fail } = latest.current;
    if (!items.length || sk == null) return Promise.resolve();
    return layoutApi.save(p, type, sk, items).then((layout) => ok?.(layout, sk)).catch((err) => {
      if (quiet) console.error('Diagram positions not saved on leaving the diagram', err);
      else fail?.(err);
    });
  }, []);

  const take = useCallback(() => {
    clearTimeout(timer.current);
    const items = [...pending.current.values()];
    pending.current.clear();
    return items;
  }, []);

  /** Queue one node by id (a drag end, a keyboard move, or an ERD collapse toggle). A change's
   * own position wins over the node's: the page may not have re-rendered with it yet. */
  const queue = useCallback((id, position) => {
    if (!canEdit) return;
    const { getNode: get, toItem: item, scopeKey: sk } = latest.current;
    const n = get(id);
    const it = n && item(position ? { ...n, position } : n);
    if (!it) return;
    pending.current.set(id, it);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => send(sk, take(), false), SAVE_DELAY);
  }, [canEdit, send, take]);

  /** Feed React Flow's node changes through: a position change that has ended is queued. */
  const onChanges = useCallback((changes) => {
    for (const c of changes) if (c.type === 'position' && !c.dragging) queue(c.id, c.position);
  }, [queue]);

  /** Place a box that is not on the canvas yet where it was dropped (slice 13d: a store a drawn flow
   * brings in). `item` is a saved item ({object_type, object_id, x, y}); it is sent now, with anything
   * still queued, and the promise settles once saved, so the page can redraw with it in place. */
  const place = useCallback((item) => {
    if (!canEdit || !item) return Promise.resolve();
    pending.current.set(`${item.object_type}:${item.object_id}`, item);
    return send(latest.current.scopeKey, take(), false);
  }, [canEdit, send, take]);

  /** Drop the queue — call it when a Reset starts. */
  const discard = useCallback(() => { clearTimeout(timer.current); pending.current.clear(); }, []);

  // Leaving the page or the scope sends what is still queued, to the scope it was queued in.
  useEffect(() => {
    const sk = scopeKey;
    return () => send(sk, take(), true);
  }, [scopeKey, send, take]);

  return useMemo(() => ({ queue, onChanges, place, discard }), [queue, onChanges, place, discard]);
}
