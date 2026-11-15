// @ts-check
// One hero: art, stats and the Standing block at once from the index; skills, wiki builds and banner history from the
// hero's own small file. The hero's own kit is the default build; wiki builds are opinions of their time and old ones
// are folded away and labelled as old.
import { h, put, toast } from '../dom.js';
import { t, tn } from '../i18n.js';
import { D, STATS, findHero, needHero, tagsOf } from '../data.js';
import { store } from '../store.js';
import { fmtDate, fmtDay, fmtUtc, isLive, isUpcoming, now } from '../time.js';
import { artImg, artOn, artUrl, face, mv, wb } from '../art.js';
import { standing } from '../standing.js';
import { countUp, enter, flourish, replay, sparkFx } from '../motion.js';
import { endsChip, endText, fullName, mergeInput, panel, raritySelect, tagChip } from '../shared.js';

/** @typedef {import('../data.js').Hero} Hero */

const SLOTS = ['weapon', 'assist', 'special', 'a', 'b', 'c', 'x', 'seal'];
const RECENT = '2024-01-01';          // builds for heroes released since then, or signed since then, are shown openly
const WIKI = 'https://feheroes.fandom.com/wiki/';
/** @param {string} pageName */
const wikiUrl = pageName => WIKI + encodeURIComponent(pageName.replaceAll(' ', '_')).replaceAll('%3A', ':').replaceAll('%2F', '/');
/** @param {string} href @param {string} text */
const out = (href, text) => h('a', { href, target: '_blank', rel: 'noopener' }, text);
/** @param {Hero} hero */
const game8 = hero => 'https://game8.co/games/fire-emblem-heroes/search?q=' + encodeURIComponent(hero.n);

/** median per stat over all heroes @type {number[]|null} */
let medians = null;
let mediansOf = null;
function median() {
  if (!medians || mediansOf !== D.heroes) { mediansOf = D.heroes; medians = STATS.map((_, i) => { const v = D.heroes.map(x => x.s[i]).sort((a, b) => a - b); return v[v.length >> 1] || 0; }); }
  return medians;
}

/** The art side of the header: large portrait, the other artwork of the hero, and the map sprite. @param {Hero} hero */
function artBox(hero) {
  const box = h('div', { class: 'hero-art glow-' + hero.c }, h('span', { class: 'glowlayer' }), h('span', { class: 'ring' }), h('span', { class: 'ph' }));
  /** @type {HTMLElement|null} */ let full = null;
  /** @param {'p'|'b'|'c'|'d'} kind @param {boolean} resp */
  const show = (kind, resp) => {
    if (full) full.remove();
    box.classList.remove('loaded', 'noart');
    full = artImg(artUrl(hero, kind, 720, resp), { class: 'full', loading: 'eager', alt: t('hero.art.alt', { name: fullName(hero) }) });
    if (full) box.append(full);
  };
  show('p', false);
  /** @type {['p'|'b'|'c'|'d', string, boolean][]} */
  const kinds = [['p', 'normal', false], ['b', 'attack', false], ['c', 'special', false], ['d', 'damaged', false]];
  if (hero.p.includes('resplendent')) kinds.push(['p', 'resplendent', true]);
  const variants = h('div', { class: 'variants', role: 'group', 'aria-label': t('hero.art.switch') }, kinds.map(([kind, name, resp], i) => {
    const thumb = h('span', { class: 'art' }, artImg(artUrl(hero, kind, 160, resp), { loading: 'eager' }));
    const btn = h('button', { type: 'button', class: 'variant', 'aria-pressed': i === 0 ? 'true' : 'false', onclick: () => {
      for (const b of variants.children) b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      show(kind, resp);
    } }, thumb, t('hero.art.' + name));
    const img = thumb.querySelector('img');
    if (img && i > 0) img.addEventListener('error', () => { btn.hidden = true; });      // the wiki has no such file for this hero
    return btn;
  }));
  const stage = h('div', { class: 'sprite-stage', 'aria-hidden': 'true', style: { '--k': '.62' } });
  const idle = artImg(artUrl(hero, 'i'), { class: 'sprite idle', loading: 'eager' }), ok = artImg(artUrl(hero, 'o'), { class: 'sprite ok', loading: 'eager' });
  if (idle) { stage.append(idle); idle.addEventListener('error', () => { stage.hidden = true; }); }
  if (ok) { stage.append(ok); ok.addEventListener('error', () => { ok.remove(); stage.classList.add('single'); }); }
  if (artOn()) box.append(variants);
  if (idle) box.append(stage);
  return box;
}

/** @param {Hero} hero @param {any} file hero/<id>.json */
function kitPanel(hero, file) {
  const kit = file.kit;
  const rows = kit && Object.keys(kit).length ? SLOTS.map(slot => {
    const s = Array.isArray(kit[slot]) && kit[slot][kit[slot].length - 1];
    if (!s) return null;
    const icon = slot === 'weapon' ? h('span', { class: 'slot weapon' }, h('i', { class: 'g-' + hero.wt.toLowerCase() })) : slot === 'assist' ? h('span', { class: 'slot assist' }, h('i', { class: 'g-assist' }))
      : slot === 'special' ? h('span', { class: 'slot special' }, h('i', { class: 'g-special' })) : h('span', { class: 'slot' }, slot === 'seal' ? 'S' : slot.toUpperCase());
    const desc = h('div', { class: 'skill-desc' }, h('div', {}, h('div', { class: 'parch-note' }, s.d ? String(s.d).split('\n').map(line => h('p', {}, line)) : h('p', {}, t('hero.skill.nodesc')))));
    const btn = h('button', { type: 'button', class: 'plate skill', 'aria-expanded': 'false', onclick: () => btn.setAttribute('aria-expanded', btn.getAttribute('aria-expanded') === 'true' ? 'false' : 'true') },
      icon, h('span', { class: 'txt' }, h('small', {}, t('slot.' + slot), s.mt ? ' · ' + t('hero.mt', { n: s.mt }) : '', s.rg ? ' · ' + t('hero.rg', { n: s.rg }) : '', s.sp ? ' · ' + t('hero.sp', { n: s.sp }) : ''), h('b', {}, s.n)),
      h('span', { class: 'meta' }, s.cd ? h('span', { class: 'cd num', title: t('hero.cd', { n: s.cd }), role: 'img', 'aria-label': t('hero.cd', { n: s.cd }) }, s.cd) : null, s.ex ? h('span', { class: 'chip gold' }, t('hero.skill.own')) : null), h('span', { class: 'chev' }));
    return h('div', {}, btn, desc);
  }) : null;
  return panel(t('hero.kit.title'), kit == null ? h('p', { class: 'dim' }, t('hero.kit.unknown')) : !rows ? h('p', { class: 'dim' }, t('hero.nokit'))
    : [h('p', { class: 'dim small note' }, t('hero.kit.note')), h('div', { class: 'skills' }, rows)], { i: 0 });
}

/** @param {any} b one wiki build */
function buildBlock(b) {
  const paras = String(b.desc || '').split('\n').filter(Boolean);
  return h('div', { class: 'build' },
    h('div', { class: 'chips' }, h('b', {}, b.name || t('hero.build')),
      b.mode ? h('span', { class: 'chip' }, t('build.mode.' + b.mode)) : null,
      b.cost ? h('span', { class: 'chip' }, t('hero.cost', { cost: t('build.cost.' + b.cost) })) : null,
      b.iv ? h('span', { class: 'chip' }, b.iv) : null,
      h('span', { class: 'chip' }, b.date ? t('build.signed', { date: fmtDate(b.date) }) : t('build.undated'))),
    h('dl', { class: 'slots' }, SLOTS.map(key => b[key] ? [h('dt', {}, t('slot.' + key)), h('dd', {}, b[key])] : null)),
    paras.length ? h('details', { class: 'srcfold' }, h('summary', {}, t('build.text')), paras.map(p => h('p', {}, p))) : null);
}

/** @param {Hero} hero @param {any} file */
function buildsPanel(hero, file) {
  /** @type {any[]|null} */
  const builds = file.builds;
  const current = (builds || []).filter(b => hero.r >= RECENT || (b.date || '') >= RECENT);
  const old = (builds || []).filter(b => !current.includes(b));
  return panel(t('hero.builds'), [
    builds == null ? h('p', { class: 'dim' }, t('hero.builds.unknown'))
      : !builds.length ? h('p', { class: 'dim' }, t('hero.nobuilds'))
      : [h('p', { class: 'dim small note' }, t('hero.builds.note')),
        current.length ? current.map(buildBlock) : h('p', {}, t('hero.builds.nocurrent')),
        old.length ? h('details', { class: 'fold oldbuilds' }, h('summary', {}, h('span', { class: 'chip sample' }, t('hero.builds.old.chip')), ' ', tn('hero.builds.old', old.length)),
          h('p', { class: 'dim small note' }, t('hero.builds.old.note')), old.map(buildBlock)) : null,
        file.buildsPage ? h('p', { class: 'small gap' }, t('hero.builds.source') + ' ', out(wikiUrl(file.buildsPage), t('link.wikibuilds')), ' · ', out(D.manifest.source.licenceUrl, D.manifest.source.licence)) : null],
    h('p', { class: 'small gap' }, t('hero.more') + ' ', out(wikiUrl(hero.page), t('link.wiki')), ' · ', out(game8(hero), t('link.game8')))], { i: 3 });
}

/** @param {Hero} hero @param {any} file */
function bannersPanel(hero, file) {
  /** @type {any[]|null} */
  const banners = file.banners;
  const at = now();
  /** @param {any} b */
  const row = b => h('li', {}, h('b', {}, b.n), h('span', { class: 'dim small', title: fmtUtc(b.s) + ' – ' + fmtUtc(b.e) }, fmtDay(b.s) + ' – ' + fmtDay(b.e)),
    isLive(b, at) ? h('span', { class: 'chip ok' }, t('summon.now')) : isUpcoming(b, at) ? h('span', { class: 'chip teal' }, t('summon.soon')) : null);
  return panel(t('hero.banners'), [h('p', {}, t('avail.' + hero.av)),
    banners == null ? h('p', { class: 'dim' }, t('hero.banners.unknown'))
      : !banners.length ? h('p', { class: 'dim' }, t('hero.nobanners', { date: fmtDate(D.manifest.bannersFrom) }))
      : [h('ul', { class: 'rows' }, banners.slice(0, 8).map(row)),
        banners.length > 8 ? h('details', { class: 'srcfold' }, h('summary', {}, tn('hero.banners.more', banners.length - 8)), h('ul', { class: 'rows' }, banners.slice(8).map(row))) : null]], { i: 4 });
}

/** @param {Hero} hero */
function statsPanel(hero) {
  const med = median(), total = D.heroes.length;
  return panel(t('hero.stats'), [h('div', { class: 'stats' }, STATS.map((key, i) => {
    const [rank, same] = D.ranks[i].get(hero.s[i]) || [0, 1];
    const val = h('span', { class: 'val num' }, hero.s[i]);
    countUp(val, hero.s[i], 320 + i * 50);
    return h('div', { class: 'stat ' + key, style: { '--i': i } }, h('span', { class: 'lab' }, t('stat.' + key)), val,
      h('span', { class: 'bar', style: { '--m': (med[i] / D.max[i]).toFixed(3) } }, h('span', { class: 'fill', style: { '--v': Math.min(1, hero.s[i] / D.max[i]).toFixed(3) } }), h('span', { class: 'tick' })),
      h('span', { class: 'rank num' + (rank <= total * .1 ? ' top' : rank > total * .9 ? ' low' : ''), title: same > 1 ? t('hero.rank.shared', { n: rank, same, total }) : t('hero.rank', { n: rank, total }) }, '#' + rank));
  })), h('p', { class: 'statnote' }, h('span', {}, t('hero.statnote', { bst: hero.bst })), h('span', { class: 'key' }, h('i', {}), t('hero.median', { total })))],
  { more: h('span', { class: 'count num' }, t('hero.total', { bst: hero.bst })), i: 1 });
}

/** @param {Hero} hero @param {any} file null while loading */
function standingPanel(hero, file) {
  const s = standing(hero, file);
  return panel(t('st.title'), [h('p', { class: 'dim small note' }, t('st.sub')),
    h('div', { class: 'chips' }, s.chips.map(c => h('span', { class: 'chip ' + (c.cls || '') }, c.text))),
    h('ul', { class: 'facts' }, s.lines.map(l => h('li', { class: l.cls || '' }, h('span', {}, l.cls === 'paidline' ? [h('span', { class: 'chip sample' }, t('bn.paid.chip')), ' '] : null, l.text)))),
    h('p', { class: 'small gap' }, t('st.game8') + ' ', out(game8(hero), t('st.game8.link')))],
  { more: h('a', { class: 'more', href: game8(hero), target: '_blank', rel: 'noopener' }, 'Game8 ›'), i: 2 });
}

export const page = {
  nav: 'heroes',
  /** @param {string} arg */
  title: arg => { const hero = findHero(arg); return hero ? fullName(hero) : t('hero.unknown'); },
  /** @param {HTMLElement} el @param {string} arg */
  render(el, arg) {
    const back = h('div', { class: 'hero-nav' }, h('a', { class: 'back', href: '#/heroes' }, '‹ ' + t('nav.heroes')));
    const hero = findHero(arg);
    if (!hero) { put(el, back, h('div', { class: 'panel', role: 'alert' }, h('div', { class: 'panel-body' }, h('h1', { class: 'errtitle' }, t('hero.unknown')), h('p', {}, t('hero.unknown.text'))))); return; }

    const total = D.heroes.length;
    const getline = h('div', { class: 'getline' });
    /** @param {any[]|null} banners the hero's banner history, null while unknown */
    const drawGet = banners => {
      const at = now(), live = (banners || []).filter(b => isLive(b, at)).sort((a, b) => a.e - b.e)[0];
      put(getline, live ? [h('span', { class: 'dot now' }), h('div', {}, h('b', {}, t('hero.get.now', { name: live.n })), h('small', { title: fmtUtc(live.e) }, t('hero.get.ends', { end: endText(live.e) })), h('small', {}, h('a', { href: '#/summon' }, t('hero.get.summon') + ' ›'))), endsChip(live, at)]
        : [h('span', { class: 'dot' }), h('div', {}, h('b', {}, t('avail.' + hero.av)), h('small', {}, banners == null ? t('hero.get.loading') : t('hero.get.none')))]);
    };
    drawGet(null);

    const ownbar = h('div', { class: 'ownbar' });
    const drawOwn = () => {
      const e = store.entry(hero.id);
      const seal = h('span', { class: 'seal' + (e ? ' on' : '') });
      const btn = h('button', { type: 'button', class: 'btn primary ownbtn', 'aria-pressed': e ? 'true' : 'false', onclick: () => {
        const r = store.toggle(hero.id);
        drawOwn();
        const again = /** @type {HTMLElement|null} */ (ownbar.querySelector('.ownbtn'));
        if (again) again.focus();
        if (r.added) { const s2 = ownbar.querySelector('.seal'); replay(s2, 'pop'); sparkFx(s2); if (hero.av !== 'pool34') flourish(hero.c); toast(t('toast.added', { name: hero.n })); }
        else toast(t('toast.removed', { name: hero.n }), { action: { label: t('undo'), run: () => { r.undo(); drawOwn(); } } });
      } }, seal, t(e ? 'box.inbox' : 'hero.own'));
      put(ownbar, h('div', { class: 'who' }, face(hero), h('span', {}, fullName(hero))),
        e ? [h('label', { class: 'field inline' }, h('span', {}, t('box.merges')), mergeInput(e.m, v => store.setMerges(hero.id, v))),
          h('label', { class: 'field inline' }, h('span', {}, t('box.rarity')), raritySelect(e.r, r => store.setRarity(hero.id, r)))] : null,
        btn);
    };
    drawOwn();

    const waiting = () => h('section', { class: 'panel' }, h('div', { class: 'panel-body' }, h('p', { class: 'dim' }, t('loading'))));
    const kitSlot = h('div', { class: 'stack' }, waiting());
    const standSlot = h('div', {}, standingPanel(hero, null));
    const more = h('div', { class: 'stack gapt' });

    put(el, back,
      h('section', { class: 'panel framed' }, h('span', { class: 'corner tl' }), h('span', { class: 'corner tr' }), h('span', { class: 'corner bl' }), h('span', { class: 'corner br' }),
        h('div', { class: 'hero-head' }, artBox(hero),
          h('div', { class: 'hero-id' },
            h('div', { class: 'slide' }, h('h1', { class: 'hero-name' }, hero.n), h('p', { class: 'hero-epithet' }, hero.ti)),
            h('div', { class: 'badge-row pops' }, h('span', { class: 'c-' + hero.c, style: { '--i': 0 } }, wb(hero), hero.w), h('span', { style: { '--i': 1 } }, mv(hero), hero.m)),
            getline,
            h('div', { class: 'quick', 'aria-hidden': 'true' }, STATS.map((key, i) => { const rank = (D.ranks[i].get(hero.s[i]) || [0])[0]; return h('span', { class: 'plate' + (rank <= total * .1 ? ' hi' : rank > total * .9 ? ' lo' : '') }, h('span', {}, t('stat.' + key)), h('b', { class: 'num' }, hero.s[i])); })),
            h('div', { class: 'chips pops' }, tagsOf(hero).map(tagChip), hero.o.map(o => h('span', { class: 'chip parch' }, o)), hero.r ? h('span', { class: 'chip' }, t('hero.released', { date: fmtDate(hero.r) })) : null),
            h('p', { class: 'credit' }, hero.art ? [t('hero.art.by') + ' ', h('b', {}, hero.art), ' · '] : null, t('hero.art.owner'), ' ', h('a', { href: '#/guide/about' }, t('hero.art.removal'))))) ),
      h('div', { class: 'cols-2 gapt' }, kitSlot, h('div', { class: 'stack' }, statsPanel(hero), standSlot)),
      more, ownbar);
    enter(el);

    // the hero's own file: a failure here leaves the page standing and offers another try
    const load = () => needHero(hero.id).then(file => {
      put(kitSlot, kitPanel(hero, file), buildsPanel(hero, file));
      put(standSlot, standingPanel(hero, file));
      put(more, bannersPanel(hero, file));
      drawGet(Array.isArray(file.banners) ? file.banners : []);
    }, e => {
      put(kitSlot, h('section', { class: 'panel', role: 'alert' }, h('div', { class: 'panel-body' }, h('p', {}, t('hero.details.failed')), h('p', { class: 'dim small' }, String(e && e.message || e)),
        h('button', { class: 'btn', type: 'button', onclick: () => { put(kitSlot, waiting()); load(); } }, t('err.retry')))));
    });
    return load();
  },
};
