"""Copies the written content into the site.

    python -I tools/build_site.py [--check]

content/ is where the texts are written and reviewed; the page can only load what lies below site/. This script
  1. copies content/summon_rules.json, picks.json and currencies.json to site/content/ (compact, same data),
  2. replaces every guide.* text in site/locales/en.json with the keys of content/guide.en.json.
With --check nothing is written: the exit code is 1 when the site is not in step with content/.
"""
import io, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
CONTENT = os.path.join(ROOT, 'content')
SITE = os.path.join(ROOT, 'site')
FILES = ('summon_rules', 'picks', 'currencies')


def load(path):
    with io.open(path, encoding='utf-8') as f: return json.load(f)

def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n'

def pretty(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + '\n'

def plan():
    """{path: text} of everything this script owns."""
    out = {}
    for name in FILES:
        out[os.path.join(SITE, 'content', name + '.json')] = compact(load(os.path.join(CONTENT, name + '.json')))
    guide = load(os.path.join(CONTENT, 'guide.en.json'))['keys']
    bad = [k for k, v in guide.items() if not k.startswith('guide.') or not isinstance(v, str)]
    if bad: raise SystemExit('guide.en.json: keys that are not guide texts: %s' % bad[:5])
    locale_path = os.path.join(SITE, 'locales', 'en.json')
    cur = load(locale_path)
    merged, placed = {}, False
    for k, v in cur.items():
        if k.startswith('guide.'):
            if not placed: merged.update(guide); placed = True       # the guide keeps its place in the file
            continue
        merged[k] = v
    if not placed: merged.update(guide)
    out[locale_path] = pretty(merged)
    return out

def main(argv):
    check = '--check' in argv
    stale = []
    for path, text in plan().items():
        old = None
        if os.path.exists(path):
            with io.open(path, encoding='utf-8') as f: old = f.read()
        if old == text: continue
        stale.append(os.path.relpath(path, ROOT))
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with io.open(path, 'w', encoding='utf-8', newline='\n') as f: f.write(text)
    if check:
        print('build_site --check: %s' % ('in step' if not stale else 'out of step: ' + ', '.join(stale)))
        return 1 if stale else 0
    print('build_site: %d file(s) written%s' % (len(stale), (': ' + ', '.join(stale)) if stale else ' (everything was in step)'))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
