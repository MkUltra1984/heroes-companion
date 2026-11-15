// @ts-check
// The Standing block: a description of a hero computed from the site's own data, following content/standing_rules.md.
// It is not a rating: no score, no letter, no color scale. A rule without data says so; it never says "none".
import { t, tn } from './i18n.js';
import { D, STATS } from './data.js';
import { fmtDate, fmtDay, isLive, now } from './time.js';
import { endText } from './shared.js';

/** @typedef {import('./data.js').Hero} Hero */
/** @typedef {{ text: string, cls?: string }} Chip */
/** @typedef {{ text: string, cls?: string }} Line */

const TYPE_ORDER = ['emblem', 'legendary', 'mythic', 'chosen', 'vista', 'entwined', 'aided', 'attuned', 'rearmed', 'ascended', 'duo', 'harmonized', 'brave', 'fallen', 'special'];
const SLOTS = ['weapon', 'assist', 'special', 'a', 'b', 'c', 'x'];

/** Whole calendar months from a date to the data date. @param {string} from YYYY-MM-DD @param {string} to ISO */
export function monthsBetween(from, to) {
  const a = from.split('-').map(Number), b = to.slice(0, 10).split('-').map(Number);
  return Math.max(0, (b[0] - a[0]) * 12 + (b[1] - a[1]) - (b[2] < a[2] ? 1 : 0));
}
/** Rule 1. @param {Hero} hero @returns {'current'|'recent'|'ageing'|'old'|'unknown'} */
export function band(hero) {
  if (!hero.r) return 'unknown';
  const m = monthsBetween(hero.r, D.manifest.dataFrom);
  return m <= 3 ? 'current' : m <= 9 ? 'recent' : m <= 18 ? 'ageing' : 'old';
}

/** @type {Map<string, Hero[]>} */
let classes = new Map();
let classesOf = null;
/** All heroes with the same movement and the same weapon (color included). @param {Hero} hero */
function classOf(hero) {
  if (classesOf !== D.heroes) {
    classes = new Map(); classesOf = D.heroes;
    for (const x of D.heroes) { const k = x.m + '|' + x.w; const list = classes.get(k); if (list) list.push(x); else classes.set(k, [x]); }
  }
  return classes.get(hero.m + '|' + hero.w) || [hero];
}

/**
 * Rule 4 as numbers. @param {Hero} hero
 * @returns {{ n: number, high: { i: number, rank: number, ties: number }[], low: number[], bstRank: number }}
 */
export function classStats(hero) {
  const cls = classOf(hero), n = cls.length, cut = Math.ceil(n / 10);
  const high = [], low = [];
  for (let i = 0; i < 5; i++) {
    const v = hero.s[i];
    let higher = 0, lower = 0, ties = -1;
    for (const x of cls) { if (x.s[i] > v) higher++; else if (x.s[i] < v) lower++; else ties++; }
    if (higher + 1 <= cut) high.push({ i, rank: higher + 1, ties });
    if (lower < cut) low.push(i);
  }
  return { n, high, low, bstRank: cls.filter(x => x.bst > hero.bst).length + 1 };
}

/** A sort key for "newest first, then stats within the class": used to order heroes, never shown as a number. @param {Hero} hero */
export function orderKey(hero) {
  const c = classStats(hero);
  return [hero.r || '', c.n >= 5 ? c.high.length : 0, -c.bstRank];
}

/** @param {Hero} hero @returns {{ chip: string|null, text: string }} rule 7 */
function howToGet(hero) {
  if (hero.av === 'grails') return { chip: t('st.get.grails.chip'), text: t('st.get.grails') };
  if (hero.av === 'story' || hero.p.includes('story')) return { chip: t('st.get.story.chip'), text: t('st.get.story') };
  if (hero.av === 'pool34') return { chip: t('st.get.pool34.chip'), text: t('st.get.pool34') };
  if (hero.av === 'sr4' || hero.av === 'seasonal_sr4') return { chip: t('st.get.sr4.chip'), text: t('st.get.sr4') };
  return { chip: null, text: t('st.get.five') };
}

/**
 * The whole block. @param {Hero} hero @param {any} [file] hero/<id>.json, or null while it is not loaded
 * @returns {{ chips: Chip[], lines: Line[] }}
 */
export function standing(hero, file) {
  /** @type {Chip[]} */ const chips = [];
  /** @type {Line[]} */ const lines = [];
  const klass = (hero.m + ' ' + hero.w).toLowerCase();

  // rule 1: age
  const b = band(hero);
  chips.push({ text: t('st.band.' + b), cls: b === 'current' ? 'teal' : '' });
  if (b === 'unknown') lines.push({ text: t('st.age.unknown'), cls: 'unknown' });
  else {
    const months = monthsBetween(hero.r, D.manifest.dataFrom), date = fmtDate(hero.r);
    lines.push({ text: b === 'current' ? t('st.age.current', { date }) : b === 'recent' ? tn('st.age.recent', months, { date })
      : b === 'ageing' ? t('st.age.ageing', { date, months }) : tn('st.age.old', Math.floor(months / 12), { date }) });
  }
  // rule 2: refreshed (only the paid Resplendent outfit is in the data)
  if (hero.p.includes('resplendent')) lines.push({ text: t('st.resplendent'), cls: 'paidline' });
  // rule 3: type
  const types = TYPE_ORDER.filter(x => hero.p.includes(x)).slice(0, 3);
  for (const x of types) { chips.push({ text: t('st.type.' + x + '.chip'), cls: 'gold' }); lines.push({ text: t('st.type.' + x) }); }
  if (!types.length) lines.push({ text: t('st.type.none'), cls: 'unknown' });
  // rule 8: refresher
  if (hero.p.includes('refresher')) { chips.push({ text: t('st.refresher.chip'), cls: 'teal' }); lines.push({ text: t('st.refresher') }); }
  // rule 4: stats within the class
  const c = classStats(hero);
  if (c.n < 5) lines.push({ text: t('st.class.few', { n: c.n, klass }) });
  else {
    if (c.high.length) {
      lines.push({ text: t('st.class.high', { n: c.n, klass, items: c.high.map(x => {
        const p = { stat: t('stat.' + STATS[x.i]), value: hero.s[x.i], rank: x.rank };
        return x.rank === 1 ? t(x.ties ? 'st.class.joint' : 'st.class.highest', p) : t('st.class.rank', p);
      }).join(', ') }) });
    } else lines.push({ text: t('st.class.nohigh', { n: c.n, klass }) });
    if (c.low.length) lines.push({ text: t('st.class.low', { items: c.low.map(i => t('stat.' + STATS[i]) + ' ' + hero.s[i]).join(', ') }) });
    lines.push({ text: t('st.class.total', { bst: hero.bst, rank: c.bstRank, n: c.n }), cls: 'minor' });
  }
  // rule 5: own weapon and skills
  const kit = file ? file.kit : undefined;
  if (kit == null || !Object.keys(kit).length) lines.push({ text: t('st.kit.unknown'), cls: 'unknown' });
  else {
    /** @param {string} slot */
    const last = slot => Array.isArray(kit[slot]) && kit[slot].length ? kit[slot][kit[slot].length - 1] : null;
    const weapon = last('weapon');
    const personal = SLOTS.filter(s => s !== 'weapon').map(last).filter(s => s && s.ex).map(s => s.n);
    const ownWeapon = !!(weapon && weapon.ex);
    const count = personal.length + (ownWeapon ? 1 : 0);
    if (count) chips.push({ text: tn('st.kit.chip', count), cls: 'violet' });
    lines.push({ text: ownWeapon && personal.length ? tn('st.kit.weaponplus', personal.length, { names: personal.join(', ') })
      : ownWeapon ? t('st.kit.weapononly', { name: weapon.n })
      : personal.length ? tn('st.kit.skillsonly', personal.length, { names: personal.join(', ') })
      : t('st.kit.none') });
  }
  // rule 6: banner history
  const banners = file ? file.banners : undefined;
  const since = fmtDate(D.manifest.bannersFrom);
  if (!Array.isArray(banners)) lines.push({ text: t('st.banners.unknown'), cls: 'unknown' });
  else {
    const at = now();
    const live = banners.filter(x => isLive(x, at)).sort((x, y) => x.e - y.e);
    const past = banners.filter(x => x.e < at).sort((x, y) => y.e - x.e);
    if (live.length) for (const x of live) lines.push({ text: t('st.banners.now', { name: x.n, end: endText(x.e) }) });
    else if (past.length) lines.push({ text: tn('st.banners.past', past.length, { since, name: past[0].n, date: fmtDay(past[0].e) }) });
    else lines.push({ text: t('st.banners.none', { since }) });
  }
  if (hero.p.includes('legendary') || hero.p.includes('mythic')) lines.push({ text: t('st.banners.return') });
  // rule 7: how to get
  const get = howToGet(hero);
  if (get.chip) chips.push({ text: get.chip, cls: 'parch' });
  lines.push({ text: get.text });
  return { chips, lines };
}
