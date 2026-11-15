// @ts-check
// Orbs: quest rewards that are open right now, and a card per currency. Free orbs and Feh Pass (paid) orbs are never
// added together unless the visitor says they have Feh Pass. What the data does not cover is named, not promised.
import { h, put } from '../dom.js';
import { t, tn } from '../i18n.js';
import { need } from '../data.js';
import { store } from '../store.js';
import { fmtDate, fmtDayTime, fmtShort, fmtUtc, isLive, isUpcoming, now } from '../time.js';
import { orb } from '../art.js';
import { needContent, sourceList } from '../content.js';
import { countUp, enter } from '../motion.js';
import { howLink, pageHead, panel } from '../shared.js';

/** @typedef {{ name: string, s: number, e: number, n: number, pass: boolean }} Row */

/** One currency card from content/currencies.json. Numbers that are null were not verified and are not printed. @param {any} c */
function currencyCard(c) {
  /** @param {string} label @param {any} x @param {string} cls */
  const advice = (label, x, cls) => x && x.text ? h('p', { class: cls }, h('b', {}, label + ' '), x.text, x.basis === 'experience' ? [' ', h('span', { class: 'chip' }, t('cur.experience'))] : null) : null;
  return h('details', { class: 'panel currency', id: 'cur-' + c.id },
    h('summary', {}, h('h3', {}, c.name), h('span', { class: 'dim' }, c.what), c.verified ? null : h('span', { class: 'chip sample' }, t('cur.unverified'))),
    h('div', { class: 'panel-body' },
      Array.isArray(c.from) && c.from.length ? [h('p', {}, h('b', {}, t('cur.from'))), h('ul', { class: 'bullets' }, c.from.map((/** @type {string} */ x) => h('li', {}, x)))] : null,
      c.paid_sources ? h('p', { class: 'paid' }, h('b', {}, t('bn.paid') + ' '), c.paid_sources) : null,
      advice(t('cur.best'), c.best_use, 'good'), advice(t('cur.donot'), c.do_not, 'warnline'),
      h('details', { class: 'srcfold' }, h('summary', {}, t('cur.sources')), sourceList(c.sources, h))));
}

export const page = {
  title: () => t('orbs.title'),
  /** @param {HTMLElement} el */
  async render(el) {
    const file = await need('orbs');
    const cur = await needContent('currencies').catch(() => null);
    /** @type {Row[]} */
    const rows = (Array.isArray(file.groups) ? file.groups : []).flatMap((/** @type {any} */ g) => Array.isArray(g.rows) ? g.rows : []);
    const draw = () => {
      const at = now();
      const open = rows.filter(r => isLive(r, at)).sort((a, b) => a.e - b.e), later = rows.filter(r => isUpcoming(r, at)).sort((a, b) => a.s - b.s);
      const free = open.filter(r => !r.pass), paid = open.filter(r => r.pass);
      /** @param {Row[]} list */
      const sum = list => list.reduce((a, r) => a + r.n, 0);
      const hasPass = store.state.prefs.fehPass;
      /** @param {Row} r @param {boolean} upcoming */
      const line = (r, upcoming) => h('li', { class: 'check' }, h('span', { class: 'what' }, h('b', {}, r.name, upcoming && r.pass ? [' ', h('span', { class: 'chip sample' }, t('orbs.pass.chip'))] : null),
        h('small', { title: fmtUtc(upcoming ? r.s : r.e) }, upcoming ? t('orbs.from', { date: fmtShort(r.s) }) : t('orbs.until', { date: fmtDayTime(r.e + 1) }))),
      h('span', { class: 'gain num' }, '+' + r.n, orb('', 22)));
      /** @param {string} title @param {Row[]} list @param {boolean} upcoming @param {string} [note] @param {string} [cls] */
      const group = (title, list, upcoming, note, cls) => {
        if (!list.length) return null;
        // free and Feh Pass orbs are never one sum: each gets its own number
        const f = sum(list.filter(r => !r.pass)), p = sum(list.filter(r => r.pass));
        return panel(title, [note ? h('p', { class: 'dim small note' }, note) : null, h('ul', { class: 'checks' }, list.map(r => line(r, upcoming)))],
          { more: h('span', { class: 'count num' }, f || !p ? t('orbs.sum.free', { n: f }) : null, f && p ? ' · ' : null, p ? h('span', { class: 'paidsum' }, t('orbs.sum.paid', { n: p })) : null), cls });
      };
      const total = h('b', { class: 'bigno num', id: 'orbs-free' }, sum(free));
      countUp(total, sum(free), 140);
      const pass = /** @type {HTMLInputElement} */ (h('input', { type: 'checkbox', checked: hasPass, onchange: () => { store.setPref('fehPass', pass.checked); draw(); } }));

      put(el, pageHead(t('orbs.title'), t('orbs.sub'), howLink('orbs')),
        !file.questsKnown ? h('div', { class: 'parch-note' }, t('orbs.unknown'))
          : h('section', { class: 'panel framed orbtotal' }, h('span', { class: 'corner tl' }), h('span', { class: 'corner tr' }), h('span', { class: 'corner bl' }), h('span', { class: 'corner br' }),
            h('div', { class: 'panel-body' }, h('span', { class: 'orb big', 'aria-hidden': 'true' }),
              h('div', {}, total, h('p', {}, t('orbs.total')),
                paid.length || hasPass ? h('p', { id: 'orbs-pass', class: 'paid' }, h('b', {}, t('bn.paid') + ' '), t('orbs.pass.total', { n: sum(paid) }), hasPass ? [' ', h('b', {}, t('orbs.pass.both', { n: sum(free) + sum(paid) }))] : null) : null,
                h('label', { class: 'checkline' }, pass, h('span', {}, t('orbs.pass.have')))))),
        h('div', { class: 'cols-2 gapt' },
          h('div', { class: 'stack' }, group(t('orbs.g.quests'), free, false), group(t('orbs.g.pass'), paid, false, t('orbs.pass.note'), 'paidpanel')),
          h('div', { class: 'stack' }, group(t('orbs.g.later'), later, true, t('orbs.later.note')),
            h('div', { class: 'parch-note' }, h('b', {}, t('orbs.notcovered')), ' ', t('orbs.note')))),
        cur && Array.isArray(cur.cards) ? [h('h2', { class: 'group-label gapt', id: 'currencies' }, t('cur.title')),
          h('p', { class: 'lead' }, t('cur.sub', { date: fmtDate(cur.as_of), version: cur.game_version })),
          h('div', { class: 'currencies' }, cur.cards.map(currencyCard)),
          Array.isArray(cur.not_covered) && cur.not_covered.length ? h('p', { class: 'dim small gap' }, t('cur.notcovered') + ' ' + cur.not_covered.join('; ') + '.') : null]
          : h('p', { class: 'dim gap' }, t('cur.failed')));
      enter(el);
    };
    draw();
  },
};
