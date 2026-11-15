"""Checks of the data pipeline and of the data files the site loads. Python only, no network.

    python -I tools/test_data.py [--verbose]

  1. Unit checks of tools/build_data.py: the text cleaner, times, availability codes, hero types, quest names.
  2. The gates: with a required table missing, with too few heroes or with a sharp drop, nothing is written;
     optional tables that are missing or half written are tolerated and marked; made-up Skills, UnitSkills and
     SummoningEventFocuses tables are picked up correctly (so the build is ready for the real ones).
  3. The files in site/data as they are on disk: complete, consistent, free of markup, in step with the cache.
Exit code 0 only when everything passed.
"""
import copy, io, json, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import build_data as B

CACHE = os.path.join(HERE, 'cache')
DATA = os.path.join(ROOT, 'site', 'data')
VERBOSE = '--verbose' in sys.argv
failed, total = [], 0

def check(name, ok, detail=''):
    global total
    total += 1
    if ok and VERBOSE: print('ok    ' + name)
    if not ok:
        failed.append(name); print('FAIL  %s%s' % (name, ('\n      ' + str(detail)[:600]) if detail != '' else ''))

def eq(name, got, want):
    check(name, got == want, 'got %r, wanted %r' % (got, want))

def load(path):
    with open(path, encoding='utf-8') as f: return json.load(f)

def dump(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)

def quiet(fn, *a):
    """Runs fn with its printing swallowed; returns (result, printed text)."""
    old, sys.stdout = sys.stdout, io.StringIO()
    try: r = fn(*a)
    finally: text, sys.stdout = sys.stdout.getvalue(), old
    return r, text


# ---- 1. unit checks --------------------------------------------------------------------------------------------------
def unit_checks():
    c = B.clean
    tip = ('<span style="white-space:nowrap;">[[File:Icon Class Green Axe.png|x26px|class=inline-icon|link=Thunder Armads]]&nbsp;[[Thunder Armads|'
           '<span title="Grants Def+3. If the number of allies within 2 spaces (excluding unit) &gt; the number of foes, foe cannot make a follow-up attack." '
           'style="border-bottom:0;text-decoration:underline dotted;cursor:help;">Thunder Armads</span>]]</span> is Hector\'s weapon of choice.')
    eq('cleaner: a tooltip whose title holds "&gt;" leaves only the skill name', c(tip), "Thunder Armads is Hector's weapon of choice.")
    eq('cleaner: file links vanish, page links keep their label', c('[[File:A.png|x26px|class=inline-icon|link=Wo Dao+]] [[Wo Dao+]] and [[Fury|Fury 3]]'), 'Wo Dao+ and Fury 3')
    eq('cleaner: a signature is removed', c('Good build. [[User:Some One|Some One]] ([[User talk:Some One|talk]]) 05:41, 25 January 2021 (UTC)'), 'Good build.')
    eq('cleaner: a signature date is found', B.signed_date('x [[User:A|A]] ([[User talk:A|talk]]) 05:41, 25 January 2021 (UTC) y 00:42, 11 October 2026 (UTC)'), '2026-10-11')
    eq('cleaner: no date, no guess', B.signed_date('written in January 2021'), '')
    eq('cleaner: bold marks, paragraphs and breaks', c("'''Weapon''': strong.<br />Next line\n\n\n''Assist'': Pivot"), 'Weapon: strong.\nNext line\nAssist: Pivot')
    eq('cleaner: text escaped twice', c('at &amp;gt;80% HP &amp;amp; more'), 'at >80% HP & more')
    eq('cleaner: "<3" and "HP<50%" are text, not tags', c('I &lt;3 Surtr, HP<50% and <100% HP'), 'I <3 Surtr, HP<50% and <100% HP')
    eq('cleaner: templates and stray brackets', c('a {{Tooltip|x|{{y}}}} b [[broken'), 'a b broken')
    eq('cleaner: outside links keep their label', c('see [https://example.org/x the video] now'), 'see the video now')
    eq('cleaner: nothing in, nothing out', (c(None), c(''), c('   ')), ('', '', ''))
    long = ' '.join('word%d' % i for i in range(400))
    eq('cleaner: long text keeps its full length', c(long), long)
    check('leak finder sees markup', len(B.find_leaks({'a': ['fine', 'x style="y"'], 'b': {'c': 'see [[Link]]'}})) == 2)
    check('leak finder accepts plain text', not B.find_leaks({'a': 'HP<50%, Atk > Def, [note] "quoted" & more = fine'}))

    eq('time: a wiki time is a UTC instant', B.epoch('2026-11-15 06:59:59'), 1794725999)
    eq('time: a date alone is midnight UTC', B.epoch('2026-11-15'), 1794700800)
    eq('time: nonsense is no time', (B.epoch(''), B.epoch(None), B.epoch('soon'), B.epoch('2026-13-45 00:00:00')), (None, None, None, None))
    eq('time: the game date changes at 07:00 UTC', (B.game_date(B.epoch('2026-11-15 06:59:59')), B.game_date(B.epoch('2026-11-15 07:00:00'))), ('2026-11-14', '2026-11-15'))
    eq('stats: level 40 formula (Marth: 41/31/34/29/23)', [B.lv40(a, g) for a, g in zip((19, 7, 8, 7, 6), (50, 55, 60, 50, 40))], B.MARTH)

    av = B.availability
    eq('availability: story', av(['story', 'limited']), 'story')
    eq('availability: Grand Hero Battle', av(['limited', 'ghb']), 'grails')
    eq('availability: Tempest Trials, also when seasonal', av(['special', 'tempest', 'specDisplay']), 'grails')
    eq('availability: demoted to 3 and 4 stars, Resplendent realm ignored', av(['demoted_240', 'resplendent', 'askr']), 'pool34')
    eq('availability: 4-star special rate', av(['brave', 'specRate_201904', 'resplendent', 'nidavellir']), 'sr4')
    eq('availability: seasonal', av(['special']), 'seasonal')
    eq('availability: seasonal with special rate is still seasonal', av(['special', 'hat', 'specRate_202202']), 'seasonal_sr4')
    eq('availability: Legendary, Mythic, Emblem', (av(['legendary']), av(['mythic', 'tiara']), av(['emblem', 'refresher'])), ('legendary', 'mythic', 'emblem'))
    eq('availability: no property means "summoned, rarity unknown", never "5 stars only"', (av([]), av(['vista']), av(['prologue'])), ('pool', 'pool', 'pool'))
    eq('hero types: "aide" and "aided" are one', B.tags_of(['special', 'aided', 'aide']), ['special', 'aided'])
    eq('hero types: vista is kept, outfit parts and realms are not', B.tags_of(['refresher', 'vista', 'hat', 'tiara', 'askr', 'limited', 'specRate_202602', 'demoted_240']), ['refresher', 'vista'])
    eq('hero types: ghb is called grail', B.tags_of(['limited', 'ghb']), ['grail'])
    eq('origins: every game, prefix removed the same way', B.origins({'Origin': 'Fire Emblem: The Binding Blade,Fire Emblem Fates,Tokyo Mirage Sessions ♯FE Encore,Fire Emblem Fates'}),
       ['The Binding Blade', 'Fates', 'Tokyo Mirage Sessions ♯FE Encore'])
    eq('quests: monthly', B.quest_name('0220261101 Nov Quests 04'), ('Monthly quests', False))
    eq('quests: Feh Pass is paid', B.quest_name('5020261110 Feh Pass 01'), ('Feh Pass quests', True))
    eq('quests: event name', B.quest_name('1120261106 Ninja Boot Camp 02'), ('Ninja Boot Camp quests', False))
    eq('quests: short code', B.quest_name('0320261110 RB  AB 01'), ('Resonant Battles and Allegiance Battles quests', False))
    rows = [{'Item': 'Orb', 'Amount': '2', 'WikiName': '5020261110 Feh Pass 01', 'StartTime': '2026-11-10 07:00:00', 'EndTime': '2026-11-25 06:59:59'},
            {'Item': 'Orb', 'Amount': '1', 'WikiName': '0420261114 Daily 01', 'StartTime': '2026-11-14 07:00:00', 'EndTime': '2026-11-15 06:59:59'},
            {'Item': 'Orb', 'Amount': '1', 'WikiName': '0420261101 Daily 01', 'StartTime': '2026-11-01 07:00:00', 'EndTime': '2026-11-02 06:59:59'},
            {'Item': 'Hero Feather', 'Amount': '500', 'WikiName': '0420261114 Daily 02', 'StartTime': '2026-11-14 07:00:00', 'EndTime': '2026-11-15 06:59:59'}]
    got = B.build_orbs(rows, B.epoch('2026-11-14 12:00:00'))
    eq('orbs: only orbs, only quests that have not ended, paid marked', [(r['name'], r['n'], r['pass']) for r in got], [('Daily quest', 1, False), ('Feh Pass quests', 2, True)])
    eq('banner kinds: a revival of Legendary heroes is a revival', (B.BANNER_KIND.get('Legendary Revival'), B.BANNER_KIND.get('Legendary'), B.BANNER_KIND.get('12 Luminaries', 'other')), ('revival', 'legendary', 'other'))


# ---- 2. gates ---------------------------------------------------------------------------------------------------------
def tree(folder):
    """{relative path: (size, mtime)} of a folder."""
    out = {}
    for base, _, names in os.walk(folder):
        for n in names:
            p = os.path.join(base, n); out[os.path.relpath(p, folder)] = (os.path.getsize(p), os.path.getmtime(p))
    return out

def gate_checks():
    if not all(os.path.exists(os.path.join(CACHE, t + '.json')) for t in B.REQUIRED):
        check('gates: the cache holds the required tables (run tools/fetch_all.py)', False); return
    tmp = tempfile.mkdtemp(prefix='hc-data-')
    try:
        cache, out = os.path.join(tmp, 'cache'), os.path.join(tmp, 'out')
        os.makedirs(cache)
        for t in B.REQUIRED + ('HeroBuilds', 'QuestRewards'):
            if os.path.exists(os.path.join(CACHE, t + '.json')): shutil.copy2(os.path.join(CACHE, t + '.json'), cache)
        units = load(os.path.join(cache, 'Units.json'))

        code, text = quiet(B.main, ['--cache', cache, '--out', out])
        check('gates: a good cache builds', code == 0 and os.path.exists(os.path.join(out, 'manifest.json')), text[-300:])
        m = load(os.path.join(out, 'manifest.json'))
        eq('gates: missing optional tables are marked, not hidden', (m['tables'].get('Skills'), m['tables'].get('SummoningEventFocuses')), ('missing', 'missing'))
        banners = load(os.path.join(out, 'banners.json'))
        check('gates: without the focus table every banner says "unknown" (null), not "none"', banners['focusKnown'] is False and all(b['f'] is None for b in banners['banners']))
        first = load(os.path.join(out, 'heroes.json'))['heroes'][0]
        hero = load(os.path.join(out, 'hero', '%d.json' % first['id']))
        check('gates: without the skill tables a hero\'s skills and banner history are unknown (null)', hero['kit'] is None and hero['banners'] is None and first['k'] is None, hero)
        before = tree(out)

        os.rename(os.path.join(cache, 'UnitStats.json'), os.path.join(cache, 'UnitStats.keep'))
        code, text = quiet(B.main, ['--cache', cache, '--out', out])
        check('gates: a missing required table refuses the build', code == 2 and 'REFUSED' in text and 'UnitStats' in text, text[-300:])
        eq('gates: ... and leaves the old output untouched', tree(out), before)
        with open(os.path.join(cache, 'UnitStats.json'), 'w', encoding='utf-8') as f: f.write('[{"WikiName": "half writ')
        code, text = quiet(B.main, ['--cache', cache, '--out', out])
        check('gates: a half-written required table refuses the build', code == 2 and 'unreadable' in text, text[-300:])
        os.remove(os.path.join(cache, 'UnitStats.json')); os.rename(os.path.join(cache, 'UnitStats.keep'), os.path.join(cache, 'UnitStats.json'))

        dump(os.path.join(cache, 'Units.json'), units[:300])
        code, text = quiet(B.main, ['--cache', cache, '--out', out])
        check('gates: too few heroes refuse the build', code == 2 and 'minimum' in text, text[-300:])
        code, text = quiet(B.main, ['--cache', cache, '--out', out, '--min-heroes', '10'])
        check('gates: a sharp drop against the last build refuses the build', code == 2 and 'fell from' in text, text[-300:])
        eq('gates: ... and leaves the old output untouched', tree(out), before)
        check('gates: no half-built folder is left behind', not os.path.exists(out + '.new') and not os.path.exists(out + '.old'))
        code, text = quiet(B.main, ['--cache', cache, '--out', out, '--min-heroes', '10', '--allow-drop'])
        check('gates: the drop can be allowed by hand', code == 0, text[-300:])
        check('gates: files of heroes that are gone are removed', len(os.listdir(os.path.join(out, 'hero'))) == load(os.path.join(out, 'manifest.json'))['counts']['heroes'])
        dump(os.path.join(cache, 'Units.json'), units)

        with open(os.path.join(cache, 'Skills.json'), 'w', encoding='utf-8') as f: f.write('[{"WikiName": "half writ')
        code, text = quiet(B.main, ['--cache', cache, '--out', out])
        m = load(os.path.join(out, 'manifest.json'))
        check('gates: a half-written optional table is tolerated and marked', code == 0 and m['tables']['Skills'] == 'unreadable', text[-300:])

        # made-up tables in the wiki's shape: two different skills share the display name "Falchion"
        by_name = {u['WikiName']: u for u in units}
        a, b = 'Marth Altean Prince', 'Alfonse Prince of Askr'
        check('gates: the two test heroes are in the cache', a in by_name and b in by_name)
        dump(os.path.join(cache, 'Skills.json'), [
            {'WikiName': 'Falchion Mystery', 'Name': 'Falchion', 'Scategory': 'weapon', 'Description': 'Effective against dragon foes.&lt;br&gt;At start of every third turn, restores 10 HP.', 'SP': '400', 'Exclusive': '1'},
            {'WikiName': 'Falchion Awakening', 'Name': 'Falchion', 'Scategory': 'weapon', 'Description': 'A different sword with the same name.', 'SP': '400', 'Exclusive': '1'},
            {'WikiName': 'Iron Sword', 'Name': 'Iron Sword', 'Scategory': 'weapon', 'Description': '', 'SP': '50', 'Exclusive': '0'},
            {'WikiName': 'Pivot', 'Name': 'Pivot', 'Scategory': 'assist', 'Description': 'Unit moves to opposite side of target ally.', 'SP': '150', 'Exclusive': '0'},
            {'WikiName': 'Escape Route 3', 'Name': 'Escape Route 3', 'Scategory': 'passiveb', 'Description': 'If unit\'s HP ≤ 50%, <span title="x &gt; y" style="a">unit can move</span> to a space adjacent to any ally.', 'SP': '240', 'Exclusive': '0'},
            {'WikiName': 'Quickened Pulse', 'Name': 'Quickened Pulse', 'Scategory': 'sacredseal', 'Description': 'A seal, not part of a hero.', 'SP': '0', 'Exclusive': '0'}])
        dump(os.path.join(cache, 'UnitSkills.json'), [
            {'WikiName': a, 'skill': 'Falchion Mystery', 'skillPos': '4', 'defaultRarity': '', 'unlockRarity': '5'},
            {'WikiName': a, 'skill': 'Iron Sword', 'skillPos': '1', 'defaultRarity': '1', 'unlockRarity': ''},
            {'WikiName': a, 'skill': 'Pivot', 'skillPos': '1', 'defaultRarity': '', 'unlockRarity': '3'},
            {'WikiName': a, 'skill': 'Escape Route 3', 'skillPos': '3', 'defaultRarity': '', 'unlockRarity': '5'},
            {'WikiName': a, 'skill': 'Quickened Pulse', 'skillPos': '1', 'defaultRarity': '', 'unlockRarity': ''},
            {'WikiName': a, 'skill': 'A Skill The Table Does Not Hold', 'skillPos': '1', 'defaultRarity': '', 'unlockRarity': ''},
            {'WikiName': b, 'skill': 'Falchion Awakening', 'skillPos': '4', 'defaultRarity': '', 'unlockRarity': '5'}])
        events = load(os.path.join(cache, 'SummoningEvents.json'))
        ev = max(events, key=lambda e: e['StartTime'])
        dump(os.path.join(cache, 'SummoningEventFocuses.json'), [
            {'WikiName': ev['WikiName'], 'Unit': by_name[a]['Page'], 'Rarity': '5'}, {'WikiName': ev['WikiName'], 'Unit': by_name[a]['Page'], 'Rarity': '5'},
            {'WikiName': ev['WikiName'], 'Unit': by_name[b]['Page'], 'Rarity': '4'}, {'WikiName': ev['WikiName'], 'Unit': 'A Hero: Who Is Not There', 'Rarity': '5'}])
        code, text = quiet(B.main, ['--cache', cache, '--out', out])
        check('gates: the build picks up Skills, UnitSkills and SummoningEventFocuses once they are there', code == 0, text[-400:])
        m = load(os.path.join(out, 'manifest.json'))
        eq('gates: ... and marks them', [m['tables'][t] for t in ('Skills', 'UnitSkills', 'SummoningEventFocuses')], ['ok', 'ok', 'ok'])
        heroes = {x['wn']: x for x in load(os.path.join(out, 'heroes.json'))['heroes']}
        ha, hb = (load(os.path.join(out, 'hero', '%d.json' % heroes[n]['id'])) for n in (a, b))
        eq('skills: learning order within a slot, the final skill last', [s['n'] for s in ha['kit']['weapon']], ['Iron Sword', 'Falchion'])
        eq('skills: the index names the final skill of each slot', heroes[a]['k'], {'weapon': 'Falchion', 'assist': 'Pivot', 'b': 'Escape Route 3'})
        check('skills: two skills with one name keep their own texts', ha['kit']['weapon'][-1]['d'].startswith('Effective against dragon foes.\nAt start') and hb['kit']['weapon'][-1]['d'] == 'A different sword with the same name.', (ha['kit']['weapon'], hb['kit']['weapon']))
        eq('skills: descriptions are cleaned', ha['kit']['b'][0]['d'], "If unit's HP ≤ 50%, unit can move to a space adjacent to any ally.")
        check('skills: seals and unknown skills stay out of the hero\'s own skills', set(ha['kit']) == {'weapon', 'assist', 'b'})
        other = next(x for x in heroes.values() if x['wn'] not in (a, b))
        eq('skills: a hero the table does not list has an empty skill list, which is not "unknown"', (load(os.path.join(out, 'hero', '%d.json' % other['id']))['kit'], other['k']), ({}, None))
        banners = load(os.path.join(out, 'banners.json'))
        target = next(x for x in banners['banners'] if x['id'] == ev['WikiName'])
        eq('focus: heroes by number with rarity, no doubles, unknown names dropped', target['f'], [[heroes[a]['id'], 5], [heroes[b]['id'], 4]])
        check('focus: a banner without rows has an empty list once the table is there', banners['focusKnown'] is True and all(x['f'] == [] for x in banners['banners'] if x['id'] != ev['WikiName']))
        eq('focus: the hero\'s own file lists the banner', [x['n'] for x in ha['banners']], [B.one_line(ev['Name'])])
        check('focus: a hero on no banner has an empty history', load(os.path.join(out, 'hero', '%d.json' % other['id']))['banners'] == [])

        files = B.build(cache)
        broken = copy.deepcopy(files); broken['hero/%d.json' % heroes[a]['id']]['kit']['weapon'][0]['d'] = 'x <span title="y">z'
        try: B.check(broken); refused = False
        except B.BuildError: refused = True
        check('gates: markup left in any text refuses the build', refused)
        broken = copy.deepcopy(files); broken['heroes.json']['heroes'][3]['id'] = broken['heroes.json']['heroes'][4]['id']
        try: B.check(broken); refused = False
        except B.BuildError: refused = True
        check('gates: a doubled hero number refuses the build', refused)
        broken = copy.deepcopy(files); next(x for x in broken['heroes.json']['heroes'] if x['wn'] == a)['s'][1] += 1
        try: B.check(broken); refused = False
        except B.BuildError: refused = True
        check('gates: a wrong level 40 value for the reference hero refuses the build', refused)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- 3. the files on disk -----------------------------------------------------------------------------------------------
def disk_checks():
    if not os.path.exists(os.path.join(DATA, 'manifest.json')):
        check('site/data/manifest.json exists (run tools/build_data.py)', False); return
    m = load(os.path.join(DATA, 'manifest.json'))
    index = load(os.path.join(DATA, 'heroes.json'))
    heroes = index['heroes']
    en = load(os.path.join(ROOT, 'site', 'locales', 'en.json'))
    eq('data: format version', (m.get('v'), index.get('v')), (2, 2))
    check('data: the manifest has build time, data age and newest release', all(re.match(r'\d{4}-\d\d-\d\d', str(m.get(k, ''))) for k in ('built', 'dataFrom', 'newestRelease')), m)
    check('data: the age of the data is the oldest table used', m['dataFrom'] == min(m['fetched'].values()) and m['dataFrom'] <= m['built'], (m['dataFrom'], m['fetched']))
    eq('data: the newest release date is the newest in the hero list', m['newestRelease'], max(x['r'] for x in heroes if x['r'] <= m['built'][:10]))
    check('data: the licence named is CC BY-NC-SA', m['source']['licence'] == 'CC BY-NC-SA' and m['source']['licenceUrl'].startswith('https://'))
    check('data: at least 1,400 heroes', len(heroes) >= 1400, len(heroes))
    eq('data: the manifest counts the heroes', m['counts']['heroes'], len(heroes))
    ids = [x['id'] for x in heroes]
    check('data: hero numbers are unique positive whole numbers', len(set(ids)) == len(ids) and all(isinstance(i, int) and i > 0 for i in ids))
    check('data: wiki names are unique (old saved data and old links map through them)', len({x['wn'] for x in heroes}) == len(heroes))
    bad = [x['page'] for x in heroes if len(x['s']) != 5 or min(x['s']) <= 0 or sum(x['s']) != x['bst'] or not x['n'] or not x['w'] or not x['m'] or not re.match(r'\d{4}-\d\d-\d\d$', x['r']) or not isinstance(x['o'], list)]
    check('data: every hero has five stats, a total, names, weapon, movement, a release date', not bad, bad[:5])
    marth = next((x for x in heroes if x['wn'] == 'Marth Altean Prince'), None)
    check('data: Marth: Altean Prince is 41/31/34/29/23', marth and marth['s'] == B.MARTH, marth and marth['s'])
    check('data: no hero type twice on one hero', all(len(set(x['p'])) == len(x['p']) for x in heroes))
    check('data: no "aide" next to "aided"', not any('aide' in x['p'] for x in heroes))
    check('data: hero type "vista" is kept', (not any('vista' in B.props_of(u) for u in table('Units'))) or any('vista' in x['p'] for x in heroes))
    codes = {x['av'] for x in heroes}
    check('data: every availability code has a text', all('avail.' + c in en for c in codes), sorted(c for c in codes if 'avail.' + c not in en))
    tags = {p for x in heroes for p in x['p']}
    shown = set('legendary mythic emblem duo harmonized chosen vista special tempest grail story rearmed attuned aided ascended entwined brave fallen resplendent refresher'.split())
    check('data: every hero type is one the site knows', tags <= shown, sorted(tags - shown))
    expected = {'Alfonse Prince of Askr': 'story', 'Marth Altean Prince': 'pool34', 'Fjorm Princess of Ice': 'legendary', 'Ike Brave Mercenary': 'sr4', 'Alfonse Spring Prince': 'seasonal_sr4',
                'Arden Strong and Tough': 'grails', 'Aelfric Custodian Monk': 'grails', 'Celica Of Echoes': 'emblem', 'Ivy Icy Insight': 'seasonal', 'Arthur Hapless Hero': 'pool'}
    got = {x['wn']: x['av'] for x in heroes if x['wn'] in expected}
    eq('data: availability of ten known heroes', got, {k: v for k, v in expected.items() if k in got})
    check('data: ... and at least eight of them are in the data', len(got) >= 8, sorted(set(expected) - set(got)))
    size = os.path.getsize(os.path.join(DATA, 'heroes.json'))
    check('data: the hero index stays under 600 KB', size < 600 * 1024, size)

    # one file per hero
    names = set(os.listdir(os.path.join(DATA, 'hero')))
    eq('data: exactly one file per hero', names, {'%d.json' % i for i in ids})
    have_kits = m['tables'].get('Skills') == 'ok' and m['tables'].get('UnitSkills') == 'ok'
    have_focus = m['tables'].get('SummoningEventFocuses') == 'ok'
    have_builds = m['tables'].get('HeroBuilds') == 'ok'
    problems, leaks, biggest, n_builds, cut, modes, costs, with_kit = [], [], 0, 0, 0, set(), set(), 0
    by_id = {x['id']: x for x in heroes}
    for name in sorted(names):
        p = os.path.join(DATA, 'hero', name)
        biggest = max(biggest, os.path.getsize(p))
        h = load(p)
        x = by_id.get(h.get('id'))
        if not x or name != '%d.json' % h['id']: problems.append(name + ': wrong id'); continue
        if (h['kit'] is None) == have_kits: problems.append(name + ': kit is %s although the skill tables are %s' % ('null' if h['kit'] is None else 'there', 'there' if have_kits else 'missing'))
        if (h['banners'] is None) == have_focus: problems.append(name + ': banner history does not match the focus table\'s state')
        if (h['builds'] is None) == have_builds: problems.append(name + ': builds do not match the build table\'s state')
        if x['nb'] != (len(h['builds']) if h['builds'] is not None else None): problems.append(name + ': build count differs from the index')
        if h['kit']:
            with_kit += 1
            if x['k'] != {slot: rows[-1]['n'] for slot, rows in h['kit'].items()}: problems.append(name + ': final skills differ from the index')
            if not set(h['kit']) <= set(B.SLOT_ORDER) or any(not rows or any(not s.get('n') for s in rows) for rows in h['kit'].values()): problems.append(name + ': odd skill list')
        for b in h['builds'] or []:
            n_builds += 1
            modes.add(b.get('mode', '')); costs.add(b.get('cost', ''))
            if not any(b.get(k) for k, _ in B.BUILD_SLOTS): problems.append(name + ': a build without skills')
            if len(b.get('desc', '')) == 900: cut += 1
            if b.get('date') and not re.match(r'\d{4}-\d\d-\d\d$', b['date']): problems.append(name + ': odd build date')
        if h['builds'] and not h.get('buildsPage', '').startswith('Fire Emblem Heroes Wiki:Build Center/'): problems.append(name + ': builds without a source page')
        for b in h['banners'] or []:
            if not (isinstance(b['s'], int) and isinstance(b['e'], int) and b['e'] > b['s'] and b['n']): problems.append(name + ': odd banner entry')
        leaks += [(name + where, s) for where, s in B.find_leaks(h)]
    check('data: every hero file is sound', not problems, problems[:6])
    check('data: no markup in any hero file', not leaks, leaks[:3])
    check('data: no build text is cut at 900 characters', cut == 0, cut)
    eq('data: the manifest counts the builds', m['counts']['builds'], n_builds)
    eq('data: the manifest counts the heroes with skills', m['counts']['heroesWithKit'], with_kit)
    if have_kits: check('data: at least 90 % of the heroes have skills', with_kit >= 0.9 * len(heroes), '%d of %d' % (with_kit, len(heroes)))
    check('data: build modes and costs are closed lists with texts', all('build.mode.' + v in en for v in modes if v) and all('build.cost.' + v in en for v in costs if v), (sorted(modes), sorted(costs)))
    check('data: the largest hero file stays under 80 KB', biggest < 80 * 1024, biggest)

    # banners
    bn = load(os.path.join(DATA, 'banners.json'))
    banners = bn['banners']
    built = B.epoch(m['built'].replace('T', ' ').rstrip('Z'))
    check('data: banner times are UTC instants, end after start', banners and all(isinstance(b['s'], int) and isinstance(b['e'], int) and b['e'] > b['s'] for b in banners))
    check('data: banners start at 07:00:00 and end at 06:59:59 UTC', all(b['s'] % 86400 == 7 * 3600 and b['e'] % 86400 == 7 * 3600 - 1 for b in banners), [b['n'] for b in banners if b['s'] % 86400 != 7 * 3600][:3])
    check('data: at least one banner ran when the data was built', any(b['s'] <= built <= b['e'] for b in banners))
    check('data: banner ids are unique', len({b['id'] for b in banners}) == len(banners))
    eq('data: focus lists are null exactly when the focus table is missing', (bn['focusKnown'], all(b['f'] is None for b in banners), any(b['f'] is None for b in banners)), (have_focus, not have_focus, not have_focus))
    check('data: focus heroes are known hero numbers', all(f[0] in by_id for b in banners for f in (b['f'] or [])))
    if have_focus: check('data: most running banners name focus heroes', sum(1 for b in banners if b['f']) >= 0.5 * len(banners), '%d of %d' % (sum(1 for b in banners if b['f']), len(banners)))
    kinds = {b['k'] for b in banners}
    check('data: every banner kind has a note text', all('summon.tip.' + k in en for k in kinds), sorted(kinds))
    check('data: no markup in banners', not B.find_leaks(bn), B.find_leaks(bn)[:2])

    # orbs
    orbs = load(os.path.join(DATA, 'orbs.json'))
    rows = [r for g in orbs['groups'] for r in g['rows']]
    check('data: orb rows have instants, an amount and the paid flag', all(isinstance(r['s'], int) and isinstance(r['e'], int) and r['e'] > r['s'] and r['n'] > 0 and isinstance(r['pass'], bool) and r['name'] for r in rows), rows[:2])
    check('data: no orb row had ended when the data was built', all(r['e'] >= built for r in rows))
    check('data: Feh Pass rows are marked as paid and nothing else is', all(r['pass'] == ('feh pass' in r['name'].lower()) for r in rows))
    eq('data: only quests are promised; the rest is named as not covered', ([g['id'] for g in orbs['groups']] in ([], ['quests']), set(orbs['notCovered']) >= {'login', 'tempest'}), (True, True))
    meta = load(os.path.join(DATA, 'meta.json'))
    check('data: the guide lists point at known heroes', all(i in by_id for i in meta['newest']) and all(i in by_id for i, _ in meta['mostBuilt']))
    check('data: "newest from summoning" holds no free hero', all(by_id[i]['av'] not in ('story', 'grails') for i in meta['newest']))

    # in step with the cache: a table that has arrived since the last build must be built in
    now = {t: B.read_table(CACHE, t)[1] for t in B.REQUIRED + B.OPTIONAL}
    stale = sorted(t for t in now if now[t] == 'ok' and m['tables'].get(t) in ('missing', 'unreadable'))
    check('data: site/data holds every table the cache holds (else run tools/build_data.py)', not stale, 'arrived since the last build: ' + ', '.join(stale))

_tables = {}
def table(name):
    if name not in _tables: _tables[name] = B.read_table(CACHE, name)[0] or []
    return _tables[name]


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    for part in (unit_checks, gate_checks, disk_checks):
        try: part()
        except Exception as e:                              # a crash in a check is a failed check, not a silent stop
            import traceback
            check(part.__name__ + ' ran to its end', False, traceback.format_exc()[-900:])
    print('test_data: %d checks, %d failed' % (total, len(failed)))
    sys.exit(1 if failed else 0)
