#!/usr/bin/env python3
"""Numeric listen-check of the generated audio: decodes every OGG in
game/assets/{sfx,music} and prints duration, size, peak, RMS, loudness,
clipping and (for loops) how cleanly the end flows into the start.

Seam columns (music loops only, measured on the decoded file):
  jump   |last - first| sample step at the wrap, relative to the 99th
         percentile of steps within +-20 ms (<= 1: no bigger than a normal step)
  click  2nd difference (curvature) across the wrap, dB relative to the 99th
         percentile within +-20 ms (a real click shows up as +10 dB or more)
  lvl    RMS of the last 2 s vs the first 2 s (dB): no level drop at the wrap
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth as S  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
NO_LOOP = {'summary'}


def hp2(x):
    return np.diff(x, 2, axis=-1)


def seam(x):
    """Wrap the file end->start and compare the sample steps / curvature that
    straddle the wrap with those in the +-20 ms around it (where a note
    attack on beat 1 legitimately lives)."""
    c = S.ns(0.5)
    w = np.concatenate([x[:, -c:], x[:, :c]], axis=1)
    nb = S.ns(0.02)
    step = np.abs(np.diff(w, axis=1))
    curv = np.abs(np.diff(w, 2, axis=1))
    near = np.r_[c - 1 - nb:c - 2, c + 1:c + 1 + nb]
    jump = step[:, c - 1].max() / (np.percentile(step[:, near], 99) + 1e-12)
    click = 20 * np.log10(curv[:, c - 2:c].max() / (np.percentile(curv[:, near], 99) + 1e-12))
    r = S.ns(2.0)
    lvl = 20 * np.log10(np.sqrt((x[:, -r:] ** 2).mean()) / np.sqrt((x[:, :r] ** 2).mean()))
    return jump, click, lvl


def main():
    rows = []
    for kind in ('music', 'sfx'):
        d = os.path.join(ROOT, 'game', 'assets', kind)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.ogg'):
                continue
            p = os.path.join(d, f)
            x = S.read_audio(p).astype(float)
            name = f[:-4]
            dur = x.shape[1] / S.SR
            pk = S.db(S.peak(x))
            rms = S.db(np.sqrt((x ** 2).mean()))
            lu = S.loudness(x)
            clip = int((np.abs(x) >= 0.999).sum())
            sm = seam(x) if kind == 'music' and name not in NO_LOOP else None
            rows.append((kind, name, x.shape[0], dur, os.path.getsize(p), pk, rms, lu, clip, sm))
    print('%-6s %-16s %2s %7s %7s %7s %7s %7s %4s  %s' % (
        'kind', 'name', 'ch', 'sec', 'KB', 'peak', 'rms', 'LUFS', 'clip', 'seam jump/click/lvl'))
    for kind, name, ch, dur, size, pk, rms, lu, clip, sm in rows:
        s = '' if sm is None else '%.2f / %+.1f dB / %+.1f dB' % sm
        print('%-6s %-16s %2d %7.2f %7d %7.1f %7.1f %7.1f %4d  %s' % (
            kind, name, ch, dur, size // 1024, pk, rms, lu, clip, s))
    bad = [r for r in rows if r[8] or r[5] > -0.5]
    print('\n%d files, %d with clipping/over -0.5 dBFS' % (len(rows), len(bad)))


if __name__ == '__main__':
    main()
