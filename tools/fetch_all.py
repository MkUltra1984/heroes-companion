"""Downloads every wiki table the site is built from into tools/cache (see wiki.py). Run with --fresh to ask again.
    python -I tools/fetch_all.py [--fresh]
"""
import datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki

fresh = '--fresh' in sys.argv
today = datetime.date.today().isoformat()
soon = "EndTime >= '%s'" % today                     # still running or still to come
recent = "EndTime >= '%s'" % (datetime.date.today() - datetime.timedelta(days=420)).isoformat()

# in the order the site needs them; the wiki allows roughly one page of 500 rows per 40 seconds
FILTERED = [('Units', None), ('UnitStats', None), ('SummoningEvents', recent), ('QuestRewards', soon), ('TempestTrialsRewards', soon), ('LogInBonusRewards', soon),
            ('HeroBuilds', None), ('UnitSkills', None), ('Skills', None), ('SummoningEventFocuses', None)]

for t, where in FILTERED:
    try: print(t, len(wiki.dump(t, where=where, fresh=fresh)), flush=True)
    except Exception as e: print(t, 'FAILED', e, flush=True)
print('done', flush=True)
