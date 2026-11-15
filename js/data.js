// @ts-check
// Loading the game data (site/data, written by tools/build_data.py, format version 2).
//   manifest.json   build time, age of the data, which wiki tables were there
//   heroes.json     index of all heroes
//   hero/<id>.json  skills, wiki builds and banner history of one hero
//   banners.json, orbs.json, meta.json

export const FORMAT = 2;
export const STATS = ['hp', 'atk', 'spd', 'def', 'res'];
export const TAGS = ['legendary', 'mythic', 'emblem', 'duo', 'harmonized', 'chosen', 'vista', 'special', 'tempest', 'grail', 'story', 'rearmed', 'attuned',
  'aided', 'ascended', 'entwined', 'brave', 'fallen', 'resplendent', 'refresher'];

/**
 * @typedef {{ id: number, wn: string, page: string, n: string, ti: string, w: string, m: string, o: string[], r: string, p: string[],
 *   s: number[], bst: number, av: string, art: string, nb: number|null, k: Record<string, string>|null,
 *   c: string, wt: string, q: string }} Hero   c: color id, wt: weapon without color, q: folded search text
 */

export const D = {
  /** @type {any} */ manifest: null,
  /** @type {Hero[]} */ heroes: [],
  /** @type {Map<number, Hero>} */ byId: new Map(),
  /** @type {Map<string, Hero>} */ byWn: new Map(),
  /** per stat: value -> [rank, number of heroes with this value] @type {Map<number, [number, number]>[]} */ ranks: [],
  /** highest value per stat @type {number[]} */ max: [],
};

/** Text folded for search: lower case, accents removed, so that "Lif" finds "Líf" and "Thjazi" finds "Þjazi". @param {string} s */
export function fold(s) {
  return String(s).toLowerCase().replace(/ð/g, 'd').replace(/þ/g, 'th').replace(/æ/g, 'ae').replace(/œ/g, 'oe').replace(/ø/g, 'o').replace(/ł/g, 'l').replace(/ß/g, 'ss')
    .normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim();
}

let stamp = '';
/** @param {string} path below data/, without ".json" @param {RequestInit} [init] */
export async function getJson(path, init) {
  const r = await fetch('data/' + path + '.json' + (stamp ? '?b=' + stamp : ''), init);
  if (!r.ok) throw new Error(path + '.json: ' + r.status);
  const v = await r.json();
  if (v == null || typeof v !== 'object') throw new Error(path + '.json: not a data file');
  return v;
}

/** The manifest and the hero index: needed by every page. */
export async function loadBase() {
  const [manifest, index] = await Promise.all([getJson('manifest', { cache: 'no-cache' }), getJson('heroes')]);
  if (manifest.v !== FORMAT || index.v !== FORMAT || !Array.isArray(index.heroes)) throw new Error('data format ' + manifest.v + ', this page reads format ' + FORMAT);
  stamp = encodeURIComponent(String(manifest.built || ''));
  D.manifest = manifest;
  D.heroes = index.heroes;
  D.byId.clear(); D.byWn.clear();
  for (const x of D.heroes) {
    x.c = (x.w.split(' ')[0] || '').toLowerCase();                       // "Red Sword" -> red
    x.wt = x.w.replace(/^(Red|Blue|Green|Colorless)\s+/, '');
    x.q = fold([x.n, x.ti, x.o.join(' '), x.w, x.m].join(' '));
    D.byId.set(x.id, x); D.byWn.set(x.wn, x);
  }
  D.ranks = STATS.map((_, i) => {
    const count = new Map();
    for (const x of D.heroes) count.set(x.s[i], (count.get(x.s[i]) || 0) + 1);
    const out = new Map(); let above = 0;
    for (const v of [...count.keys()].sort((a, b) => b - a)) { out.set(v, [above + 1, count.get(v)]); above += count.get(v); }
    return out;
  });
  D.max = STATS.map((_, i) => Math.max(1, ...D.heroes.map(x => x.s[i])));
}

// Files loaded when a page needs them. A failed download is not remembered, so the next try asks again.
/** @type {Map<string, Promise<any>>} */
const cache = new Map();
/** @param {string} path */
export function need(path) {
  let p = cache.get(path);
  if (!p) {
    p = getJson(path);
    cache.set(path, p);
    p.catch(() => cache.delete(path));
  }
  return p;
}
/** @param {number} id */
export const needHero = id => need('hero/' + id);

/** A hero from an address part: the id, or the wiki name old links used. @param {string} arg @returns {Hero|undefined} */
export function findHero(arg) {
  if (/^\d{1,7}$/.test(arg)) return D.byId.get(Number(arg));
  return D.byWn.get(arg);
}
/** @param {Hero} hero */
export const tagsOf = hero => hero.p.filter(p => TAGS.includes(p));
/** Whether a wiki table was there when the data was built. @param {string} table */
export const tableOk = table => !!D.manifest && !!D.manifest.tables && D.manifest.tables[table] === 'ok';
