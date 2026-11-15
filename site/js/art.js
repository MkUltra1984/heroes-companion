// @ts-check
// Hero artwork and the painted badges. Game artwork is never stored on this site: the visitor's browser loads it from
// the wiki's image host, always over a designed fallback (a silhouette on the hero's color). The address of a file on
// that host starts with two characters of the MD5 hash of its name, which is computed here.
import { h } from './dom.js';
import { t } from './i18n.js';
import { store } from './store.js';

/** @typedef {import('./data.js').Hero} Hero */

export const CDN = 'https://static.wikia.nocookie.net/feheroes_gamepedia_en/images/';
/** file kinds on the wiki: face icon, portrait, attack, special, damaged, map sprite idle and ok */
export const KINDS = { f: 'Face FC.webp', p: 'Face.webp', b: 'BtlFace.webp', c: 'BtlFace C.webp', d: 'BtlFace D.webp', i: 'Mini Unit Idle.png', o: 'Mini Unit Ok.png' };

const S = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
const K = Array.from({ length: 64 }, (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) | 0);
/** MD5 of a text as 32 hex characters. @param {string} text */
export function md5(text) {
  const bytes = new TextEncoder().encode(text), n = bytes.length;
  const w = new Int32Array((((n + 8) >> 6) + 1) * 16);
  for (let i = 0; i < n; i++) w[i >> 2] |= bytes[i] << ((i % 4) * 8);
  w[n >> 2] |= 0x80 << ((n % 4) * 8);
  w[w.length - 2] = n * 8;
  let a = 0x67452301, b = 0xefcdab89 | 0, c = 0x98badcfe | 0, d = 0x10325476;
  for (let i = 0; i < w.length; i += 16) {
    let A = a, B = b, C = c, D = d;
    for (let j = 0; j < 64; j++) {
      let f, g;
      if (j < 16) { f = (B & C) | (~B & D); g = j; }
      else if (j < 32) { f = (D & B) | (~D & C); g = (5 * j + 1) % 16; }
      else if (j < 48) { f = B ^ C ^ D; g = (3 * j + 5) % 16; }
      else { f = C ^ (B | ~D); g = (7 * j) % 16; }
      const x = (A + f + K[j] + w[i + g]) | 0, s = S[(j >> 4) * 4 + (j % 4)];
      A = D; D = C; C = B;
      B = (B + ((x << s) | (x >>> (32 - s)))) | 0;
    }
    a = (a + A) | 0; b = (b + B) | 0; c = (c + C) | 0; d = (d + D) | 0;
  }
  return [a, b, c, d].map(v => [0, 8, 16, 24].map(sh => ((v >>> sh) & 255).toString(16).padStart(2, '0')).join('')).join('');
}

/** Whether game artwork is shown: the visitor's switch, and a test can turn it off with window.__hcArt = false. */
export const artOn = () => store.state.prefs.art !== false && /** @type {any} */ (window).__hcArt !== false;
/** The image host; a test can point it at its own server with window.__hcCdn. */
const cdn = () => /** @type {any} */ (window).__hcCdn || CDN;

/**
 * Address of one artwork file. Nothing says whether the file exists: the image's error event shows the fallback.
 * @param {Hero} hero @param {keyof typeof KINDS} kind @param {number} [width] scaled down by the host @param {boolean} [resp] Resplendent attire
 */
export function artUrl(hero, kind, width, resp) {
  const name = (hero.wn + (resp ? ' Resplendent ' : ' ') + KINDS[kind]).replaceAll(' ', '_');
  const x = md5(name).slice(0, 2);
  return cdn() + x[0] + '/' + x + '/' + encodeURIComponent(name) + '/revision/latest' + (width ? '/scale-to-width-down/' + width : '');
}

/**
 * An image that shows itself when it has loaded and marks its parent when it failed. With artwork switched off no
 * image element is made at all, so nothing is requested.
 * @param {string} src @param {Record<string, any>} [attrs] @returns {HTMLImageElement|null}
 */
export function artImg(src, attrs = {}) {
  if (!artOn()) return null;
  const img = /** @type {HTMLImageElement} */ (h('img', { alt: '', decoding: 'async', loading: 'lazy', draggable: 'false', ...attrs }));
  const host = () => /** @type {HTMLElement|null} */ (img.parentElement);
  img.addEventListener('load', () => { const p = host(); if (p) { p.classList.add('loaded'); p.classList.remove('noart'); } });
  img.addEventListener('error', () => { const p = host(); if (p) { p.classList.remove('loaded'); p.classList.add('noart'); } });
  img.src = src;
  return img;
}

/** The square face of a hero over the fallback. @param {Hero} hero @param {string} [cls] */
export const face = (hero, cls) => h('span', { class: 'art glow-' + hero.c + (cls ? ' ' + cls : '') }, artImg(artUrl(hero, 'f'), { width: 158, height: 158 }));
/** Weapon badge: the painted weapon symbol on the hero's color. @param {Hero} hero */
export const wb = hero => h('span', { class: 'wb ' + hero.c, title: hero.w, role: 'img', 'aria-label': hero.w }, h('i', { class: 'g-' + hero.wt.toLowerCase() }));
/** Movement badge. @param {Hero} hero */
export const mv = hero => h('span', { class: 'mv', title: hero.m, role: 'img', 'aria-label': hero.m }, h('i', { class: 'g-' + hero.m.toLowerCase() }));
/** @param {string} [color] red, blue, green, colorless @param {number} [size] */
export const orb = (color, size) => h('span', { class: 'orb' + (color ? ' ' + color : ''), style: size ? { '--sz': size + 'px' } : null, 'aria-hidden': 'true' });
/** @param {Hero} hero */
export const heroLabel = hero => hero.n + ': ' + hero.ti + ', ' + hero.w + ', ' + hero.m;

/**
 * A hero tile: a link to the hero page, or (in marking mode) a button that toggles ownership.
 * @param {Hero} hero @param {{ i?: number, isNew?: boolean, mark?: boolean, owned?: boolean }} [o]
 */
export function tile(hero, o = {}) {
  const owned = o.owned != null ? o.owned : store.has(hero.id);
  const inner = [h('span', { class: 'tile-frame' }, face(hero), wb(hero), mv(hero), h('span', { class: 'seal on' }), o.isNew ? h('span', { class: 'new' }, t('tile.new')) : null),
    h('span', { class: 'tile-name' }, hero.n), h('span', { class: 'tile-title' }, hero.ti)];
  const cls = 'tile' + (hero.av === 'pool34' ? ' r4' : '') + (owned ? ' owned' : '');
  const style = { '--i': Math.min(o.i || 0, 12) };
  if (o.mark) return h('button', { type: 'button', class: cls, 'data-id': hero.id, 'aria-pressed': owned ? 'true' : 'false', 'aria-label': heroLabel(hero), style }, inner);
  return h('a', { class: cls, 'data-id': hero.id, href: '#/hero/' + hero.id, 'aria-label': heroLabel(hero) + (owned ? ', ' + t('tile.owned') : ''), style }, inner);
}
