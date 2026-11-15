// @ts-check
// Everything the visitor saves: barracks, teams, orb count, settings. It lives in this browser only (localStorage).
//
//   key "hc.v2":  { v: 2, box: { "<hero id>": { m: merges 0-10, r: rarity 1-5 } }, teams: [{ name, ids: [id|null x4] }],
//                   orbs: 0-99999, prefs: { fehPass: boolean, art: boolean }, unmapped: { "<old wiki name>": { m, r } },
//                   pulls: { "<banner id>": summons made there, 0-9999 } }
//
// Heroes are keyed by the game's own number (the wiki's IntID), which survives a rename on the wiki.
// Rules: whatever is read (from storage or from a file) goes through sanitize() first, so no page ever sees a broken shape;
// every change is applied to a fresh read of the storage, so two open tabs do not overwrite each other;
// a browser that refuses to store keeps working in memory and says so.

export const VERSION = 2;
export const LIMITS = { merges: 10, rarity: 5, orbs: 99999, pulls: 9999, banners: 300, teams: 60, teamName: 40, heroes: 6000, fileBytes: 1000000 };
const KEY = 'hc.v2', BACKUP = 'hc.backup', BROKEN = 'hc.broken';
const LEGACY = ['hc.box', 'hc.teams', 'hc.orbs'];          // the concept version: three keys, heroes keyed by wiki name

/** @typedef {{ m: number, r: number }} Entry */
/** @typedef {{ name: string, ids: (number|null)[] }} Team */
/** @typedef {{ v: number, box: Record<string, Entry>, teams: Team[], orbs: number, prefs: { fehPass: boolean, art: boolean }, unmapped: Record<string, Entry>, pulls: Record<string, number> }} State */

/** @param {any} v */
const isObj = v => v != null && typeof v === 'object' && !Array.isArray(v);
/** @returns {State} */
export const empty = () => ({ v: VERSION, box: {}, teams: [], orbs: 0, prefs: { fehPass: false, art: true }, unmapped: {}, pulls: {} });

/** A whole number inside [lo, hi]; anything that is not a number becomes dflt. @param {any} v @param {number} lo @param {number} hi @param {number} [dflt] */
export function clampInt(v, lo, hi, dflt = lo) {
  const n = typeof v === 'number' ? v : (typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);
  if (Number.isNaN(n)) return dflt;
  return Math.min(hi, Math.max(lo, Math.trunc(n)));
}
/** @param {any} k @returns {number} a hero id, or 0 */
const asId = k => (typeof k === 'number' ? Number.isInteger(k) && k > 0 && k < 1e7 : typeof k === 'string' && /^[1-9]\d{0,6}$/.test(k)) ? Number(k) : 0;
/** @param {any} e @returns {Entry|null} */
const asEntry = e => isObj(e) ? { m: clampInt(e.m, 0, LIMITS.merges, 0), r: clampInt(e.r, 1, LIMITS.rarity, 5) } : null;

/**
 * Any value -> a valid state. Never throws. Entries that cannot be understood are counted in `dropped`.
 * @param {any} raw @param {(name: string) => number|undefined} [mapName] old wiki name -> hero id
 * @returns {{ state: State, dropped: number }}
 */
export function sanitize(raw, mapName) {
  const state = empty(); let dropped = 0;
  if (!isObj(raw)) return { state, dropped: raw == null ? 0 : 1 };
  /** @param {any} src */
  const takeBox = src => {
    if (src == null) return;
    if (!isObj(src)) { dropped++; return; }
    let n = 0;
    for (const [k, v] of Object.entries(src)) {
      if (++n > LIMITS.heroes) { dropped++; continue; }
      const entry = asEntry(v);
      if (!entry) { dropped++; continue; }
      const id = asId(k) || (mapName && mapName(k)) || 0;
      if (id) state.box[String(id)] = entry;
      else if (k && k.length <= 120) state.unmapped[k] = entry;      // a name the data does not know: kept, shown, removable
      else dropped++;
    }
  };
  takeBox(raw.box); takeBox(raw.unmapped);
  if (raw.teams != null && !Array.isArray(raw.teams)) dropped++;
  for (const team of Array.isArray(raw.teams) ? raw.teams : []) {
    if (!isObj(team) || state.teams.length >= LIMITS.teams) { dropped++; continue; }
    /** @type {(number|null)[]} */
    const ids = [];
    for (const x of (Array.isArray(team.ids) ? team.ids : []).slice(0, 4)) {
      const id = asId(x) || (typeof x === 'string' && mapName && mapName(x)) || 0;
      ids.push(id && !ids.includes(id) ? id : null);
    }
    while (ids.length < 4) ids.push(null);
    state.teams.push({ name: typeof team.name === 'string' ? team.name.trim().slice(0, LIMITS.teamName) : '', ids });
  }
  state.orbs = clampInt(raw.orbs, 0, LIMITS.orbs, 0);
  state.prefs.fehPass = isObj(raw.prefs) && raw.prefs.fehPass === true;
  state.prefs.art = !(isObj(raw.prefs) && raw.prefs.art === false);        // game artwork is shown unless switched off
  if (isObj(raw.pulls)) {
    let n = 0;
    for (const [k, v] of Object.entries(raw.pulls)) {
      const c = clampInt(v, 0, LIMITS.pulls, 0);
      if (c > 0 && k.length <= 120 && k !== '__proto__' && ++n <= LIMITS.banners) state.pulls[k] = c;
    }
  }
  return { state, dropped };
}

// ---- storage access: every call guarded, because a browser may forbid storage altogether --------------------------
/** @param {string} key @returns {string|null} */
function readRaw(key) { try { return window.localStorage.getItem(key); } catch { return null; } }
/** @param {string} key @param {string} text */
function writeRaw(key, text) { try { window.localStorage.setItem(key, text); return true; } catch { return false; } }
/** @param {string|null} text @returns {any} undefined when it is not JSON */
function parse(text) { if (text == null) return undefined; try { return JSON.parse(text); } catch { return undefined; } }

/** @type {State} */
let state = empty();
/** @type {(name: string) => number|undefined} */
let mapName = () => undefined;
/** @type {Set<(why: 'local'|'external'|'blocked') => void>} */
const subs = new Set();
let listening = false;
/** @param {'local'|'external'|'blocked'} why */
const emit = why => { for (const fn of [...subs]) { try { fn(why); } catch (e) { console.error(e); } } };

/** Reads the stored state. @returns {{ state: State, note: ''|'corrupt'|'dropped'|'migrated' }|null} null: nothing stored */
function load() {
  const text = readRaw(KEY);
  if (text != null) {
    const raw = parse(text);
    if (!isObj(raw)) { writeRaw(BROKEN, text.slice(0, LIMITS.fileBytes)); return { state: empty(), note: 'corrupt' }; }
    const r = sanitize(raw, mapName);
    return { state: r.state, note: r.dropped ? 'dropped' : '' };
  }
  const old = LEGACY.map(k => parse(readRaw(k)));
  if (old.some(v => v !== undefined)) {
    const r = sanitize({ box: isObj(old[0]) ? old[0] : {}, teams: Array.isArray(old[1]) ? old[1] : [], orbs: old[2] }, mapName);
    return { state: r.state, note: 'migrated' };          // the old keys stay where they are, as a copy
  }
  return null;
}
const persist = () => writeRaw(KEY, JSON.stringify(state));

export const store = {
  /** true once the browser refused to save */
  blocked: false,
  get state() { return state; },

  /**
   * Call once, after the hero index is loaded. @param {{ mapName?: (name: string) => number|undefined }} [opt]
   * @returns {''|'corrupt'|'dropped'|'migrated'} what happened to the stored data, for a notice
   */
  init(opt = {}) {
    if (opt.mapName) mapName = opt.mapName;
    const got = load();
    state = got ? got.state : empty();
    if (got && got.note && !persist()) this.blocked = true;        // write the repaired or migrated form back
    try { const probe = 'hc.probe'; window.localStorage.setItem(probe, '1'); window.localStorage.removeItem(probe); } catch { this.blocked = true; }
    if (!listening) {
      listening = true;
      window.addEventListener('storage', e => {             // another tab changed something
        if (e.key !== null && e.key !== KEY) return;
        const fresh = load();
        state = fresh ? fresh.state : empty();
        emit('external');
      });
    }
    return got ? got.note : '';
  },

  /** @param {(why: 'local'|'external'|'blocked') => void} fn */
  subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },

  /**
   * One change: read what is stored now, apply fn, validate, write. @param {(s: State) => void} fn
   * @returns {boolean} false when the browser did not save (the change still holds in this tab)
   */
  update(fn) {
    const raw = parse(readRaw(KEY));
    const fresh = !this.blocked && isObj(raw) ? sanitize(raw, mapName).state : state;   // blocked: the memory copy is the newest
    fn(fresh);
    state = sanitize(fresh, mapName).state;
    const ok = persist();
    if (!ok && !this.blocked) { this.blocked = true; emit('blocked'); }
    emit('local');
    return ok;
  },

  // ---- barracks ----
  /** @param {number} id */
  has(id) { return Object.prototype.hasOwnProperty.call(state.box, String(id)); },
  /** @param {number} id @returns {Entry|undefined} */
  entry(id) { return this.has(id) ? state.box[String(id)] : undefined; },
  /** @returns {number[]} */
  ids() { return Object.keys(state.box).map(Number); },
  count() { return Object.keys(state.box).length; },
  /**
   * Adds or removes a hero. Removing also empties the hero's team slots; undo() puts both back.
   * @param {number} id @returns {{ added: boolean, undo: () => void }}
   */
  toggle(id) {
    const key = String(id);
    const before = this.entry(id);
    const slots = state.teams.map(team => team.ids.indexOf(id));
    this.update(s => {
      if (before) { delete s.box[key]; for (const team of s.teams) team.ids = team.ids.map(x => x === id ? null : x); }
      else s.box[key] = { m: 0, r: 5 };
    });
    return {
      added: !before,
      undo: () => this.update(s => {
        if (!before) { delete s.box[key]; return; }
        s.box[key] = before;
        slots.forEach((slot, i) => { if (slot >= 0 && s.teams[i] && s.teams[i].ids[slot] == null && !s.teams[i].ids.includes(id)) s.teams[i].ids[slot] = id; });
      }),
    };
  },
  /** @param {number} id @param {any} v @returns {number} the value that was stored */
  setMerges(id, v) { const m = clampInt(v, 0, LIMITS.merges, 0); this.update(s => { if (s.box[String(id)]) s.box[String(id)].m = m; }); return m; },
  /** @param {number} id @param {any} v */
  setRarity(id, v) { const r = clampInt(v, 1, LIMITS.rarity, 5); this.update(s => { if (s.box[String(id)]) s.box[String(id)].r = r; }); return r; },
  /** An entry whose hero the data does not know. @param {string} key an id or an old wiki name */
  forget(key) { this.update(s => { delete s.box[key]; delete s.unmapped[key]; }); },

  // ---- orbs and settings ----
  /** @param {any} v @returns {number} the value that was stored */
  setOrbs(v) { const n = clampInt(v, 0, LIMITS.orbs, 0); this.update(s => { s.orbs = n; }); return n; },
  /** @param {'fehPass'|'art'} key @param {boolean} on */
  setPref(key, on) { this.update(s => { s.prefs[key] = !!on; }); },
  /** Summons the visitor made on one banner (for the free pick after 40). @param {string} banner @returns {number} */
  pulls(banner) { return Object.prototype.hasOwnProperty.call(state.pulls, banner) ? state.pulls[banner] : 0; },
  /** @param {string} banner @param {any} v @returns {number} the value that was stored */
  setPulls(banner, v) { const n = clampInt(v, 0, LIMITS.pulls, 0); this.update(s => { if (n) s.pulls[banner] = n; else delete s.pulls[banner]; }); return n; },
  /** Marks or unmarks many heroes in one step (marking mode). @param {Record<string, boolean>} changes hero id -> owned */
  setMany(changes) {
    return this.update(s => {
      for (const [key, on] of Object.entries(changes)) {
        if (on) { if (!s.box[key]) s.box[key] = { m: 0, r: 5 }; }
        else if (s.box[key]) { delete s.box[key]; const id = Number(key); for (const team of s.teams) team.ids = team.ids.map(x => x === id ? null : x); }
      }
    });
  },

  // ---- teams ----
  /** @param {string} name */
  addTeam(name) { this.update(s => { if (s.teams.length < LIMITS.teams) s.teams.push({ name, ids: [null, null, null, null] }); }); },
  /** @param {number} i */
  deleteTeam(i) { this.update(s => { s.teams.splice(i, 1); }); },
  /** @param {number} i @param {string} name */
  renameTeam(i, name) { this.update(s => { if (s.teams[i]) s.teams[i].name = String(name); }); },
  /** @param {number} i @param {number} slot 0-3 @param {number|null} id */
  setSlot(i, slot, id) { this.update(s => { if (s.teams[i] && slot >= 0 && slot < 4) s.teams[i].ids[slot] = id; }); },

  // ---- backup file ----
  exportText() { return JSON.stringify({ app: 'heroes-companion', saved: new Date().toISOString(), ...state }); },
  /**
   * Checks a backup file's text. Nothing is changed yet.
   * @param {string} text
   * @returns {{ ok: false, error: 'toobig'|'badfile' } | { ok: true, state: State, heroes: number, teams: number, unknown: number, dropped: number }}
   */
  parseImport(text) {
    if (typeof text !== 'string' || text.length > LIMITS.fileBytes) return { ok: false, error: 'toobig' };
    const raw = parse(text);
    if (!isObj(raw) || !isObj(raw.box)) return { ok: false, error: 'badfile' };
    const r = sanitize(raw, mapName);
    return { ok: true, state: r.state, heroes: Object.keys(r.state.box).length, teams: r.state.teams.length, unknown: Object.keys(r.state.unmapped).length, dropped: r.dropped };
  },
  /** @param {State} next a state from parseImport @param {'replace'|'merge'} mode */
  applyImport(next, mode) {
    writeRaw(BACKUP, JSON.stringify(state));                // one step back, kept in the browser
    return this.update(s => {
      if (mode === 'replace') { s.box = next.box; s.teams = next.teams; s.orbs = next.orbs; s.prefs = next.prefs; s.unmapped = next.unmapped; s.pulls = next.pulls; return; }
      Object.assign(s.box, next.box); Object.assign(s.unmapped, next.unmapped);
      s.teams.push(...next.teams);
    });
  },
  /** Deletes everything saved, after keeping one copy under hc.backup. */
  reset() {
    writeRaw(BACKUP, JSON.stringify(state));
    try { window.localStorage.removeItem(KEY); for (const k of LEGACY) window.localStorage.removeItem(k); } catch { /* blocked storage: memory is cleared below */ }
    state = empty();
    emit('local');
  },
};
