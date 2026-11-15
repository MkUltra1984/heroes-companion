// @ts-check
// Heroes Companion: a static page. Data files in data/ are built from the community wiki by tools/build_data.py,
// written content in content/ is copied by tools/build_site.py.
// Everything personal (barracks, teams, orbs) stays in this browser; nothing is sent anywhere.
import { $, h, put, toast } from './dom.js';
import { loadStrings, t } from './i18n.js';
import { D, loadBase } from './data.js';
import { store } from './store.js';
import { ageDays, fmtDate, gameDay, nextReset, now } from './time.js';
import { register, refresh, start } from './router.js';
import { initMotion } from './motion.js';
import { page as home } from './pages/home.js';
import { page as heroes } from './pages/heroes.js';
import { page as hero } from './pages/hero.js';
import { page as barracks } from './pages/barracks.js';
import { page as teams } from './pages/teams.js';
import { page as summon } from './pages/summon.js';
import { page as orbs } from './pages/orbs.js';
import { page as guide } from './pages/guide.js';

const STALE_DAYS = 10;
/** what happened to the saved data at start: shown once, can be closed @type {string} */
let startNote = '';

function paintNotices() {
  const m = D.manifest;
  const age = ageDays(m.dataFrom);
  /** @param {string} text @param {(() => void)} [close] */
  const note = (text, close) => h('div', { class: 'note' }, text, close ? [' ', h('button', { class: 'link', type: 'button', onclick: close }, t('notice.close'))] : null);
  put($('notice'),
    age > STALE_DAYS ? note(t('notice.stale', { date: fmtDate(m.dataFrom), days: age })) : null,
    store.blocked ? note(t('store.blocked')) : null,
    startNote ? note(t('store.' + startNote, { n: store.count() }), () => { startNote = ''; paintNotices(); }) : null);
}

function paintOrbs() {
  $('orbcount').textContent = String(store.state.orbs);
  $('orbchip').setAttribute('aria-label', t('top.orbs', { n: store.state.orbs }));
}

function paintFrame() {
  const m = D.manifest;
  for (const a of document.querySelectorAll('#nav a, #nav2 a')) { const s = a.querySelector('span'); if (s) s.textContent = t('nav.' + a.getAttribute('data-v')); }
  for (const nav of [$('nav'), $('nav2')]) nav.setAttribute('aria-label', t('nav.label'));
  const skip = $('skip');
  skip.textContent = t('skip');
  skip.addEventListener('click', e => { e.preventDefault(); $('view').focus(); });       // the address stays a route
  const art = h('button', { type: 'button', class: 'switch', id: 'artswitch', 'aria-pressed': store.state.prefs.art ? 'true' : 'false', onclick: () => {
    store.setPref('art', !store.state.prefs.art);
    art.setAttribute('aria-pressed', store.state.prefs.art ? 'true' : 'false');
    refresh();
  } }, h('i', {}), t('foot.artswitch'));
  put($('foot'), h('div', { class: 'foot-in' }, h('img', { src: 'art/emblem.webp', alt: '', width: 36, height: 36 }),
    h('div', { class: 'foot-text' },
      h('p', {}, t('foot.text')),
      h('p', {}, t('foot.art'), ' ', h('a', { href: '#/guide/about' }, t('foot.about'))),
      h('p', {}, t('foot.data', { fetched: fmtDate(m.dataFrom), release: fmtDate(m.newestRelease) }), ' ',
        h('a', { href: m.source.url, target: '_blank', rel: 'noopener' }, m.source.name), ' · ',
        h('a', { href: m.source.licenceUrl, target: '_blank', rel: 'license noopener' }, t('foot.licence', { licence: m.source.licence })))),
    art));
  paintOrbs();
}

/** Keeps the page honest while it stays open: at every 07:00 UTC the current route is drawn again. */
function watchClock() {
  let day = gameDay(now());
  const check = () => { const d = gameDay(now()); if (d !== day) { day = d; paintNotices(); refresh(); } };
  const arm = () => window.setTimeout(() => { check(); arm(); }, Math.min(2 ** 31 - 1, (nextReset(now()) - now() + 1) * 1000));
  arm();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
}

async function boot() {
  initMotion();
  try {
    await Promise.all([loadStrings(), loadBase()]);
  } catch (e) {
    console.error('start failed:', e);
    /** @type {any} */ (window).hcBootFailed(String(/** @type {any} */ (e) && /** @type {any} */ (e).message || e));
    return;
  }
  startNote = store.init({ mapName: name => { const x = D.byWn.get(name); return x ? x.id : undefined; } });
  store.subscribe(why => {
    if (why === 'blocked') { paintNotices(); toast(t('store.blocked.short')); }
    if (why === 'external') { paintNotices(); const sw = document.getElementById('artswitch'); if (sw) sw.setAttribute('aria-pressed', store.state.prefs.art ? 'true' : 'false'); refresh(); }
    paintOrbs();
  });
  register('home', home); register('heroes', heroes); register('hero', hero); register('barracks', barracks); register('teams', teams);
  register('summon', summon); register('orbs', orbs); register('guide', guide);
  paintFrame(); paintNotices(); watchClock();
  start();
}
boot();
