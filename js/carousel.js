// @ts-check
// The hero carousel on Home: cards stand on a ring that is spun by dragging (mouse or touch, with momentum and a snap
// to the nearest card), by the mouse wheel while the pointer is over it, by the arrow buttons and by the arrow keys.
// With three cards or more the ring is endless; with one or two it stops at its ends. With reduced motion there is
// no ring and no spin: the cards form a plain row that scrolls.
// Every card is a real link to its hero page; a card works without artwork (silhouette on the hero's color).
import { h, put } from './dom.js';
import { t } from './i18n.js';
import { artImg, artUrl, mv, wb } from './art.js';
import { onMotionChange, reduced, still } from './motion.js';

/** @typedef {import('./data.js').Hero} Hero */
/** @typedef {{ hero: Hero, labels: { text: string, cls: string }[], info: () => any }} Item */

const STEP = 19;                 // degrees between two cards on the ring
const NEAR = 4;                  // cards on each side that are drawn (and whose artwork is requested)
const RAD = Math.PI / 180;

/** @param {Item} item @param {number} i */
function card(item, i) {
  const hero = item.hero;
  return h('a', { class: 'car-card glow-' + hero.c, href: '#/hero/' + hero.id, 'data-i': i, draggable: 'false',
    'aria-label': hero.n + ': ' + hero.ti + '. ' + item.labels.map(l => l.text).join(', ') },
  h('span', { class: 'car-art art glow-' + hero.c }),
  h('span', { class: 'car-labels' }, item.labels.map(l => h('span', { class: 'car-label ' + l.cls }, l.text))),
  h('span', { class: 'car-badges' }, wb(hero), mv(hero)),
  h('span', { class: 'car-plate' }, h('b', {}, hero.n), h('small', {}, hero.ti)));
}

/**
 * @param {Item[]} items at least one @param {{ label: string }} opt
 * @returns {HTMLElement} the carousel; it keeps itself running while it is in the page
 */
export function carousel(items, opt) {
  const n = items.length;
  const endless = n >= 3;
  const ring = h('div', { class: 'car-ring' });
  const stage = h('div', { class: 'car-stage' }, ring);
  const info = h('div', { class: 'car-info', 'aria-live': 'polite' });
  const count = h('span', { class: 'car-count num' });
  const hint = h('p', { class: 'car-hint dim' });
  const prev = /** @type {HTMLButtonElement} */ (h('button', { type: 'button', class: 'car-arrow prev', 'aria-label': t('car.prev') }, h('span', { class: 'chev' })));
  const next = /** @type {HTMLButtonElement} */ (h('button', { type: 'button', class: 'car-arrow next', 'aria-label': t('car.next') }, h('span', { class: 'chev' })));
  const el = h('section', { class: 'carousel', 'aria-roledescription': 'carousel', 'aria-label': opt.label, 'data-n': n },
    h('div', { class: 'car-view' }, prev, stage, next), h('div', { class: 'car-foot' }, info, count), hint);
  const cards = items.map(card);
  ring.append(...cards);
  if (n < 2) { prev.hidden = true; next.hidden = true; }

  /** which card's artwork has been asked for @type {Set<number>} */
  const asked = new Set();
  /** @param {number} i */
  const loadArt = i => {
    if (i < 0 || asked.has(i)) return;
    asked.add(i);
    const img = artImg(artUrl(items[i].hero, 'p', 360), { loading: 'eager' });
    if (img) /** @type {HTMLElement} */ (cards[i].firstElementChild).append(img);
  };
  /** @param {number} v */
  const wrap = v => ((v % n) + n) % n;
  /** A position the ring may rest at. @param {number} v */
  const rest = v => endless ? Math.round(v) : Math.max(0, Math.min(n - 1, Math.round(v)));
  let pos = 0, target = 0, current = -1, radius = 520, running = false, plain = false;

  /** @param {number} i */
  const showInfo = i => {
    if (i === current) return;
    current = i;
    put(info, items[i].info());
    count.textContent = t('car.count', { i: i + 1, n });
    cards.forEach((c, k) => { c.classList.toggle('cur', k === i); c.tabIndex = k === i ? 0 : -1; });
    if (!endless || plain) { prev.disabled = i === 0; next.disabled = i === n - 1; }
  };

  // ---- ring mode -------------------------------------------------------------------------------------------------
  const paint = () => {
    for (let i = 0; i < n; i++) {
      let d = i - pos;
      if (endless) d = ((d + n / 2) % n + n) % n - n / 2;              // the shortest way round the ring, at any card count
      const c = cards[i], a = Math.abs(d);
      if (a > NEAR + .5) { if (!c.hidden) c.hidden = true; continue; }
      if (c.hidden) c.hidden = false;
      if (a <= NEAR) loadArt(i);
      const th = d * STEP * RAD;
      const x = Math.sin(th) * radius, z = (Math.cos(th) - 1) * radius, scale = 1 + .1 * Math.max(0, 1 - a);
      c.style.transform = 'translate3d(' + x.toFixed(1) + 'px,0,' + z.toFixed(1) + 'px) rotateY(' + (d * STEP * .85).toFixed(2) + 'deg) scale(' + scale.toFixed(3) + ')';
      c.style.opacity = String(Math.max(0, Math.min(1, NEAR + .5 - a)));
      c.style.zIndex = String(1000 - Math.round(a * 100));            // the ring is not a shared 3D space, so this decides who is in front
      c.style.setProperty('--dim', String(Math.min(.62, a * .22)));
    }
    showInfo(wrap(rest(pos)));
  };
  const frame = () => {
    if (!el.isConnected || plain) { running = false; return; }
    const diff = target - pos;
    if (dragging || Math.abs(diff) < .002) { if (!dragging) pos = target; paint(); running = false; return; }
    pos += diff * .14;
    paint();
    requestAnimationFrame(frame);
  };
  const run = () => { if (still) { pos = target; paint(); return; } if (!running) { running = true; requestAnimationFrame(frame); } };
  /** @param {number} by cards */
  const spin = by => {
    if (plain) { const i = Math.max(0, Math.min(n - 1, current + by)); cards[i].scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'center' }); showInfo(i); return; }
    target = rest(target + by); run();
  };

  // dragging with momentum. The pointer is not captured, so a plain click still opens the card; instead the window is
  // listened to while a button is down, so a release anywhere ends the gesture.
  let dragging = false, down = false, downX = 0, downPos = 0, pointer = -1, moved = false, lastX = 0, lastT = 0, speed = 0;
  const perCard = () => Math.sin(STEP * RAD) * radius;
  /** @param {PointerEvent} e */
  const onMove = e => {
    if (!down || e.pointerId !== pointer) return;
    if (e.pointerType === 'mouse' && e.buttons === 0) { release(e); return; }          // the button came up where no event reached us
    const dx = e.clientX - downX;
    if (!dragging) {
      if (Math.abs(dx) < 6) return;
      dragging = moved = true;
      stage.classList.add('drag');
    }
    const dt = Math.max(1, e.timeStamp - lastT);
    speed = .7 * speed + .3 * ((lastX - e.clientX) / perCard() / dt);          // cards per millisecond, smoothed
    lastX = e.clientX; lastT = e.timeStamp;
    pos = downPos - dx / perCard();
    if (!endless) pos = Math.max(-.35, Math.min(n - .65, pos));
    target = pos;
    paint();
  };
  /** @param {PointerEvent|Event} e */
  const release = e => {
    if (!down || ('pointerId' in e && e.pointerId !== pointer)) return;
    down = false; pointer = -1;
    window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', release);
    window.removeEventListener('pointercancel', release); window.removeEventListener('blur', release);
    stage.classList.remove('drag');
    if (!dragging) return;
    dragging = false;
    const fling = e.timeStamp - lastT < 80 ? Math.max(-4, Math.min(4, speed * 260)) : 0;
    target = rest(pos + fling);
    run();
    window.setTimeout(() => { moved = false; }, 0);            // the click that ends this drag comes first and is swallowed below
  };
  stage.addEventListener('pointerdown', e => {
    if (plain || e.button > 0) return;
    if (down) release(e);
    down = true; pointer = e.pointerId; downX = lastX = e.clientX; lastT = e.timeStamp; downPos = pos; moved = false; speed = 0;
    window.addEventListener('pointermove', onMove); window.addEventListener('pointerup', release);
    window.addEventListener('pointercancel', release); window.addEventListener('blur', release);
  });
  stage.addEventListener('lostpointercapture', release);
  stage.addEventListener('click', e => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } }, true);
  stage.addEventListener('dragstart', e => e.preventDefault());
  let wheelSum = 0, wheelAt = 0;
  stage.addEventListener('wheel', e => {
    if (plain || e.ctrlKey) return;
    const sideways = Math.abs(e.deltaX) > Math.abs(e.deltaY) || e.shiftKey;
    // a mouse wheel turns in notches (large steps, or counted in lines); a touchpad sends many small ones and keeps scrolling the page
    const notch = !sideways && e.deltaX === 0 && (e.deltaMode !== 0 || Math.abs(e.deltaY) >= 50);
    if (!sideways && !notch) return;
    e.preventDefault();
    if (notch) { if (e.timeStamp - wheelAt > 60) { spin(Math.sign(e.deltaY)); wheelAt = e.timeStamp; } return; }
    wheelSum += e.deltaX || e.deltaY;
    if (Math.abs(wheelSum) >= 40) { spin(Math.sign(wheelSum)); wheelSum = 0; }
  }, { passive: false });
  el.addEventListener('keydown', e => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const by = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    const at = plain ? current : wrap(rest(target));
    if (by) spin(by);
    else if (e.key === 'Home') spin(-at);
    else if (e.key === 'End') spin(n - 1 - at);
    else return;
    e.preventDefault();
    if (ring.contains(document.activeElement)) cards[plain ? current : wrap(rest(target))].focus({ preventScroll: !plain });
  });
  ring.addEventListener('focusin', e => {                       // a card that is not in front got the focus: bring it there
    const i = cards.indexOf(/** @type {HTMLElement} */ (e.target));
    if (i < 0) return;
    if (plain) { showInfo(i); return; }
    const front = wrap(rest(target));
    if (i === front) return;
    let d = i - front;
    if (endless) { if (d > n / 2) d -= n; else if (d < -n / 2) d += n; }
    target = rest(target) + d; run();
  });
  prev.addEventListener('click', () => spin(-1));
  next.addEventListener('click', () => spin(1));

  // ---- plain mode (reduced motion): a row that scrolls ---------------------------------------------------------
  ring.addEventListener('scroll', () => {
    if (!plain || ring.contains(document.activeElement)) return;
    const w = cards[0].offsetWidth + 16;
    showInfo(Math.max(0, Math.min(n - 1, Math.round(ring.scrollLeft / w))));
  }, { passive: true });

  /** @type {IntersectionObserver|null} */
  let io = null;
  const setup = () => {
    plain = reduced();
    el.classList.toggle('car-plain', plain);
    hint.textContent = t(plain ? 'car.hint.plain' : n > 1 ? 'car.hint' : 'car.hint.one');
    if (io) { io.disconnect(); io = null; }
    current = -1;
    prev.disabled = next.disabled = false;
    if (plain) {
      for (let i = 0; i < n; i++) { const c = cards[i]; c.hidden = false; c.removeAttribute('style'); if (i < 8) loadArt(i); }
      if ('IntersectionObserver' in window) {
        io = new IntersectionObserver(list => { for (const x of list) if (x.isIntersecting) loadArt(cards.indexOf(/** @type {HTMLElement} */ (x.target))); }, { root: ring, rootMargin: '0px 400px' });
        for (const c of cards) io.observe(c);
      } else cards.forEach((_, i) => loadArt(i));
      showInfo(0);
    } else { pos = target = rest(target); measure(); }
  };
  const measure = () => {
    const w = cards[0].offsetWidth || 200;
    radius = Math.max(260, Math.min(w * 3.25, (stage.clientWidth || 900) * .78));
    if (!plain) paint();
  };
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(stage);
  let seen = false;
  // the listener lives as long as the carousel is in the page; motion.js drops it at the next route change after that
  onMotionChange(() => { if (el.isConnected) setup(); }, () => { seen = seen || el.isConnected; return !seen || el.isConnected; });
  setup();
  return el;
}
