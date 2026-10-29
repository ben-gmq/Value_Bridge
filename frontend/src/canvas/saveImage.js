// Save a diagram exactly as it is shown on screen, as PNG (function 41, EX-1; Ben 2026-10-29: html-to-image).
// One saver for every canvas, as there is one canvas (VB law 8). The zoom controls, minimap and attribution are left
// out; the picture keeps the canvas's own background, so it reads the same in the dark and the light scheme. Fonts are
// the app's own (@fontsource, same origin) — nothing is fetched from outside (slice 1f §8). Not audited (spec A8).
// No SVG: html-to-image's SVG wraps the page's HTML in a foreignObject, which §14.5 forbids in an exported SVG; a PNG
// is pixels only. SVG waits on Ben (history §1).
import { toPng } from 'html-to-image';

const LEAVE_OUT = ['react-flow__controls', 'react-flow__minimap', 'react-flow__attribution'];

export const IMAGE_FORMATS = ['png'];

/** `el` holds the canvas and anything its lines refer to (e.g. the ERD's marker defs). The file name is made from
 * ids only, never from user text. */
export async function saveCanvasImage(el, format, fileName) {
  const canvas = el.querySelector('[data-canvas-kind]') ?? el;
  const options = {
    backgroundColor: getComputedStyle(canvas).backgroundColor,
    filter: (n) => !(n.classList && LEAVE_OUT.some((c) => n.classList.contains(c))),
    pixelRatio: 2,                                         // sharp enough for a slide
  };
  if (!IMAGE_FORMATS.includes(format)) throw new Error(`unsupported format ${format}`);
  const url = await toPng(el, options);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${fileName}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
