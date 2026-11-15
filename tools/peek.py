"""Shows the shape of a cached wiki table: python -I tools/peek.py Units [field to count values of] [substring filter]"""
import collections, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
rows = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', sys.argv[1] + '.json'), encoding='utf-8'))
print(len(rows), 'rows')
flt = sys.argv[3] if len(sys.argv) > 3 else None
shown = 0
for r in rows:
    if flt and flt.lower() not in json.dumps(r, ensure_ascii=False).lower(): continue
    print(json.dumps({k: (v[:160] if isinstance(v, str) else v) for k, v in r.items()}, ensure_ascii=False)); shown += 1
    if shown >= 3: break
if len(sys.argv) > 2 and sys.argv[2] != '-':
    c = collections.Counter()
    for r in rows:
        for part in str(r.get(sys.argv[2]) or '').split(','): c[part.strip()] += 1
    print(sys.argv[2], c.most_common(60))
