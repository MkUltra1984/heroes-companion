// @ts-check
// Game time. Every time in the data is a UTC instant in epoch seconds. The game day changes at 07:00 UTC:
// banners and quests start at 07:00:00 and end at 06:59:59.

export const DAY = 86400;
export const RESET = 7 * 3600;

/** The current instant in epoch seconds. Tests set window.__hcNow to move the clock. */
export function now() {
  const fake = typeof window !== 'undefined' ? /** @type {any} */ (window).__hcNow : undefined;
  return typeof fake === 'number' && isFinite(fake) ? Math.floor(fake) : Math.floor(Date.now() / 1000);
}

/** Number of the game day an instant belongs to. @param {number} ts */
export const gameDay = ts => Math.floor((ts - RESET) / DAY);
/** The game's calendar date of an instant as YYYY-MM-DD. @param {number} ts */
export const gameDate = ts => new Date((ts - RESET) * 1000).toISOString().slice(0, 10);
/** The next day change after an instant. @param {number} ts */
export const nextReset = ts => (gameDay(ts) + 1) * DAY + RESET;

/** @typedef {{ s: number, e: number }} Span  start and end, both inclusive */
/** @param {Span} x @param {number} [t] */
export const isLive = (x, t = now()) => x.s <= t && t <= x.e;
/** @param {Span} x @param {number} [t] */
export const isUpcoming = (x, t = now()) => x.s > t;
/** @param {Span} x @param {number} [t] */
export const hasEnded = (x, t = now()) => t > x.e;
/** Full game days left after the current one; 0 means it ends with the current game day. @param {Span} x @param {number} [t] */
export const daysLeft = (x, t = now()) => gameDay(x.e) - gameDay(t);
/** Seconds until the end, never negative. @param {Span} x @param {number} [t] */
export const secondsLeft = (x, t = now()) => Math.max(0, x.e - t);

const LOCALE = 'en-GB';
const fmt = (/** @type {Intl.DateTimeFormatOptions} */ o) => new Intl.DateTimeFormat(LOCALE, o);
const F = {
  day: fmt({ day: 'numeric', month: 'short', year: 'numeric' }),
  dayUtc: fmt({ day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }),
  short: fmt({ day: 'numeric', month: 'short' }),
  time: fmt({ hour: '2-digit', minute: '2-digit' }),
  dayTime: fmt({ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }),
  utc: fmt({ day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }),
  utcShort: fmt({ day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }),
  utcTime: fmt({ hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }),
};
const safe = (/** @type {Intl.DateTimeFormat} */ f, /** @type {number} */ ms) => isFinite(ms) ? f.format(new Date(ms)) : '';

/** An instant as a date in the visitor's time zone: "15 Nov 2026". @param {number} ts */
export const fmtDay = ts => safe(F.day, ts * 1000);
/** "15 Nov" @param {number} ts */
export const fmtShort = ts => safe(F.short, ts * 1000);
/** "07:59" in the visitor's time zone. @param {number} ts */
export const fmtTime = ts => safe(F.time, ts * 1000);
/** "15 Nov, 07:59" in the visitor's time zone. @param {number} ts */
export const fmtDayTime = ts => safe(F.dayTime, ts * 1000);
/** "15 Nov 2026, 06:59 UTC": the exact instant, for tooltips. @param {number} ts */
export const fmtUtc = ts => { const s = safe(F.utc, ts * 1000); return s ? s + ' UTC' : ''; };
/** "16 Nov, 07:00" in UTC, the way the game states its times. @param {number} ts */
export const fmtUtcShort = ts => safe(F.utcShort, ts * 1000);
/** "07:00" in UTC. @param {number} ts */
export const fmtUtcTime = ts => safe(F.utcTime, ts * 1000);
/** A calendar date from the data ("2026-11-06" or an ISO instant) as "6 Nov 2026". @param {string} d */
export const fmtDate = d => d ? safe(F.dayUtc, Date.parse(d.length === 10 ? d + 'T00:00:00Z' : d)) : '';
/** Whole days between an ISO instant and now. @param {string} isoText @param {number} [t] */
export const ageDays = (isoText, t = now()) => { const ms = Date.parse(isoText); return isFinite(ms) ? Math.floor((t - ms / 1000) / DAY) : NaN; };
