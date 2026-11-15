// @ts-check
// Written content (site/content, copied from content/ by tools/build_site.py): the summon rules per banner type,
// the hand-written Picks and the currency cards. Each file carries its sources and the date it was written.

/** @type {Map<string, Promise<any>>} */
const cache = new Map();
/** @param {string} name summon_rules, picks or currencies */
export function needContent(name) {
  let p = cache.get(name);
  if (!p) {
    p = fetch('content/' + name + '.json').then(r => { if (!r.ok) throw new Error('content/' + name + '.json: ' + r.status); return r.json(); })
      .then(v => { if (v == null || typeof v !== 'object') throw new Error('content/' + name + '.json: not a content file'); return v; });
    cache.set(name, p);
    p.catch(() => cache.delete(name));
  }
  return p;
}

/** The rules of one banner type, or null when the type is not in the file. @param {any} rules summon_rules.json @param {string} type */
export function rulesFor(rules, type) {
  const list = rules && Array.isArray(rules.types) ? rules.types : [];
  return list.find((/** @type {any} */ x) => x.type === type) || null;
}

/** Whether the Picks list is older than its own limit. @param {any} picks @param {number} nowSeconds */
export function picksStale(picks, nowSeconds) {
  const made = Date.parse(String(picks.as_of) + 'T00:00:00Z') / 1000;
  return !isFinite(made) || nowSeconds - made > (Number(picks.stale_after_days) || 45) * 86400;
}

/** "November 2026" from "2026-11-15". @param {string} iso */
export function monthYear(iso) {
  const ms = Date.parse(String(iso).slice(0, 10) + 'T00:00:00Z');
  return isFinite(ms) ? new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(ms)) : '';
}

/** A list of sources as links with their dates. Only http(s) addresses become links. @param {any[]} sources @param {(tag: string, attrs: any, ...kids: any[]) => HTMLElement} h */
export function sourceList(sources, h) {
  return h('ul', { class: 'sources' }, (Array.isArray(sources) ? sources : []).map(s => h('li', {},
    /^https?:\/\//.test(String(s.url || '')) ? h('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.title) : s.title,
    s.date ? h('span', { class: 'dim' }, ' (' + s.date + (s.date_kind ? ', ' + s.date_kind : '') + ')') : null)));
}
