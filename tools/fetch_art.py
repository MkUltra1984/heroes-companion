"""Fetches hero artwork for the site from the Fire Emblem Heroes community wiki. Standard library only, resumable.

    python -I tools/fetch_art.py manifest [selection] [--max-api N] [--probe] [--kinds fpbcdio] [--recheck]
    python -I tools/fetch_art.py download [selection] [--force]
    python -I tools/fetch_art.py stats

    selection:  --limit N            the N newest heroes (order of site/data/heroes.json)
                --heroes "A;B"       these hero ids as well (or only these, without --limit)
                (neither)            every hero

manifest  Finds out which files each hero has and writes art/manifest.json after every request, so a stopped run
          goes on where it was and a second run asks nothing twice. Two sources:
            - the wiki's API (imageinfo, 50 file titles per request, through wiki.ask with its pause and back-off).
              This host is rate limited. --max-api N caps the requests of this run (retries count); the run also
              stops when the wiki answers "ratelimited" three times in a row.
            - --probe: for every title still unknown afterwards, one HEAD request to the image CDN at the address
              computed from the file name (no wiki request at all). Use --max-api 0 --probe to stay off the wiki.
download  Fetches from the image CDN at the final sizes, as WebP, one file at a time with a short pause:
            art/face/{file}.webp           square face icon, 128 px
            art/card/{file}.webp           full portrait, 300 px wide (300 x 360)
            art/sprite/{file}_idle.webp    map sprite, standing pose, native size
            art/sprite/{file}_ok.webp      map sprite, cheering pose, native size
          {file} is the hero id with spaces as underscores; a Resplendent attire is {file}_Resplendent.
          Files that exist are skipped. A file the manifest does not know yet is simply tried and the answer
          (there / not there) is written into the manifest, so "download" also works without a manifest run.
stats     Bytes per hero at each size from what is on disk, and the projection for all heroes.

Known state (2026-11-15): the image CDN answers Python's own HTTPS client with a challenge page (status 403) even
with a Referer and an agent name, so --probe and "download" stop after five such answers and fetch nothing. The API
part of "manifest" works. See reviews/round2/assets.md for the options; the owner decides.

Not fetched on purpose: attack, special and damaged portraits are only listed in the manifest (the hero page loads
them from the CDN); weapon and movement icons are original generated art (PLAN.md, decision 4); skill icons need the
icon field of the wiki's Skills table and cannot be guessed from a name, so they are not part of this tool.
"""
import argparse, hashlib, http.client, io, json, os, sys, time, types, urllib.error, urllib.parse, urllib.request

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
ART = os.path.join(ROOT, 'art')
MANIFEST = os.path.join(ART, 'manifest.json')
HEROES = os.path.join(ROOT, 'site', 'data', 'heroes.json')
UNITS = os.path.join(TOOLS, 'cache', 'Units.json')

CDN_HOST = 'static.wikia.nocookie.net'
CDN_PATH = '/feheroes_gamepedia_en/images/'
REFERER = 'https://feheroes.fandom.com/'          # without a referrer the CDN answers a challenge page
AGENT = 'Mozilla/5.0 (compatible; fan-site-art-fetch/1.0)'
CDN_PAUSE = 0.4
STOP_AFTER_BAD = 5                                 # answers in a row that are neither an image nor "not found"

# key -> file title ending on the wiki
KINDS = {'f': 'Face FC.webp', 'p': 'Face.webp', 'b': 'BtlFace.webp', 'c': 'BtlFace C.webp', 'd': 'BtlFace D.webp',
         'i': 'Mini Unit Idle.png', 'o': 'Mini Unit Ok.png'}
KIND_NAMES = {'f': 'face icon', 'p': 'portrait', 'b': 'attack portrait', 'c': 'special portrait',
              'd': 'damaged portrait', 'i': 'map sprite, idle', 'o': 'map sprite, ok'}
# local name -> (source kind, folder, file name ending, CDN size part)
OUTPUTS = {'face': ('f', 'face', '', '/scale-to-width-down/128'),
           'card': ('p', 'card', '', '/scale-to-width-down/300'),
           'idle': ('i', 'sprite', '_idle', ''),
           'ok': ('o', 'sprite', '_ok', '')}
SETS = ('base', 'resp')


class StopRun(BaseException):
    """Ends the run in an orderly way (passes through wiki.ask, which only catches Exception)."""


# ---------------------------------------------------------------- names and addresses

def file_stem(hero_id, resp=False):
    """Hero id -> name that is safe in URLs and on every file system (ASCII letters, digits, _ and -)."""
    stem = ''.join(c if c.isascii() and (c.isalnum() or c == '-') else '_' for c in hero_id)
    return stem + ('_Resplendent' if resp else '')

def title_of(hero_id, kind, resp=False):
    return '%s %s%s' % (hero_id, 'Resplendent ' if resp else '', KINDS[kind])

def hash_of(title):
    return hashlib.md5(title.replace(' ', '_').encode('utf-8')).hexdigest()[:2]

def cdn_path(title, prefix=None, size=''):
    name = title.replace(' ', '_')
    h = prefix or hash_of(title)
    return '%s%s/%s/%s/revision/latest%s' % (CDN_PATH, h[0], h, urllib.parse.quote(name), size)


# ---------------------------------------------------------------- manifest file

def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding='utf-8') as f: return json.load(f)
    return {'version': 1,
            'about': 'Which artwork files each hero has on the Fire Emblem Heroes Wiki and what was downloaded. '
                     'Written by tools/fetch_art.py. See art/README.md.',
            'cdn': 'https://' + CDN_HOST + CDN_PATH,
            'kinds': KINDS,
            'heroes': {}}

def save_manifest(man):
    os.makedirs(ART, exist_ok=True)
    man['updated'] = time.strftime('%Y-%m-%d', time.gmtime())
    tmp = MANIFEST + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    os.replace(tmp, MANIFEST)

def select(args):
    with open(HEROES, encoding='utf-8') as f: heroes = json.load(f)['heroes']
    known = {h['id']: h for h in heroes}
    named = [s.strip() for s in (args.heroes or '').split(';') if s.strip()]
    for n in named:
        if n not in known: sys.exit('unknown hero id: ' + n)
    if args.limit is None and not named: chosen = heroes
    else:
        first = heroes[:args.limit or 0]
        have = {h['id'] for h in first}
        chosen = [known[n] for n in named if n not in have] + first
    stems = {}
    for h in heroes:                                    # two ids must never end in the same file name
        s = file_stem(h['id']).lower()
        if s in stems: sys.exit('file name clash: %s / %s' % (stems[s], h['id']))
        stems[s] = h['id']
    return chosen, heroes

def entry(man, hero, artists):
    e = man['heroes'].setdefault(hero['id'], {})
    e['file'] = file_stem(hero['id'])
    if hero['id'] in artists: e['artist'] = artists[hero['id']]
    e.setdefault('base', {})
    if 'resplendent' in hero.get('p', []): e.setdefault('resp', {})
    e.setdefault('local', {})
    return e

def load_artists():
    if not os.path.exists(UNITS): return {}
    with open(UNITS, encoding='utf-8') as f: rows = json.load(f)
    return {r['WikiName']: r['Artist'].strip() for r in rows if r.get('WikiName') and (r.get('Artist') or '').strip()}


# ---------------------------------------------------------------- the image CDN (one connection, one file at a time)

class Cdn:
    def __init__(self):
        self.conn = None; self.last = 0.0; self.requests = 0; self.bad = 0

    def ask(self, method, path):
        """-> (status, content type, body). Status 0 means the connection failed twice."""
        for attempt in range(2):
            wait = CDN_PAUSE - (time.time() - self.last)
            if wait > 0: time.sleep(wait)
            self.last = time.time(); self.requests += 1
            try:
                if self.conn is None: self.conn = http.client.HTTPSConnection(CDN_HOST, timeout=60)
                self.conn.request(method, path, headers={'User-Agent': AGENT, 'Referer': REFERER, 'Accept': 'image/webp,image/*'})
                r = self.conn.getresponse()
                body = r.read()
                return r.status, (r.getheader('Content-Type') or ''), body, r.getheader('Content-Length')
            except Exception as e:
                try: self.conn.close()
                except Exception: pass
                self.conn = None; err = e
                time.sleep(5)
        return 0, str(err), b'', None

    def judge(self, status):
        """Counts answers that are neither "here it is" nor "not found" and stops the run when they pile up."""
        if status in (200, 404): self.bad = 0; return
        self.bad += 1
        if self.bad >= STOP_AFTER_BAD: raise StopRun('%d answers in a row from the image CDN were not usable (last status %s)' % (self.bad, status))


def image_size(data):
    """(format, width, height) of a WebP or PNG file, or None when it is neither."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png', int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP' or len(data) < 30: return None
    tag = data[12:16]
    if tag == b'VP8X':
        return 'webp', int.from_bytes(data[24:27], 'little') + 1, int.from_bytes(data[27:30], 'little') + 1
    if tag == b'VP8L':
        bits = int.from_bytes(data[21:25], 'little')
        return 'webp', (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
    if tag == b'VP8 ':
        return 'webp', int.from_bytes(data[26:28], 'little') & 0x3fff, int.from_bytes(data[28:30], 'little') & 0x3fff
    return None


# ---------------------------------------------------------------- step: manifest

def guarded_wiki(max_requests):
    """wiki.ask with two extra brakes that count every attempt: a request budget, and a stop after three
    "ratelimited" answers in a row. wiki.py itself is not changed; only the opener it sees is wrapped."""
    if TOOLS not in sys.path: sys.path.insert(0, TOOLS)
    import wiki
    state = types.SimpleNamespace(sent=0, limited=0, limited_total=0)

    def urlopen(req, timeout=60):
        if max_requests is not None and state.sent >= max_requests: raise StopRun('API request budget of %d used' % max_requests)
        state.sent += 1
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: body = r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429: raise
            body = b'{"error":{"code":"ratelimited","info":"HTTP 429"}}'
        if b'"ratelimited"' in body[:400]:
            state.limited += 1; state.limited_total += 1
            if state.limited >= 3: raise StopRun('the wiki answered "ratelimited" three times in a row')
        else: state.limited = 0
        return io.BytesIO(body)

    wiki.urllib = types.SimpleNamespace(parse=urllib.parse, request=types.SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen))
    return wiki, state

def step_manifest(args):
    chosen, _ = select(args)
    man, artists = load_manifest(), load_artists()
    kinds = [k for k in KINDS if k in (args.kinds or ''.join(KINDS))]
    todo = []                                           # (hero id, set, kind, title)
    for h in chosen:
        e = entry(man, h, artists)
        for s in SETS:
            if s not in e: continue
            for k in kinds:
                if k not in e[s] or (args.recheck and e[s][k] is None): todo.append((h['id'], s, k, title_of(h['id'], k, s == 'resp')))
    save_manifest(man)
    print('%d heroes selected, %d file titles to look up' % (len(chosen), len(todo)))
    done = {'api': 0, 'cdn': 0}; mismatch = []; stopped = None
    started = time.time(); state = None; cdn = Cdn()
    try:
        if todo and args.max_api != 0:
            wiki, state = guarded_wiki(args.max_api)
            while todo:
                batch, by_title = todo[:50], {}
                for hid, s, k, t in batch: by_title[t] = (hid, s, k)
                q = wiki.ask({'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|size|mime|timestamp',
                              'titles': '|'.join('File:' + t for t in by_title)}).get('query', {})
                back = {n['to']: n['from'] for n in q.get('normalized', [])}
                seen = 0
                for page in q.get('pages', {}).values():
                    t = back.get(page.get('title'), page.get('title', ''))
                    t = t[5:] if t.startswith('File:') else t
                    if t not in by_title: continue
                    hid, s, k = by_title[t]; seen += 1
                    info = (page.get('imageinfo') or [None])[0]
                    if info is None: man['heroes'][hid][s][k] = None; continue
                    x = info['url'].split(CDN_PATH, 1)[-1].split('/')[1] if CDN_PATH in info['url'] else hash_of(t)
                    if x != hash_of(t): mismatch.append(t)
                    man['heroes'][hid][s][k] = {'x': x, 'w': info.get('width'), 'h': info.get('height'), 'bytes': info.get('size'),
                                                'ts': info.get('timestamp'), 'via': 'api'}
                if seen != len(batch): print('  warning: %d of %d titles not answered; they stay unknown' % (len(batch) - seen, len(batch)))
                todo = todo[50:]; done['api'] += seen
                save_manifest(man)
                print('  api request %d: %d titles, %.0f s since start' % (state.sent, seen, time.time() - started))
    except StopRun as e:
        stopped = str(e); print('  stopped asking the wiki: ' + stopped)
    try:
        if todo and args.probe:
            print('  probing %d titles on the image CDN' % len(todo))
            for n, (hid, s, k, t) in enumerate(todo):
                status, ctype, body, length = cdn.ask('HEAD', cdn_path(t))
                cdn.judge(status)
                if status == 200: man['heroes'][hid][s][k] = {'x': hash_of(t), 'via': 'cdn'}; done['cdn'] += 1
                elif status == 404: man['heroes'][hid][s][k] = None; done['cdn'] += 1
                if n % 25 == 24: save_manifest(man)
            todo = [x for x in todo if x[2] not in man['heroes'][x[0]][x[1]]]
    except StopRun as e:
        stopped = str(e); print('  stopped: ' + stopped)
        todo = [x for x in todo if x[2] not in man['heroes'][x[0]][x[1]]]
    finally:
        save_manifest(man)
    have = miss = 0; gaps = {}
    for h in chosen:
        e = man['heroes'][h['id']]
        for s in SETS:
            for k, v in e.get(s, {}).items():
                if v is None: miss += 1; gaps.setdefault(k, []).append(h['id'] + (' (Resplendent)' if s == 'resp' else ''))
                else: have += 1
    print('manifest: %d files exist, %d missing, %d still unknown' % (have, miss, len(todo)))
    print('  looked up now: %d by API in %d request(s)%s, %d by CDN probe (%d CDN requests), %.0f s' % (
        done['api'], state.sent if state else 0, (', %d rate-limit answers' % state.limited_total) if state else '', done['cdn'], cdn.requests, time.time() - started))
    if mismatch: print('  address rule differs from the API for %d titles, e.g. %s' % (len(mismatch), mismatch[0]))
    for k in KINDS:
        if k in gaps: print('  no %s: %s' % (KIND_NAMES[k], '; '.join(gaps[k][:12]) + (' ... (%d)' % len(gaps[k]) if len(gaps[k]) > 12 else '')))
    without = [h['id'] for h in chosen if 'artist' not in man['heroes'][h['id']]]
    if without: print('  no artist name for %d heroes, e.g. %s' % (len(without), without[0]))
    return 1 if stopped else 0


# ---------------------------------------------------------------- step: download

def out_path(stem, out, fmt='webp'):
    kind, folder, tail, size = OUTPUTS[out]
    return os.path.join(ART, folder, '%s%s.%s' % (stem, tail, fmt))

def step_download(args):
    chosen, _ = select(args)
    man, artists = load_manifest(), load_artists()
    cdn = Cdn(); count = {'new': 0, 'skipped': 0, 'missing': 0, 'failed': 0}; new_bytes = 0; failures = []; stopped = None
    started = time.time()
    for folder in {v[1] for v in OUTPUTS.values()}: os.makedirs(os.path.join(ART, folder), exist_ok=True)
    try:
        for n, h in enumerate(chosen):
            e = entry(man, h, artists)
            for s in SETS:
                if s not in e: continue
                stem = file_stem(h['id'], s == 'resp')
                for out, (kind, folder, tail, size) in OUTPUTS.items():
                    key = out if s == 'base' else 'r_' + out
                    src = e[s].get(kind, {})
                    if src is None: count['missing'] += 1; continue
                    loc = e['local'].get(key)
                    if loc and not args.force and loc.get('ts') == src.get('ts') and os.path.exists(out_path(stem, out, loc.get('fmt', 'webp'))):
                        count['skipped'] += 1; continue
                    title = title_of(h['id'], kind, s == 'resp')
                    status, ctype, body, _ = cdn.ask('GET', cdn_path(title, src.get('x'), size))
                    if status == 404:
                        cdn.judge(status); e[s][kind] = None; count['missing'] += 1; continue
                    img = image_size(body) if status == 200 else None
                    if img is None:
                        count['failed'] += 1; failures.append('%s: status %s, %s, %d bytes' % (title, status, ctype[:40], len(body)))
                        cdn.judge(status if status != 200 else -1); continue
                    cdn.judge(200)
                    fmt, w, hgt = img
                    path = out_path(stem, out, fmt)
                    with open(path + '.part', 'wb') as f: f.write(body)
                    os.replace(path + '.part', path)
                    if not src: e[s][kind] = src = {'x': hash_of(title), 'via': 'cdn'}
                    e['local'][key] = {'bytes': len(body), 'w': w, 'h': hgt}
                    if fmt != 'webp': e['local'][key]['fmt'] = fmt
                    if src.get('ts'): e['local'][key]['ts'] = src['ts']
                    count['new'] += 1; new_bytes += len(body)
            if n % 10 == 9:
                save_manifest(man)
                print('  %d of %d heroes, %d new files, %.1f MB, %.0f s' % (n + 1, len(chosen), count['new'], new_bytes / 1e6, time.time() - started))
    except StopRun as e:
        stopped = str(e)
    except KeyboardInterrupt:
        stopped = 'interrupted'
    finally:
        save_manifest(man)
    print('download: %d new, %d already there, %d not on the wiki, %d failed; %.2f MB fetched in %d CDN requests, %.0f s' % (
        count['new'], count['skipped'], count['missing'], count['failed'], new_bytes / 1e6, cdn.requests, time.time() - started))
    for line in failures[:20]: print('  failed: ' + line)
    if stopped: print('  stopped early: ' + stopped)
    return 1 if stopped or failures else 0


# ---------------------------------------------------------------- step: stats

def step_stats(args):
    with open(HEROES, encoding='utf-8') as f: heroes = json.load(f)['heroes']
    man = load_manifest()
    n_base, n_resp = len(heroes), sum('resplendent' in h.get('p', []) for h in heroes)
    sums = {}; done = 0
    for hid, e in man['heroes'].items():
        if e.get('local'): done += 1
        for key, loc in e.get('local', {}).items():
            s = sums.setdefault(key, [0, 0, 0, 0]); s[0] += 1; s[1] += loc['bytes']; s[2] = max(s[2], loc['bytes']); s[3] = max(s[3], loc['w'] * 10000 + loc['h'])
    print('%d heroes with downloaded files; all heroes: %d, of them with a Resplendent attire: %d' % (done, n_base, n_resp))
    print('%-8s %6s %10s %10s %10s %12s' % ('file', 'count', 'average', 'largest', 'max w x h', 'projected'))
    total = 0; per_hero = 0
    for key in list(OUTPUTS) + ['r_' + o for o in OUTPUTS]:
        if key not in sums: continue
        c, b, mx, dim = sums[key]
        proj = b / c * (n_resp if key.startswith('r_') else n_base); total += proj
        if not key.startswith('r_'): per_hero += b / c
        print('%-8s %6d %8.1f kB %8.1f kB %10s %9.1f MB' % (key, c, b / c / 1e3, mx / 1e3, '%dx%d' % (dim // 10000, dim % 10000), proj / 1e6))
    print('per hero (one attire, four files): %.1f kB; projected for all heroes and attires: %.0f MB in about %d files' % (
        per_hero / 1e3, total / 1e6, (n_base + n_resp) * len(OUTPUTS)))
    return 0


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    ap = argparse.ArgumentParser(description='Hero artwork: manifest, download, stats.')
    ap.add_argument('step', choices=['manifest', 'download', 'stats'])
    ap.add_argument('--limit', type=int, help='the N newest heroes')
    ap.add_argument('--heroes', help='hero ids separated by ";"')
    ap.add_argument('--max-api', type=int, help='manifest: at most this many wiki API requests in this run (0 = none)')
    ap.add_argument('--probe', action='store_true', help='manifest: look up what is still unknown on the image CDN')
    ap.add_argument('--kinds', help='manifest: only these file kinds, letters of ' + ''.join(KINDS))
    ap.add_argument('--recheck', action='store_true', help='manifest: ask again for files that were missing')
    ap.add_argument('--force', action='store_true', help='download: fetch again what is already there')
    a = ap.parse_args()
    sys.exit({'manifest': step_manifest, 'download': step_download, 'stats': step_stats}[a.step](a))
