"""Reads the Fire Emblem Heroes community wiki's data tables (Cargo) politely: one request every few seconds,
back-off when the wiki says "rate limited", every answer kept in tools/cache so a second run asks nothing twice.

    python -I tools/wiki.py fields Units Skills        # field names of tables
    python -I tools/wiki.py dump Units                 # all rows of a table into tools/cache/Units.json
"""
import io, json, os, sys, time, urllib.parse, urllib.request

API = 'https://feheroes.fandom.com/api.php'
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
PAUSE = 2.5
_last = 0.0

def ask(params):
    global _last
    url = API + '?' + urllib.parse.urlencode(dict(params, format='json'))
    for attempt in range(8):
        wait = PAUSE - (time.time() - _last)
        if wait > 0: time.sleep(wait)
        _last = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'feh-companion-data/0.1 (static fan site builder)'})
            with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
        except Exception as e:
            data = {'error': {'code': 'network', 'info': str(e)}}
        err = data.get('error')
        if not err: return data
        if err.get('code') in ('ratelimited', 'network'):
            time.sleep(15 * (attempt + 1)); continue
        raise RuntimeError('%s: %s' % (err.get('code'), err.get('info')))
    raise RuntimeError('gave up after repeated rate limits: ' + url)

def fields(table):
    return list((ask({'action': 'cargofields', 'table': table}).get('cargofields') or {}).keys())

def dump(table, where=None, fresh=False, extra=None):
    """All rows of a table as a list of dicts (cached)."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, table + '.json')
    if os.path.exists(path) and not fresh:
        with open(path, encoding='utf-8') as f: return json.load(f)
    names = fields(table)
    cols = ['_pageName=Page'] + names + (extra or [])
    part = path + '.part'                      # pages so far, so a stopped download goes on where it was
    rows = []
    if os.path.exists(part) and not fresh:
        with open(part, encoding='utf-8') as f: rows = json.load(f)
    offset = len(rows)
    while True:
        p = {'action': 'cargoquery', 'tables': table, 'fields': ','.join(cols), 'limit': '500', 'offset': str(offset), 'order_by': '_pageName,_ID'}
        if where: p['where'] = where
        got = [r['title'] for r in ask(p).get('cargoquery', [])]
        rows += got; offset += len(got)
        print('  %s: %d rows' % (table, len(rows)), file=sys.stderr)
        if len(got) < 500: break
        with open(part, 'w', encoding='utf-8') as f: json.dump(rows, f, ensure_ascii=False)
    with open(path, 'w', encoding='utf-8') as f: json.dump(rows, f, ensure_ascii=False)
    if os.path.exists(part): os.remove(part)
    return rows

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    cmd, tables = sys.argv[1], sys.argv[2:]
    for t in tables:
        if cmd == 'fields': print(t, fields(t))
        else:
            rows = dump(t)
            print(t, len(rows), 'rows; first:', json.dumps(rows[0], ensure_ascii=False)[:700] if rows else None)
