// @ts-check
// Pieces several pages use.
import { h, toast } from './dom.js';
import { t, tn } from './i18n.js';
import { store } from './store.js';
import { daysLeft, secondsLeft, fmtTime, fmtUtc, fmtUtcShort, fmtUtcTime, now } from './time.js';
import { replay, sparkFx } from './motion.js';

/** @typedef {import('./data.js').Hero} Hero */

/** An end time as the game states it, with the visitor's own clock: "16 Nov, 07:00 UTC (08:00 your time)". @param {number} e the last second, as in the data */
export const endText = e => t('time.end', { utc: fmtUtcShort(e + 1), local: fmtTime(e + 1) });
/** @param {Hero} hero */
export const fullName = hero => hero.n + ': ' + hero.ti;
/** @param {Hero} hero */
export const heroHref = hero => '#/hero/' + hero.id;
/** The hero's color as a small orb; the weapon's name is in the text alternative. @param {Hero} hero */
export const colorDot = hero => h('span', { class: 'orb dot ' + hero.c, title: hero.w, role: 'img', 'aria-label': hero.w });
/** @type {Record<string, string>} */
const TAG_STYLE = { emblem: 'gold', legendary: 'gold', mythic: 'gold', brave: 'gold', chosen: 'gold', special: 'pink', fallen: 'pink', harmonized: 'violet', duo: 'violet', resplendent: 'violet',
  rearmed: 'teal', attuned: 'teal', aided: 'teal', refresher: 'teal', vista: 'teal', entwined: 'teal', ascended: 'teal' };
/** @param {string} tag */
export const tagChip = tag => h('span', { class: 'chip ' + (TAG_STYLE[tag] || '') }, t('tag.' + tag));
/** @param {Hero} hero @param {boolean} [withTitle] */
export const heroLink = (hero, withTitle) => h('a', { href: heroHref(hero) }, hero.n, withTitle ? [': ', hero.ti] : null);
/** The stone title plate of a page, a line under it, and something beside it. @param {string} title @param {string} [sub] @param {any} [aside] */
export const pageHead = (title, sub, aside) => [h('div', { class: 'page-head' }, h('h1', { class: 'plate-title' }, title), aside || null), sub ? h('p', { class: 'lead' }, sub) : null];
/** "How this works": the link from a page to the part of the guide that explains it. @param {string} section */
export const howLink = section => h('a', { class: 'btn small quiet how', href: '#/guide/' + section }, t('how'));
/**
 * A panel with the teal title bar. @param {string} title @param {any} body
 * @param {{ more?: any, cls?: string, i?: number, id?: string }} [o]
 */
export const panel = (title, body, o = {}) => h('section', { class: 'panel rise ' + (o.cls || ''), id: o.id, style: { '--i': o.i || 0 } },
  h('div', { class: 'panel-head' }, h('h2', {}, title), o.more || null), h('div', { class: 'panel-body' }, body));
/** @param {number} r @param {(r: number) => void} onchange @param {string} [label] */
export const raritySelect = (r, onchange, label) => h('select', { 'aria-label': label, onchange: (/** @type {any} */ e) => onchange(+e.target.value) },
  [5, 4, 3, 2, 1].map(x => { const o = /** @type {HTMLOptionElement} */ (h('option', { value: x }, x + '★')); if (r === x) o.selected = true; return o; }));
/**
 * A number field for merges that never shows a value outside 0-10. @param {number} m @param {(v: any) => number} save returns the stored value
 * @param {string} [label]
 */
export const mergeInput = (m, save, label) => h('input', { type: 'number', min: 0, max: 10, step: 1, inputmode: 'numeric', value: m, 'aria-label': label,
  onchange: (/** @type {any} */ e) => { e.target.value = save(e.target.value); } });

/**
 * The seal that puts a hero into the barracks or takes it out. The button changes itself, so keyboard focus stays on it.
 * @param {Hero} hero @param {() => void} [onChange] called after every change, also after an undo
 */
export function ownStar(hero, onChange) {
  const seal = h('span', { class: 'seal' });
  const btn = h('button', { class: 'star', type: 'button', onclick: (/** @type {Event} */ e) => {
    e.preventDefault(); e.stopPropagation();
    const r = store.toggle(hero.id);
    paint();
    if (r.added) { replay(seal, 'pop'); sparkFx(seal); toast(t('toast.added', { name: hero.n })); }
    else toast(t('toast.removed', { name: hero.n }), { action: { label: t('undo'), run: () => { r.undo(); paint(); if (onChange) onChange(); } } });
    if (onChange) onChange();
  } }, seal);
  const paint = () => {
    const on = store.has(hero.id);
    const label = t(on ? 'box.remove.name' : 'box.add.name', { name: fullName(hero) });
    btn.classList.toggle('on', on); seal.classList.toggle('on', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.setAttribute('aria-label', label); btn.title = label;
  };
  paint();
  return btn;
}

/**
 * "3 days left" or, on the last game day, "ends in 5 h, at 07:59"; the exact UTC instant is in the tooltip.
 * Red with a soft pulse on the last game day, amber with up to two days left.
 * @param {{ s: number, e: number }} x @param {number} [at]
 */
export function endsChip(x, at = now()) {
  const days = daysLeft(x, at), secs = secondsLeft(x, at);
  const text = days >= 1 ? tn('time.daysLeft', days)
    : secs >= 3600 ? t('time.endsHours', { n: Math.floor(secs / 3600), time: fmtUtcTime(x.e + 1) })
    : t('time.endsMinutes', { n: Math.max(1, Math.ceil(secs / 60)), time: fmtUtcTime(x.e + 1) });
  return h('span', { class: 'time ' + (days < 1 ? 'today' : days <= 2 ? 'soon' : ''), title: t('time.endsAt', { utc: fmtUtc(x.e) }) + ' · ' + endText(x.e) }, h('i', { class: 'clock', 'aria-hidden': 'true' }), text);
}

/** The guide's small text format: "## heading", "- list item", anything else a paragraph. @param {string[]} paras */
export function prose(paras) {
  /** @type {any[]} */ const out = [];
  /** @type {HTMLElement|null} */ let list = null;
  for (const p of paras) {
    if (p.startsWith('- ')) { if (!list) { list = h('ul', { class: 'bullets' }); out.push(list); } list.append(h('li', {}, p.slice(2))); continue; }
    list = null;
    out.push(p.startsWith('## ') ? h('h3', { class: 'sub' }, p.slice(3)) : h('p', {}, p));
  }
  return out;
}

/** An empty state with the lantern illustration. @param {string} title @param {string} text @param {any} [action] */
export const emptyState = (title, text, action) => h('div', { class: 'empty' }, h('img', { src: 'art/empty-lantern.webp', alt: '', width: 220, height: 220 }), h('h2', {}, title), h('p', {}, text), action || null);
