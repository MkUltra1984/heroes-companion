// @ts-check
// Motion: every animation moves with transform and opacity only, and all of it is off when the visitor's system
// asks for reduced motion (class "rm" on <html>). Two address switches exist for testing and screenshots:
// ?rm=1 behaves as if reduced motion were on, ?still=1 freezes every animation at its end state.
import { h } from './dom.js';

const root = document.documentElement;
const query = new URLSearchParams(location.search);
const media = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
const forced = query.get('rm') === '1';
export const still = query.get('still') === '1';

/** Whether motion is reduced right now. */
export const reduced = () => root.classList.contains('rm');
/** listener -> whether it is still needed @type {Map<() => void, () => boolean>} */
const listeners = new Map();
/**
 * Calls fn whenever the reduced motion setting changes, for as long as alive() says so (checked at every route change,
 * so that a page that is gone does not stay in memory).
 * @param {() => void} fn @param {() => boolean} [alive]
 */
export function onMotionChange(fn, alive = () => true) { listeners.set(fn, alive); return () => listeners.delete(fn); }
/** How many listeners are held (for the tests). */
export const motionListeners = () => listeners.size;

export function initMotion() {
  const apply = () => {
    const before = reduced();
    root.classList.toggle('rm', forced || !!(media && media.matches));
    if (before !== reduced()) for (const fn of [...listeners.keys()]) fn();
  };
  apply();
  if (still) root.classList.add('still');
  if (media && media.addEventListener) media.addEventListener('change', apply);
}

/** true from the moment a route starts to draw until its first drawing is done */
let fresh = false;
/** The router calls this before a page draws itself for the first time. */
export function pageStart() {
  fresh = true;
  for (const [fn, alive] of [...listeners]) if (!alive()) listeners.delete(fn);
}
/**
 * Starts the entrance animations of a freshly drawn page. A page that draws itself again (a filter, a changed number)
 * does not play them a second time.
 * @param {HTMLElement} el
 */
export function enter(el) {
  if (el.hasAttribute('data-entered')) return;
  el.setAttribute('data-entered', '');
  el.classList.add('enter');
  window.setTimeout(() => { fresh = false; }, 0);
  if (!still) window.setTimeout(() => el.classList.remove('enter'), 1600);
}

/** Plays a one-shot animation class again. @param {Element|null} el @param {string} cls */
export function replay(el, cls) {
  if (!el) return;
  el.classList.remove(cls);
  void (/** @type {HTMLElement} */ (el)).offsetWidth;
  el.classList.add(cls);
}

/** A ring and six sparks around an element (a hero was marked as owned). @param {Element|null} host */
export function sparkFx(host) {
  if (!host || reduced() || still) return;
  const fx = h('span', { class: 'fx', 'aria-hidden': 'true' }, h('span', { class: 'ringfx' }),
    [0, 1, 2, 3, 4, 5].map(i => h('span', { class: 'sp', style: { '--a': (i * 60 + 15) + 'deg' } })));
  host.append(fx);
  window.setTimeout(() => fx.remove(), 520);
}

let lastFlourish = 0;
/** The summoning-orb flourish: at most once in three seconds, never blocks input. @param {string} color */
export function flourish(color) {
  if (reduced() || still) return;
  const now = Date.now();
  if (now - lastFlourish < 3000) return;
  lastFlourish = now;
  const f = h('div', { class: 'flourish o-' + (color || 'plain'), 'aria-hidden': 'true' }, h('span', { class: 'rg' }), h('span', { class: 'o' }),
    [0, 1, 2, 3, 4, 5, 6, 7].map(i => h('span', { class: 'ry', style: { '--a': (i * 45) + 'deg' } })),
    Array.from({ length: 12 }, (_, i) => h('span', { class: 'dr', style: { '--dx': Math.round((i - 5.5) * 13) + 'px', 'animation-delay': (i % 4 * 40) + 'ms' } })));
  document.body.append(f);
  window.setTimeout(() => f.remove(), 1000);
}

/** Counts a number up to its value. @param {HTMLElement} el @param {number} to @param {number} [delay] */
export function countUp(el, to, delay = 0) {
  el.textContent = String(to);
  if (reduced() || still || !(to > 0) || !fresh) return;
  const width = String(to).length;
  /** @param {number} v */
  const show = v => { el.textContent = String(v).padStart(width, ' '); };   // figure spaces: the text keeps its width
  show(0);
  let t0 = 0;
  /** @param {number} time */
  const step = time => {
    if (!el.isConnected) return;
    if (!t0) t0 = time;
    const p = Math.min(1, (time - t0) / 600);
    show(Math.round(to * (1 - Math.pow(1 - p, 4))));
    if (p < 1) requestAnimationFrame(step); else el.textContent = String(to);
  };
  window.setTimeout(() => requestAnimationFrame(step), delay);
  window.setTimeout(() => { el.textContent = String(to); }, delay + 900);       // safety net when frames are throttled
}
