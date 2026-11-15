// @ts-check
// Guide: written advice, kept in locales/en.json as guide.<section>.<n> (merged from content/guide.en.json), plus the
// hand-written Picks on the "Strong heroes" tab. Picks name their sources and their date; no rating is copied.
import { h, put } from '../dom.js';
import { t, series } from '../i18n.js';
import { D, need } from '../data.js';
import { fmtDate, now } from '../time.js';
import { face, mv, tile, wb } from '../art.js';
import { needContent, monthYear, picksStale, sourceList } from '../content.js';
import { enter } from '../motion.js';
import { heroLink, pageHead, panel, prose } from '../shared.js';

/** @typedef {import('../data.js').Hero} Hero */

const GUIDE = ['start', 'summon', 'orbs', 'spend', 'meta', 'about'];
/** @param {string} section */
const sectionOf = section => GUIDE.includes(section) ? section : 'start';

/** @param {any} picks picks.json */
function picksPanel(picks) {
  const when = monthYear(picks.as_of);
  const text = picks.page_text || {};
  /** @param {string} s */
  const fill = s => String(s || '').replace('{month} {year}', when);
  return panel(fill(text.heading) || t('picks.title'), [
    h('p', {}, text.sub || ''),
    picksStale(picks, now()) ? h('p', { class: 'paid' }, h('b', {}, t('picks.stale') + ' '), fill(text.stale)) : null,
    h('ul', { class: 'picks' }, (picks.picks || []).map((/** @type {any} */ p) => {
      const hero = D.byWn.get(p.id);
      return h('li', {}, hero ? h('a', { class: 'mini', href: '#/hero/' + hero.id, 'aria-label': hero.n + ': ' + hero.ti }, face(hero)) : null,
        h('div', {}, h('b', {}, hero ? [heroLink(hero, true), ' ', wb(hero), ' ', mv(hero)] : p.name), ' ', h('span', { class: 'chip gold' }, t('car.pick')), p.type ? [' ', h('span', { class: 'chip' }, p.type)] : null,
          h('p', { class: 'dim small' }, p.role, ' · ', t('picks.released', { date: fmtDate(p.released) })),
          h('p', {}, p.why),
          h('p', { class: 'small' }, (p.sources || []).filter((/** @type {any} */ s) => /^https?:\/\//.test(String(s.url || ''))).map((/** @type {any} */ s) => [h('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.title), ' (' + fmtDate(s.date) + ') '])) ));
    })),
    h('details', { class: 'srcfold' }, h('summary', {}, t('picks.method')), h('p', {}, picks.method), h('p', {}, picks.limits), sourceList(picks.shared_sources, h)),
    Array.isArray(picks.shared_sources) && picks.shared_sources[0] ? h('p', { class: 'small gap' }, h('a', { href: picks.shared_sources[0].url, target: '_blank', rel: 'noopener' }, (text.link || t('meta.game8')) + ' ↗')) : null], { id: 'picks' });
}

export const page = {
  nav: 'home',
  /** @param {string} section */
  title: section => t('guide.title') + ': ' + t('guide.tab.' + sectionOf(section)),
  /** @param {HTMLElement} el @param {string} section */
  async render(el, section) {
    const cur = sectionOf(section);
    const meta = cur === 'meta' ? await need('meta').catch(() => null) : null;
    const picks = cur === 'meta' ? await needContent('picks').catch(() => null) : null;
    /** @param {any} id */
    const hero = id => D.byId.get(Number(id));
    const newest = meta && Array.isArray(meta.newest) ? /** @type {Hero[]} */ (meta.newest.map(hero).filter(Boolean)).slice(0, 12) : [];
    put(el, pageHead(t('guide.title'), t('guide.sub')),
      h('nav', { class: 'chiprow guidetabs', 'aria-label': t('guide.title') }, GUIDE.map(g => h('a', { class: 'fchip text' + (g === cur ? ' on' : ''), href: '#/guide/' + g, 'aria-current': g === cur ? 'page' : null }, t('guide.tab.' + g)))),
      h('section', { class: 'panel parchment prose rise' }, h('div', { class: 'panel-body' }, h('h2', {}, t('guide.tab.' + cur)), prose(series('guide.' + cur)),
        cur === 'spend' ? h('p', {}, h('a', { href: '#/orbs' }, t('cur.link') + ' ›')) : null,
        cur === 'about' ? [h('h3', { class: 'sub' }, t('about.art.title')), h('p', {}, t('about.art.1')), h('p', {}, t('about.art.2')), h('p', {}, t('about.art.3')), h('p', {}, h('a', { href: 'https://github.com/MkUltra1984/heroes-companion/issues', rel: 'noopener' }, t('about.art.issues'))),
          h('h3', { class: 'sub' }, t('about.data.title')), h('p', {}, t('about.data.1', { licence: D.manifest.source.licence }), ' ', h('a', { href: D.manifest.source.url, target: '_blank', rel: 'noopener' }, D.manifest.source.name), ' · ',
            h('a', { href: D.manifest.source.licenceUrl, target: '_blank', rel: 'license noopener' }, D.manifest.source.licence)),
          h('p', {}, t('about.fonts'))] : null)),
      cur === 'meta' ? h('div', { class: 'stack gapt' },
        picks ? picksPanel(picks) : h('p', { class: 'dim' }, t('picks.failed')),
        newest.length ? panel(t('meta.newest'), [h('p', { class: 'dim small note' }, t('meta.newest.text')), h('div', { class: 'strip' }, newest.map((x, i) => tile(x, { i })))]) : null,
        h('p', { class: 'small' }, h('a', { href: 'https://game8.co/games/fire-emblem-heroes/archives/242267', target: '_blank', rel: 'noopener' }, t('meta.game8') + ' ↗'))) : null);
    enter(el);
  },
};
