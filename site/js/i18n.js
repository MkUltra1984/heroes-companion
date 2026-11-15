// @ts-check
// Texts. The site is English only; every visible text still lives in locales/en.json, not in the code.

/** @type {Record<string, string>} */
let STR = {};

export async function loadStrings() {
  const r = await fetch('locales/en.json');
  if (!r.ok) throw new Error('locales/en.json: ' + r.status);
  const v = await r.json();
  if (!v || typeof v !== 'object') throw new Error('locales/en.json: not a text file');
  STR = v;
}

/** @param {string} key */
export const has = key => STR[key] != null;

const reported = new Set();
/**
 * Text for a key, with {name} placeholders filled. A missing key is shown as the key and reported once.
 * @param {string} key @param {Record<string, any>} [params]
 */
export function t(key, params) {
  let s = STR[key];
  if (s == null) {
    if (!reported.has(key)) { reported.add(key); console.error('missing text key: ' + key); }
    return key;
  }
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll('{' + k + '}', String(v));
  return s;
}

const plural = new Intl.PluralRules('en');
/** Counted text: picks key.one or key.other and fills {n}. @param {string} key @param {number} n @param {Record<string, any>} [params] */
export const tn = (key, n, params) => t(key + '.' + (plural.select(n) === 'one' ? 'one' : 'other'), { n, ...params });

/** All texts prefix.1, prefix.2, ... as a list (the guide's paragraphs). @param {string} prefix */
export function series(prefix) {
  const out = [];
  for (let i = 1; STR[prefix + '.' + i] != null; i++) out.push(STR[prefix + '.' + i]);
  return out;
}
