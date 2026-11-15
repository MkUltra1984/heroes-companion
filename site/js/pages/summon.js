// @ts-check
// Summon: a decision tool. The visitor's orbs on the summoning circle, then every running banner with what is new
// for this barracks, what the banner type offers (content/summon_rules.json) and how far the free pick is.
import { h, put } from '../dom.js';
import { t, tn } from '../i18n.js';
import { D, need } from '../data.js';
import { store, LIMITS } from '../store.js';
import { fmtDate, fmtShort, isUpcoming, now } from '../time.js';
import { orb } from '../art.js';
import { needContent } from '../content.js';
import { MINOR, PICK_AT, bannerCard, bannerFold, earnable, liveBanners, orbsFor, summonsFor } from '../banners.js';
import { enter, flourish } from '../motion.js';
import { howLink, pageHead } from '../shared.js';

export { orbsFor, summonsFor };

/** where the five stones sit on the painted circle (percent), and what each costs */
const STONES = [[50, 12.5, 'colorless', 5], [86, 38.5, 'red', 4], [72.5, 81, 'blue', 4], [27.5, 81, 'green', 4], [14, 38.5, 'red', 3]];

export const page = {
  title: () => t('summon.title'),
  /** @param {HTMLElement} el */
  async render(el) {
    const file = await need('banners');
    // the rules and the quest orbs add advice; the banner list works without them
    const [rules, orbsFile] = await Promise.all([needContent('summon_rules').catch(() => null), need('orbs').catch(() => null)]);
    /** @type {import('../banners.js').Banner[]} */
    const banners = file.banners;

    const draw = () => {
      const at = now();
      const all = liveBanners(banners, at);
      const live = all.filter(b => !MINOR.includes(b.k)), minor = all.filter(b => MINOR.includes(b.k));
      const soon = banners.filter(b => isUpcoming(b, at)).sort((a, b) => a.s - b.s);
      const lastEnd = Math.max(0, ...live.map(b => b.e));

      const orbsNo = h('b', { class: 'num' }), lines = h('div', { class: 'budget-lines', role: 'status' });
      const stones = STONES.map(([x, y, color, cost]) => h('span', { class: 'stone', style: { '--x': x + '%', '--y': y + '%' } }, orb(String(color)), h('small', { class: 'num' }, cost)));
      const field = /** @type {HTMLInputElement} */ (h('input', { type: 'number', class: 'orbs', id: 'orbs-field', min: 0, max: LIMITS.orbs, step: 1, inputmode: 'numeric', value: store.state.orbs,
        onchange: () => { field.value = String(store.setOrbs(field.value)); draw(); } }));
      const paintBudget = () => {
        const o = store.state.orbs, n = summonsFor(o), circles = Math.floor(o / 20), inCircle = n % 5, rest = o % 20;
        orbsNo.textContent = String(o);
        stones.forEach((s, i) => s.classList.toggle('lit', i < inCircle));
        const extra = lastEnd ? earnable(orbsFile, lastEnd, at) : 0;
        put(lines, h('span', {}, h('b', { class: 'num' }, tn('summon.buys', n, { circles }))),
          h('small', {}, rest ? t('summon.rest', { n: inCircle, left: 20 - rest }) : t('summon.exact')),
          h('small', {}, t('summon.cost')),
          h('small', {}, t('summon.forty', { orbs: orbsFor(PICK_AT) - 5 })),
          extra ? h('span', { class: 'gap' }, h('a', { href: '#/orbs' }, t('summon.extra', { n: extra, date: fmtShort(lastEnd + 1) }) + ' ›')) : null);
      };
      paintBudget();
      /** @param {number} by */
      const step = by => h('button', { type: 'button', class: 'btn', 'aria-label': t(by < 0 ? 'summon.step.less' : 'summon.step.more', { n: Math.abs(by) }), onclick: () => {
        const before = Math.floor(store.state.orbs / 20);
        store.setOrbs(store.state.orbs + by);
        const grew = Math.floor(store.state.orbs / 20) > before;
        draw();
        if (grew) flourish('blue');
        const again = /** @type {HTMLElement|null} */ (el.querySelector('[data-step="' + by + '"]'));
        if (again) again.focus({ preventScroll: true });
      }, 'data-step': by }, (by < 0 ? '−' : '+') + Math.abs(by));
      const pass = /** @type {HTMLInputElement} */ (h('input', { type: 'checkbox', checked: store.state.prefs.fehPass, onchange: () => { store.setPref('fehPass', pass.checked); draw(); } }));

      put(el, pageHead(t('summon.title'), t('summon.sub'), howLink('summon')),
        h('div', { class: 'summon-grid' },
          h('section', { class: 'panel framed budget' }, h('span', { class: 'corner tl' }), h('span', { class: 'corner tr' }), h('span', { class: 'corner bl' }), h('span', { class: 'corner br' }),
            h('div', { class: 'panel-head' }, h('h2', {}, t('summon.budget'))),
            h('div', { class: 'panel-body' },
              h('div', { class: 'dais' }, h('img', { src: 'art/circle.webp', alt: '', width: 640, height: 640 }), stones, h('div', { class: 'mid' }, orbsNo, h('span', {}, t('summon.orbs.unit')))),
              h('div', { class: 'stepper' }, step(-5), step(-1), step(1), step(5)),
              h('label', { class: 'field inline center' }, h('span', {}, t('summon.orbs')), field),
              lines,
              h('label', { class: 'checkline' }, pass, h('span', {}, t('orbs.pass.have'), ' ', h('span', { class: 'chip sample' }, t('bn.paid.chip')))),
              h('p', { class: 'dim small' }, t('summon.pass.note')))),
          h('div', { class: 'stack' },
            h('h2', { class: 'group-label' }, t('summon.live', { n: live.length })),
            live.length ? live.map((b, i) => bannerCard(b, rules, orbsFile, i, draw)) : h('p', { class: 'dim' }, t('summon.none', { date: fmtDate(D.manifest.dataFrom) })),
            rules ? null : h('p', { class: 'dim small' }, t('summon.norules')),
            minor.length ? [h('h2', { class: 'group-label' }, t('summon.minor', { n: minor.length })), h('p', { class: 'dim small' }, t('summon.minor.note')), minor.map(b => bannerFold(b, rules, orbsFile, draw))] : null,
            soon.length ? [h('h2', { class: 'group-label' }, t('summon.upcoming')), soon.map(b => bannerFold(b, rules, orbsFile, draw))] : null,
            rules && rules.shared_rules ? h('section', { class: 'panel parchment' }, h('div', { class: 'panel-body' }, h('p', { class: 'parch-title' }, t('summon.rules.title')),
              h('ul', { class: 'bullets' }, [rules.shared_rules.cost && rules.shared_rules.cost.text, rules.shared_rules.free_pick && rules.shared_rules.free_pick.text,
                rules.shared_rules.rate_rise && rules.shared_rules.rate_rise.standard].filter(Boolean).map(x => h('li', {}, x))),
              h('p', {}, rules.shared_rules.rate_rise && rules.shared_rules.rate_rise.verified === false ? t('summon.rules.unverified') + ' ' : '', h('a', { href: '#/guide/summon' }, t('summon.guide') + ' ›')))) : null)));
      enter(el);
    };
    draw();
  },
};
