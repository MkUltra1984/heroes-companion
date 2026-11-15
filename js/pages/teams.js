// @ts-check
// Teams of four from the barracks. Part of the Barracks destination.
import { h, put } from '../dom.js';
import { t } from '../i18n.js';
import { D } from '../data.js';
import { store, LIMITS } from '../store.js';
import { artImg, artUrl, face, mv, wb } from '../art.js';
import { enter } from '../motion.js';
import { emptyState, heroLink, pageHead, tagChip } from '../shared.js';
import { barracksTabs } from './barracks.js';

/** @typedef {import('../data.js').Hero} Hero */

export const page = {
  nav: 'barracks',
  title: () => t('teams.title'),
  /** @param {HTMLElement} el */
  render(el) {
    const draw = () => {
      const pool = D.heroes.filter(x => store.has(x.id)).sort((a, b) => a.n.localeCompare(b.n));
      const teams = store.state.teams;
      put(el, pageHead(t('teams.title'), t('teams.sub')), barracksTabs('teams'),
        h('div', { class: 'stack gapt' }, teams.map((team, ti) => {
          const members = /** @type {Hero[]} */ (team.ids.map(id => id == null ? undefined : D.byId.get(id)).filter(Boolean));
          const colors = new Set(members.map(x => x.c)), moves = new Set(members.map(x => x.m));
          return h('section', { class: 'panel team rise', style: { '--i': Math.min(ti, 6) } },
            h('div', { class: 'panel-head' }, h('input', { type: 'text', value: team.name, maxlength: LIMITS.teamName, 'aria-label': t('teams.name'), class: 'teamname', onchange: (/** @type {any} */ e) => store.renameTeam(ti, e.target.value) }),
              h('button', { class: 'btn small', type: 'button', onclick: () => { store.deleteTeam(ti); draw(); } }, t('teams.delete'))),
            h('div', { class: 'panel-body' },
              h('div', { class: 'teamrow' }, [0, 1, 2, 3].map(i => {
                const id = team.ids[i];
                const hero = id == null ? undefined : D.byId.get(id);
                if (hero) {
                  const stage = h('span', { class: 'sprite-stage small', 'aria-hidden': 'true', });
                  const idle = artImg(artUrl(hero, 'i'), { class: 'sprite still' });
                  if (idle) { stage.append(idle); idle.addEventListener('error', () => { stage.hidden = true; }); }
                  return h('div', { class: 'slotbox' }, h('div', { class: 'slothead' }, h('span', { class: 'mini' }, face(hero)), idle ? stage : null),
                    h('b', {}, heroLink(hero)), h('small', { class: 'dim' }, hero.ti), h('span', { class: 'cellbadge' }, wb(hero), mv(hero)),
                    h('button', { class: 'link small', type: 'button', onclick: () => { store.setSlot(ti, i, null); draw(); } }, t('teams.remove')));
                }
                return h('div', { class: 'slotbox emptyslot' }, id != null ? h('div', { class: 'dim small' }, t('box.lost.id', { id })) : null,
                  h('select', { 'aria-label': t('teams.pick'), onchange: (/** @type {any} */ e) => { store.setSlot(ti, i, Number(e.target.value) || null); draw(); } },
                    h('option', { value: '' }, t('teams.pick')), pool.filter(x => !team.ids.includes(x.id)).map(x => h('option', { value: x.id }, x.n + ': ' + x.ti))));
              })),
              members.length ? h('div', { class: 'chips gap' }, [...colors].map(c => h('span', { class: 'chip c-' + c }, t('color.' + c))), [...moves].map(m => h('span', { class: 'chip' }, m)),
                h('span', { class: 'chip' }, t('teams.bst', { n: members.reduce((a, x) => a + x.bst, 0) })),
                ['legendary', 'mythic', 'duo', 'harmonized', 'emblem'].map(tag => members.some(x => x.p.includes(tag)) ? tagChip(tag) : null),
                colors.size < Math.min(3, members.length) ? h('span', { class: 'chip sample warnchip' }, t('teams.samecolor')) : null) : null));
        })),
        pool.length ? (teams.length < LIMITS.teams ? h('p', { class: 'gap' }, h('button', { class: 'btn primary', type: 'button', onclick: () => { store.addTeam(t('teams.new') + ' ' + (teams.length + 1)); draw(); } }, t('teams.add'))) : null)
          : h('section', { class: 'panel gapt' }, emptyState(t('teams.empty.title'), t('teams.needbox'), h('a', { class: 'btn primary', href: '#/heroes/mark' }, t('mark.start')))));
      enter(el);
    };
    draw();
  },
};
