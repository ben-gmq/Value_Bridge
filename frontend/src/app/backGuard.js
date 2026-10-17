import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * The one Back / Forward guard (VB-007, VB-010). Chrome runs a window's popstate listeners in the order they were
 * added, capture or not, and BrowserRouter adds its own when the app mounts — so a listener a screen adds later
 * always runs after the router has already moved. This one is added when the module loads (main.jsx imports it
 * before the app renders), so it runs first and can stop the move.
 *
 * A screen registers with useBackGuard(onBack). onBack(target) returns true to stop the move: the entry on screen
 * is put back, and the screen asks, then navigates to `target` itself if the user goes on. Presentation only.
 */
const guards = [];                 // the mounted screens' guards, newest last
let here = null;                   // the entry on screen, { url, state }, kept by the guarded screens

const urlOf = (l) => l.pathname + l.search + l.hash;

window.addEventListener('popstate', (e) => {
  if (!here) return;
  const target = urlOf(window.location);
  for (let i = guards.length - 1; i >= 0; i -= 1) {
    if (guards[i](target)) {
      e.stopImmediatePropagation();
      window.history.pushState(here.state, '', here.url);
      return;
    }
  }
}, true);

export function useBackGuard(onBack) {
  const location = useLocation();
  const latest = useRef(onBack);
  useEffect(() => { latest.current = onBack; });
  useEffect(() => {
    here = { url: urlOf(location), state: window.history.state };
  }, [location]);
  useEffect(() => {
    const guard = (target) => latest.current(target);
    guards.push(guard);
    return () => { guards.splice(guards.indexOf(guard), 1); };
  }, []);
}
