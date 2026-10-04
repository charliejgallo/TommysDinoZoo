#!/usr/bin/env python3
"""Add (or update with --force) strings in content/<pack>/lang/{es,en}.po.

    python3 tools/po_add.py strings.json [--pack base] [--force]

strings.json: {"key": ["castellano", "English"], ...}
"""
import json
import re
import sys

args = sys.argv[1:]
pack = 'base'
if '--pack' in args:
    pack = args[args.index('--pack') + 1]
force = '--force' in args
data = json.load(open(args[0]))
for i, loc in enumerate(('es', 'en')):
    p = f'game/content/{pack}/lang/{loc}.po'
    s = open(p).read()
    for k, v in data.items():
        val = v[i].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        if f'msgid "{k}"\n' in s:
            if force:
                s = re.sub(r'(msgid "%s"\nmsgstr )".*"' % re.escape(k), lambda m: m.group(1) + '"%s"' % val, s)
        else:
            s += f'msgid "{k}"\nmsgstr "{val}"\n\n'
    open(p, 'w').write(s)
print(len(data), 'strings')
