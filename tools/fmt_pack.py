#!/usr/bin/env python3
"""Rewrite a pack.json compactly: one entry per line inside each table."""
import json
import sys

for path in sys.argv[1:]:
    d = json.load(open(path))
    out = ['{']
    keys = list(d)
    for i, k in enumerate(keys):
        v = d[k]
        comma = ',' if i < len(keys) - 1 else ''
        if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            out.append('  %s: {' % json.dumps(k))
            ids = list(v)
            w = max(len(json.dumps(x)) for x in ids) + 1
            for j, e in enumerate(ids):
                c2 = ',' if j < len(ids) - 1 else ''
                out.append('    %s %s%s' % ((json.dumps(e) + ':').ljust(w), json.dumps(v[e], ensure_ascii=False), c2))
            out.append('  }' + comma)
        else:
            out.append('  %s: %s%s' % (json.dumps(k), json.dumps(v, ensure_ascii=False), comma))
    out.append('}')
    open(path, 'w').write('\n'.join(out) + '\n')
