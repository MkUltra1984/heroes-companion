"""Adds or replaces text keys in both language files, keeping the files' order.
    python -I tools/addkeys.py <json file with { "key": ["english", "german"], ... }> [key after which new keys go]
"""
import io, json, os, sys, collections
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site', 'locales')
new = json.load(io.open(sys.argv[1], encoding='utf-8'), object_pairs_hook=collections.OrderedDict)
after = sys.argv[2] if len(sys.argv) > 2 else None
for i, lang in enumerate(('en', 'de')):
    p = os.path.join(root, lang + '.json')
    cur = json.load(io.open(p, encoding='utf-8'), object_pairs_hook=collections.OrderedDict)
    out = collections.OrderedDict()
    fresh = [(k, v[i]) for k, v in new.items() if k not in cur]
    for k, v in cur.items():
        out[k] = new[k][i] if k in new else v
        if k == after:
            for nk, nv in fresh: out[nk] = nv
            fresh = []
    for nk, nv in fresh: out[nk] = nv
    io.open(p, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(lang, len(out), 'keys')
