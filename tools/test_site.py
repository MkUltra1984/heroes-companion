"""Smoke test of the site with Python and headless Chrome only.

    python -I -B tools/test_site.py [--no-shots] [--shots DIR] [--verbose]

What it does:
  1. Static checks on site/: no HTML-injecting calls in the scripts, every text key the code uses exists in
     locales/en.json, no user folder path in any file.
  2. Starts a local server on a free port (it is always stopped again), serving site/ plus a test harness.
  3. Runs the harness in headless Chrome: it opens every route in an iframe of desktop and phone width (360 and
     420 px) and checks for a heading, real content, no console error, no raw text key, no sideways overflow; it then
     runs the behaviour tests (game clock, saved data, migration, import, two tabs, blocked storage, broken addresses).
  4. Takes screenshots of every route (desktop directly, phone widths through an iframe, because a headless Chrome
     window on Windows does not go below about 500 px) into reviews/round3/shots/ and fails on any console error Chrome logs while doing so.
     Screenshots load hero artwork from the wiki's image host as a visitor's browser does; messages about that host
     are counted and reported, not failed (the designed fallback shows instead).
The harness itself never asks the image host for anything: artwork is off there, or comes from a test route.
Exit code 0 only when everything passed.
"""
import argparse, base64, concurrent.futures, http.server, io, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
SITE = os.path.join(ROOT, 'site')
SHOTS = os.path.join(ROOT, 'reviews', 'round3', 'shots')
CHROME = [os.environ.get('HC_CHROME') or '', r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
          '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']

# ---- pages the server adds for the test ------------------------------------------------------------------------------
# hook.js runs inside the application's page before anything else: it records errors and lets a test move the clock
# (?now=<epoch seconds>) or forbid storage (?block=1).
HOOK_JS = r"""
(function () {
  var errors = window.__errors = [];
  var q = new URLSearchParams(location.search);
  if (q.get('now')) window.__hcNow = Number(q.get('now'));
  if (q.get('art') !== '1') window.__hcArt = false;            // the harness never loads artwork from the wiki's image host
  else window.__hcCdn = '/__t/cdn/';                          // ... and when a test wants artwork, it comes from the test server
  document.addEventListener('securitypolicyviolation', function (e) { errors.push('security policy: ' + e.violatedDirective + ' ' + e.blockedURI); });
  if (q.get('block')) {
    var deny = function () { throw new DOMException('storage is blocked (test)', 'SecurityError'); };
    Storage.prototype.setItem = deny; Storage.prototype.getItem = deny; Storage.prototype.removeItem = deny;
  }
  var real = console.error;
  console.error = function () { errors.push('console.error: ' + Array.prototype.map.call(arguments, function (a) { return a && a.message || String(a); }).join(' ')); real.apply(console, arguments); };
  window.addEventListener('error', function (e) { errors.push('error: ' + (e.message || (e.target && e.target.src) || 'resource')); }, true);
  window.addEventListener('unhandledrejection', function (e) { errors.push('unhandled rejection: ' + (e.reason && e.reason.message || e.reason)); });
})();
"""

FRAME_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>frame</title>
<style>html,body{margin:0;background:#3a3f4b}iframe{display:block;border:0;background:#0d1016}</style></head><body><script>
// Shows the site in an iframe of the wanted width. The page's own load event is held back (by an image the server
// keeps open) until the route inside has finished drawing, so that Chrome's screenshot shows the finished page.
var q = new URLSearchParams(location.search), id = q.get('id');
try { if (q.get('seed')) localStorage.setItem('hc.v2', q.get('seed')); else localStorage.removeItem('hc.v2'); } catch (e) {}
var hold = new Image(); hold.src = '/__t/hold?id=' + id; hold.style.display = 'none'; document.body.appendChild(hold);
var f = document.createElement('iframe');
f.width = q.get('w') || 360; f.height = q.get('h') || 780;
f.src = '/index.html?still=1' + (q.get('q') || '') + (q.get('r') || '');
document.body.appendChild(f);
var last = -1, same = 0, started = Date.now();
function state() {
  var d = f.contentDocument, v = d && d.getElementById('view');
  if (!v) return { ready: false, why: 'no page' };
  var text = (v.textContent || '').replace(/\s+/g, ' ').trim();
  var fail = d.getElementById('bootfail');
  if (fail && !fail.hidden) return { ready: true, ok: false, why: 'the page could not start: ' + text.slice(0, 120) };
  if (!v.getAttribute('data-ready') || /Loading…/.test(text)) return { ready: false, why: 'still loading: ' + text.slice(0, 60) };
  if (text.length !== last) { last = text.length; same = 0; return { ready: false, why: 'still changing' }; }
  if (++same < 3) return { ready: false, why: 'settling' };
  var wide = d.documentElement.scrollWidth > d.documentElement.clientWidth + 1;
  return { ready: true, ok: !!v.querySelector('h1') && text.length > 30 && !wide, why: !v.querySelector('h1') ? 'no heading' : wide ? 'the page scrolls sideways' : text.length <= 30 ? 'blank page' : '' };
}
function tick() {
  var st = state();
  if (!st.ready && Date.now() - started < 45000) return setTimeout(tick, 60);
  requestAnimationFrame(function () { setTimeout(function () {
    fetch('/__t/release?id=' + id + '&ok=' + (st.ready && st.ok ? 1 : 0) + '&why=' + encodeURIComponent(st.why || ''));
  }, 80); });
}
tick();
</script></body></html>"""

HARNESS_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>harness</title>
<style>html,body{margin:0}iframe{border:0;display:block}</style></head><body><div id="frames"></div>
<script type="module" src="/__t/harness.js"></script></body></html>"""

HARNESS_JS = r"""
const results = [];
let group = '';
const ok = (name, cond, detail) => { results.push({ name: group + ': ' + name, ok: !!cond, detail: cond ? '' : String(detail ?? '') }); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, ms = 8000) { const end = Date.now() + ms; for (;;) { let v; try { v = fn(); } catch (e) { v = false; } if (v) return v; if (Date.now() > end) return false; await sleep(25); } }
const frames = document.getElementById('frames');
const KEYS = ['hc.v2', 'hc.box', 'hc.teams', 'hc.orbs', 'hc.backup', 'hc.broken'];
const text = el => (el && el.textContent || '').replace(/\s+/g, ' ').trim();

// opens the application in a fresh iframe; storage: the localStorage content to start with (null keeps what is there)
async function open(route, { w = 1280, h = 900, storage = {}, query = '', keep = false, motion = false } = {}) {
  if (!keep) frames.replaceChildren();
  if (storage) { for (const k of KEYS) localStorage.removeItem(k); for (const [k, v] of Object.entries(storage)) localStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v)); }
  let f = document.createElement('iframe'); f.width = w; f.height = h;
  f.src = '/index.html?t=1' + (motion ? '' : '&still=1') + query + route;      // still: animations stand at their end state
  frames.append(f);
  // the test server now and then drops a connection when hundreds of pages load in a row: one more try for a file that did not arrive
  const arrived = await until(() => f.contentDocument && f.contentDocument.getElementById('view') && (f.contentDocument.getElementById('view').getAttribute('data-ready') || !f.contentDocument.getElementById('bootfail').hidden), 15000);
  if (arrived && !f.contentDocument.getElementById('view').getAttribute('data-ready') && /did not arrive/.test(f.contentDocument.getElementById('bootfail').textContent)) {
    const again = document.createElement('iframe'); again.width = w; again.height = h; again.src = f.src; f.replaceWith(again); f = again; await sleep(50);
  }
  const fr = { f, get win() { return f.contentWindow; }, get doc() { return f.contentDocument; }, get view() { return f.contentDocument.getElementById('view'); },
    get errors() { return f.contentWindow.__errors || ['no error hook']; } };
  fr.ready = await until(() => fr.doc && fr.view && fr.view.getAttribute('data-ready') && !fr.view.querySelector('#bootwait'), 15000);
  await settle(fr);
  return fr;
}
// waits until the page has stopped changing (lazy parts of a page arrive after the route is ready)
async function settle(fr) { let last = -1; for (let i = 0; i < 80; i++) { const n = fr.view ? fr.view.textContent.length : 0; const busy = /Loading…/.test(fr.view ? fr.view.textContent : ''); if (n === last && !busy) return; last = n; await sleep(50); } }
async function go(fr, route) {
  fr.view.removeAttribute('data-ready');
  fr.win.location.hash = route;
  const r = await until(() => fr.view.getAttribute('data-ready'));
  await settle(fr);
  return r;
}
const stored = () => JSON.parse(localStorage.getItem('hc.v2') || 'null');
function setInput(fr, el, value) { el.value = value; el.dispatchEvent(new fr.win.Event('input', { bubbles: true })); el.dispatchEvent(new fr.win.Event('change', { bubbles: true })); }
function rawKeys(fr) { const out = []; const w = fr.doc.createTreeWalker(fr.doc.body, 4); for (let n = w.nextNode(); n; n = w.nextNode()) { const s = n.nodeValue.trim(); if (/^[a-z]+(\.[a-z0-9_-]+)+$/.test(s)) out.push(s); } return out; }
// elements that reach past the right edge of the page, outside containers that scroll on purpose
function overflow(fr) {
  const width = fr.doc.documentElement.clientWidth, out = [];
  if (fr.doc.documentElement.scrollWidth > width + 1) out.push('page scrolls sideways: ' + fr.doc.documentElement.scrollWidth + ' > ' + width);
  for (const el of fr.doc.querySelectorAll('#view *, #foot *, #notice *, #top > *, #nav a')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > width + 1 && !el.closest('.sr') && !clipped(fr, el, width)) { out.push(el.tagName.toLowerCase() + '.' + el.className + ' reaches ' + Math.round(r.right)); if (out.length > 3) break; }
  }
  return out;
}
// inside a box that scrolls on purpose or cuts its content off (hero strips, filter chips, the carousel, the art frame)
function clipped(fr, el, width) {
  for (let p = el.parentElement; p && p.id !== 'view'; p = p.parentElement) {
    if (fr.win.getComputedStyle(p).overflowX !== 'visible' && p.getBoundingClientRect().right <= width + 1) return true;
  }
  return false;
}
function checkPage(fr, label, { expectErrors = false } = {}) {
  ok(label + ' is ready', fr.ready !== false && fr.view && fr.view.getAttribute('data-ready'), 'route never became ready');
  const h1 = fr.view && fr.view.querySelector('h1');
  ok(label + ' has a heading', h1 && text(h1).length > 0, 'no h1');
  ok(label + ' is not blank', fr.view && text(fr.view).length > 30, 'text: ' + text(fr.view).slice(0, 60));
  ok(label + ' shows no raw text key', rawKeys(fr).length === 0, rawKeys(fr).join(', '));
  if (!expectErrors) ok(label + ' logs no error', fr.errors.length === 0, fr.errors.join(' | '));
  ok(label + ' does not overflow sideways', overflow(fr).length === 0, overflow(fr).join('; '));
}

async function run() {
  const manifest = await (await fetch('/data/manifest.json')).json();
  const index = (await (await fetch('/data/heroes.json')).json()).heroes;
  const banners = (await (await fetch('/data/banners.json')).json()).banners;
  const orbs = await (await fetch('/data/orbs.json')).json();
  const en = await (await fetch('/locales/en.json')).json();
  const T = await import('/js/time.js');
  const S = await import('/js/store.js');
  const SU = await import('/js/pages/summon.js');
  const DA = await import('/js/data.js');
  const picks = await (await fetch('/content/picks.json')).json();
  const marth = index.find(x => x.wn === 'Marth Altean Prince') || index[index.length - 1];
  const withBuilds = index.find(x => x.nb > 3) || index[0];
  const accented = index.find(x => /[^\x00-\x7f]/.test(x.n) && DA.fold(x.n) !== x.n.toLowerCase()) || index[0];
  const newest = index[0];
  const nowReal = Math.floor(Date.now() / 1000);

  // ---------------------------------------------------------------------------------------------------- game time
  group = 'time';
  const utc = s => Date.parse(s) / 1000;
  const span = { s: utc('2026-11-08T07:00:00Z'), e: utc('2026-11-15T06:59:59Z') };
  ok('live two seconds before the day change', T.isLive(span, utc('2026-11-15T06:59:58Z')) && !T.hasEnded(span, utc('2026-11-15T06:59:58Z')));
  ok('ended one second after the day change', !T.isLive(span, utc('2026-11-15T07:00:01Z')) && T.hasEnded(span, utc('2026-11-15T07:00:01Z')));
  ok('not live before 07:00 UTC of its first day', !T.isLive(span, utc('2026-11-08T06:59:59Z')) && T.isUpcoming(span, utc('2026-11-08T06:59:59Z')) && T.isLive(span, utc('2026-11-08T07:00:00Z')));
  ok('0 days left on the last game day', T.daysLeft(span, utc('2026-11-14T07:00:00Z')) === 0 && T.daysLeft(span, utc('2026-11-15T06:00:00Z')) === 0, T.daysLeft(span, utc('2026-11-14T07:00:00Z')));
  ok('1 day left the game day before', T.daysLeft(span, utc('2026-11-14T06:59:59Z')) === 1 && T.daysLeft(span, utc('2026-11-13T07:00:00Z')) === 1);
  ok('game date changes at 07:00 UTC', T.gameDate(utc('2026-11-15T06:59:59Z')) === '2026-11-14' && T.gameDate(utc('2026-11-15T07:00:00Z')) === '2026-11-15');
  ok('next reset', T.nextReset(utc('2026-11-15T06:59:59Z')) === utc('2026-11-15T07:00:00Z') && T.nextReset(utc('2026-11-15T07:00:00Z')) === utc('2026-11-16T07:00:00Z'));
  ok('all banner times are instants', banners.every(b => Number.isInteger(b.s) && Number.isInteger(b.e) && b.e > b.s));

  // ---------------------------------------------------------------------------------------------------- orb maths
  group = 'summon maths';
  const slow = o => { let n = 0; while (SU.orbsFor(n + 1) <= o) n++; return n; };
  let same = true; for (let o = 0; o <= 3000; o++) if (slow(o) !== SU.summonsFor(o)) { same = false; break; }
  ok('closed form equals counting for 0 to 3000 orbs', same);
  ok('99,999 orbs', SU.summonsFor(99999) === slow(99999));

  // ---------------------------------------------------------------------------------------------------- sanitize
  group = 'store';
  const shapes = [undefined, null, 0, 'x', [], [1, 2], {}, { box: null }, { box: [] }, { box: { x: true } }, { box: { 5: null, 6: 7, 7: 'a', 8: [] } }, { box: { 5: { m: 99, r: -3 } } },
    { box: { 5: { m: '1e9', r: 'abc' } }, orbs: 1e15 }, { teams: {} }, { teams: [{ name: 'x' }] }, { teams: [null, 5, 'a', { ids: 'abc' }, { ids: [5, 5, '7', {}, 9, 10], name: 12 }] },
    { orbs: '1e99' }, { orbs: -4 }, { orbs: NaN }, { prefs: 'yes' }, { prefs: { fehPass: 1 } }, { box: { 'Some Name': { m: 2, r: 4 } }, unmapped: { other: { m: 1 } } },
    { teams: new Array(500).fill({ name: 'n'.repeat(500), ids: [1, 2, 3, 4] }) }, JSON.parse('{"box":{"__proto__":{"m":1}}}')];
  let bad = '';
  for (const raw of shapes) {
    try {
      const st = S.sanitize(raw).state;
      const valid = st.v === 2 && Object.entries(st.box).every(([k, e]) => /^\d+$/.test(k) && Number.isInteger(e.m) && e.m >= 0 && e.m <= 10 && Number.isInteger(e.r) && e.r >= 1 && e.r <= 5)
        && Array.isArray(st.teams) && st.teams.length <= 60 && st.teams.every(t => typeof t.name === 'string' && t.name.length <= 40 && t.ids.length === 4 && t.ids.every(i => i === null || (Number.isInteger(i) && i > 0)))
        && Number.isInteger(st.orbs) && st.orbs >= 0 && st.orbs <= 99999 && typeof st.prefs.fehPass === 'boolean';
      if (!valid) bad += ' invalid for ' + JSON.stringify(raw).slice(0, 60);
    } catch (e) { bad += ' threw for ' + JSON.stringify(raw) + ': ' + e.message; }
  }
  ok('sanitize makes ' + shapes.length + ' broken shapes valid', !bad, bad);
  ok('clampInt', S.clampInt('1e15', 0, 99999) === 99999 && S.clampInt(-5, 0, 10) === 0 && S.clampInt('abc', 0, 10, 0) === 0 && S.clampInt(3.9, 0, 10) === 3 && S.clampInt(Infinity, 0, 10) === 10);
  ok('search folding', DA.fold('Líf') === 'lif' && DA.fold('Þjazi') === 'thjazi' && DA.fold('Níðhöggr') === 'nidhoggr' && DA.fold('Céline') === 'celine', DA.fold('Níðhöggr'));

  // ---------------------------------------------------------------------------------------------------- every route
  const routes = [['home', '#/home'], ['heroes', '#/heroes'], ['marking mode', '#/heroes/mark'], ['empty address', ''], ['hero', '#/hero/' + marth.id], ['hero with builds', '#/hero/' + withBuilds.id], ['newest hero', '#/hero/' + newest.id],
    ['barracks', '#/barracks'], ['teams', '#/teams'], ['summon', '#/summon'], ['orbs', '#/orbs'],
    ['guide', '#/guide'], ['guide start', '#/guide/start'], ['guide summon', '#/guide/summon'], ['guide orbs', '#/guide/orbs'], ['guide spend', '#/guide/spend'], ['guide meta', '#/guide/meta'], ['guide about', '#/guide/about'],
    ['unknown hero', '#/hero/9999999'], ['hero by old wiki name', '#/hero/' + encodeURIComponent(marth.wn)], ['broken address', '#/hero/%E0%A4%A'], ['unknown page', '#/nosuchpage'], ['odd address', '#!!'], ['unknown guide tab', '#/guide/zzz']];
  const seed = { v: 2, box: Object.fromEntries(index.slice(0, 12).map((x, i) => [x.id, { m: i % 11, r: 5 - (i % 3) }])), teams: [{ name: 'Arena', ids: [index[0].id, index[1].id, null, null] }], orbs: 137, prefs: { fehPass: false } };
  for (const [w, h] of [[1280, 900], [420, 800], [360, 740]]) {
    group = 'routes at ' + w + ' px';
    for (const [label, route] of routes) {
      const fr = await open(route, { w, h, storage: { 'hc.v2': seed } });
      checkPage(fr, label);
      if (w === 1280) ok(label + ' sets the page title', fr.doc.title.endsWith('Heroes Companion') && (fr.doc.title.length > 16 || /unknown page|broken|odd/.test(label)), fr.doc.title);
    }
  }

  // ---------------------------------------------------------------------------------------------------- navigation
  group = 'navigation';
  let fr = await open('#/heroes', { storage: {} });
  ok('first load leaves the focus alone', fr.doc.activeElement === fr.doc.body, fr.doc.activeElement && fr.doc.activeElement.tagName);
  await go(fr, '#/orbs');
  ok('focus moves to the heading on a route change', fr.doc.activeElement && fr.doc.activeElement.tagName === 'H1', fr.doc.activeElement && fr.doc.activeElement.tagName);
  ok('the menu marks the current page', text(fr.doc.querySelector('#nav a[aria-current="page"]')) === en['nav.orbs']);
  await go(fr, '#/hero/9999999');
  ok('unknown hero says so', text(fr.view).includes(en['hero.unknown']) && fr.errors.length === 0, text(fr.view).slice(0, 80) + fr.errors.join('|'));
  await go(fr, '#/hero/%E0%A4%A');
  ok('malformed address says so', text(fr.view).includes(en['err.badaddress']) && fr.errors.length === 0, text(fr.view).slice(0, 80) + fr.errors.join('|'));
  await go(fr, '#/nosuchpage');
  ok('unknown page says so', text(fr.view).includes(en['err.notfound']), text(fr.view).slice(0, 80));
  await go(fr, '#/hero/' + encodeURIComponent(marth.wn));
  ok('old link by wiki name still opens the hero', text(fr.view.querySelector('h1')).includes(marth.n), text(fr.view.querySelector('h1')));
  ok('footer names the right licence', text(fr.doc.getElementById('foot')).includes('CC BY-NC-SA') && !/CC BY-SA/.test(fr.doc.body.textContent), text(fr.doc.getElementById('foot')));
  ok('footer shows the age of the data', text(fr.doc.getElementById('foot')).includes(T.fmtDate(manifest.dataFrom)), text(fr.doc.getElementById('foot')));

  // ---------------------------------------------------------------------------------------------------- hero list
  group = 'hero list';
  fr = await open('#/heroes', { storage: {} });
  const tiles = () => [...fr.view.querySelectorAll('.tile')];
  const ids = () => tiles().map(x => Number(x.getAttribute('data-id')));
  const byId = new Map(index.map(x => [x.id, x]));
  ok('every tile is a real link', tiles().length === 60 && tiles().every(x => x.tagName === 'A' && x.getAttribute('href') === '#/hero/' + x.getAttribute('data-id')), tiles().length);
  ok('tiles carry weapon and movement badges with names', tiles().every(x => x.querySelector('.wb[aria-label]') && x.querySelector('.mv[aria-label]') && x.getAttribute('aria-label').length > 5));
  ok('with artwork off no image is requested', fr.view.querySelectorAll('.art img').length === 0 && fr.view.querySelectorAll('.art').length >= 60);
  const search = fr.view.querySelector('input[type=search]');
  setInput(fr, search, DA.fold(accented.n));
  await until(() => tiles().length < 60 && tiles().some(r => text(r).includes(accented.n)), 3000);
  ok('search without accents finds "' + accented.n + '" when "' + DA.fold(accented.n) + '" is typed', tiles().some(r => text(r).includes(accented.n)), tiles().length + ' tiles');
  ok('typing keeps the search field', fr.view.querySelector('input[type=search]') === search);
  setInput(fr, search, 'zzzzqqq');
  await until(() => tiles().length === 0, 3000);
  ok('no match shows a message and a way out', text(fr.view).includes(en['heroes.none']) && text(fr.view).includes(en['heroes.clear']));
  [...fr.view.querySelectorAll('button')].find(b => text(b) === en['heroes.clear']).click();
  await until(() => tiles().length === 60, 3000);
  ok('"Clear filters" brings the heroes back', tiles().length === 60);
  [...fr.view.querySelectorAll('.fchip')].find(b => text(b) === en['color.red']).click();
  ok('the color filter is a pressed button and filters', fr.view.querySelector('.fchip[aria-pressed="true"]') && ids().length > 0 && ids().every(id => byId.get(id).w.startsWith('Red')), ids().slice(0, 5).join());
  [...fr.view.querySelectorAll('.fchip')].find(b => text(b) === en['color.red']).click();
  [...fr.view.querySelectorAll('.fchip')].find(b => text(b) === en['f.more']).click();
  const sortSel = fr.view.querySelector('select[data-pick="sort"]');
  sortSel.value = 'atk'; sortSel.dispatchEvent(new fr.win.Event('change', { bubbles: true }));
  const atk = ids().map(id => byId.get(id).s[1]);
  ok('sorted by attack, with the value on the tile', atk.length === 60 && atk.every((v, i) => i === 0 || atk[i - 1] >= v) && text(tiles()[0].querySelector('.tile-stat')).includes(String(atk[0])), atk.slice(0, 10).join(','));
  sortSel.value = 'r'; sortSel.dispatchEvent(new fr.win.Event('change', { bubbles: true }));
  fr.view.querySelector('[data-view="current"]').click();
  const cutoff = new Date(Date.parse(manifest.dataFrom) - 125 * 86400000).toISOString().slice(0, 10);
  ok('"Current" shows only heroes of the last months of the data', ids().length > 0 && ids().every(id => byId.get(id).r >= cutoff), ids().length);
  fr.view.querySelector('[data-view="picks"]').click();
  await until(() => tiles().length > 0 && tiles().length <= 12, 3000);
  ok('"Picks" shows the hand-written list', tiles().length === picks.picks.length, tiles().length);
  fr.view.querySelector('[data-view="all"]').click();

  group = 'marking mode';
  fr.view.querySelector('[data-act="edit"]').click();
  const marks = () => [...fr.view.querySelectorAll('button.tile')];
  ok('marking mode shows every hero as a button, grouped by color', marks().length === index.length && fr.view.querySelectorAll('.groups section').length === 4 && !fr.view.querySelector('a.tile'), marks().length);
  const m0 = marks()[0], m1 = marks()[1], firstName = text(m0.querySelector('.tile-name'));
  m0.focus(); m0.click(); m1.click();
  ok('a tap marks the hero and keeps the focus', m0.getAttribute('aria-pressed') === 'true' && m0.classList.contains('owned') && fr.doc.activeElement === m0 && m0.getAttribute('aria-label').includes(firstName), m0.getAttribute('aria-label'));
  ok('nothing is saved before "Done"', stored() === null || Object.keys(stored().box).length === 0, localStorage.getItem('hc.v2'));
  const liveText = () => text(fr.view.querySelector('.actionbar .live'));
  ok('the live count follows', liveText().startsWith('2 ') && /\+2 added/.test(liveText()), liveText());
  [...fr.view.querySelectorAll('.actionbar button')].find(b => text(b) === en['undo']).click();
  ok('Undo takes the last tap back', m1.getAttribute('aria-pressed') === 'false' && liveText().startsWith('1 '), liveText());
  fr.view.querySelector('[data-act="done"]').click();
  ok('"Done" saves and says so', stored() && Object.keys(stored().box).length === 1 && /^\d+$/.test(Object.keys(stored().box)[0]) && stored().v === 2 && /Barracks saved: 1 heroes/.test(text(fr.doc.getElementById('toast'))), localStorage.getItem('hc.v2') + ' ' + text(fr.doc.getElementById('toast')));
  ok('the count follows', /· 1 in your barracks/.test(text(fr.view.querySelector('.countline'))) && fr.view.querySelectorAll('a.tile.owned').length === 1, text(fr.view.querySelector('.countline')));
  fr.view.querySelector('[data-act="edit"]').click();
  marks()[5].click();
  [...fr.view.querySelectorAll('button')].find(b => text(b).includes(en['cancel'])).click();
  ok('"Cancel" discards the taps', Object.keys(stored().box).length === 1 && !fr.view.querySelector('button.tile'));
  ok('hero list logs no error', fr.errors.length === 0, fr.errors.join(' | '));

  // ---------------------------------------------------------------------------------------------------- home and the carousel
  group = 'home';
  const liveNow = banners.filter(b => b.s <= nowReal && nowReal <= b.e);
  fr = await open('#/home', { storage: {} });
  const car = fr.view.querySelector('.carousel'), cards = () => [...fr.view.querySelectorAll('.car-card')];
  const curCard = () => fr.view.querySelector('.car-card.cur');
  ok('the carousel renders with cards', car && cards().length >= picks.picks.length && cards().length <= picks.picks.length + 16, cards().length);
  ok('every card is a link to a hero page and is labelled "Pick" or "On banner now"', cards().every(c => /^#\/hero\/\d+$/.test(c.getAttribute('href')) && c.querySelectorAll('.car-label').length > 0 && [...c.querySelectorAll('.car-label')].every(l => [en['car.pick'], en['car.banner']].includes(text(l)))));
  const pickIds = picks.picks.map(p => index.find(x => x.wn === p.id).id);
  ok('the Picks come first, in the order of the list', cards().slice(0, pickIds.length).every((c, i) => c.getAttribute('href') === '#/hero/' + pickIds[i] && text(c.querySelector('.car-label')) === en['car.pick']));
  const focusNow = new Set(liveNow.flatMap(b => (b.f || []).map(f => f[0])));
  ok('the other cards are focus heroes of banners that run now', cards().slice(pickIds.length).every(c => focusNow.has(Number(c.getAttribute('href').slice(7)))) && (cards().length > pickIds.length || focusNow.size === 0));
  ok('the card in front says where the pick comes from and when', curCard() === cards()[0] && text(fr.view.querySelector('.car-info')).includes(T.fmtDate(picks.as_of)) && fr.view.querySelectorAll('.car-info a[href^="https://"]').length >= 2, text(fr.view.querySelector('.car-info')).slice(0, 200));
  ok('no rating is shown in the carousel', !/tier [SABCD]\b|[0-9]\/10|S-tier|\brated\b|\bscore\b/i.test(text(car)), text(car).slice(0, 200));
  ok('cards stand on a ring (3D transforms)', /rotateY/.test(cards()[1].style.transform) && /translate3d/.test(cards()[1].style.transform) && cards().filter(c => !c.hidden).length <= 9, cards()[1].style.transform);
  fr.view.querySelector('.car-arrow.next').click();
  ok('the arrow button brings the next card to the front', curCard() === cards()[1], curCard() && curCard().getAttribute('href'));
  curCard().focus();
  curCard().dispatchEvent(new fr.win.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  ok('the right arrow key spins on and moves the focus', curCard() === cards()[2] && fr.doc.activeElement === cards()[2], curCard() && curCard().getAttribute('href'));
  curCard().dispatchEvent(new fr.win.KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
  ok('the left arrow key spins back', curCard() === cards()[1]);
  ok('only the card in front is in the tab order', cards().filter(c => c.tabIndex === 0).length === 1 && curCard().tabIndex === 0);
  const stage = fr.view.querySelector('.car-stage'), box = stage.getBoundingClientRect();
  const pe = (type, x) => stage.dispatchEvent(new fr.win.PointerEvent(type, { pointerId: 7, pointerType: 'mouse', button: 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: box.top + 150, bubbles: true, cancelable: true }));
  const before = cards().indexOf(curCard()), mid = box.left + box.width / 2;
  pe('pointerdown', mid); for (let x = 0; x <= 10; x++) pe('pointermove', mid - x * 50); await sleep(120); pe('pointerup', mid - 500);
  const moved = (cards().indexOf(curCard()) - before + cards().length) % cards().length;
  ok('dragging to the left spins the ring forward and snaps to a card', moved >= 1 && moved <= 4 && /scale\(1\.1/.test(curCard().style.transform), 'moved ' + moved + ', ' + curCard().style.transform);
  const clickEv = new fr.win.MouseEvent('click', { bubbles: true, cancelable: true }); curCard().dispatchEvent(clickEv);
  ok('the click that ends a drag opens nothing', clickEv.defaultPrevented && fr.win.location.hash === '#/home', fr.win.location.hash);
  const wheel = new fr.win.WheelEvent('wheel', { deltaX: 120, deltaY: 0, bubbles: true, cancelable: true }); const b4 = curCard(); stage.dispatchEvent(wheel);
  const wheel2 = new fr.win.WheelEvent('wheel', { deltaY: 4, bubbles: true, cancelable: true }); stage.dispatchEvent(wheel2);
  ok('a sideways wheel spins, a small up-down touchpad step is left to the page', curCard() !== b4 && wheel.defaultPrevented && !wheel2.defaultPrevented);
  const target = curCard().getAttribute('href');
  fr.view.removeAttribute('data-ready'); curCard().click();
  await until(() => fr.view.getAttribute('data-ready') === 'hero'); await settle(fr);
  ok('a click on a card opens that hero page', fr.win.location.hash === target && !!fr.view.querySelector('.hero-name'), fr.win.location.hash + ' vs ' + target);
  ok('home and carousel log no error', fr.errors.length === 0, fr.errors.join(' | '));
  fr = await open('#/home', { storage: {}, query: '&rm=1' });
  ok('reduced motion: no ring, a plain row that scrolls', fr.view.querySelector('.carousel.car-plain') && cards().every(c => !c.style.transform && !c.hidden) && fr.win.getComputedStyle(fr.view.querySelector('.car-ring')).overflowX === 'auto' && fr.doc.documentElement.classList.contains('rm'));
  ok('reduced motion: one tab stop, an honest hint, no animation runs', cards().filter(c => c.tabIndex === 0).length === 1 && text(fr.view.querySelector('.car-hint')) === en['car.hint.plain'] && fr.doc.getAnimations().length === 0, fr.doc.getAnimations().length);
  fr = await open('#/home', { storage: {}, motion: true });
  await sleep(1300);
  ok('with motion on, the numbers end at their values and nothing is logged', text(fr.view.querySelector('.kpi b')) === '0' && fr.errors.length === 0, fr.errors.join(' | '));
  fr = await open('#/home', { storage: { 'hc.v2': seed } });
  ok('home shows the visitor\'s numbers', text(fr.view.querySelector('.kpis')).includes('137') && text(fr.view.querySelector('.kpi b')) === '12' && text(fr.doc.getElementById('orbcount')) === '137', text(fr.view.querySelector('.kpis')));
  ok('home shows running banners with a verdict each', fr.view.querySelectorAll('.banner.compact .verdict b').length === Math.min(2, liveNow.filter(b => !['revival', 'free'].includes(b.k)).length));
  ok('both menus have the five destinations', fr.doc.querySelectorAll('#nav a').length === 5 && fr.doc.querySelectorAll('#nav2 a').length === 5 && text(fr.doc.querySelector('#nav2 a[aria-current="page"]')) === en['nav.home']);
  fr = await open('#/heroes', { storage: {} });
  const rf0 = fr.win.fetch; fr.win.fetch = (u, o) => /content\/|data\/(banners|orbs)/.test(String(u)) ? Promise.resolve(new fr.win.Response('gone', { status: 404 })) : rf0(u, o);
  await go(fr, '#/home');
  ok('home stands when its extra files fail', fr.view.querySelector('h1') && fr.view.querySelector('.kpis') && text(fr.view).includes(en['home.failed']) && fr.errors.length === 0, text(fr.view).slice(0, 120) + fr.errors.join('|'));

  // ---------------------------------------------------------------------------------------------------- artwork
  group = 'artwork';
  const AR = await import('/js/art.js');
  ok('md5 is right', AR.md5('') === 'd41d8cd98f00b204e9800998ecf8427e' && AR.md5('abc') === '900150983cd24fb0d6963f7d28e17f72' && AR.md5('The quick brown fox jumps over the lazy dog') === '9e107d9d372bb6826bd81d3542a419d6'
    && AR.md5('a'.repeat(64)) === '014842d480b571495a4a0363793f7367' && AR.md5('Líf') === '34558919b2881f51200048934d9a6019', AR.md5('abc'));
  ok('the address of Marth\'s portrait is the one the wiki uses', AR.artUrl(marth, 'p', 600) === 'https://static.wikia.nocookie.net/feheroes_gamepedia_en/images/f/fb/Marth_Altean_Prince_Face.webp/revision/latest/scale-to-width-down/600'
    && AR.artUrl(marth, 'f', 0, true).includes('/7/7a/Marth_Altean_Prince_Resplendent_Face_FC.webp/revision/latest'), AR.artUrl(marth, 'p', 600));
  fr = await open('#/heroes', { storage: {}, query: '&art=1' });
  await until(() => fr.view.querySelectorAll('.art.loaded').length >= 8, 6000);
  ok('artwork that arrives is shown over the fallback', fr.view.querySelectorAll('.art.loaded').length >= 8 && fr.view.querySelectorAll('.art img[loading="lazy"]').length === 60, fr.view.querySelectorAll('.art.loaded').length);
  await go(fr, '#/hero/' + marth.id);
  await until(() => fr.view.querySelector('.hero-art.noart'), 6000);
  ok('artwork that fails leaves the designed fallback, no broken image', fr.view.querySelector('.hero-art.noart') && fr.win.getComputedStyle(fr.view.querySelector('.hero-art .full')).display === 'none' && fr.win.getComputedStyle(fr.view.querySelector('.hero-art .ph')).opacity > 0.5);
  ok('the hero page credits the artist and names the owner', text(fr.view.querySelector('.credit')).includes(marth.art) && /Nintendo \/ INTELLIGENT SYSTEMS/.test(text(fr.view.querySelector('.credit'))), text(fr.view.querySelector('.credit')));
  await until(() => fr.view.querySelectorAll('.variant[hidden]').length === 4, 4000);
  ok('art variants that do not exist are hidden, the others are buttons', fr.view.querySelectorAll('.variant').length === 5 && fr.view.querySelectorAll('.variant[hidden]').length === 4, fr.view.querySelectorAll('.variant[hidden]').length);
  const sw = fr.doc.getElementById('artswitch');
  ok('the footer has the "Show game artwork" switch, on', sw && sw.getAttribute('aria-pressed') === 'true' && text(sw) === en['foot.artswitch'] && /Nintendo \/ INTELLIGENT SYSTEMS/.test(text(fr.doc.getElementById('foot'))));
  fr.view.removeAttribute('data-ready'); sw.click(); await until(() => fr.view.getAttribute('data-ready')); await settle(fr);
  ok('switched off: remembered, and no artwork element is left', sw.getAttribute('aria-pressed') === 'false' && stored().prefs.art === false && fr.view.querySelectorAll('.art img, .hero-art img, .sprite').length === 0 && !fr.view.querySelector('.variants'));
  ok('no security policy violation', !fr.errors.some(e => /security policy/.test(e)), fr.errors.join(' | '));

  // ---------------------------------------------------------------------------------------------------- standing, summon rules
  group = 'standing';
  const hector = index.find(x => x.wn === 'Hector Of Strength');
  if (hector) {
    fr = await open('#/hero/' + hector.id, { storage: {} });
    const st = text(fr.view.querySelector('.facts')), stAll = text(fr.view.querySelector('.facts').closest('.panel'));
    ok('Hector follows the worked example of the rules', st.includes('Among the 34 armored green axe heroes: HP 55 (rank 2), joint highest Atk (50), joint highest Def (50), Res 46 (rank 2).') && st.includes('Low for this class: Spd 16.')
      && st.includes('Stat total 217: rank 1 of 34.') && st.includes('Emblem hero: can engage with one other hero') && st.includes('Summoned at 5 stars.'), st);
    ok('the block says it is no rating and shows none', stAll.includes(en['st.sub']) && !/\d\/10|\btier\b|\bbest\b|\bmeta\b/i.test(st), stAll.slice(0, 200));
    const sk = fr.view.querySelector('.skill');
    ok('the own kit is the default build, skills open on a tap', text(fr.view).includes(en['hero.kit.title']) && fr.view.querySelectorAll('.skill[aria-expanded="false"]').length >= 3 && (sk.click(), sk.getAttribute('aria-expanded') === 'true'));
  } else ok('Hector: Of Strength is in the data', false);
  fr = await open('#/hero/' + withBuilds.id, { storage: {} });
  const oldFold = fr.view.querySelector('details.oldbuilds');
  ok('builds of a hero from before 2024 are folded and labelled as old', withBuilds.r >= '2024-01-01' || (oldFold && !oldFold.open && text(oldFold.querySelector('summary')).includes(en['hero.builds.old.chip'])), withBuilds.r);
  ok('the hero page links to Game8', fr.view.querySelectorAll('a[href^="https://game8.co/"]').length >= 2);

  group = 'summon';
  const rules = await (await fetch('/content/summon_rules.json')).json();
  ok('every banner type in the data has a written rule', banners.every(b => rules.types.some(x => x.type === b.t)), [...new Set(banners.filter(b => !rules.types.some(x => x.type === b.t)).map(b => b.t))].join());
  fr = await open('#/summon', { storage: { 'hc.v2': { v: 2, orbs: 200 } } });
  const mainCards = [...fr.view.querySelectorAll('article[data-banner]')];
  ok('running banners have a verdict, rates and their focus heroes', mainCards.length > 0 && mainCards.every(a => a.querySelector('.verdict b') && a.querySelector('.rates') && (a.querySelector('.focus-row') || /focus/i.test(text(a)))), mainCards.length);
  const passOnly = liveNow.find(b => (rules.types.find(x => x.type === b.t) || { free_pick: {} }).free_pick.who === 'feh_pass' && !['revival', 'free'].includes(b.k) && (b.f || []).length && !b.re && !/4★SHSR/.test(b.n));
  if (passOnly) {
    const cardOf = () => [...fr.view.querySelectorAll('[data-banner]')].find(x => x.getAttribute('data-banner') === passOnly.id);
    ok('a Feh Pass free pick is labelled as paid and not counted', text(cardOf().querySelector('.pick')).startsWith(en['bn.paid']) && !cardOf().querySelector('.pick .bar') && text(cardOf().querySelector('.verdict b')) !== en['bn.v.reach'], text(cardOf().querySelector('.pick')));
    fr.view.querySelector('.budget input[type=checkbox]').click();
    ok('with "I have Feh Pass" it is counted, still labelled', stored().prefs.fehPass === true && cardOf().querySelector('.pick .bar') && text(cardOf().querySelector('.pick')).includes(en['bn.paid.chip']) && text(cardOf().querySelector('.verdict b')) === (rules.types.find(x => x.type === passOnly.t).verdict.rule === 'skip_unless_wanted' ? en['bn.v.want'] : en['bn.v.reach']), text(cardOf().querySelector('.pick')));
    [...cardOf().querySelectorAll('.banner-actions button')].find(b => text(b) === '+1').click();
    ok('"+1" records a summon on that banner', stored().pulls[passOnly.id] === 1, JSON.stringify(stored().pulls));
    [...cardOf().querySelectorAll('.banner-actions button')].find(b => text(b) === en['bn.pulls.circle']).click();
    ok('a full circle records five summons and takes 20 orbs, with Undo', stored().pulls[passOnly.id] === 6 && stored().orbs === 180 && text(fr.doc.querySelector('#toast button')) === en['undo'], JSON.stringify(stored()));
    fr.doc.querySelector('#toast button').click();
    ok('Undo puts both back', stored().pulls[passOnly.id] === 1 && stored().orbs === 200);
  }
  ok('the cost of a circle is on the page', text(fr.view).includes('5 + 4 + 4 + 4 + 3 = 20') && text(fr.view).includes('155 orbs'));
  const foldEl = fr.view.querySelector('details.banner.fold');
  if (foldEl) { foldEl.open = true; await sleep(120); ok('a folded banner shows its body when opened', !!foldEl.querySelector('.banner-body .verdict')); }
  ok('summon logs no error', fr.errors.length === 0, fr.errors.join(' | '));
  fr = await open('#/orbs', { storage: {} });
  const curr = await (await fetch('/content/currencies.json')).json();
  ok('the Orbs page has a card per currency, with sources', fr.view.querySelectorAll('.currency').length === curr.cards.length && fr.view.querySelectorAll('.currency .sources a[href^="https://"]').length > 20, fr.view.querySelectorAll('.currency').length);
  ok('nothing unknown is printed as "null" or "undefined"', !/\bnull\b|undefined/.test(text(fr.view)));

  // ---------------------------------------------------------------------------------------------------- hero page
  group = 'hero page';
  fr = await open('#/hero/' + withBuilds.id, { storage: { 'hc.v2': { v: 2, box: { [withBuilds.id]: { m: 2, r: 5 } } } } });
  const heroText = text(fr.view);
  ok('no markup in the build texts', !/style=|\[\[|\]\]|class=|link=|&nbsp;|&lt;|<span/.test(fr.view.textContent), (fr.view.textContent.match(/.{20}(style=|\[\[|class=|link=).{20}/) || [''])[0]);
  ok('builds link to their source page', !!fr.view.querySelector('a[href*="Build_Center"]'));
  ok('skills say "unknown" when the tables are missing', (manifest.tables.Skills === 'ok' && manifest.tables.UnitSkills === 'ok') || heroText.includes(en['hero.kit.unknown']), heroText.slice(0, 200));
  ok('banner history says "unknown" when the table is missing', manifest.tables.SummoningEventFocuses === 'ok' ? !heroText.includes(en['hero.banners.unknown']) : heroText.includes(en['hero.banners.unknown']) && !/No banner with this hero/.test(heroText));
  const merges = fr.view.querySelector('input[type=number]');
  setInput(fr, merges, '99');
  ok('merges are held at 10, also in the field', merges.value === '10' && stored().box[withBuilds.id].m === 10, merges.value + ' / ' + localStorage.getItem('hc.v2'));
  setInput(fr, merges, '-5');
  ok('merges are held at 0', merges.value === '0' && stored().box[withBuilds.id].m === 0, merges.value);
  setInput(fr, merges, 'abc');
  ok('merges survive text', merges.value === '0' && stored().box[withBuilds.id].m === 0, merges.value);
  ok('hero page logs no error', fr.errors.length === 0, fr.errors.join(' | '));
  // the hero's own file fails to load: the page stays, offers another try, and recovers
  fr = await open('#/heroes', { storage: {} });
  const realFetch = fr.win.fetch;
  fr.win.fetch = (u, o) => /data\/(hero\/|orbs)/.test(String(u)) ? Promise.resolve(new fr.win.Response('gone', { status: 404 })) : realFetch(u, o);
  await go(fr, '#/hero/' + newest.id);
  ok('a failed hero file leaves the page standing', text(fr.view.querySelector('h1')).includes(newest.n) && text(fr.view).includes(en['hero.details.failed']), text(fr.view).slice(0, 200));
  await go(fr, '#/orbs');
  ok('a failed page download shows the error card', text(fr.view).includes(en['err.load']) && !!fr.view.querySelector('h1') && text(fr.view).includes(en['err.retry']), text(fr.view).slice(0, 200));
  fr.win.fetch = realFetch;
  fr.view.removeAttribute('data-ready');
  [...fr.view.querySelectorAll('button')].find(b => text(b) === en['err.retry']).click();
  await until(() => fr.view.getAttribute('data-ready')); await settle(fr);
  ok('"Try again" recovers', text(fr.view.querySelector('h1')) === en['orbs.title'], text(fr.view).slice(0, 100));

  // ---------------------------------------------------------------------------------------------------- game clock on the pages
  group = 'clock';
  const sample = banners.filter(b => b.e > nowReal).sort((a, b) => a.e - b.e)[0];
  if (sample) {
    const count = at => banners.filter(b => (b.s <= at && at <= b.e) || b.s > at).length;
    fr = await open('#/summon', { storage: {}, query: '&now=' + (sample.e - 1) });
    const before = fr.view.querySelectorAll('[data-banner]').length;
    ok('one second before its end the banner is shown, ending in 1 min', before === count(sample.e - 1) && text(fr.view).includes(sample.n) && /ends in 1 min/.test(text(fr.view)), before + ' vs ' + count(sample.e - 1));
    ok('the exact end is on the page', !!fr.view.querySelector('.time[title*="06:59 UTC"]'), 'no chip with the UTC end');
    fr = await open('#/summon', { storage: {}, query: '&now=' + (sample.e + 2) });
    const after = fr.view.querySelectorAll('[data-banner]').length;
    ok('two seconds after its end the banner is gone', after === count(sample.e + 2) && ![...fr.view.querySelectorAll('[data-banner]')].some(x => x.getAttribute('data-banner') === sample.id), after + ' vs ' + count(sample.e + 2));
    ok('no "0 days left" anywhere', !/\b0 days left/.test(text(fr.view)));
  } else ok('a banner that has not ended exists in the data', false, 'the data is too old for the clock test');
  const orbRows = (orbs.groups[0] || { rows: [] }).rows;
  for (const at of [nowReal, ...orbRows.slice(0, 3).map(r => r.e + 1), ...orbRows.slice(0, 2).map(r => r.s - 1)]) {
    const open_ = orbRows.filter(r => r.s <= at && at <= r.e);
    const free = open_.filter(r => !r.pass).reduce((a, r) => a + r.n, 0), paid = open_.filter(r => r.pass).reduce((a, r) => a + r.n, 0);
    fr = await open('#/orbs', { storage: {}, query: '&now=' + at });
    const shown = fr.view.querySelector('#orbs-free');
    ok('free orb total at ' + new Date(at * 1000).toISOString() + ' is ' + free + ', Feh Pass apart', shown && Number(text(shown)) === free && (paid === 0 || text(fr.view.querySelector('#orbs-pass')).includes(String(paid))), shown ? text(shown) : 'no total');
    if (at === nowReal) {
      fr.view.querySelector('input[type=checkbox]').click();
      await sleep(50);
      ok('"I have Feh Pass" shows the sum and is remembered', text(fr.view.querySelector('#orbs-pass')).includes(String(free + paid)) && stored().prefs.fehPass === true && Number(text(fr.view.querySelector('#orbs-free'))) === free, text(fr.view.querySelector('#orbs-pass')));
      ok('what is not covered is named', text(fr.view).includes(en['orbs.notcovered']) && !/Tempest Trials that have not ended/.test(text(fr.view)));
    }
  }
  fr = await open('#/heroes', { storage: {}, query: '&now=' + (Date.parse(manifest.dataFrom) / 1000 + 11 * 86400) });
  ok('data older than 10 days is announced on the page', /11 days ago/.test(text(fr.doc.getElementById('notice'))), text(fr.doc.getElementById('notice')));
  fr = await open('#/heroes', { storage: {}, query: '&now=' + (Date.parse(manifest.dataFrom) / 1000 + 2 * 86400) });
  ok('fresh data has no such notice', text(fr.doc.getElementById('notice')) === '', text(fr.doc.getElementById('notice')));

  // ---------------------------------------------------------------------------------------------------- defects found by the QA round
  group = 'qa fixes';
  // a page whose Picks and banner files are made up by the test: k focus heroes on one running banner, no Picks
  const fakeBanner = (heroes, extra = {}) => ({ v: 2, focusKnown: true, from: 0, banners: heroes.length ? [{ id: 'test banner', n: 'Test banner', s: nowReal - 3600, e: nowReal + 5 * 86400, t: 'Emblem', k: 'legendary', f: heroes.map(x => [x.id, 5]), ...extra }] : [] });
  async function withBanners(route, file, { w = 1280, h = 900, storage = {} } = {}) {
    const f2 = await open('#/barracks', { storage, w, h });
    const real = f2.win.fetch;
    f2.win.fetch = (u, o) => /content\/picks/.test(String(u)) ? Promise.resolve(new f2.win.Response(JSON.stringify({ ...picks, picks: [] })))
      : /data\/banners/.test(String(u)) ? Promise.resolve(new f2.win.Response(JSON.stringify(file))) : real(u, o);
    await go(f2, route);
    return f2;
  }
  // 1: the carousel works at any card count
  for (const k of [0, 1, 2, 3, 8, 9, 10, 16]) {
    fr = await withBanners('#/home', fakeBanner(index.slice(0, k)));
    const cs = [...fr.view.querySelectorAll('.car-card')], cur = () => fr.view.querySelector('.car-card.cur');
    if (k === 0) { ok('no card: no carousel, the page stands', !fr.view.querySelector('.carousel') && fr.view.querySelector('h1') && fr.view.querySelector('.kpis') && fr.errors.length === 0, fr.errors.join('|')); continue; }
    const front = () => { const c = cur(); return !!c && !c.hidden && c.style.opacity === '1' && /translate3d\(0px/.test(c.style.transform) && /scale\(1\.1/.test(c.style.transform); };
    let bad = cs.length === k && front() && cur() === cs[0] ? '' : 'at the start: ' + cs.length + ' cards';
    const nextBtn = fr.view.querySelector('.car-arrow.next'), prevBtn = fr.view.querySelector('.car-arrow.prev');
    for (let step = 1; step <= k + 2 && !bad; step++) {
      nextBtn.click();
      const want = k >= 3 ? step % k : Math.min(step, k - 1);
      if (!front() || cur() !== cs[want] || text(fr.view.querySelector('.car-count')) !== (want + 1) + ' / ' + k) bad = 'after ' + step + ' x next: front card ' + cs.indexOf(cur()) + ' (wanted ' + want + '), hidden ' + (cur() && cur().hidden) + ', ' + (cur() && cur().style.transform);
    }
    for (let step = 1; step <= 2 && !bad && k >= 3; step++) { prevBtn.click(); if (!front()) bad = 'after going back'; }
    ok(k + ' card(s): a card is in front after every step, ' + (k >= 3 ? 'the ring is endless' : 'the ends stop'), !bad && (k >= 3 || (nextBtn.disabled && (k === 1 ? nextBtn.hidden : !prevBtn.disabled))) && fr.errors.length === 0, bad + fr.errors.join('|'));
  }
  // 2: on a phone the front card lies on top of its neighbours
  fr = await withBanners('#/home', fakeBanner(index.slice(0, 10)), { w: 420, h: 800 });
  {
    const c = fr.view.querySelector('.car-card.cur'), r = c.getBoundingClientRect(), y = r.top + r.height * .5;
    const at = x => { const e2 = fr.doc.elementFromPoint(x, y); return e2 && e2.closest('.car-card'); };
    ok('phone: the front card is on top across its whole width', at(r.left + r.width * .08) === c && at(r.left + r.width * .5) === c && at(r.left + r.width * .92) === c && fr.win.getComputedStyle(fr.view.querySelector('.car-ring')).transformStyle !== 'preserve-3d',
      [.08, .5, .92].map(p => { const e2 = at(r.left + r.width * p); return e2 ? e2.getAttribute('data-i') : 'none'; }).join(','));
  }
  // 3: a release outside the stage ends the gesture
  fr = await withBanners('#/home', fakeBanner(index.slice(0, 10)));
  {
    const stage2 = fr.view.querySelector('.car-stage'), b2 = stage2.getBoundingClientRect(), mid2 = b2.left + b2.width / 2, y = b2.top + 150;
    const ev = (el2, type, x, buttons) => el2.dispatchEvent(new fr.win.PointerEvent(type, { pointerId: 9, pointerType: 'mouse', button: 0, buttons, clientX: x, clientY: y, bubbles: true, cancelable: true }));
    const cur = () => fr.view.querySelector('.car-card.cur');
    const first = cur();
    ev(stage2, 'pointerdown', mid2, 1); ev(stage2, 'pointermove', mid2 - 3, 1);
    ev(fr.doc.getElementById('foot'), 'pointerup', mid2 - 3, 0);                     // released outside the stage
    ev(stage2, 'pointermove', mid2 - 150, 0); ev(stage2, 'pointermove', mid2 - 400, 0); await sleep(60);
    ok('a release outside the stage ends the drag: hovering afterwards moves nothing', cur() === first && !stage2.classList.contains('drag'), 'front ' + cur().getAttribute('data-i') + ', drag ' + stage2.classList.contains('drag'));
    ev(stage2, 'pointerdown', mid2, 1); ev(stage2, 'pointermove', mid2 - 120, 1);
    ev(stage2, 'pointermove', mid2 - 400, 0); await sleep(60);                       // the button came up without any event
    ok('a move with no button pressed ends a drag as well', !stage2.classList.contains('drag'));
    ev(stage2, 'pointerdown', mid2, 1); ev(stage2, 'pointermove', mid2 - 200, 1); ev(stage2, 'pointercancel', mid2 - 200, 0); await sleep(60);
    ok('a cancelled pointer ends a drag and the ring snaps to a card', !stage2.classList.contains('drag') && /scale\(1\.1/.test(cur().style.transform), cur().style.transform);
    await sleep(30);
    const enter = new fr.win.MouseEvent('click', { bubbles: true, cancelable: true }); cur().addEventListener('click', e2 => e2.preventDefault()); cur().dispatchEvent(enter);
    ok('a drag that ended without a click does not swallow the next one', !enter.cancelBubble);
    // the mouse wheel over the ring spins it; small touchpad steps and reduced motion leave the page scrolling
    const b4 = cur(), notch = new fr.win.WheelEvent('wheel', { deltaY: 100, bubbles: true, cancelable: true }); stage2.dispatchEvent(notch);
    const pad = new fr.win.WheelEvent('wheel', { deltaY: 4, bubbles: true, cancelable: true }); stage2.dispatchEvent(pad);
    ok('a mouse wheel notch over the ring spins one card, a touchpad scroll is left to the page', cur() !== b4 && notch.defaultPrevented && !pad.defaultPrevented);
  }
  // 4 and 5: re-runs have no free pick; rates come from the variant that fits, or are unknown
  const BN = await import('/js/banners.js');
  const special = rules.types.find(x => x.type === 'Special'), omega = rules.types.find(x => x.type === 'ω Special Heroes'), dbl = rules.types.find(x => x.type === 'Double Special Heroes');
  {
    const shsr = BN.ratesFor({ n: 'Wyvern Ninja (4★SHSR)', f: [], f4: true }, special) || {};
    ok('rates of a (4★SHSR) banner are the variant written for it', shsr.focus5 === 4 && shsr.other5 === 2 && shsr.focus4 === 3 && shsr.special4_shsr === 6 && shsr.star4 === 52 && shsr.star3 === 30, JSON.stringify(shsr));
    const plain4 = BN.ratesFor({ n: 'Some Banner', f: [[1, 5]], f4: true }, special) || {}, plain = BN.ratesFor({ n: 'Some Banner', f: [[1, 5]] }, special) || {};
    ok('a 4-star focus hero selects its variant, none keeps the base rates', plain4.focus4 === 3 && plain4.star4 === 52 && plain.focus4 == null && plain.star4 === 55, JSON.stringify([plain4, plain]));
    ok('rates that cannot be decided are unknown, not the base numbers', BN.ratesFor({ n: 'Some Banner', f: null }, special) === null && BN.ratesFor({ n: 'New Year (4★SHSR)', f: [] }, omega) === null
      && BN.ratesFor({ n: 'X', f: [] }, rules.types.find(x => x.type === 'Other')) === null && BN.ratesFor({ n: 'D', f: [[1, 5]] }, dbl).focus4 == null && BN.ratesFor({ n: 'D', f: [[1, 5]], f4: true }, dbl).focus4 === 3);
    ok('a re-run is told by the data or by its name', BN.isRerun({ n: 'A', re: true }) && BN.isRerun({ n: 'Wyvern Ninja (4★SHSR)' }) && !BN.isRerun({ n: 'Ninja Boot Camp' }));
    const rerun = { id: 'rerun', n: 'Old Seasonal Banner', s: nowReal - 3600, e: nowReal + 5 * 86400, t: 'Special', k: 'special', f: index.slice(0, 4).map(x => [x.id, 5]), re: true };
    const firstRun = { ...rerun, id: 'first', n: 'New Seasonal Banner', re: undefined }, shsrB = { ...rerun, id: 'shsr', n: 'Wyvern Ninja (4★SHSR)', re: undefined, f4: true };
    fr = await withBanners('#/summon', { v: 2, focusKnown: true, from: 0, banners: [rerun, firstRun, shsrB] }, { storage: { 'hc.v2': { v: 2, orbs: 200, prefs: { fehPass: true } } } });
    const cardOf = id => [...fr.view.querySelectorAll('[data-banner]')].find(x => x.getAttribute('data-banner') === id);
    const pickOf = id => text(cardOf(id).querySelector('.pick')), verdictOf = id => text(cardOf(id).querySelector('.verdict'));
    ok('with Feh Pass on, a re-run seasonal banner offers no free pick', !cardOf('rerun').querySelector('.pick .bar') && pickOf('rerun').includes(en['bn.pick.rerun']) && !cardOf('shsr').querySelector('.pick .bar') && pickOf('shsr').includes(en['bn.pick.rerun']), pickOf('rerun'));
    ok('a first-run seasonal banner still counts the Feh Pass pick, labelled paid', !!cardOf('first').querySelector('.pick .bar') && pickOf('first').includes(en['bn.paid.chip']), pickOf('first'));
    ok('the (4★SHSR) card prints the variant rates', /5★ focus 4%/.test(text(cardOf('shsr').querySelector('.rates'))) && /seasonal special rate 6%/.test(text(cardOf('shsr').querySelector('.rates'))) && !/5★ focus 3%/.test(text(cardOf('shsr').querySelector('.rates'))), text(cardOf('shsr').querySelector('.rates')));
    // 6: the verdict agrees with the free-pick block
    ok('verdict and free-pick block agree when the orbs are enough', pickOf('first').includes('You hold the 155 orbs') && !/more than you hold/.test(verdictOf('first')) && verdictOf('first').includes('Your orbs reach the free pick'), verdictOf('first'));
    ok('the verdict of a re-run says there is no free pick', verdictOf('rerun').includes(en['bn.v.want.rerun']), verdictOf('rerun'));
    fr.view.querySelector('input.orbs').value = '100'; fr.view.querySelector('input.orbs').dispatchEvent(new fr.win.Event('change', { bubbles: true }));
    ok('with too few orbs both say so', /more than you hold/.test(verdictOf('first')) && /short|still takes/.test(pickOf('first')) && !pickOf('first').includes('You hold'), verdictOf('first') + ' / ' + pickOf('first'));
  }
  // 7: on a tie no color is singled out
  {
    const of = (color, nth) => index.filter(x => x.w.startsWith(color))[nth];
    fr = await withBanners('#/summon', fakeBanner([of('Red', 0), of('Red', 1), of('Blue', 0), of('Blue', 1), of('Green', 0)]));
    const card = fr.view.querySelector('[data-banner="test banner"]');
    ok('two colors with the same number of new heroes: none is called the one with most', !card.querySelector('.focus-row.best') && !/of them are/.test(text(card.querySelector('.verdict'))) && !text(card).includes(en['bn.tally.best']), text(card.querySelector('.verdict')));
    fr = await withBanners('#/summon', fakeBanner([of('Red', 0), of('Red', 1), of('Blue', 0), of('Green', 0)]));
    const card2 = fr.view.querySelector('[data-banner="test banner"]');
    ok('one color clearly ahead is named', card2.querySelectorAll('.focus-row.best').length === 1 && /2 of them are red/.test(text(card2.querySelector('.verdict'))), text(card2.querySelector('.verdict')));
    ok('banner end times name UTC and the visitor\'s time', /\d\d:\d\d UTC \(\d\d:\d\d your time\)/.test(text(card2.querySelector('.run'))), text(card2.querySelector('.run')));
    ok('the color has a name next to its orb on every width', [...card2.querySelectorAll('.focus-row .col')].every(c => text(c).length > 2));
  }
  // 9: free and Feh Pass orbs are never one sum
  {
    const at = orbRows.filter(r => r.pass).map(r => r.s - 5).find(t0 => orbRows.some(r => !r.pass && r.s > t0));
    if (at) {
      fr = await open('#/orbs', { storage: {}, query: '&now=' + at });
      const later = orbRows.filter(r => r.s > at), f = later.filter(r => !r.pass).reduce((a, r) => a + r.n, 0), p = later.filter(r => r.pass).reduce((a, r) => a + r.n, 0);
      const head = [...fr.view.querySelectorAll('.panel-head')].find(x => text(x).includes(en['orbs.g.later']));
      ok('"Starting later" shows free (' + f + ') and Feh Pass (' + p + ') orbs apart', head && text(head).includes(f + ' free') && text(head).includes('Feh Pass (paid) ' + p) && !text(head).includes(String(f + p) + ' orbs'), head && text(head));
    }
  }
  {
    fr = await open('#/hero/' + hector.id, { storage: {} });
    ok('the weapon shows might and range', /Might \d+ · Range \d/.test(text(fr.view.querySelector('.skill'))), text(fr.view.querySelector('.skill')));
  }

  // ---------------------------------------------------------------------------------------------------- saved data
  group = 'saved data';
  fr = await open('#/barracks', { storage: { 'hc.box': { [marth.wn]: { m: 3, r: 4 }, 'Gone Hero Renamed': { m: 1, r: 5 } }, 'hc.teams': [{ name: 'Old team', ids: [marth.wn, null, null, null] }], 'hc.orbs': '1e12' } });
  let st = stored();
  ok('the concept keys are moved to hc.v2 under hero numbers', st && st.v === 2 && st.box[marth.id] && st.box[marth.id].m === 3 && st.box[marth.id].r === 4 && st.teams[0].ids[0] === marth.id, localStorage.getItem('hc.v2'));
  ok('a name the data does not know is kept and shown', st && st.unmapped['Gone Hero Renamed'] && text(fr.view.querySelector('#lost')).includes('Gone Hero Renamed'), text(fr.view).slice(0, 200));
  ok('orbs are clamped on the way in', st && st.orbs === 99999, st && st.orbs);
  ok('the old keys are left as a copy', localStorage.getItem('hc.box') !== null);
  ok('the visitor is told', /moved to the new storage format/.test(text(fr.doc.getElementById('notice'))), text(fr.doc.getElementById('notice')));
  fr.view.querySelector('#lost button').click();
  ok('the unknown entry can be removed', !fr.view.querySelector('#lost') && !('Gone Hero Renamed' in stored().unmapped));
  const t0 = performance.now(); await go(fr, '#/summon');
  ok('the summon page is quick with any stored orb count', performance.now() - t0 < 3000 && /= 24999 summons/.test(text(fr.view)), Math.round(performance.now() - t0) + ' ms ' + text(fr.view).slice(0, 150));
  const orbField = fr.view.querySelector('input.orbs');
  setInput(fr, orbField, '1e15');
  ok('the orb field is clamped, also in the field', orbField.value === '99999' && stored().orbs === 99999, orbField.value);
  setInput(fr, orbField, '-3');
  ok('the orb field does not go below 0', orbField.value === '0' && stored().orbs === 0 && /= 0 summons/.test(text(fr.view)), orbField.value);
  setInput(fr, orbField, '21');
  ok('21 orbs are 5 summons', /= 5 summons \(1 full circles/.test(text(fr.view)), text(fr.view).slice(0, 200));
  ok('migration logs no error', fr.errors.length === 0, fr.errors.join(' | '));

  const broken = ['not json', 'null', '[1,2]', '{"box":null}', '{"v":2,"box":{"5":"x"},"teams":{}}', '{"teams":[{"name":"x"}]}', '{"teams":[null,5,{"ids":"abc"}]}', '{"orbs":"1e99"}', '{"v":99,"box":{"5":{"m":50}}}', '""', '{"box":{"999999":{"m":1,"r":5}},"teams":[{"name":"t","ids":[999999,5,5,5]}]}'];
  for (const raw of broken) {
    for (const route of ['#/teams', '#/barracks', '#/summon', '#/heroes']) {
      fr = await open(route, { storage: { 'hc.v2': raw } });
      const fine = fr.ready && fr.view.querySelector('h1') && text(fr.view).length > 30 && fr.errors.length === 0 && !text(fr.view).includes(en['err.load']);
      if (!fine) ok('stored ' + raw + ' on ' + route, false, text(fr.view).slice(0, 80) + ' ' + fr.errors.join('|'));
    }
  }
  ok(broken.length + ' broken stored values leave four working pages each', true);
  fr = await open('#/teams', { storage: { 'hc.teams': '[{"name":"x"}]', 'hc.box': '{"a":1}' } });
  ok('a broken team in the concept keys gives a working Teams page', fr.view.querySelector('h1') && fr.errors.length === 0 && !text(fr.view).includes(en['err.load']), text(fr.view).slice(0, 100) + fr.errors.join('|'));
  fr = await open('#/barracks', { storage: { 'hc.v2': 'not json' } });
  ok('unreadable storage is set aside and said', localStorage.getItem('hc.broken') === 'not json' && /could not be read/.test(text(fr.doc.getElementById('notice'))), text(fr.doc.getElementById('notice')));
  fr = await open('#/barracks', { storage: { 'hc.v2': '{"box":{"999999":{"m":1,"r":5}}}' } });
  ok('a hero number the data does not hold is listed, not hidden', text(fr.view.querySelector('#lost')).includes('999999') && text(fr.view.querySelector('.bigno')) === '0', text(fr.view).slice(0, 200));

  // ---------------------------------------------------------------------------------------------------- import
  group = 'import';
  const give = async (content, name = 'file.json') => {
    const input = fr.view.querySelector('input[type=file]');
    const dt = new fr.win.DataTransfer(); dt.items.add(new fr.win.File([content], name, { type: 'application/json' }));
    input.files = dt.files; input.dispatchEvent(new fr.win.Event('change', { bubbles: true }));
    await sleep(150);
  };
  const toastText = () => text(fr.doc.getElementById('toast'));
  fr = await open('#/barracks', { storage: { 'hc.v2': { v: 2, box: { [marth.id]: { m: 1, r: 5 } }, teams: [{ name: 'Mine', ids: [marth.id, null, null, null] }], orbs: 40 } } });
  for (const [label, content] of [['{"box":null}', '{"box":null}'], ['an empty file', ''], ['text that is not JSON', 'hello'], ['a list', '[1,2,3]'], ['a file over 1 MB', '{"box":{},"x":"' + 'a'.repeat(1100000) + '"}']]) {
    await give(content);
    ok(label + ' is refused with a message and changes nothing', (toastText() === en['box.badfile'] || toastText() === en['box.toobig']) && !fr.view.querySelector('#import-ask') && stored().box[marth.id].m === 1 && fr.view.querySelector('h1'), toastText());
  }
  await give('{"box":{"x":true,"' + index[3].id + '":{"m":"7","r":9}},"teams":{}}');
  ok('a file with odd entries asks first and counts what it skipped', fr.view.querySelector('#import-ask') && /holds 1 heroes/.test(text(fr.view.querySelector('#import-ask'))) && stored().box[index[3].id] === undefined, text(fr.view.querySelector('#import-ask')));
  fr.view.querySelector('#import-ask [data-act=cancel]').click();
  ok('cancel changes nothing', !fr.view.querySelector('#import-ask') && Object.keys(stored().box).length === 1);
  await give(JSON.stringify({ v: 1, box: { [index[4].wn]: { m: 4, r: 5 }, [index[5].wn]: { m: 0, r: 3 } }, teams: [{ name: 'From file', ids: [index[4].wn, index[5].wn] }], orbs: 7 }));
  fr.view.querySelector('#import-ask [data-act=merge]').click(); await sleep(50);
  st = stored();
  ok('"Add" merges a concept-format file by name', st.box[marth.id] && st.box[index[4].id].m === 4 && st.box[index[5].id].r === 3 && st.teams.length === 2 && st.teams[1].ids[1] === index[5].id && st.orbs === 40, localStorage.getItem('hc.v2'));
  await give(JSON.stringify({ app: 'heroes-companion', v: 2, box: { [index[6].id]: { m: 10, r: 5 } }, teams: [], orbs: 12 }));
  fr.view.querySelector('#import-ask [data-act=replace]').click(); await sleep(50);
  st = stored();
  ok('"Replace" replaces and keeps a backup', Object.keys(st.box).join() === String(index[6].id) && st.orbs === 12 && JSON.parse(localStorage.getItem('hc.backup')).box[marth.id], localStorage.getItem('hc.v2'));
  ok('the page shows the loaded barracks', text(fr.view.querySelector('.bigno')) === '1' && text(fr.view).includes(index[6].ti));
  fr = await open('#/barracks', { storage: {} });
  await give(JSON.stringify({ box: { [index[7].id]: { m: 1, r: 5 } }, teams: [{ name: 't', ids: [index[7].id] }] }));
  ok('an empty barracks takes a file without asking', !fr.view.querySelector('#import-ask') && stored().box[index[7].id] && text(fr.view.querySelector('.bigno')) === '1', localStorage.getItem('hc.v2'));
  await go(fr, '#/teams');
  ok('the Teams page works after every import', fr.view.querySelector('h1') && text(fr.view).includes(index[7].n) && fr.errors.length === 0, fr.errors.join('|'));
  ok('import logs no error', fr.errors.length === 0, fr.errors.join(' | '));

  // ---------------------------------------------------------------------------------------------------- undo
  group = 'remove and undo';
  fr = await open('#/barracks', { storage: { 'hc.v2': { v: 2, box: { [marth.id]: { m: 6, r: 4 } }, teams: [{ name: 'A', ids: [null, marth.id, null, null] }] } } });
  fr.view.querySelector('button.star').click();
  ok('removing a hero also empties its team slot', !stored().box[marth.id] && stored().teams[0].ids[1] === null, localStorage.getItem('hc.v2'));
  const undo = fr.doc.querySelector('#toast button'); ok('the message offers Undo', undo && text(undo) === en['undo']);
  if (undo) undo.click();
  ok('Undo puts hero, merges and team slot back', stored().box[marth.id] && stored().box[marth.id].m === 6 && stored().teams[0].ids[1] === marth.id, localStorage.getItem('hc.v2'));

  // ---------------------------------------------------------------------------------------------------- two tabs
  group = 'two tabs';
  const a = await open('#/heroes', { storage: {}, w: 640, h: 500 });
  const b = await open('#/heroes', { storage: null, keep: true, w: 640, h: 500 });
  const markOne = (f2, n) => { f2.view.querySelector('[data-act="edit"]').click(); f2.view.querySelectorAll('button.tile')[n].click(); f2.view.querySelector('[data-act="done"]').click(); };
  markOne(a, 0);
  await sleep(200);
  markOne(b, 1);
  await sleep(200);
  ok('two tabs that each star one hero end with two heroes', Object.keys(stored().box).length === 2, localStorage.getItem('hc.v2'));
  ok('the first tab shows the second tab\'s change', /· 2 in your barracks/.test(text(a.view.querySelector('.countline'))) && a.view.querySelectorAll('a.tile.owned').length === 2, text(a.view.querySelector('.countline')));
  ok('the second tab saw the first tab\'s change', /· 2 in your barracks/.test(text(b.view.querySelector('.countline'))), text(b.view.querySelector('.countline')));
  ok('two tabs log no error', a.errors.length === 0 && b.errors.length === 0, a.errors.concat(b.errors).join(' | '));

  // ---------------------------------------------------------------------------------------------------- blocked storage
  group = 'blocked storage';
  fr = await open('#/heroes', { storage: {}, query: '&block=1' });
  ok('the page works without storage', fr.ready && fr.view.querySelectorAll('a.tile').length > 20);
  ok('and says that nothing is saved', text(fr.doc.getElementById('notice')).includes(en['store.blocked']), text(fr.doc.getElementById('notice')));
  markOne(fr, 0);
  ok('marking still works in the open tab', fr.view.querySelectorAll('a.tile.owned').length === 1 && /· 1 in your barracks/.test(text(fr.view.querySelector('.countline'))));
  await go(fr, '#/barracks');
  ok('the barracks shows the unsaved hero', text(fr.view.querySelector('.bigno')) === '1');
  for (const route of ['#/teams', '#/summon', '#/orbs', '#/hero/' + marth.id]) { await go(fr, route); if (!fr.view.querySelector('h1')) ok(route + ' without storage', false, text(fr.view).slice(0, 80)); }
  ok('blocked storage raises no error', fr.errors.length === 0, fr.errors.join(' | '));

  // ---------------------------------------------------------------------------------------------------- reset from the error card
  group = 'error card';
  fr = await open('#/heroes', { storage: { 'hc.v2': { v: 2, box: { [marth.id]: { m: 1, r: 5 } } } } });
  const rf = fr.win.fetch; fr.win.fetch = (u, o) => /data\/banners/.test(String(u)) ? Promise.reject(new TypeError('offline (test)')) : rf(u, o);
  await go(fr, '#/summon');
  const resetBtn = [...fr.view.querySelectorAll('button')].find(x => text(x) === en['err.reset']);
  ok('the error card offers a reset and a backup file', !!resetBtn && [...fr.view.querySelectorAll('button')].some(x => text(x) === en['box.export']));
  if (resetBtn) { resetBtn.click(); ok('the reset asks once more', text(resetBtn) === en['err.reset.confirm'] && stored().box[marth.id]); fr.win.fetch = rf; resetBtn.click(); await sleep(300); }
  ok('the reset empties the saved data and keeps a backup', localStorage.getItem('hc.v2') === null && JSON.parse(localStorage.getItem('hc.backup')).box[marth.id], localStorage.getItem('hc.v2'));
  frames.replaceChildren();
  for (const k of KEYS) localStorage.removeItem(k);
}

run().catch(e => { results.push({ name: 'harness', ok: false, detail: 'the harness stopped: ' + (e && e.stack || e) }); })
  .finally(() => fetch('/__t/report', { method: 'POST', body: JSON.stringify(results) }));
"""


# ---- static checks -------------------------------------------------------------------------------------------------------
def static_checks():
    """[(name, ok, detail)] for things that need no browser."""
    out = []
    js, texts = {}, {}
    for base, _, names in os.walk(SITE):
        if os.path.join(SITE, 'data') in base: continue
        for n in names:
            p = os.path.join(base, n)
            if n.endswith(('.js', '.html', '.css', '.json')):
                with open(p, encoding='utf-8') as f: texts[os.path.relpath(p, ROOT)] = f.read()
            if n.endswith('.js'): js[os.path.relpath(p, ROOT)] = texts[os.path.relpath(p, ROOT)]
    for name in ('tools/build_data.py', 'tools/test_data.py', 'tools/test_site.py'):
        p = os.path.join(ROOT, *name.split('/'))
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f: texts[name] = f.read()
    code = {n: '\n'.join(l for l in s.split('\n') if not l.lstrip().startswith(('//', '*', '/*'))) for n, s in js.items()}       # comments may name them
    banned = [(n, w) for n, s in code.items() for w in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write') if w in s]
    out.append(('scripts build the page from text nodes only', not banned, str(banned)))
    with open(os.path.join(SITE, 'locales', 'en.json'), encoding='utf-8') as f: en = json.load(f)
    used, missing = set(), []
    for n, s in js.items():
        for fn, key in re.findall(r"\b(tn?)\('([a-zA-Z0-9_.-]+)'[,)]", s):
            keys = [key + '.one', key + '.other'] if fn == 'tn' else [key]
            used.update(keys)
            missing += [(n, k) for k in keys if k not in en]
        for prefix in re.findall(r"\bt\('([a-zA-Z0-9_.-]+\.)' \+", s):
            used.update(k for k in en if k.startswith(prefix))
            if not any(k.startswith(prefix) for k in en): missing.append((n, prefix + '*'))
    out.append(('every text key in the scripts exists in locales/en.json', not missing, str(missing[:8])))
    for prefix, values in (('tag.', 'legendary mythic emblem duo harmonized chosen vista special tempest grail story rearmed attuned aided ascended entwined brave fallen resplendent refresher'),
                           ('avail.', 'story grails legendary mythic emblem seasonal seasonal_sr4 pool34 sr4 pool'), ('summon.tip.', 'new legendary special revival other free'),
                           ('build.mode.', 'all arena assault chain pve aether-defense aether-offense aether other'), ('build.cost.', 'low medium high veryhigh'),
                           ('slot.', 'weapon assist special a b c x seal'), ('nav.', 'home heroes barracks teams summon orbs guide'), ('store.', 'migrated corrupt dropped blocked')):
        lack = [prefix + v for v in values.split() if prefix + v not in en]
        if lack: out.append(('texts for ' + prefix + '*', False, str(lack)))
    leftovers = [n for n, s in texts.items() if n.startswith('site') and re.search(r"LANG\b|de\.json|locales/' \+", s)]
    out.append(('no language switching code is left', not leftovers, str(leftovers)))
    index_html = texts.get(os.path.join('site', 'index.html'), '')
    policy = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', index_html)
    out.append(('index.html carries a content security policy without inline allowances', bool(policy) and "'unsafe-inline'" not in policy.group(1) and "'unsafe-eval'" not in policy.group(1)
                and "script-src 'self'" in policy.group(1) and 'https://static.wikia.nocookie.net' in policy.group(1), policy.group(1) if policy else 'no policy'))
    inline = [n for n, t2 in texts.items() if n.startswith('site') and n.endswith('.html') and re.search(r'\sstyle="|<style|\son[a-z]+="|<script(?![^>]*\ssrc=)', t2)]
    inline += [n for n, t2 in code.items() if re.search(r"setAttribute\('style'|\.cssText|style: '", t2)]
    out.append(('no inline style or script, which the policy would block', not inline, str(inline)))
    stray = [n for b2, _, ns in os.walk(SITE) for n in ns if re.search(r'_(Face|BtlFace|Mini_Unit)', n)]
    out.append(('no hero artwork file is stored in site/', not stray, str(stray)))
    try:
        sys.path.insert(0, HERE)
        import build_site
        behind = []
        for p2, t2 in build_site.plan().items():
            with open(p2, encoding='utf-8') as f2:
                if f2.read() != t2: behind.append(os.path.relpath(p2, ROOT))
    except Exception as e:
        behind = ['build_site failed: %s' % e]
    out.append(('site/content and the guide texts are in step with content/ (tools/build_site.py)', not behind, str(behind)))
    out.append(('the old single script is gone and index.html loads one module', not os.path.exists(os.path.join(SITE, 'app.js')) and texts.get(os.path.join('site', 'index.html'), '').count('type="module"') == 1, ''))
    long_files = [(n, s.count('\n')) for n, s in js.items() if s.count('\n') > 400]
    out.append(('no script over 400 lines', not long_files, str(long_files)))
    private = [n for n, s in texts.items() if re.search(r'[A-Za-z]:[\\/]+Users[\\/]|/Users/|/home/[a-z]', s) and not n.endswith('test_site.py')]
    out.append(('no user folder path in site/ or the tools', not private, str(private)))
    wrong = [n for n, s in texts.items() if n.startswith('site') and 'CC BY-SA' in s]
    out.append(('the wrong licence name appears nowhere in site/', not wrong, str(wrong)))
    return out


# ---- server ----------------------------------------------------------------------------------------------------------------
PIXEL = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
ART_HOST = 'static.wikia.nocookie.net'

class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'                           # keep-alive: far fewer connections than one per file
    report = None
    got = threading.Event()
    holds = {}                                              # screenshot id -> [event, ok, why]
    lock = threading.Lock()

    @classmethod
    def hold(cls, key):
        with cls.lock: return cls.holds.setdefault(key, [threading.Event(), None, 'the page never reported'])

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _send(self, body, ctype):
        data = body.encode('utf-8')
        self.send_response(200); self.send_header('Content-Type', ctype + '; charset=utf-8'); self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ('/', '/index.html') and 't=1' in urllib.parse.urlsplit(self.path).query:   # the real page with the error hook in front of everything
            with open(os.path.join(SITE, 'index.html'), encoding='utf-8') as f: page = f.read()
            return self._send(page.replace('<head>', '<head><script src="/__t/hook.js"></script>', 1), 'text/html')
        if path == '/__t/hook.js': return self._send(HOOK_JS, 'text/javascript')
        if path == '/__t/harness.html': return self._send(HARNESS_HTML, 'text/html')
        if path == '/__t/harness.js': return self._send(HARNESS_JS, 'text/javascript')
        if path == '/__t/frame.html': return self._send(FRAME_HTML, 'text/html')
        if path == '/__t/hold':                             # answered only when the framed page says it is drawn
            self.hold(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id', [''])[0])[0].wait(60)
            self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers(); return
        if path == '/__t/release':
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            h = self.hold(q.get('id', [''])[0]); h[1] = q.get('ok', ['0'])[0] == '1'; h[2] = q.get('why', [''])[0]; h[0].set()
            self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers(); return
        if path.startswith('/__t/cdn/'):                     # stands in for the wiki's image host: face icons exist, nothing else does
            if 'Face_FC' not in path: self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
            self.send_response(200); self.send_header('Content-Type', 'image/png'); self.send_header('Content-Length', str(len(PIXEL))); self.end_headers(); self.wfile.write(PIXEL); return
        if path == '/favicon.ico': self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers(); return
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n)
        if urllib.parse.urlsplit(self.path).path == '/__t/report':
            try: Handler.report = json.loads(body.decode('utf-8'))
            except ValueError: Handler.report = [{'name': 'report', 'ok': False, 'detail': 'unreadable report'}]
            Handler.got.set()
        self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers()


def find_chrome():
    for p in CHROME:
        if p and os.path.exists(p): return p
    return None

def chrome_args(chrome, profile, *more):
    return [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
            '--disable-background-networking', '--disable-sync', '--user-data-dir=' + profile, '--enable-logging=stderr', '--log-level=0', *more]

CONSOLE = re.compile(r':CONSOLE[:(]\d+\)?\]\s*(.*)')

def console_errors(stderr_text):
    """What the page wrote to the console, from Chrome's log. Chrome logs every level alike, and the site writes
    nothing to the console when all is well, so any message counts as an error."""
    out = []
    for line in stderr_text.splitlines():
        m = CONSOLE.search(line)
        if m and 'favicon' not in line: out.append(m.group(1).strip()[:300])
    return out

def run_harness(chrome, base, tmp, timeout=420):
    profile = os.path.join(tmp, 'harness-profile')
    log = os.path.join(tmp, 'harness.log')
    Handler.report = None; Handler.got.clear()
    with open(log, 'wb') as err:
        p = subprocess.Popen(chrome_args(chrome, profile, '--window-size=1400,1000', base + '/__t/harness.html'), stdout=subprocess.DEVNULL, stderr=err)
        try:
            Handler.got.wait(timeout)
        finally:
            p.terminate()
            try: p.wait(15)
            except subprocess.TimeoutExpired: p.kill()
    if Handler.report is None:
        with open(log, encoding='utf-8', errors='replace') as f: tail = f.read()[-1500:]
        return [{'name': 'harness', 'ok': False, 'detail': 'no report within %d s; end of the Chrome log: %s' % (timeout, tail)}]
    return Handler.report

def shot_list(base, sample):
    """(name, url, window width, window height, id). Every shot goes through an iframe of the wanted width: a headless
    Chrome window on Windows does not go below about 500 px, and the frame page tells us when the route is drawn."""
    hero, built = sample
    routes = [('home', '#/home', 2300), ('heroes', '#/heroes', 1700), ('heroes-mark', '#/heroes/mark', 1500), ('hero', '#/hero/%d' % hero, 2300), ('hero-builds', '#/hero/%d' % built, 2600),
              ('summon', '#/summon', 3000), ('orbs', '#/orbs', 2300), ('barracks', '#/barracks', 1500), ('teams', '#/teams', 1200),
              ('guide-start', '#/guide/start', 1500), ('guide-summon', '#/guide/summon', 2600), ('guide-meta', '#/guide/meta', 2600), ('guide-about', '#/guide/about', 1600),
              ('unknown-hero', '#/hero/9999999', 900), ('unknown-page', '#/nosuchpage', 900)]
    def seed(art=True):
        return json.dumps({'v': 2, 'box': {str(i): {'m': i % 11, 'r': 5 - i % 3} for i in (hero, built, 21, 165, 191, 1400, 1420, 1428, 1431)},
                           'teams': [{'name': 'Arena', 'ids': [hero, built, 191, None]}], 'orbs': 137, 'prefs': {'fehPass': False, 'art': art}}, separators=(',', ':'))
    out = []
    def add(name, w, h, r, s='', q=''):
        url = base + '/__t/frame.html?' + urllib.parse.urlencode(dict({'id': name, 'w': w, 'h': h, 'r': r, 'q': q}, **({'seed': s} if s else {})))
        out.append((name, url, max(w, 600), h))
    for n, r, h in routes: add('desktop-' + n, 1280, h, r)
    for n, r, h in routes: add('phone420-' + n, 420, int(h * 1.5) if h > 1000 else h, r)
    for n, r, h in (routes[0], routes[1], routes[5], routes[7], routes[8]):
        add('desktop-own-' + n, 1280, h, r, seed())
        add('phone420-own-' + n, 420, int(h * 1.5), r, seed())
    add('desktop-home-reduced-motion', 1280, 1100, '#/home', q='&rm=1')
    add('phone420-home-reduced-motion', 420, 1300, '#/home', q='&rm=1')
    for n, r, h in (routes[0], routes[1], routes[3]):
        add('desktop-noart-' + n, 1280, min(h, 1500), r, seed(False))
        add('phone420-noart-' + n, 420, min(h, 1500), r, seed(False))
    add('phone360-home', 360, 3300, '#/home')
    add('phone360-summon', 360, 3600, '#/summon')
    return out

def take_shot(chrome, tmp, folder, item):
    name, url, w, h = item
    png = os.path.join(folder, name + '.png')
    errors, art = [], []
    for attempt in (1, 2):                                  # Chrome now and then writes no file at all: one more try
        profile = tempfile.mkdtemp(prefix='p-', dir=tmp)
        if os.path.exists(png): os.remove(png)
        with Handler.lock: Handler.holds.pop(name, None)
        try:
            r = subprocess.run(chrome_args(chrome, profile, '--window-size=%d,%d' % (w, h), '--screenshot=' + png, url),
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
            errors = console_errors(r.stderr.decode('utf-8', 'replace'))
            art = [e for e in errors if ART_HOST in e]; errors = [e for e in errors if ART_HOST not in e]
        except subprocess.TimeoutExpired:
            errors = ['Chrome did not finish within 120 s']
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        held = Handler.hold(name)
        if held[1] is not True: errors.append('the page was not drawn: ' + str(held[2]))
        if not os.path.exists(png) or os.path.getsize(png) < 4000: errors.append('no usable screenshot was written')
        if not errors: break
    return name, errors, art


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--no-shots', action='store_true', help='skip the screenshots')
    ap.add_argument('--shots', default=SHOTS, help='folder for the screenshots')
    ap.add_argument('--verbose', action='store_true', help='also print the checks that passed')
    a = ap.parse_args(argv)
    failed, total = [], 0
    def note(name, ok, detail=''):
        nonlocal total
        total += 1
        if ok and a.verbose: print('ok    ' + name)
        if not ok: failed.append(name); print('FAIL  %s%s' % (name, ('\n      ' + str(detail)[:700]) if detail else ''))

    for name, ok, detail in static_checks(): note('static: ' + name, ok, detail)
    chrome = find_chrome()
    if not chrome:
        print('FAIL  Chrome was not found (set HC_CHROME to its path)'); return 1
    if not os.path.exists(os.path.join(SITE, 'data', 'manifest.json')):
        print('FAIL  site/data/manifest.json is missing: run tools/build_data.py first'); return 1

    http.server.ThreadingHTTPServer.request_queue_size = 128   # four Chromes ask at once
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    base = 'http://127.0.0.1:%d' % server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    tmp = tempfile.mkdtemp(prefix='hc-test-')
    shots = art_misses = 0
    try:
        print('server on %s, Chrome harness running ...' % base, flush=True)
        t0 = time.time()
        for r in run_harness(chrome, base, tmp): note(r.get('name', '?'), r.get('ok'), r.get('detail', ''))
        print('harness done in %.0f s' % (time.time() - t0), flush=True)
        if not a.no_shots:
            folder = os.path.abspath(a.shots); os.makedirs(folder, exist_ok=True)
            with open(os.path.join(SITE, 'data', 'heroes.json'), encoding='utf-8') as f: heroes = json.load(f)['heroes']
            marth = next((x['id'] for x in heroes if x['wn'] == 'Marth Altean Prince'), heroes[-1]['id'])
            built = next((x['id'] for x in heroes if (x.get('nb') or 0) > 3), heroes[0]['id'])
            items = shot_list(base, (marth, built))
            with concurrent.futures.ThreadPoolExecutor(3) as pool:
                for name, errors, art in pool.map(lambda it: take_shot(chrome, tmp, folder, it), items):
                    shots += 1; art_misses += len(art)
                    note('screenshot ' + name + ': no console error', not errors, ' | '.join(errors))
            print('%d screenshots in %s; %d console message(s) about the image host (artwork that did not load shows the fallback)' % (shots, os.path.relpath(folder, ROOT), art_misses), flush=True)
    finally:
        server.shutdown(); server.server_close(); thread.join(5)
        shutil.rmtree(tmp, ignore_errors=True)
        print('server stopped', flush=True)
    print('test_site: %d checks, %d failed%s' % (total, len(failed), '' if a.no_shots else ', %d screenshots' % shots))
    return 1 if failed else 0

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
