// @ts-check
// Heroes: the grid of all heroes with search and filters, and the marking mode in which every tap marks a hero as owned.
import { h, put, toast, debounce } from '../dom.js';
import { t } from '../i18n.js';
import { D, STATS, TAGS, fold } from '../data.js';
import { store } from '../store.js';
import { mv, orb, tile } from '../art.js';
import { needContent } from '../content.js';
import { band } from '../standing.js';
import { enter, replay, sparkFx } from '../motion.js';
import { emptyState, pageHead } from '../shared.js';

/** @typedef {import('../data.js').Hero} Hero */

// filters and sorting stay as they are while the visitor looks at a hero and comes back
const HL = { q: '', colors: /** @type {string[]} */ ([]), moves: /** @type {string[]} */ ([]), weapon: '', tag: '', view: 'all', sort: 'r', shown: 60, more: false, marking: false };
const FIRST = 60, MORE = 120;
const COLORS = ['red', 'blue', 'green', 'colorless'], MOVES = ['Infantry', 'Armored', 'Cavalry', 'Flying'];
/** @type {Record<string, (x: Hero) => string|number>} */
const sortValue = { r: x => x.r || '', n: x => x.n, bst: x => x.bst, hp: x => x.s[0], atk: x => x.s[1], spd: x => x.s[2], def: x => x.s[3], res: x => x.s[4] };
/** hero ids of the Picks list, once it has loaded @type {Set<number>|null} */
let pickIds = null;

export const page = {
  title: () => t('heroes.title'),
  /** @param {HTMLElement} el @param {string} arg "mark" opens the marking mode */
  render(el, arg) {
    HL.marking = arg === 'mark';
    /** changes made in marking mode, saved together on "Done": hero id -> owned @type {Map<number, boolean>} */
    let pending = new Map();
    /** @type {[number, boolean][][]} */ let undo = [];
    /** @param {number} id */
    const owned = id => pending.has(id) ? /** @type {boolean} */ (pending.get(id)) : store.has(id);
    const ownCount = () => { let n = store.count(); for (const [id, on] of pending) if (on !== store.has(id)) n += on ? 1 : -1; return n; };

    /** @param {Hero} hero @param {string[]} words folded search words */
    const matches = (hero, words) => {
      if (HL.colors.length && !HL.colors.includes(hero.c)) return false;
      if (HL.moves.length && !HL.moves.includes(hero.m)) return false;
      if (HL.weapon && hero.wt !== HL.weapon) return false;
      if (HL.tag && !hero.p.includes(HL.tag)) return false;
      if (!HL.marking) {
        if (HL.view === 'mine' && !store.has(hero.id)) return false;
        if (HL.view === 'current' && band(hero) !== 'current') return false;
        if (HL.view === 'picks' && !(pickIds && pickIds.has(hero.id))) return false;
      }
      for (const w of words) if (!hero.q.includes(w)) return false;
      return true;
    };
    const list = () => {
      const words = fold(HL.q).split(' ').filter(Boolean);
      const out = D.heroes.filter(x => matches(x, words));
      const val = sortValue[HL.sort] || sortValue.r, dir = HL.sort === 'n' ? 1 : -1;
      return out.sort((a, b) => { const x = val(a), y = val(b); return (x < y ? -1 : x > y ? 1 : 0) * dir || a.n.localeCompare(b.n) || a.id - b.id; });
    };
    const clear = () => { HL.q = ''; HL.colors = []; HL.moves = []; HL.weapon = ''; HL.tag = ''; if (!HL.marking) HL.view = 'all'; draw(); };
    const empty = () => emptyState(t('heroes.none.title'), t('heroes.none'), h('button', { type: 'button', class: 'btn primary', onclick: clear }, t('heroes.clear')));

    const body = h('div', {});
    const countLine = h('p', { class: 'countline', role: 'status' });
    const live = h('b', { class: 'num' }), delta = h('small', {});
    const undoBtn = /** @type {HTMLButtonElement} */ (h('button', { type: 'button', class: 'btn', onclick: () => { const step = undo.pop(); if (step) for (const [id, was] of step) setOwn(id, was); counts(); } }, t('undo')));

    /** @param {number} id @param {boolean} on */
    const setOwn = (id, on) => {
      if (on === store.has(id)) pending.delete(id); else pending.set(id, on);
      const el2 = body.querySelector('.tile[data-id="' + id + '"]');
      if (el2) { el2.classList.toggle('owned', on); el2.setAttribute('aria-pressed', on ? 'true' : 'false'); }
      return el2;
    };
    const counts = () => {
      const words = fold(HL.q).split(' ').filter(Boolean);
      for (const c of COLORS) {
        const cnt = body.querySelector('[data-cnt="' + c + '"]');
        if (!cnt) continue;
        const group = D.heroes.filter(x => x.c === c && matches(x, words));
        cnt.textContent = t('mark.group', { n: group.filter(x => owned(x.id)).length, total: group.length });
      }
      let add = 0, rem = 0;
      for (const [id, on] of pending) if (on !== store.has(id)) { if (on) add++; else rem++; }
      live.textContent = String(ownCount());
      delta.textContent = add || rem ? t('mark.delta', { add, rem }) : t('mark.nochange');
      undoBtn.disabled = !undo.length;
    };
    /** @param {[number, boolean][]} step */
    const pushUndo = step => { if (step.length) undo.push(step); if (undo.length > 50) undo.shift(); };

    const drawBody = () => {
      const all = list();
      if (HL.marking) {
        put(body, all.length ? h('div', { class: 'groups' }, COLORS.map(c => {
          const group = all.filter(x => x.c === c);
          if (!group.length) return null;
          /** @param {boolean} on */
          const setAll = on => { /** @type {[number, boolean][]} */ const step = []; for (const x of group) if (owned(x.id) !== on) { step.push([x.id, !on]); setOwn(x.id, on); } pushUndo(step); counts(); };
          return h('section', { 'data-g': c }, h('div', { class: 'group-head' },
            h('h2', { class: 'c-' + c }, orb(c, 26), t('color.' + c), ' ', h('span', { class: 'cnt num', 'data-cnt': c })),
            h('button', { type: 'button', class: 'btn small', 'aria-label': t('mark.all.label', { color: t('color.' + c) }), onclick: () => setAll(true) }, t('mark.all')),
            h('button', { type: 'button', class: 'btn small', 'aria-label': t('mark.none.label', { color: t('color.' + c) }), onclick: () => setAll(false) }, t('mark.none'))),
          h('div', { class: 'grid stagger' }, group.map((x, i) => tile(x, { mark: true, i, owned: owned(x.id) }))));
        })) : empty());
        counts();
        return;
      }
      const shown = all.slice(0, HL.shown);
      const stat = STATS.indexOf(HL.sort);
      put(countLine, h('span', {}, t('heroes.count', { n: all.length, total: D.heroes.length, own: store.count() })),
        h('span', { class: 'chip' }, t('heroes.sorted.' + HL.sort)));
      put(body, all.length ? h('div', { class: 'grid stagger' }, shown.map((x, i) => {
        const el2 = tile(x, { i, isNew: band(x) === 'current' && x.r === D.manifest.newestRelease && !store.has(x.id) });
        if (stat >= 0 || HL.sort === 'bst') /** @type {HTMLElement} */ (el2.firstElementChild).append(h('span', { class: 'tile-stat num' }, stat >= 0 ? t('stat.' + HL.sort) + ' ' + x.s[stat] : String(x.bst)));
        return el2;
      })) : empty(),
      all.length > HL.shown ? h('div', { class: 'center gap' }, h('button', { class: 'btn', type: 'button', onclick: () => { HL.shown += MORE; drawBody(); } }, t('heroes.more', { n: all.length - HL.shown }))) : null);
    };

    body.addEventListener('click', e => {
      const tl = /** @type {HTMLElement|null} */ (/** @type {HTMLElement} */ (e.target).closest('button.tile'));
      if (!tl || !HL.marking) return;
      const id = Number(tl.getAttribute('data-id')), on = !owned(id);
      pushUndo([[id, !on]]);
      setOwn(id, on);
      replay(tl, 'tap');
      if (on) { const seal = tl.querySelector('.seal'); replay(seal, 'pop'); sparkFx(seal); }
      counts();
    });

    const draw = () => {
      /** @param {'colors'|'moves'} key @param {string} v @param {any} ico @param {string} label */
      const fchip = (key, v, ico, label) => h('button', { type: 'button', class: 'fchip', 'aria-pressed': HL[key].includes(v) ? 'true' : 'false',
        onclick: () => { HL[key] = HL[key].includes(v) ? HL[key].filter(x => x !== v) : [...HL[key], v]; HL.shown = FIRST; draw(); } }, ico, label);
      /** @param {'weapon'|'tag'|'sort'} key @param {string} label @param {[string, string][]} options @param {boolean} [noAll] */
      const pick = (key, label, options, noAll) => h('label', { class: 'field' }, h('span', {}, label), h('select', { 'data-pick': key, onchange: (/** @type {any} */ e) => { HL[key] = e.target.value; HL.shown = FIRST; drawBody(); } },
        noAll ? null : h('option', { value: '' }, t('f.any')), options.map(([v, text]) => { const o = /** @type {HTMLOptionElement} */ (h('option', { value: v }, text)); if (HL[key] === v) o.selected = true; return o; })));
      const search = /** @type {HTMLInputElement} */ (h('input', { type: 'search', placeholder: t('heroes.search'), 'aria-label': t('heroes.search'), value: HL.q, autocomplete: 'off', spellcheck: 'false' }));
      search.addEventListener('input', debounce(() => { HL.q = search.value; HL.shown = FIRST; drawBody(); }, 120));
      const searchBox = h('label', { class: 'search' }, h('i', { class: 'lens', 'aria-hidden': 'true' }), search);
      /** @param {string} v @param {string} label @param {number} [n] */
      const seg = (v, label, n) => h('button', { type: 'button', 'data-view': v, 'aria-pressed': HL.view === v ? 'true' : 'false', onclick: () => { HL.view = v; HL.shown = FIRST; draw(); } }, label, n != null ? [' ', h('span', { class: 'num' }, n)] : null);
      const weapons = [...new Set(D.heroes.map(x => x.wt))].sort();
      const chips = h('div', { class: 'chiprow', role: 'group', 'aria-label': t('f.title') },
        COLORS.map(c => fchip('colors', c, orb(c, 24), t('color.' + c))), h('span', { class: 'sep' }),
        MOVES.map(m => fchip('moves', m, h('span', { class: 'mv', style: { '--sz': '24px' } }, h('i', { class: 'g-' + m.toLowerCase() })), m)), h('span', { class: 'sep' }),
        h('button', { type: 'button', class: 'fchip text', 'aria-expanded': HL.more ? 'true' : 'false', onclick: () => { HL.more = !HL.more; draw(); } }, t('f.more')));
      const more = HL.more ? h('div', { class: 'morefilters' },
        pick('weapon', t('f.weapon'), weapons.map(w => [w, w])),
        pick('tag', t('f.tag'), TAGS.filter(tag => D.heroes.some(x => x.p.includes(tag))).map(tag => [tag, t('tag.' + tag)])),
        HL.marking ? null : pick('sort', t('f.sort'), Object.keys(sortValue).map(k => [k, t('heroes.sorted.' + k)]), true)) : null;
      el.classList.toggle('mark-on', HL.marking);
      if (HL.marking) {
        put(el, h('div', { class: 'editbar' },
          h('button', { type: 'button', class: 'btn small quiet', onclick: () => { HL.marking = false; pending = new Map(); undo = []; draw(); toast(t('mark.discarded')); } }, '× ' + t('cancel')),
          h('h1', { class: 'plate-title' }, t('mark.title'))),
        h('p', { class: 'lead' }, t('mark.sub')), h('div', { class: 'toolbar' }, searchBox), chips, more, body,
        h('div', { class: 'actionbar' }, h('div', { class: 'actionbar-in' },
          h('div', { class: 'live', 'aria-live': 'polite' }, h('span', {}, live, ' ' + t('mark.inbox')), delta), undoBtn,
          h('button', { type: 'button', class: 'btn primary', 'data-act': 'done', onclick: () => {
            /** @type {Record<string, boolean>} */ const changes = {}; let add = 0, rem = 0;
            for (const [id, on] of pending) if (on !== store.has(id)) { changes[String(id)] = on; if (on) add++; else rem++; }
            const ok = !(add || rem) || store.setMany(changes);
            HL.marking = false; pending = new Map(); undo = []; draw();
            toast(ok ? t('mark.saved', { n: store.count(), add, rem }) : t('store.blocked.short'));
          } }, t('mark.done')))));
      } else {
        put(el, pageHead(t('heroes.title'), t('heroes.sub')),
          h('div', { class: 'toolbar' },
            h('div', { class: 'seg', role: 'group', 'aria-label': t('heroes.view') }, seg('all', t('heroes.view.all'), D.heroes.length), seg('picks', t('heroes.view.picks')), seg('current', t('heroes.view.current')), seg('mine', t('heroes.view.mine'), store.count())),
            searchBox,
            h('button', { type: 'button', class: 'btn primary', 'data-act': 'edit', onclick: () => { HL.marking = true; pending = new Map(); undo = []; draw(); window.scrollTo(0, 0); } }, t('mark.start'))),
          chips, more,
          HL.view === 'picks' ? h('p', { class: 'dim small viewnote' }, t('heroes.view.picks.note'), ' ', h('a', { href: '#/guide/meta' }, t('car.more') + ' ›'))
            : HL.view === 'current' ? h('p', { class: 'dim small viewnote' }, t('heroes.view.current.note')) : null,
          countLine, body);
      }
      drawBody();
      enter(el);
    };
    draw();
    if (!pickIds) needContent('picks').then(p => { pickIds = new Set((p.picks || []).map((/** @type {any} */ x) => { const hero = D.byWn.get(x.id); return hero ? hero.id : 0; })); if (HL.view === 'picks' && el.isConnected) drawBody(); }, () => { pickIds = new Set(); });
  },
};
