// @ts-check
// Barracks: the heroes the visitor owns, and the backup file. Teams live here too (second tab).
import { h, put, toast } from '../dom.js';
import { t, tn } from '../i18n.js';
import { D } from '../data.js';
import { store, LIMITS } from '../store.js';
import { saveBackup } from '../router.js';
import { face, mv, wb } from '../art.js';
import { enter } from '../motion.js';
import { emptyState, heroLink, mergeInput, ownStar, pageHead, panel, raritySelect } from '../shared.js';

/** @typedef {import('../data.js').Hero} Hero */

/** The two tabs of the Barracks destination. @param {'barracks'|'teams'} cur */
export const barracksTabs = cur => h('nav', { class: 'seg tabs2', 'aria-label': t('box.tabs') },
  h('a', { href: '#/barracks', 'aria-current': cur === 'barracks' ? 'page' : null }, t('box.tab.heroes'), ' ', h('span', { class: 'num' }, store.count())),
  h('a', { href: '#/teams', 'aria-current': cur === 'teams' ? 'page' : null }, t('nav.teams'), ' ', h('span', { class: 'num' }, store.state.teams.length)));

export const page = {
  title: () => t('box.title'),
  /** @param {HTMLElement} el */
  render(el) {
    /** a checked backup file waiting for the visitor's decision @type {any} */
    let pending = null;

    /** @param {'replace'|'merge'} mode */
    const apply = mode => {
      const ok = store.applyImport(pending.state, mode);
      pending = null;
      toast(t(ok ? 'box.imported' : 'store.blocked.short'));
      draw();
    };
    /** @param {any} e */
    const onFile = async e => {
      const file = e.target.files && e.target.files[0];
      e.target.value = '';
      if (!file) return;
      let r;
      try { r = file.size > LIMITS.fileBytes ? { ok: false, error: 'toobig' } : store.parseImport(await file.text()); }
      catch { r = { ok: false, error: 'badfile' }; }
      if (!r.ok) { pending = null; toast(t(r.error === 'toobig' ? 'box.toobig' : 'box.badfile')); draw(); return; }
      pending = r;
      if (!store.count() && !store.state.teams.length) apply('replace'); else draw();
    };

    const draw = () => {
      const owned = D.heroes.filter(x => store.has(x.id)).sort((a, b) => a.n.localeCompare(b.n));
      /** entries whose hero the data does not hold: ids from newer data, or names from before a rename */
      const lost = [...store.ids().filter(id => !D.byId.has(id)).map(String), ...Object.keys(store.state.unmapped)];
      /** @param {(x: Hero) => string} fn @returns {[string, number][]} */
      const count = fn => { /** @type {Record<string, number>} */ const m = {}; for (const x of owned) { const k = fn(x); m[k] = (m[k] || 0) + 1; } return Object.entries(m).sort((a, b) => b[1] - a[1]); };
      put(el, pageHead(t('box.title'), t('box.sub')), barracksTabs('barracks'),
        h('div', { class: 'cols-2 gapt' },
          h('section', { class: 'panel rise' }, h('div', { class: 'panel-body boxsum' }, h('img', { src: 'art/nav-barracks.webp', alt: '', width: 56, height: 56 }),
            h('div', {}, h('div', { class: 'bigno num' }, owned.length), h('p', { class: 'dim' }, t('box.of', { total: D.heroes.length })),
              h('div', { class: 'chips gap' }, count(x => x.c).map(([k, n]) => h('span', { class: 'chip c-' + k }, t('color.' + k) + ' ' + n)), count(x => x.m).map(([k, n]) => h('span', { class: 'chip' }, k + ' ' + n))),
              h('p', { class: 'gap' }, h('a', { class: 'btn primary', href: '#/heroes/mark' }, t('mark.start')))))),
          panel(t('box.backup'), [h('p', { class: 'dim small' }, t('box.backup.text')),
            h('div', { class: 'chips gap' },
              h('button', { class: 'btn', type: 'button', onclick: saveBackup }, t('box.export')),
              h('label', { class: 'btn filebtn' }, t('box.import'), h('input', { type: 'file', accept: 'application/json,.json', class: 'sr', onchange: onFile })))], { i: 1 })),
        pending ? h('section', { class: 'panel gapt', role: 'alert', id: 'import-ask' }, h('div', { class: 'panel-body' },
          h('h2', { class: 'sub' }, t('box.import.title')),
          h('p', {}, t('box.import.found', { heroes: pending.heroes, teams: pending.teams })),
          pending.unknown || pending.dropped ? h('p', { class: 'dim small' }, t('box.import.skipped', { unknown: pending.unknown, dropped: pending.dropped })) : null,
          h('div', { class: 'chips gap' },
            h('button', { class: 'btn primary', type: 'button', 'data-act': 'merge', onclick: () => apply('merge') }, t('box.import.merge')),
            h('button', { class: 'btn', type: 'button', 'data-act': 'replace', onclick: () => apply('replace') }, t('box.import.replace', { n: store.count() })),
            h('button', { class: 'btn', type: 'button', 'data-act': 'cancel', onclick: () => { pending = null; draw(); } }, t('cancel'))))) : null,
        lost.length ? h('section', { class: 'panel gapt', id: 'lost' }, h('div', { class: 'panel-body' }, h('h2', { class: 'sub' }, tn('box.lost', lost.length)), h('p', { class: 'dim small' }, t('box.lost.text')),
          h('ul', { class: 'rows' }, lost.map(key => h('li', {}, h('span', { class: 'grow' }, /^\d+$/.test(key) ? t('box.lost.id', { id: key }) : key),
            h('button', { class: 'btn small', type: 'button', onclick: () => { store.forget(key); draw(); } }, t('teams.remove'))))))) : null,
        owned.length ? h('section', { class: 'panel gapt' }, h('div', { class: 'tablewrap' }, h('table', { class: 'list' }, h('caption', { class: 'sr' }, t('box.title')),
          h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, h('span', { class: 'sr' }, t('col.own'))), h('th', { scope: 'col' }, t('col.name')), h('th', { scope: 'col', class: 'hide-s' }, t('col.weapon')),
            h('th', { scope: 'col', class: 'hide-s' }, t('col.move')), h('th', { scope: 'col' }, t('box.rarity')), h('th', { scope: 'col' }, t('box.merges')))),
          h('tbody', {}, owned.map(hero => {
            const e = store.entry(hero.id) || { m: 0, r: 5 };
            return h('tr', {},
              h('td', {}, ownStar(hero, draw)), h('td', {}, h('div', { class: 'hname' }, h('span', { class: 'mini' }, face(hero)), h('span', {}, h('b', {}, heroLink(hero)), h('small', {}, hero.ti)))),
              h('td', { class: 'hide-s' }, h('span', { class: 'cellbadge' }, wb(hero), hero.wt)), h('td', { class: 'hide-s' }, h('span', { class: 'cellbadge' }, mv(hero), hero.m)),
              h('td', {}, raritySelect(e.r, r => store.setRarity(hero.id, r), t('box.rarity'))),
              h('td', {}, mergeInput(e.m, v => store.setMerges(hero.id, v), t('box.merges'))));
          })))))
          : h('section', { class: 'panel gapt' }, emptyState(t('box.empty.title'), t('box.empty'), h('a', { class: 'btn primary', href: '#/heroes/mark' }, t('mark.start')))));
      enter(el);
    };
    draw();
  },
};
