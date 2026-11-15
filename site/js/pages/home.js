// @ts-check
// Home: the hero carousel, the visitor's numbers, the banners that matter now, open quest orbs and the newest heroes.
import { h, put } from '../dom.js';
import { t, tn } from '../i18n.js';
import { D, need } from '../data.js';
import { store } from '../store.js';
import { fmtDate, fmtDayTime, fmtShort, gameDay, isLive, now } from '../time.js';
import { orb, tile } from '../art.js';
import { needContent, monthYear, picksStale } from '../content.js';
import { MINOR, bannerTeaser, focusOf, liveBanners, summonsFor } from '../banners.js';
import { orderKey } from '../standing.js';
import { carousel } from '../carousel.js';
import { countUp } from '../motion.js';
import { saveBackup } from '../router.js';
import { endText, panel } from '../shared.js';

/** @typedef {import('../data.js').Hero} Hero */
const ON_BANNER_MAX = 16;

/**
 * The carousel's heroes: the hand-written Picks first (newest first, as the list has them), then focus heroes of
 * banners that run now, newest release first and then by their stats within their class. No rating is shown or implied.
 * @param {any} picks picks.json or null @param {any[]} live running banners @param {number} at
 */
function spotlight(picks, live, at) {
  /** @type {import('../carousel.js').Item[]} */ const items = [];
  /** hero id -> the running banner that features the hero and ends last @type {Map<number, any>} */
  const onBanner = new Map();
  for (const b of live) if (b.k !== 'free') for (const x of focusOf(b)) { const cur = onBanner.get(x.id); if (!cur || (MINOR.includes(cur.k) && !MINOR.includes(b.k))) onBanner.set(x.id, b); }
  /** @param {any} b */
  const bannerLine = b => t('car.banner.info', { name: b.n, end: endText(b.e) });
  const seen = new Set();
  const stale = picks ? picksStale(picks, at) : false;
  for (const p of picks && Array.isArray(picks.picks) ? picks.picks : []) {
    const hero = D.byWn.get(p.id);
    if (!hero || seen.has(hero.id)) continue;
    seen.add(hero.id);
    const b = onBanner.get(hero.id);
    const src = [...(picks.shared_sources || []), ...(p.sources || [])].filter(s => /^https?:\/\//.test(String(s.url || '')));
    items.push({ hero, labels: [{ text: t('car.pick'), cls: 'pick' }, ...(b ? [{ text: t('car.banner'), cls: 'now' }] : [])],
      info: () => [h('p', { class: 'car-kind' }, h('span', { class: 'car-label pick' }, t('car.pick')), ' ', t('car.pick.info', { date: fmtDate(picks.as_of) }),
        stale ? [' ', h('span', { class: 'chip sample' }, t('car.pick.stale'))] : null),
      h('p', { class: 'car-name' }, h('a', { href: '#/hero/' + hero.id }, hero.n + ': ' + hero.ti), p.role ? h('span', { class: 'dim' }, ' · ' + p.role) : null),
      h('p', {}, p.why),
      b ? h('p', {}, h('span', { class: 'car-label now' }, t('car.banner')), ' ', bannerLine(b)) : null,
      h('p', { class: 'car-src dim' }, t('car.pick.sources') + ' ', src.map((s, i) => [i ? ' · ' : '', h('a', { href: s.url, target: '_blank', rel: 'noopener' }, String(s.title).split(',')[0]), ' (' + fmtDate(s.date) + ')']))] });
  }
  const rest = [...onBanner.keys()].filter(id => !seen.has(id)).map(id => /** @type {Hero} */ (D.byId.get(id)));
  const keys = new Map(rest.map(x => [x.id, orderKey(x)]));
  rest.sort((a, b) => { const x = /** @type {any[]} */ (keys.get(a.id)), y = /** @type {any[]} */ (keys.get(b.id)); return (x[0] < y[0] ? 1 : x[0] > y[0] ? -1 : 0) || y[1] - x[1] || y[2] - x[2]; });
  for (const hero of rest.slice(0, ON_BANNER_MAX)) {
    const b = onBanner.get(hero.id);
    items.push({ hero, labels: [{ text: t('car.banner'), cls: 'now' }],
      info: () => [h('p', { class: 'car-kind' }, h('span', { class: 'car-label now' }, t('car.banner')), ' ', bannerLine(b)),
        h('p', { class: 'car-name' }, h('a', { href: '#/hero/' + hero.id }, hero.n + ': ' + hero.ti), h('span', { class: 'dim' }, ' · ' + hero.w + ', ' + hero.m)),
        h('p', {}, t('car.banner.why', { date: fmtDate(hero.r) })),
        h('p', { class: 'car-src dim' }, t('car.banner.order'))] });
  }
  return items;
}

export const page = {
  title: () => t('home.title'),
  /** @param {HTMLElement} el */
  async render(el) {
    // every extra file may fail on its own: Home then shows what it has
    const [bannersFile, orbsFile, picks, rules] = await Promise.all([need('banners').catch(() => null), need('orbs').catch(() => null),
      needContent('picks').catch(() => null), needContent('summon_rules').catch(() => null)]);
    const at = now();
    const live = bannersFile && Array.isArray(bannersFile.banners) ? liveBanners(bannersFile.banners, at) : [];
    const main = live.filter(b => !MINOR.includes(b.k));
    const items = spotlight(picks, live, at);
    const own = store.count(), orbs = store.state.orbs, teams = store.state.teams.length;

    /** @type {any[]} */
    const rows = orbsFile && orbsFile.questsKnown ? (orbsFile.groups || []).flatMap((/** @type {any} */ g) => g.rows || []).filter((/** @type {any} */ r) => isLive(r, at)) : [];
    const free = rows.filter(r => !r.pass).sort((a, b) => a.e - b.e), paid = rows.filter(r => r.pass);
    /** @param {any[]} list */
    const sum = list => list.reduce((a, r) => a + r.n, 0);
    /** @param {any} r */
    const until = r => gameDay(r.e) === gameDay(at) ? h('small', { class: 'today' }, t('home.orbs.today')) : h('small', {}, t('orbs.until', { date: fmtDayTime(r.e + 1) }));
    const kpi = (/** @type {string} */ href, /** @type {any} */ ico, /** @type {number} */ n, /** @type {string} */ label, /** @type {string} */ extra, /** @type {number} */ i) => {
      const b = h('b', { class: 'num' }, n);
      countUp(b, n, 140 + i * 40);
      return h('a', { class: 'plate kpi', href, style: { '--i': i } }, ico, h('div', {}, b, h('span', {}, label, ' ', h('em', {}, extra))));
    };
    const newest = D.heroes.slice().sort((a, b) => a.r < b.r ? 1 : a.r > b.r ? -1 : b.id - a.id).slice(0, 12);
    const newestDate = newest.length ? newest[0].r : '';

    put(el,
      h('h1', { class: 'plate-title' }, t(own ? 'home.welcome.back' : 'home.welcome')),
      items.length ? h('section', { class: 'panel framed spot rise' }, h('span', { class: 'corner tl' }), h('span', { class: 'corner tr' }), h('span', { class: 'corner bl' }), h('span', { class: 'corner br' }),
        h('div', { class: 'panel-head' }, h('h2', {}, t('car.title')), h('a', { class: 'more', href: '#/guide/meta' }, t('car.more') + ' ›')),
        h('p', { class: 'spot-sub' }, t('car.sub', { picks: picks ? monthYear(picks.as_of) : '' })),
        carousel(items, { label: t('car.title') })) : null,
      h('div', { class: 'kpis pops' },
        kpi('#/barracks', h('img', { class: 'ico', src: 'art/nav-heroes.webp', alt: '', width: 48, height: 48 }), own, t('home.kpi.heroes'), t('home.kpi.heroes.of', { pct: Math.round(own / Math.max(1, D.heroes.length) * 100), total: D.heroes.length }), 0),
        kpi('#/summon', h('span', { class: 'ico orb' }), orbs, t('home.kpi.orbs'), tn('home.kpi.summons', summonsFor(orbs)), 1),
        kpi('#/teams', h('img', { class: 'ico', src: 'art/nav-barracks.webp', alt: '', width: 48, height: 48 }), teams, t('home.kpi.teams'), t('home.kpi.teams.saved'), 2)),
      own ? null : h('div', { class: 'parch-note start' }, h('b', {}, t('home.start.title')), ' ', t('home.start.text'), ' ', h('a', { href: '#/heroes' }, t('home.start.link')), ' · ', h('a', { href: '#/guide/start' }, t('home.start.guide'))),
      h('div', { class: 'home-grid' },
        panel(t('home.banners'), !bannersFile ? h('p', { class: 'dim' }, t('home.failed'))
          : main.length ? h('div', { class: 'stack' }, main.slice(0, 2).map((b, i) => bannerTeaser(b, rules, i)))
          : h('p', { class: 'dim' }, t('summon.none', { date: fmtDate(D.manifest.dataFrom) })),
        { more: h('a', { class: 'more', href: '#/summon' }, tn('home.banners.all', live.length) + ' ›'), i: 0 }),
        h('div', { class: 'stack' },
          panel(t('home.orbs'), !orbsFile ? h('p', { class: 'dim' }, t('home.failed')) : !orbsFile.questsKnown ? h('p', { class: 'dim' }, t('orbs.unknown')) : [
            free.length ? h('ul', { class: 'checks' }, free.slice(0, 4).map(r => h('li', { class: 'check' }, h('span', { class: 'what' }, h('b', {}, r.name), until(r)), h('span', { class: 'gain num' }, '+' + r.n, orb('', 22)))))
              : h('p', { class: 'dim' }, t('home.orbs.none')),
            free.length > 4 ? h('p', { class: 'dim small' }, tn('home.orbs.more', free.length - 4)) : null,
            paid.length ? h('p', { class: 'paid' }, h('b', {}, t('home.orbs.paid') + ' '), t('home.orbs.paid.text', { n: sum(paid), date: fmtShort(Math.max(...paid.map(r => r.e))) })) : null,
            h('p', { class: 'gap' }, h('a', { class: 'btn small', href: '#/orbs' }, t('home.orbs.all') + ' ›'))],
          { more: orbsFile && orbsFile.questsKnown ? h('span', { class: 'count num' }, t('home.orbs.open', { n: sum(free) })) : null, i: 1 }),
          h('section', { class: 'panel parchment rise', style: { '--i': 2 } }, h('div', { class: 'panel-body' }, h('p', { class: 'parch-title' }, t('home.backup.title')),
            h('p', {}, t('home.backup.text'), ' ', h('button', { type: 'button', class: 'link', onclick: saveBackup }, t('home.backup.link')))))) ),
      panel(t('home.newest'), [h('div', { class: 'strip' }, newest.map((x, i) => tile(x, { i, isNew: x.r === newestDate && !store.has(x.id) }))),
        h('p', { class: 'dim small gap' }, t('home.newest.note', { date: fmtDate(D.manifest.newestRelease) }))],
      { more: h('a', { class: 'more', href: '#/heroes' }, t('home.newest.all') + ' ›'), i: 3, cls: 'gapt' }),
      h('section', { class: 'panel rise gapt guidecard', style: { '--i': 4 } }, h('div', { class: 'panel-body' },
        h('img', { src: 'art/emblem.webp', alt: '', width: 56, height: 56 }),
        h('div', {}, h('h2', {}, t('home.guide.title')), h('p', { class: 'dim' }, t('home.guide.text'))),
        h('a', { class: 'btn primary', href: '#/guide' }, t('home.guide.link')))));
  },
};
