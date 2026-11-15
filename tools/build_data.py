"""Turns the cached wiki tables (tools/cache, see fetch_all.py) into the files the site loads (site/data).

    python -I tools/build_data.py [--cache DIR] [--out DIR] [--min-heroes N] [--allow-drop]

What it writes (format version 2, described in reviews/round2/foundation.md):
    manifest.json     build time, age of the data, which tables were there, counts
    heroes.json       compact index of every hero (list fields, level 40 stats, availability code)
    hero/<id>.json    one small file per hero: skills, wiki builds, banner history
    banners.json      banners that run, are coming, or ended in the last 60 days
    orbs.json         orb rewards of quests that have not ended, free and Feh Pass apart
    meta.json         lists for the guide page

Rules:
  - Required tables (Units, UnitStats, SummoningEvents) must be there, or nothing is written.
  - Optional tables (HeroBuilds, QuestRewards, Skills, UnitSkills, SummoningEventFocuses) may be missing or still
    downloading; the manifest then marks them "missing" and the site says "unknown", never "none".
  - Output is built in a temporary folder, checked, and only then swapped in. A failed check leaves site/data as it was.
  - All times are UTC instants (epoch seconds). The game day changes at 07:00 UTC.
"""
import argparse, collections, datetime, html, io, json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = 2
REQUIRED = ('Units', 'UnitStats', 'SummoningEvents')
OPTIONAL = ('HeroBuilds', 'QuestRewards', 'Skills', 'UnitSkills', 'SummoningEventFocuses')
UTC = datetime.timezone.utc
STAT_KEYS = ('HP', 'Atk', 'Spd', 'Def', 'Res')
MARTH = [41, 31, 34, 29, 23]            # Marth: Altean Prince at level 40 as the game shows him: a fixed check


class BuildError(Exception):
    """A validation gate refused the build. Nothing is written."""


# ---- small helpers -----------------------------------------------------------------------------------------------
def num(x, d=0):
    try: return int(float(x))
    except (TypeError, ValueError): return d

def epoch(s):
    """'2026-11-15 06:59:59' (the wiki stores UTC) -> epoch seconds, or None."""
    m = re.match(r'(\d{4})-(\d\d)-(\d\d)(?:[ T](\d\d):(\d\d)(?::(\d\d))?)?', str(s or ''))
    if not m: return None
    y, mo, d, h, mi, sec = (int(x) if x else 0 for x in m.groups())
    try: return int(datetime.datetime(y, mo, d, h, mi, sec, tzinfo=UTC).timestamp())
    except (ValueError, OverflowError): return None

def iso(ts):
    return datetime.datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

def game_date(ts):
    """The game's calendar date of an instant: the day changes at 07:00 UTC."""
    return datetime.datetime.fromtimestamp(ts - 7 * 3600, UTC).strftime('%Y-%m-%d')


# ---- wiki text -> plain text -------------------------------------------------------------------------------------
# A real tag: only names HTML knows, so that "Spd<foe's Spd ... Atk>5" in a skill text is never taken for one.
# Attribute values hold only escaped entities ('&gt;'), which is why tags are removed before entities are un-escaped.
_TAG = re.compile(r'</?(?:span|small|big|sup|sub|div|p|b|i|u|s|em|strong|font|center|code|nowiki|ref|a|img|hr|li|ul|ol|dl|dt|dd|table|tbody|tr|td|th|h[1-6])\b[^<>]*>', re.I)
_BREAK = re.compile(r'<\s*br\s*/?\s*>|</\s*(?:p|div|li|tr)\s*>', re.I)
_LINK = re.compile(r'\[\[([^\[\]]*)\]\]')
_EXT = re.compile(r'\[(?:https?:)?//[^\s\]]+\s*([^\]]*)\]')
_STAMP = re.compile(r'(\d\d):(\d\d), (\d{1,2}) ([A-Z][a-z]+) (\d{4}) \(UTC\)')
_DROP_NS = ('file:', 'image:', 'category:', 'user:', 'user talk:', 'userprofile:', 'special:', 'user blog:', 'message wall:')
_MONTHS = {m: i + 1 for i, m in enumerate('January February March April May June July August September October November December'.split())}

def clean(s):
    """Wiki text with HTML and wiki markup -> plain text. Paragraphs are separated by one line feed.
    Order matters: tags are removed while entities are still escaped (a tooltip's title attribute may hold '&gt;'),
    wiki links next, entities last."""
    s = str(s or '')
    if not s: return ''
    s = _BREAK.sub('\n', s)
    s = _TAG.sub('', s)
    while True:                                             # templates, innermost first
        t = re.sub(r'\{\{[^{}]*\}\}', '', s)
        if t == s: break
        s = t
    def link(m):
        parts = m.group(1).split('|')
        target = parts[0].strip().lstrip(':')
        if target.lower().startswith(_DROP_NS): return ''
        return parts[-1].strip() if len(parts) > 1 else target
    while True:                                             # links, innermost first
        t = _LINK.sub(link, s)
        if t == s: break
        s = t
    s = _EXT.sub(lambda m: m.group(1), s)
    s = s.replace('[[', '').replace(']]', '').replace('{{', '').replace('}}', '')
    for _ in range(3):                                      # some texts are escaped twice (&amp;gt;)
        t = html.unescape(s)
        if t == s: break
        s = t
    s = _TAG.sub('', _BREAK.sub('\n', s))                   # tags that were themselves escaped (&lt;br&gt;)
    s = s.replace(chr(0xA0), ' ').replace(chr(0x200B), '')        # no-break and zero-width spaces
    s = re.sub(r"'{2,}", '', s)
    s = _STAMP.sub('', s)                                   # what is left of a signature: "(talk) 05:41, 25 January 2021 (UTC)"
    s = re.sub(r'\(\s*(?:talk|contribs)?\s*(?:[•|·]\s*(?:talk|contribs)?\s*)*\)', '', s)
    s = re.sub(r'~{3,5}', '', s)
    lines = []
    for line in s.split('\n'):
        line = re.sub(r'^\s*=+\s*(.*?)\s*=+\s*$', r'\1', line)         # == heading ==
        line = re.sub(r'^\s*[*#:;]+\s*', '', line)                      # list and indent marks
        line = re.sub(r'[ \t\r\f\v]+', ' ', line).strip()
        if line and not re.fullmatch(r'[-–—\s]*', line): lines.append(line)
    return '\n'.join(lines)

def one_line(s):
    return clean(s).replace('\n', ' ')

def signed_date(raw):
    """The newest wiki signature date in a raw text ('05:41, 25 January 2021 (UTC)') as 'YYYY-MM-DD', or ''."""
    best = ''
    for m in _STAMP.finditer(str(raw or '')):
        mo = _MONTHS.get(m.group(4))
        if mo: best = max(best, '%04d-%02d-%02d' % (int(m.group(5)), mo, int(m.group(3))))
    return best

LEAK = re.compile(r'style="|class=|link=|\dpx\||\[\[|\]\]|\{\{|\}\}|<span|<br|<small|<sup|</[a-z]|&nbsp;|&lt;|&gt;|&#\d+;|&amp;')

def find_leaks(obj, path=''):
    """Every string in a JSON-like value that still looks like markup: [(path, snippet)]."""
    out = []
    if isinstance(obj, str):
        m = LEAK.search(obj)
        if m: out.append((path, obj[max(0, m.start() - 30):m.end() + 30]))
    elif isinstance(obj, dict):
        for k, v in obj.items(): out += find_leaks(v, '%s.%s' % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj): out += find_leaks(v, '%s[%d]' % (path, i))
    return out


# ---- heroes ------------------------------------------------------------------------------------------------------
def lv40(lv1, gr):
    # 5-star, neutral: growth value = trunc(0.39 * trunc(rate * 1.14))
    return lv1 + int(0.39 * int(gr * 1.14 + 1e-9) + 1e-9)

def props_of(unit):
    return [p.strip() for p in (unit.get('Properties') or '').split(',') if p.strip()]

# properties that are not hero types: outfit parts, the Resplendent realm, flags of the wiki's own templates
NOT_A_TAG = {'tiara', 'hat', 'mask', 'hair', 'notRandomized', 'prologue', 'limited', 'specDisplay',
             'askr', 'embla', 'nifl', 'muspell', 'hel', 'ljosalfheimr', 'dokkalfheimr', 'jotunheimr', 'nidavellir', 'vanaheimr', 'yggdrasill'}
RENAME_TAG = {'ghb': 'grail', 'aide': 'aided'}

def tags_of(props):
    out = []
    for p in props:
        if p.startswith(('demoted', 'specRate')) or p in NOT_A_TAG: continue
        p = RENAME_TAG.get(p, p)
        if p not in out: out.append(p)                      # "aide" and "aided" are one type: no doubles
    return out

def availability(props):
    """A code for how the hero is obtained, from the wiki's properties only. The texts live in locales/en.json
    (avail.<code>). 'pool' means: summoned, and the data does not say at which rarity."""
    p = set(props)
    demoted = any(x.startswith('demoted') for x in p)
    sr4 = any(x.startswith('specRate') for x in p)
    if 'story' in p: return 'story'
    if 'ghb' in p or 'tempest' in p: return 'grails'
    if 'legendary' in p: return 'legendary'
    if 'mythic' in p: return 'mythic'
    if 'emblem' in p: return 'emblem'
    if 'special' in p: return 'seasonal_sr4' if sr4 else 'seasonal'
    if demoted: return 'pool34'
    if sr4: return 'sr4'
    return 'pool'

def origins(unit):
    out = []
    for o in (unit.get('Origin') or '').split(','):
        o = re.sub(r'^Fire Emblem:?\s+', '', o.strip())
        if o and o not in out: out.append(o)
    return out

def build_heroes(units, stats):
    by_stats = {s.get('WikiName'): s for s in stats}
    heroes, dropped = [], []
    for u in units:
        props = props_of(u)
        if {'enemy', 'generic'} & set(props): continue
        st = by_stats.get(u.get('WikiName'))
        hid = num(u.get('IntID'), 0)
        lv1 = [num(st.get('Lv1%s5' % k)) for k in STAT_KEYS] if st else []
        gr = [num(st.get('%sGR3' % k)) for k in STAT_KEYS] if st else []
        if not st or not u.get('WeaponType') or not any(gr) or hid <= 0:
            dropped.append(u.get('Page') or u.get('WikiName') or '?'); continue
        s40 = [lv40(a, b) for a, b in zip(lv1, gr)]
        heroes.append({'id': hid, 'wn': u['WikiName'], 'page': u.get('Page') or '', 'n': u.get('Name') or '', 'ti': u.get('Title') or '',
                       'w': u['WeaponType'], 'm': u.get('MoveType') or '', 'o': origins(u), 'r': str(u.get('ReleaseDate') or '')[:10],
                       'p': tags_of(props), 's': s40, 'bst': sum(s40), 'av': availability(props), 'art': one_line(u.get('Artist'))})
    heroes.sort(key=lambda x: (x['r'], x['n'], x['id']), reverse=True)
    return heroes, dropped


# ---- skills and kits ---------------------------------------------------------------------------------------------
SLOT = {'weapon': 'weapon', 'assist': 'assist', 'special': 'special', 'passivea': 'a', 'passiveb': 'b', 'passivec': 'c', 'passivex': 'x'}
SLOT_ORDER = ('weapon', 'assist', 'special', 'a', 'b', 'c', 'x')

def build_kits(skill_rows, unit_skill_rows):
    """hero wiki name -> {slot: [skill, ...]} in learning order; the last entry of a slot is the hero's final skill.
    Skills are looked up by the wiki's own skill key (WikiName), never by display name: several skills share a name."""
    skills = {}
    for s in skill_rows:
        key = s.get('WikiName') or ''
        if not key or key in skills: continue
        skills[key] = {'n': one_line(s.get('Name')) or key, 'c': (s.get('Scategory') or '').lower(), 'd': clean(s.get('Description')),
                       'sp': num(s.get('SP')), 'ex': str(s.get('Exclusive')).lower() in ('1', 'true', 'yes'),
                       'mt': num(s.get('Might')), 'rg': num(s.get('UseRange')), 'cd': num(s.get('Cooldown'))}
    kits = collections.defaultdict(lambda: collections.defaultdict(list))
    unknown = 0
    for us in unit_skill_rows:
        sk = skills.get(us.get('skill') or '')
        if not sk: unknown += 1; continue
        slot = SLOT.get(sk['c'])
        if not slot: continue
        rec = {'n': sk['n'], 'pos': num(us.get('skillPos'))}
        if sk['sp']: rec['sp'] = sk['sp']
        if sk['d']: rec['d'] = sk['d']
        if sk['ex']: rec['ex'] = True
        if sk['c'] == 'weapon' and sk['mt']: rec['mt'] = sk['mt']
        if sk['c'] == 'weapon' and sk['rg']: rec['rg'] = sk['rg']
        if sk['c'] == 'special' and sk['cd']: rec['cd'] = sk['cd']
        r = num(us.get('unlockRarity')) or num(us.get('defaultRarity'))
        if r: rec['r'] = r
        kits[us.get('WikiName')][slot].append(rec)
    out = {}
    for wn, slots in kits.items():
        out[wn] = {}
        for slot in SLOT_ORDER:
            if slot not in slots: continue
            rows = sorted(slots[slot], key=lambda x: (x['pos'], x.get('sp', 0)))
            for x in rows: del x['pos']
            out[wn][slot] = rows
    return out, unknown


# ---- wiki builds -------------------------------------------------------------------------------------------------
BUILD_SLOTS = (('weapon', 'Weapon'), ('assist', 'Assist'), ('special', 'Special'), ('a', 'PassiveA'), ('b', 'PassiveB'), ('c', 'PassiveC'), ('x', 'PassiveX'), ('seal', 'Seal'))
MODES = {'all': 'all', 'any': 'all', 'allpurpose': 'all', 'allprupose': 'all', 'allpurppose': 'all', 'flexible': 'all', 'general': 'all',
         'arena': 'arena', 'assault': 'assault', 'arenaassault': 'assault', 'chain': 'chain', 'chian': 'chain', 'flexiblechain': 'chain',
         'storychainchallenge': 'chain', 'pve': 'pve', 'defense': 'aether-defense', 'defending': 'aether-defense', 'ard': 'aether-defense',
         'aro': 'aether-offense', 'aetherraids': 'aether'}
COSTS = {'low': 'low', 'medium': 'medium', 'high': 'high', 'veryhigh': 'veryhigh'}
KINDS = {'optimal': 'optimal', 'optinal': 'optimal', 'optmal': 'optimal', 'alternative': 'alternative', 'alternate': 'alternative',
         'alternatuve': 'alternative', 'creative': 'creative', 'crative': 'creative', 'crewative': 'creative', 'budget': 'budget'}
squash = lambda s: re.sub(r'[^a-z0-9]', '', one_line(s).lower())

def refine_text(v):
    v = one_line(v)
    if not v: return ''
    if v.lower().startswith('skill'): return 'effect refine'
    return '+%s refine' % v.capitalize()

def build_builds(rows, by_page, by_wn):
    builds, pages, unmatched = collections.defaultdict(list), {}, 0
    for b in rows:
        page = str(b.get('Page') or '')
        hid = by_page.get(b.get('Hero')) or by_wn.get(b.get('Hero')) or by_page.get(page.split('/', 1)[-1])
        if not hid: unmatched += 1; continue
        rec = {'name': one_line(b.get('BuildName')), 'kind': KINDS.get(squash(b.get('Type')), ''), 'cost': COSTS.get(squash(b.get('InvestmentCost')), ''),
               'iv': one_line(b.get('IV')), 'desc': clean(b.get('Description')), 'date': signed_date(b.get('Description'))}
        mode = squash(b.get('Mode'))
        rec['mode'] = MODES.get(mode, 'other' if mode else '')
        for key, col in BUILD_SLOTS:
            v, alt = one_line(b.get(col)), one_line(b.get(col + '2'))
            if key == 'weapon':
                if v and refine_text(b.get('WeaponRefine')): v += ' (%s)' % refine_text(b.get('WeaponRefine'))
                if alt and refine_text(b.get('WeaponRefine2')): alt += ' (%s)' % refine_text(b.get('WeaponRefine2'))
            if v: rec[key] = v + (' / ' + alt if alt else '')
        if not any(rec.get(k) for k, _ in BUILD_SLOTS): continue        # an entry without a single skill is not a build
        builds[hid].append({k: v for k, v in rec.items() if v})
        if page: pages[hid] = page
    return builds, pages, unmatched


# ---- banners -----------------------------------------------------------------------------------------------------
# The banner's kind decides its place on the Summon page and its one-line note. Exact type names from the wiki;
# anything not listed is 'other', which makes no claim.
BANNER_KIND = {
    'New Heroes': 'new',
    'Legendary': 'legendary', 'Mythic': 'legendary', 'Emblem': 'legendary', 'Legendary & Mythic': 'legendary',
    'Emblem & Legendary': 'legendary', 'Emblem & Mythic': 'legendary',
    'Special': 'special', 'Double Special Heroes': 'special', 'ω Special Heroes': 'special',
    'Weekly Revival': 'revival', 'New Heroes Revival': 'revival', 'Legendary Revival': 'revival', 'Mythic Revival': 'revival',
    'Hall of Forms Revival': 'revival', 'Returning': 'revival', 'Legendary & Mythic Hero Remix': 'revival',
    'Legendary, Mythic & Emblem Hero Remix': 'revival', 'Skill': 'revival', 'New Power': 'revival', 'Tempest Trials': 'revival',
    'Voting Gauntlet': 'revival', 'Bound Hero Battle': 'revival', 'Hall of Forms': 'revival',
    'Free Summon': 'free',
}

def build_banners(events, focus_rows, by_page, by_wn):
    """focus_rows is None when the focus table is not there: every banner then has f = null (unknown)."""
    focus, four = None, set()
    first_run = {}                                           # banner name -> its earliest start: a later one is a re-run
    for e in events:
        s = epoch(e.get('StartTime'))
        name = one_line(e.get('Name'))
        if s is not None and name and (name not in first_run or s < first_run[name]): first_run[name] = s
    if focus_rows is not None:
        focus = collections.defaultdict(list)
        for f in focus_rows:
            hid = by_page.get(f.get('Unit')) or by_wn.get(f.get('Unit'))
            if num(f.get('Rarity')) == 4: four.add(f.get('WikiName'))      # a focus hero that also comes at 4 stars
            if hid and not any(x[0] == hid for x in focus[f.get('WikiName')]):
                focus[f.get('WikiName')].append([hid, num(f.get('Rarity')) or None])
    banners, bad = [], 0
    for e in events:
        s, end = epoch(e.get('StartTime')), epoch(e.get('EndTime'))
        if s is None or end is None or end <= s or not e.get('WikiName'): bad += 1; continue
        t = one_line(e.get('EventType'))
        banners.append({'id': e['WikiName'], 'n': one_line(e.get('Name')), 's': s, 'e': end, 't': t, 'k': BANNER_KIND.get(t, 'other'),
                        'f': None if focus is None else focus.get(e['WikiName'], [])})
        if first_run.get(banners[-1]['n'], s) < s: banners[-1]['re'] = True          # the same name ran before
        if e['WikiName'] in four: banners[-1]['f4'] = True
    banners.sort(key=lambda b: (b['s'], b['id']), reverse=True)
    return banners, bad


# ---- orbs --------------------------------------------------------------------------------------------------------
QUEST_NAMES = {'RB': 'Resonant Battles quests', 'RB AB': 'Resonant Battles and Allegiance Battles quests', 'Daily': 'Daily quest',
               'Grand Hero Battles': 'Grand Hero Battle quests', 'Tempest Trials': 'Tempest Trials quests'}

def quest_name(wikiname):
    """'0220261101 Nov Quests 04' -> ('Monthly quests', paid)."""
    core = re.sub(r'\s+', ' ', re.sub(r'^\d+\s*|\s*\d+$', '', one_line(wikiname))).strip()
    if core.lower().startswith('feh pass'): return 'Feh Pass quests', True
    m = re.fullmatch(r'[A-Z][a-z]{2} (Quests|Training)', core)
    if m: return ('Monthly quests' if m.group(1) == 'Quests' else 'Monthly training quests'), False
    if core in QUEST_NAMES: return QUEST_NAMES[core], False
    return (core + ' quests' if core else 'Quests'), False

def build_orbs(quest_rows, now):
    rows = collections.OrderedDict()
    for r in quest_rows:
        if (r.get('Item') or '') != 'Orb': continue
        s, e = epoch(r.get('StartTime')), epoch(r.get('EndTime'))
        if s is None or e is None or e < now: continue      # ended before this build; the page checks again against the clock
        name, paid = quest_name(r.get('WikiName'))
        key = (name, s, e, paid)
        rows[key] = rows.get(key, 0) + max(0, num(r.get('Amount'), 1))
    out = [{'name': k[0], 's': k[1], 'e': k[2], 'n': n, 'pass': k[3]} for k, n in rows.items() if n]
    out.sort(key=lambda x: (x['e'], x['s'], x['name']))
    return out


# ---- reading the cache -------------------------------------------------------------------------------------------
def read_table(cache, name):
    """(rows or None, status, fetched epoch or None). status: ok | missing | unreadable.
    A table that is still downloading exists only as <name>.json.part and counts as missing."""
    p = os.path.join(cache, name + '.json')
    if not os.path.exists(p): return None, 'missing', None
    try:
        with open(p, encoding='utf-8') as f: rows = json.load(f)
    except (ValueError, OSError):
        return None, 'unreadable', None
    if not isinstance(rows, list): return None, 'unreadable', None
    return rows, 'ok', int(os.path.getmtime(p))


# ---- the build ---------------------------------------------------------------------------------------------------
def build(cache, now=None):
    """Reads the cache and returns {relative file name: data}. Raises BuildError when a gate refuses."""
    now = int(now if now is not None else datetime.datetime.now(UTC).timestamp())
    tables, status, fetched = {}, {}, {}
    for name in REQUIRED + OPTIONAL:
        rows, st, at = read_table(cache, name)
        tables[name], status[name] = rows, st
        if at: fetched[name] = at
    for name in REQUIRED:
        if status[name] != 'ok' or not tables[name]:
            raise BuildError('required table %s is %s' % (name, status[name] if status[name] != 'ok' else 'empty'))
    for name in OPTIONAL:
        if status[name] == 'ok' and not tables[name] and name != 'QuestRewards':
            status[name] = 'empty'; tables[name] = None       # an empty answer is "we do not know", not "there is none"

    heroes, dropped = build_heroes(tables['Units'], tables['UnitStats'])
    by_page = {x['page']: x['id'] for x in heroes}
    by_wn = {x['wn']: x['id'] for x in heroes}

    kits, have_kits = {}, tables['Skills'] is not None and tables['UnitSkills'] is not None
    if have_kits: kits, _ = build_kits(tables['Skills'], tables['UnitSkills'])
    have_builds = tables['HeroBuilds'] is not None
    builds, build_pages, _ = build_builds(tables['HeroBuilds'], by_page, by_wn) if have_builds else ({}, {}, 0)
    have_focus = tables['SummoningEventFocuses'] is not None
    banners, bad_banners = build_banners(tables['SummoningEvents'], tables['SummoningEventFocuses'], by_page, by_wn)
    have_quests = tables['QuestRewards'] is not None

    for x in heroes:
        x['nb'] = len(builds.get(x['id'], [])) if have_builds else None
        kit = kits.get(x['wn']) if have_kits else None
        x['k'] = {slot: rows[-1]['n'] for slot, rows in kit.items()} if kit else None

    files = collections.OrderedDict()
    history = collections.defaultdict(list)
    if have_focus:
        for b in banners:
            for hid, rarity in b['f']:
                history[hid].append({'n': b['n'], 's': b['s'], 'e': b['e'], 't': b['t']})
    for x in heroes:
        rec = {'v': FORMAT, 'id': x['id'],
               'kit': (kits.get(x['wn']) or {}) if have_kits else None,
               'builds': builds.get(x['id'], []) if have_builds else None,
               'buildsPage': build_pages.get(x['id'], ''),
               'banners': history.get(x['id'], []) if have_focus else None}
        files['hero/%d.json' % x['id']] = rec

    keep_from = now - 60 * 86400
    files['banners.json'] = {'v': FORMAT, 'focusKnown': have_focus, 'from': keep_from, 'banners': [b for b in banners if b['e'] >= keep_from]}
    orb_rows = build_orbs(tables['QuestRewards'], now) if have_quests else []
    files['orbs.json'] = {'v': FORMAT, 'questsKnown': have_quests, 'groups': [{'id': 'quests', 'rows': orb_rows}] if orb_rows else [],
                          # sources the wiki's tables hold no orb rows for: the page names them instead of promising them
                          'notCovered': ['login', 'tempest', 'story', 'weekly', 'events']}
    today = game_date(now)
    summoned = [x for x in heroes if x['av'] not in ('story', 'grails') and x['r'] and x['r'] <= today]
    most_built = sorted(((hid, len(v)) for hid, v in builds.items()), key=lambda kv: (-kv[1], kv[0]))[:25]
    files['meta.json'] = {'v': FORMAT, 'newest': [x['id'] for x in summoned[:30]], 'mostBuilt': most_built}
    files['heroes.json'] = {'v': FORMAT, 'heroes': heroes}

    released = [x['r'] for x in heroes if x['r'] and x['r'] <= today]
    used = [n for n in REQUIRED + OPTIONAL if n in fetched]
    files['manifest.json'] = {
        'v': FORMAT, 'built': iso(now),
        'fetched': {n: iso(fetched[n]) for n in used},
        'dataFrom': iso(min(fetched[n] for n in used)),       # the age of the data: the oldest table used
        'newestRelease': max(released) if released else '',
        'newestBannerStart': iso(max(b['s'] for b in banners if b['s'] <= now)) if any(b['s'] <= now for b in banners) else '',
        'bannersFrom': iso(min(b['e'] for b in banners)) if banners else '',   # banner history reaches back to here
        'tables': status,
        'counts': {'heroes': len(heroes), 'dropped': len(dropped), 'banners': len(banners), 'bannersWithFocus': sum(1 for b in banners if b['f']),
                   'builds': sum(len(v) for v in builds.values()), 'heroesWithBuilds': len(builds), 'heroesWithKit': sum(1 for x in heroes if x['k']),
                   'orbRows': len(orb_rows)},
        'dropped': dropped[:50],
        'source': {'name': 'Fire Emblem Heroes Wiki', 'url': 'https://feheroes.fandom.com/', 'licence': 'CC BY-NC-SA', 'licenceUrl': 'https://www.fandom.com/licensing'},
    }
    check(files, bad_banners)
    return files


def check(files, bad_banners=0):
    """Gates on the content itself. Raises BuildError."""
    heroes = files['heroes.json']['heroes']
    ids = [x['id'] for x in heroes]
    if len(ids) != len(set(ids)): raise BuildError('hero ids are not unique')
    if len({x['wn'] for x in heroes}) != len(heroes): raise BuildError('hero wiki names are not unique')
    for x in heroes:
        if len(x['s']) != 5 or min(x['s']) <= 0: raise BuildError('bad stats for %s' % x['page'])
        if not x['n'] or not x['w'] or not x['m']: raise BuildError('missing name, weapon or movement for id %s' % x['id'])
    marth = next((x for x in heroes if x['wn'] == 'Marth Altean Prince'), None)
    if marth and marth['s'] != MARTH: raise BuildError('Marth: Altean Prince comes out as %s, the game shows %s' % (marth['s'], MARTH))
    dropped = files['manifest.json']['counts']['dropped']
    if dropped > max(3, len(heroes) // 100): raise BuildError('%d heroes have no stats and would be left out' % dropped)
    banners = files['banners.json']['banners']
    if not banners: raise BuildError('no banner in the last 60 days')
    if bad_banners > 5: raise BuildError('%d banners without usable times' % bad_banners)
    leaks = []
    for name, data in files.items():
        leaks += [(name + p, s) for p, s in find_leaks(data)]
    if leaks: raise BuildError('%d texts still hold markup, first: %s %r' % (len(leaks), leaks[0][0], leaks[0][1]))


def previous_count(out):
    try:
        with open(os.path.join(out, 'manifest.json'), encoding='utf-8') as f: return int(json.load(f)['counts']['heroes'])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:                                                    # the concept's format, before there was a manifest
        with open(os.path.join(out, 'heroes.json'), encoding='utf-8') as f: return len(json.load(f)['heroes'])
    except (OSError, ValueError, KeyError, TypeError):
        return 0

def write(files, out):
    """Writes everything into <out>.new, then swaps it in. The old folder is only removed after the new one is in place."""
    tmp, old = out + '.new', out + '.old'
    for p in (tmp, old):
        if os.path.exists(p): shutil.rmtree(p)
    os.makedirs(os.path.join(tmp, 'hero'))
    for name, data in files.items():
        with open(os.path.join(tmp, *name.split('/')), 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    if os.path.exists(out): os.rename(out, old)
    os.rename(tmp, out)
    if os.path.exists(old): shutil.rmtree(old)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cache', default=os.path.join(HERE, 'cache'))
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'site', 'data'))
    ap.add_argument('--min-heroes', type=int, default=1000, help='refuse to write fewer heroes than this')
    ap.add_argument('--allow-drop', action='store_true', help='write even when the hero count fell against the last build')
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    try:
        files = build(a.cache)
        n, before = files['manifest.json']['counts']['heroes'], previous_count(out)
        if n < a.min_heroes: raise BuildError('only %d heroes (minimum %d)' % (n, a.min_heroes))
        if before and n < before * 0.97 and not a.allow_drop:
            raise BuildError('hero count fell from %d to %d; run with --allow-drop if that is right' % (before, n))
    except BuildError as e:
        print('REFUSED: %s. Nothing was written.' % e)
        return 2
    write(files, out)
    m = files['manifest.json']
    size = lambda names: sum(os.path.getsize(os.path.join(out, *n.split('/'))) for n in names) / 1024
    hero_files = [n for n in files if n.startswith('hero/')]
    for n in files:
        if not n.startswith('hero/'): print('%-14s %7.0f KB' % (n, size([n])))
    print('%-14s %7.0f KB in %d files' % ('hero/*.json', size(hero_files), len(hero_files)))
    print('tables:', ', '.join('%s %s' % kv for kv in m['tables'].items()))
    print('counts:', ', '.join('%s %s' % kv for kv in m['counts'].items()))
    print('data from %s, newest hero released %s' % (m['dataFrom'], m['newestRelease']))
    print('OK: wrote %d files' % len(files))
    return 0

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
