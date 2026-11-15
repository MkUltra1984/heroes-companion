// @ts-check
// DOM helpers. Everything on the page is built with h(): text always becomes a text node, never markup.
// Rule for this folder: no innerHTML, outerHTML, insertAdjacentHTML or document.write (tools/test_site.py checks it).

/** @param {string} id */
export const $ = id => /** @type {HTMLElement} */ (document.getElementById(id));

/**
 * Element builder: h('a', { href, class, onclick }, 'text', child, [more])
 * @param {string} tag @param {Record<string, any>|null} [attrs] @param {...any} kids
 * @returns {HTMLElement}
 */
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') /** @type {any} */ (el).value = v;
    else if (k === 'style') { for (const [prop, val] of Object.entries(v)) el.style.setProperty(prop, String(val)); }   // an object, set through the style API: the security policy forbids style attributes
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  el.append(...nodes(kids));
  return el;
}

/** Nested lists flattened, empty entries skipped, everything else turned into text nodes. @param {any[]} kids */
export const nodes = kids => kids.flat(Infinity).filter(k => k != null && k !== false && k !== true).map(k => k.nodeType ? k : document.createTextNode(String(k)));
/** @param {Element} el @param {...any} kids */
export const put = (el, ...kids) => el.replaceChildren(...nodes(kids));
/** @param {Element} el @param {...any} kids */
export const add = (el, ...kids) => el.append(...nodes(kids));

let toastTimer = 0;
/**
 * A short message at the bottom. With an action it stays longer and can be clicked.
 * @param {string} msg @param {{ action?: { label: string, run: () => void }, ms?: number }} [opt]
 */
export function toast(msg, opt = {}) {
  const el = $('toast');
  if (!el) return;
  const close = () => el.classList.remove('on', 'act');
  put(el, msg, opt.action ? [' ', h('button', { class: 'link', onclick: () => { close(); if (opt.action) opt.action.run(); } }, opt.action.label)] : null);
  el.classList.add('on');
  el.classList.toggle('act', !!opt.action);
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(close, opt.ms || (opt.action ? 6000 : 2400));
}

/** Runs fn after the user stopped for ms. @template {(...a: any[]) => void} F @param {F} fn @param {number} ms @returns {F} */
export function debounce(fn, ms) {
  let timer = 0;
  return /** @type {any} */ ((...a) => { clearTimeout(timer); timer = window.setTimeout(() => fn(...a), ms); });
}
