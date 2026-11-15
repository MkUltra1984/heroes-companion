// @ts-check
// Banner logic and the banner card, used by Home, Summon and the hero page. What a banner type offers (rates, free
// pick, the written verdict) comes from content/summon_rules.json; what is new for the visitor comes from the barracks.
// Paid things (Feh Pass) are labelled and are counted only when the visitor has switched "I have Feh Pass" on.
import { h, toast } from './dom.js';
import { t, tn } from './i18n.js';
import { D } from './data.js';
import { store } from './store.js';
import { fmtDayTime, fmtShort, fmtUtc, isLive, isUpcoming, now } from './time.js';
import { artImg, artUrl, face, orb } from './art.js';
import { rulesFor, sourceList } from './content.js';
import { endsChip, endText } from './shared.js';

/** @typedef {import('./data.js').Hero} Hero */
/** @typedef {{ id: string, n: string, s: number, e: number, t: string, k: string, f: [number, number|null][]|null, re?: boolean, f4?: boolean }} Banner
 *   f null: focus heroes unknown; re: the same banner name ran before; f4: a focus hero also comes at 4 stars */

// Orbs for n summons when every circle of five is emptied (5 + 4 + 4 + 4 + 3 = 20), and the other way round.
/** @param {number} n */
export const orbsFor = n => Math.floor(n / 5) * 20 + [0, 5, 9, 13, 17][n % 5];
/** @param {number} orbs */
export const summonsFor = orbs => { const r = orbs % 20; return Math.floor(orbs / 20) * 5 + (r >= 17 ? 4 : r >= 13 ? 3 : r >= 9 ? 2 : r >= 5 ? 1 : 0); };

export const PICK_AT = 40;
/** @type {Record<string, number>} */
export const KIND_ORDER = { new: 0, legendary: 1, special: 2, other: 3, revival: 4, free: 5 };
export const MINOR = ['revival', 'free'];
const COLORS = ['red', 'blue', 'green', 'colorless'];
const RATE_KEYS = ['focus5', 'other5', 'focus4', 'special4', 'special4_shsr', 'star4', 'star3'];

/** @param {Banner} b @returns {Hero[]} */
export const focusOf = b => /** @type {Hero[]} */ ((b.f || []).map(f => D.byId.get(f[0])).filter(Boolean));
/** A banner that has run before: the data marks it (the same name earlier in the wiki's banner list), or its name says so. @param {Banner} b */
export const isRerun = b => b.re === true || /4★SHSR/.test(b.n);
/**
 * The starting rates of one banner: the type's rates, or the variant the banner can be shown to be. When that cannot
 * be decided the answer is null ("check the details screen"): numbers known to be doubtful are not printed.
 * @param {Banner} b @param {any} rule @returns {Record<string, number|null>|null}
 */
export function ratesFor(b, rule) {
  if (!rule) return null;
  /** @type {any[]} */ const variants = Array.isArray(rule.rates_variants) ? rule.rates_variants : [];
  /** @param {any} r */
  const usable = r => r && RATE_KEYS.some(k => typeof r[k] === 'number') ? r : null;
  if (/4★SHSR/.test(b.n)) { const named = variants.filter(v => /4★SHSR/.test(String(v.when))); return named.length === 1 ? usable(named[0].rates) : null; }
  const base = usable(rule.rates);
  if (!base) return null;
  const with4 = variants.find(v => /also a 4-star focus/.test(String(v.when))), without4 = variants.find(v => /no 4-star focus/.test(String(v.when)));
  if (!with4 && !without4) return base;
  if (b.f == null) return null;                              // whether a focus hero also comes at 4 stars is not known
  if (b.f4) return with4 ? usable(with4.rates) : base.focus4 != null ? base : null;
  return without4 ? usable(without4.rates) : base;
}
/** @param {Banner} b */
export const newFor = b => focusOf(b).filter(x => !store.has(x.id));
/** Running banners, the ones that matter first. @param {Banner[]} banners @param {number} [at] */
export function liveBanners(banners, at = now()) {
  return banners.filter(b => isLive(b, at)).sort((a, b) => (KIND_ORDER[a.k] ?? 3) - (KIND_ORDER[b.k] ?? 3) || newFor(b).length - newFor(a).length || a.e - b.e);
}
/** Free quest orbs listed in the data that can still be collected before an instant. @param {any} orbsFile orbs.json or null @param {number} until */
export function earnable(orbsFile, until, at = now()) {
  if (!orbsFile || !orbsFile.questsKnown) return 0;
  const rows = (Array.isArray(orbsFile.groups) ? orbsFile.groups : []).flatMap((/** @type {any} */ g) => Array.isArray(g.rows) ? g.rows : []);
  return rows.filter((/** @type {any} */ r) => !r.pass && r.e >= at && r.s <= until).reduce((/** @type {number} */ a, /** @type {any} */ r) => a + r.n, 0);
}

/**
 * The free pick of a banner for this visitor.
 * @param {Banner} b @param {any} rule the banner type's rules or null
 * @returns {{ state: 'everyone'|'pass'|'paid'|'notlisted'|'unknown'|'none'|'rerun', check: boolean, made: number, cost: number, can: number }}
 *   state "rerun": a seasonal banner that returns has no free pick for anyone; state "pass": Feh Pass only and the visitor has it; "paid": Feh Pass only and the visitor has not; cost: orbs still needed; can: summons the orbs buy
 */
export function freePick(b, rule) {
  const fp = rule && rule.free_pick, who = fp ? fp.who : null;
  const made = store.pulls(b.id), need = Math.max(0, PICK_AT - made);
  const cost = Math.max(0, orbsFor(need) - (made === 0 && need > 0 ? 5 : 0));          // the first summon on a banner is free
  const can = Math.min(need, summonsFor(store.state.orbs + (made === 0 ? 5 : 0)));
  const state = !fp || who == null ? 'unknown' : who === 'not_listed' ? 'notlisted' : fp.after_summons !== PICK_AT ? 'none'
    : rule.type === 'Special' && isRerun(b) ? 'rerun'
    : who === 'everyone' ? 'everyone' : store.state.prefs.fehPass ? 'pass' : 'paid';
  return { state, check: !!(fp && fp.needs_in_game_check), made, cost, can };
}

/**
 * The verdict for this visitor. The head is one of five fixed labels; the reason is counted from the barracks, and the
 * written advice of the banner type follows it on the full card.
 * @param {Banner} b @param {any} rule
 * @returns {{ cls: string, head: string, why: string, best: string|null }}
 */
export function verdict(b, rule) {
  const focus = focusOf(b), lack = focus.filter(x => !store.has(x.id));
  /** @type {Record<string, number>} */ const per = {};
  for (const x of lack) per[x.c] = (per[x.c] || 0) + 1;
  const top = Math.max(0, ...Object.values(per)), tops = Object.keys(per).filter(c => per[c] === top);
  const bestColor = top >= 2 && tops.length === 1 ? tops[0] : null;          // on a tie no color is singled out
  const kind = rule && rule.verdict ? rule.verdict.rule : null;
  if (kind === 'always_take') return { cls: '', head: t('bn.v.free'), why: t('bn.v.free.why'), best: null };
  if (b.f == null) return { cls: 'wait', head: t('bn.v.check'), why: t('summon.focus.unknown'), best: null };
  if (!focus.length) return { cls: 'wait', head: t('bn.v.check'), why: t('summon.nofocus'), best: null };
  const count = tn('bn.newcount', focus.length, { missing: lack.length }) + (bestColor ? ' ' + t('bn.bestcolor', { n: per[bestColor], color: t('color.' + bestColor).toLowerCase() }) : '');
  if (!lack.length) return { cls: 'wait', head: t('bn.v.nothing'), why: t('bn.v.nothing.why'), best: null };
  if (!kind || kind === 'check_in_game') return { cls: 'wait', head: t('bn.v.check'), why: count + ' ' + t('bn.v.check.why'), best: bestColor };
  const fp = freePick(b, rule);
  const open = fp.state === 'everyone' || fp.state === 'pass', reach = open && store.state.orbs >= fp.cost;
  if (kind !== 'skip_unless_wanted' && reach) return { cls: '', head: t('bn.v.reach'), why: count + ' ' + t('bn.v.reach.why'), best: bestColor };
  return { cls: 'want', head: t('bn.v.want'), why: count + ' ' + t(reach ? 'bn.v.want.reach' : open ? 'bn.v.want.short' : fp.state === 'paid' ? 'bn.v.want.paid' : fp.state === 'rerun' ? 'bn.v.want.rerun' : 'bn.v.want.nopick', { cost: fp.cost }), best: bestColor };
}

/** The painted top of a banner card: backdrop, up to three focus portraits, name, type, time left. @param {Banner} b @param {number} at @param {number} [n] */
function bannerTop(b, at, n = 0) {
  const cast = focusOf(b).slice(0, 3).reverse();
  return h('div', { class: 'banner-art' + (n % 2 ? ' mood2' : '') },
    h('div', { class: 'cast', 'aria-hidden': 'true' }, cast.map(x => h('span', { class: 'p' }, artImg(artUrl(x, 'p', 420))))),
    h('div', { class: 'banner-top' }, h('h3', {}, b.t ? h('small', {}, h('span', { class: 'chip gold' }, b.t)) : null, b.n),
      isLive(b, at) ? endsChip(b, at) : h('span', { class: 'time mid', title: fmtUtc(b.s) }, h('i', { class: 'clock', 'aria-hidden': 'true' }), t('bn.starts', { date: fmtShort(b.s) }))));
}
/** @param {{ cls: string, head: string, why: string }} v @param {string} [more] */
const verdictBox = (v, more) => h('div', { class: 'verdict ' + v.cls }, h('b', {}, v.head), h('span', {}, v.why, more ? [' ', h('span', { class: 'dim' }, more)] : null));

/** The short card on Home: a link to the banner on the Summon page. @param {Banner} b @param {any} rules @param {number} i */
export function bannerTeaser(b, rules, i) {
  return h('a', { class: 'panel banner compact rise', href: '#/summon', style: { '--i': i }, 'data-banner': b.id }, bannerTop(b, now(), i),
    h('div', { class: 'banner-body' }, verdictBox(verdict(b, rulesFor(rules, b.t)))));
}

/** @param {Banner} b @param {any} rule */
function ratesLine(b, rule) {
  const r = ratesFor(b, rule);
  const parts = r ? RATE_KEYS.filter(k => typeof r[k] === 'number' && (/** @type {number} */ (r[k]) > 0 || k === 'other5')).map(k => t('bn.rate.' + k, { n: r[k] })) : [];
  if (!parts.length) return h('p', { class: 'rates dim' }, t('bn.rates.check'));
  return h('p', { class: 'rates' }, h('b', {}, t('bn.rates')), ' ', parts.join(' · '));
}

/** Focus heroes by color, each with "new" or the owned seal. @param {Banner} b @param {string|null} best */
function focusRows(b, best) {
  const focus = focusOf(b);
  if (b.f == null) return h('p', { class: 'dim' }, t('summon.focus.unknown'));
  if (!focus.length) return h('p', { class: 'dim' }, t('summon.nofocus'));
  return h('div', { class: 'focus' }, COLORS.map(c => {
    const list = focus.filter(x => x.c === c);
    if (!list.length) return null;
    const fresh = list.filter(x => !store.has(x.id)).length;
    return h('div', { class: 'focus-row' + (best === c ? ' best' : '') },
      h('span', { class: 'col c-' + c }, orb(c, 24), h('span', { class: 't' }, t('color.' + c))),
      h('span', { class: 'faces' }, list.map(x => {
        const own = store.has(x.id);
        return h('a', { class: 'mini' + (own ? ' have' : ''), href: '#/hero/' + x.id, title: x.n + ': ' + x.ti, 'aria-label': x.n + ': ' + x.ti + ', ' + t(own ? 'summon.have' : 'summon.new') },
          face(x), own ? h('span', { class: 'seal on' }) : h('span', { class: 'new' }, t('tile.new')));
      })),
      h('span', { class: 'tally' }, h('b', {}, t('bn.tally.new', { n: fresh })), ' ' + t('bn.tally.of', { n: list.length }), best === c ? h('small', {}, t('bn.tally.best')) : null));
  }));
}

/** The free pick: progress towards 40 summons, or why there is none to count. @param {Banner} b @param {any} rule @param {any} orbsFile */
function pickBlock(b, rule, orbsFile) {
  const fp = freePick(b, rule);
  const note = fp.check ? [' ', h('span', { class: 'dim' }, t('bn.pick.checkname'))] : null;
  if (fp.state === 'unknown') return h('div', { class: 'pick' }, h('p', {}, h('b', {}, t('bn.pick') + ' '), t('bn.pick.unknown')));
  if (fp.state === 'notlisted' || fp.state === 'none' || fp.state === 'rerun') return h('div', { class: 'pick' }, h('p', {}, h('b', {}, t('bn.pick') + ' '), t(fp.state === 'rerun' ? 'bn.pick.rerun' : fp.state === 'none' ? 'bn.pick.none' : 'bn.pick.notlisted')));
  if (fp.state === 'paid') return h('div', { class: 'pick' }, h('p', { class: 'paid' }, h('b', {}, t('bn.paid') + ' '), t('bn.pick.paid'), note));
  const orbs = store.state.orbs, extra = earnable(orbsFile, b.e);
  const withOrbs = fp.made + fp.can, withMore = fp.made + Math.min(PICK_AT - fp.made, summonsFor(orbs + extra + (fp.made === 0 ? 5 : 0)));
  const msg = fp.made >= PICK_AT ? t('bn.pick.done') : orbs >= fp.cost ? t('bn.pick.enough', { cost: fp.cost })
    : orbs + extra >= fp.cost ? t('bn.pick.withquests', { cost: fp.cost, extra }) : t('bn.pick.short', { cost: fp.cost, short: fp.cost - orbs - extra, extra });
  return h('div', { class: 'pick' },
    h('div', { class: 'row' }, h('span', {}, t(fp.state === 'pass' ? 'bn.pick.title.pass' : 'bn.pick.title'), fp.state === 'pass' ? [' ', h('span', { class: 'chip sample' }, t('bn.paid.chip'))] : null),
      h('span', { class: 'num' }, t('bn.pick.count', { n: Math.min(PICK_AT, withOrbs), total: PICK_AT }))),
    h('div', { class: 'bar', role: 'img', 'aria-label': t('bn.pick.bar', { made: fp.made, can: fp.can }) },
      h('span', { class: 'fill extra', style: { '--v': (withMore / PICK_AT).toFixed(3), '--i': 3 } }), h('span', { class: 'fill can', style: { '--v': (withOrbs / PICK_AT).toFixed(3), '--i': 2 } }),
      h('span', { class: 'fill', style: { '--v': (Math.min(PICK_AT, fp.made) / PICK_AT).toFixed(3), '--i': 1 } })),
    h('p', {}, msg, ' ', h('span', { class: 'dim' }, t('bn.pick.legend')), note));
}

/** "Summons made here" with its buttons. @param {Banner} b @param {() => void} redraw */
function pullsRow(b, redraw) {
  const made = store.pulls(b.id);
  /** @param {number} by @param {number} orbs */
  const change = (by, orbs) => {
    const beforePulls = made, beforeOrbs = store.state.orbs;
    store.setPulls(b.id, made + by);
    if (orbs) store.setOrbs(Math.max(0, beforeOrbs - orbs));
    redraw();
    if (orbs) toast(t('bn.pulls.spent', { n: Math.min(orbs, beforeOrbs) }), { action: { label: t('undo'), run: () => { store.setPulls(b.id, beforePulls); store.setOrbs(beforeOrbs); redraw(); } } });
  };
  return h('div', { class: 'banner-actions' },
    h('span', { class: 'pulls' }, t('bn.pulls'), ' ', h('b', { class: 'num' }, made)),
    h('button', { type: 'button', class: 'btn small', disabled: made < 1, 'aria-label': t('bn.pulls.minus'), onclick: () => change(-1, 0) }, '−1'),
    h('button', { type: 'button', class: 'btn small', 'aria-label': t('bn.pulls.plus'), onclick: () => change(1, 0) }, '+1'),
    h('button', { type: 'button', class: 'btn small', onclick: () => change(5, 20) }, t('bn.pulls.circle')));
}

/** Everything below the painted top of a full card. @param {Banner} b @param {any} rules @param {any} orbsFile @param {() => void} redraw */
function bannerBody(b, rules, orbsFile, redraw) {
  const rule = rulesFor(rules, b.t), at = now(), v = verdict(b, rule);
  const run = Math.max(0, Math.min(1, (at - b.s) / Math.max(1, b.e - b.s)));
  return h('div', { class: 'banner-body' },
    verdictBox(v),
    rule && rule.verdict && rule.verdict.text ? h('p', { class: 'advice' }, rule.verdict.text) : null,
    isLive(b, at) ? h('div', { class: 'run' }, h('div', { class: 'bar' }, h('span', { class: 'fill', style: { '--v': run.toFixed(3), '--i': 1 } })),
      h('small', {}, h('span', {}, t('bn.started', { date: fmtShort(b.s) })), h('span', { title: fmtUtc(b.e) }, t('bn.ends') + ' ', h('b', {}, endText(b.e)))))
      : h('p', { class: 'dim small' }, t('bn.runs', { from: fmtDayTime(b.s), to: endText(b.e) })),
    focusRows(b, v.best),
    ratesLine(b, rule),
    isLive(b, at) ? [pickBlock(b, rule, orbsFile), pullsRow(b, redraw)] : null,
    rule ? h('details', { class: 'srcfold' }, h('summary', {}, t('bn.sources', { type: b.t })),
      rule.description ? h('p', {}, rule.description) : null,
      rule.free_pick && rule.free_pick.note ? h('p', { class: 'dim' }, rule.free_pick.note) : null,
      h('p', { class: 'dim' }, t(rule.verified ? 'bn.verified' : 'bn.unverified')),
      sourceList(rule.sources, h)) : h('p', { class: 'dim small' }, t('bn.norule', { type: b.t || '?' })));
}

/** The full card of the Summon page. @param {Banner} b @param {any} rules @param {any} orbsFile @param {number} i @param {() => void} redraw */
export function bannerCard(b, rules, orbsFile, i, redraw) {
  return h('article', { class: 'panel banner rise', style: { '--i': Math.min(i, 6) }, 'data-banner': b.id }, bannerTop(b, now(), i), bannerBody(b, rules, orbsFile, redraw));
}

/** A folded banner (revivals, free summons, coming banners): one line, the full body when it is opened. @param {Banner} b @param {any} rules @param {any} orbsFile @param {() => void} redraw */
export function bannerFold(b, rules, orbsFile, redraw) {
  const at = now(), fresh = newFor(b).length, known = b.f != null && focusOf(b).length > 0;
  const body = h('div', {});
  const el = h('details', { class: 'panel banner fold', 'data-banner': b.id, ontoggle: () => { if (/** @type {any} */ (el).open && !body.hasChildNodes()) body.append(bannerBody(b, rules, orbsFile, redraw)); } },
    h('summary', { class: 'collapsed-line' }, h('b', {}, h('h3', {}, b.n), b.t ? h('span', { class: 'chip gold' }, b.t) : null),
      h('span', {}, known ? tn('bn.fold.new', fresh) : t('bn.fold.unknown')),
      isUpcoming(b, at) ? h('span', { class: 'time mid', title: fmtUtc(b.s) }, h('i', { class: 'clock', 'aria-hidden': 'true' }), t('bn.starts', { date: fmtShort(b.s) })) : endsChip(b, at)),
    body);
  return el;
}
