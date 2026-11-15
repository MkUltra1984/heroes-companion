// @ts-check
// Hash routes: #/<page>/<argument>. Whatever happens (a page that throws, a failed download, a broken address),
// the visitor gets a visible message and a way on. A route never ends in an empty page.
import { $, h, put } from './dom.js';
import { t } from './i18n.js';
import { store } from './store.js';
import { pageStart } from './motion.js';

/** @typedef {{ title: (arg: string) => string, render: (el: HTMLElement, arg: string) => void|Promise<void>, nav?: string }} Page */
/** @type {Map<string, Page>} */
const pages = new Map();
const HOME = 'home';
let seq = 0;
let first = true;
/** our own copy of the history, to give "back" its scroll position: [{ hash, y }] @type {{ hash: string, y: number }[]} */
const trail = [];

/** @param {string} name @param {Page} page */
export function register(name, page) { pages.set(name, page); }

/**
 * @param {string} hash
 * @returns {{ name: string, arg: string }} name is a registered page, or 'notfound' / 'badaddress'
 */
export function parseHash(hash) {
  if (hash === '' || hash === '#' || hash === '#/') return { name: HOME, arg: '' };
  const m = /^#\/([a-z]+)(?:\/([^?]*))?(?:\?.*)?$/.exec(hash);
  if (!m) return { name: 'notfound', arg: '' };
  let arg = '';
  try { arg = decodeURIComponent(m[2] || ''); } catch { return { name: 'badaddress', arg: '' }; }
  if (arg.length > 200) return { name: 'badaddress', arg: '' };
  return { name: pages.has(m[1]) ? m[1] : 'notfound', arg };
}

/** A card for anything that went wrong, with the ways out. @param {string} message @param {string} [detail] @param {{ retry?: boolean, reset?: boolean }} [opt] */
export function errorCard(message, detail, opt = {}) {
  let armed = false;
  const resetBtn = h('button', { class: 'btn small', onclick: () => {
    if (!armed) { armed = true; resetBtn.textContent = t('err.reset.confirm'); return; }
    store.reset(); refresh();
  } }, t('err.reset'));
  return h('div', { class: 'card', role: 'alert' },
    h('h1', { class: 'errtitle' }, t('err.title')),
    h('p', {}, message),
    detail ? h('p', { class: 'dim small' }, detail) : null,
    h('div', { class: 'chips gap' },
      opt.retry ? h('button', { class: 'btn primary', onclick: () => refresh() }, t('err.retry')) : null,
      h('a', { class: 'btn', href: '#/' + HOME }, t('err.home')),
      opt.reset ? [h('button', { class: 'btn small', onclick: saveBackup }, t('box.export')), resetBtn] : null));
}

/** Offers the saved data as a file. */
export function saveBackup() {
  const url = URL.createObjectURL(new Blob([store.exportText()], { type: 'application/json' }));
  const a = h('a', { href: url, download: 'heroes-companion-barracks.json' });
  document.body.append(a); a.click(); a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** @param {{ focus?: boolean, y?: number }} [opt] */
async function show(opt = {}) {
  const my = ++seq;
  const view = $('view');
  const r = parseHash(location.hash);
  const page = pages.get(r.name);
  const tab = page && page.nav || r.name;
  for (const a of document.querySelectorAll('#nav a, #nav2 a')) {
    const on = a.getAttribute('data-v') === tab;
    a.classList.toggle('bounce', on && !first && !a.hasAttribute('aria-current'));        // the icon of a newly chosen tab hops once
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  const el = h('div', { class: 'page', 'data-page': r.name });
  let title = '';
  /** @type {any} */
  let failed = null;
  try {
    if (r.name === 'notfound') put(el, errorCard(t('err.notfound')));
    else if (r.name === 'badaddress' || !page) put(el, errorCard(t('err.badaddress')));
    else {
      pageStart();
      const p = page.render(el, r.arg);
      if (p && typeof p.then === 'function') {
        if (!el.hasChildNodes()) put(el, h('p', { class: 'dim pad' }, t('loading')));
        put(view, el);
        await p;
      }
      title = page.title(r.arg);
    }
  } catch (e) { failed = e || new Error('unknown error'); }
  if (my !== seq) return;                                   // the visitor has already gone on
  if (!failed && !(el.textContent || '').trim()) failed = new Error('the page came out empty');
  if (failed) {
    console.error('page "' + r.name + '" failed:', failed);
    put(el, errorCard(t('err.load'), String(failed && failed.message || failed), { retry: true, reset: true }));
  }
  put(view, el);
  view.setAttribute('data-ready', r.name);
  document.title = (title ? title + ' · ' : '') + t('app.name');
  window.scrollTo(0, opt.y || 0);
  if (opt.focus) {
    const head = /** @type {HTMLElement|null} */ (el.querySelector('h1'));
    if (head) { head.tabIndex = -1; head.focus({ preventScroll: true }); }
  }
}

/** Draws the current route again, keeping the scroll position (the clock moved on, another tab saved, "Try again"). */
export function refresh() { return show({ y: window.scrollY }); }

function onHash() {
  const hash = location.hash;
  const cur = trail[trail.length - 1];
  if (cur) cur.y = window.scrollY;
  let y = 0;
  if (trail.length >= 2 && trail[trail.length - 2].hash === hash) { trail.pop(); y = trail[trail.length - 1].y; }   // "back"
  else trail.push({ hash, y: 0 });
  if (trail.length > 50) trail.shift();
  show({ focus: !first, y });
  first = false;
}

export function start() {
  try { history.scrollRestoration = 'manual'; } catch { /* old browser: its own scroll restoring stays on */ }
  window.addEventListener('hashchange', onHash);
  onHash();
}
