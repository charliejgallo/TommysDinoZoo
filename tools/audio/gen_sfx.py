#!/usr/bin/env python3
"""Generate every sound effect of Tommy's Dino Zoo into game/assets/sfx/*.ogg.

All procedural (see synth.py). Soft and round on purpose: no harsh highs,
short attacks only where a tick or click needs them, peaks at -6 dBFS
(footsteps and menu ticks lower).

    python3 tools/audio/gen_sfx.py            # all
    python3 tools/audio/gen_sfx.py pet eat     # only these
    WAV=1 ...                                  # also dump WAVs to the scratch dir
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth import *  # noqa: E402,F401,F403
import synth as S  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'game', 'assets', 'sfx')
SCRATCH = os.environ.get('AUDIO_SCRATCH', '/private/tmp/claude-501/-Users-charlie-Dropbox-ClaudeCode/'
                         'bea4eb56-79a2-4f4b-8313-37463248a60c/scratchpad/audio')

# ---------------------------------------------------------------- helpers


class Mix:
    """Mono timeline: place signals at times (seconds)."""

    def __init__(self, length):
        self.x = np.zeros(ns(length))

    def at(self, t, sig, gain=1.0):
        s = ns(t)
        sig = np.asarray(sig, float)
        if sig.ndim == 2:
            sig = sig.mean(0)
        if s + len(sig) > len(self.x):
            self.x = np.concatenate([self.x, np.zeros(s + len(sig) - len(self.x))])
        self.x[s:s + len(sig)] += sig * gain
        return self

    def out(self):
        return self.x


def room(x, wet=0.15, size=0.5, damp=0.45, tail=0.6):
    x = np.concatenate([x, np.zeros(ns(tail))])
    r = reverb(x, room=size, damp=damp, predelay=0.012).mean(0)
    return x + r * wet * 6


def glide(f0, f1, dur, curve=3.0):
    """Exponential-ish pitch glide array from f0 to f1."""
    n = ns(dur)
    u = np.linspace(0, 1, n)
    k = (1 - np.exp(-curve * u)) / (1 - np.exp(-curve)) if curve else u
    return f0 * (f1 / f0) ** k


def blip(f0, f1, dur, tau=None, a=0.003, harm=0.15, curve=3.0):
    f = glide(f0, f1, dur, curve)
    n = len(f)
    c = 2 * np.pi * cycles(f, n)
    x = np.sin(c) + harm * np.sin(2 * c) + harm * 0.3 * np.sin(3 * c)
    env = perc(n, a, tau if tau else dur / 3)
    return fade(x * env, 0, 0.004)


def thump(f=110, dur=0.25, tau=0.06, drop=1.6, nz=0.5, nzf=500):
    n = ns(dur)
    t = tvec(n)
    f_ = f * (1 + (drop - 1) * np.exp(-t / 0.02))
    x = np.sin(2 * np.pi * cycles(f_, n)) * perc(n, 0.002, tau)
    x += lowpass(noise(n) * perc(n, 0.001, tau * 0.5), nzf) * nz * 2
    return fade(x, 0, 0.01)


def wood(f, dur=0.25, taus=(0.06, 0.025, 0.012), amps=(1, 0.45, 0.18), ratios=(1, 2.32, 4.1)):
    return modal(f, dur, ratios, amps, taus, attack=0.0006)


SPARK_PC = [0, 2, 4, 7, 9]  # pentatonic


def sparkle(count=4, lo=84, hi=100, spread=0.25, vel=0.5, up=False, inst=glock):
    """A few high pentatonic pings. lo/hi are MIDI notes."""
    pool = [m for m in range(lo, hi + 1) if m % 12 in SPARK_PC]
    picks = sorted(S.rng().choice(pool, count)) if up else S.rng().choice(pool, count)
    mx = Mix(spread + 2.5)
    for i, m in enumerate(picks):
        t = (i / max(count - 1, 1)) * spread if up else S.rng().uniform(0, spread)
        mx.at(t, inst(hz(int(m)), vel * S.rng().uniform(0.6, 1.0)))
    return mx.out()


def grains(dur, count, flo, fhi, glen=(0.003, 0.009), env=None, q=2.0):
    """Granular texture: short band-passed noise bursts at random times."""
    mx = Mix(dur + 0.05)
    for _ in range(count):
        if env is None:
            t = S.rng().uniform(0, dur)
        else:
            t = env()
        n = ns(S.rng().uniform(*glen))
        g = bandpass(noise(n + 64), S.rng().uniform(flo, fhi), q)[:n] * np.hanning(n)
        mx.at(t, g, S.rng().uniform(0.4, 1.0))
    return mx.out()


def swish(dur, f0, f1, q=1.2, shape=1.0):
    n = ns(dur)
    u = np.linspace(0, 1, n)
    f = f0 * (f1 / f0) ** u
    x = bandpass(noise(n), f, q)
    env = np.sin(np.pi * u ** shape) ** 2
    return x * env


def tri_env(n, peak_at=0.3):
    u = np.linspace(0, 1, n)
    return np.where(u < peak_at, u / peak_at, (1 - u) / (1 - peak_at))


def finish(x, peak_db=-6.0, trim_db=-42, fout=None, maxlen=2.0):
    x = np.asarray(x, float)
    if len(x) > ns(maxlen):
        # damp long ringing tails naturally instead of chopping them
        t = tvec(len(x))
        t0 = 0.45 * maxlen
        x = x * np.exp(-np.maximum(t - t0, 0) * 6.9 / (maxlen - t0))
        x = x[:ns(maxlen)]
    x = highpass(x, 40)
    a = np.abs(x)
    thr = a.max() * undb(trim_db)
    idx = np.nonzero(a > thr)[0]
    if len(idx):
        x = x[:min(len(x), idx[-1] + ns(0.02))]
    if fout is None:
        fout = min(0.45, 0.3 * len(x) / SR)
    x = fade(x, 0.0008, fout)
    return normalize(x, peak_db)


# ---------------------------------------------------------------- sounds

def slot():
    x = wood(1850, 0.08, taus=(0.014, 0.008, 0.004), amps=(1, 0.35, 0.12))
    x += wood(700, 0.08, taus=(0.02, 0.01, 0.005), amps=(0.35, 0.1, 0.0))
    return finish(room(x, 0.06, tail=0.2), -8)


def drop():
    x = thump(95, 0.35, tau=0.075, drop=1.7, nz=0.6, nzf=420)
    x += wood(260, 0.35, taus=(0.05, 0.02, 0.01), amps=(0.25, 0.08, 0.02))
    return finish(room(x, 0.05, tail=0.3))


def pickup():
    mx = Mix(0.4)
    mx.at(0, blip(520, 1050, 0.11, tau=0.05))
    mx.at(0.065, blip(780, 1560, 0.13, tau=0.06), 0.8)
    return finish(room(mx.out(), 0.12, tail=0.4))


def pet():
    mx = Mix(1.2)
    # purr: low hum with 24 Hz pulses
    n = ns(0.7)
    t = tvec(n)
    pf = 92 + 6 * np.sin(2 * np.pi * 1.4 * t)
    purr = voice(pf, [(0, 'm'), (1, 'm')], scale=1.1)
    purr *= (0.55 + 0.45 * np.sin(2 * np.pi * 24 * t) ** 2) * tri_env(n, 0.25)
    mx.at(0, lowpass(purr, 900), 0.55)
    # coo: rising-falling "oo"
    n = ns(0.42)
    u = np.linspace(0, 1, n)
    f0 = 500 + 140 * np.sin(np.pi * u ** 0.8) - 30 * u
    coo = voice(f0, [(0, 'u'), (0.5, 'o'), (1, 'u')], scale=1.45) * adsr(n, 0.04, 0.2, 0.8, 0.12)
    mx.at(0.08, coo, 0.9)
    mx.at(0.32, sparkle(3, 91, 100, 0.25, 0.35, up=True))
    return finish(room(mx.out(), 0.18, tail=0.6), maxlen=1.6)


def eat():
    mx = Mix(1.0)
    for i, (t, p) in enumerate([(0, 1.0), (0.21, 1.1), (0.42, 0.94)]):
        n = ns(0.09)
        crunch = grains(0.07, 14, 1300 * p, 3200 * p, (0.002, 0.006))[:n]
        crunch = crunch * tri_env(len(crunch), 0.2)
        mx.at(t, crunch, 0.7)
        nn = ns(0.14)
        f0 = glide(250 * p, 190 * p, 0.14)
        nom = voice(f0, [(0, 'o'), (0.55, 'u'), (1, 'm')], scale=1.3) * adsr(nn, 0.01, 0.08, 0.7, 0.05)
        mx.at(t + 0.015, nom, 0.9)
        mx.at(t, thump(120 * p, 0.12, tau=0.03, drop=1.3, nz=0.2), 0.35)
    return finish(room(mx.out(), 0.06, tail=0.3))


def nope():
    mx = Mix(0.8)
    for t, f, d in [(0, hz('E4'), 0.19), (0.24, hz('C4'), 0.28)]:
        n = ns(d)
        u = np.linspace(0, 1, n)
        f0 = f * (1.03 - 0.05 * u)
        x = voice(f0, [(0, 'm'), (0.5, 'u'), (1, 'm')], scale=1.2) * adsr(n, 0.03, 0.1, 0.85, 0.06)
        mx.at(t, x)
    return finish(room(mx.out(), 0.08, tail=0.3))


def brush():
    mx = Mix(0.8)
    mx.at(0, swish(0.22, 2400, 4600, q=1.0, shape=0.8))
    mx.at(0.27, swish(0.24, 4400, 2600, q=1.0, shape=0.8), 0.9)
    x = lowpass(mx.out(), 7000)
    return finish(room(x, 0.05, tail=0.2), -8)


def happy():
    mx = Mix(1.2)
    for i, m in enumerate(['C6', 'E6', 'G6', 'C7']):
        mx.at(i * 0.06, kalimba(hz(m), 0.6 + 0.1 * i))
    n = ns(0.3)
    t = tvec(n)
    f = glide(900, 1700, 0.3, 2.0) * (1 + 0.03 * np.sin(2 * np.pi * 14 * t))
    mx.at(0.05, np.sin(2 * np.pi * cycles(f, n)) * adsr(n, 0.02, 0.1, 0.6, 0.1), 0.3)
    return finish(room(mx.out(), 0.15, tail=0.6), maxlen=1.4)


def photo():
    mx = Mix(0.5)
    mx.at(0, wood(2300, 0.05, taus=(0.008, 0.004, 0.002)), 0.6)
    for t, g in [(0.03, 1.0), (0.10, 0.7)]:
        n = ns(0.03)
        burst = bandpass(noise(n), 2600, 2.0) * perc(n, 0.0005, 0.006)
        mech = modal(1350, 0.06, [1, 1.9, 3.3], [1, 0.4, 0.2], [0.018, 0.01, 0.006], attack=0.0005)
        mx.at(t, burst * 1.5, g)
        mx.at(t, mech, 0.5 * g)
    x = lowpass(mx.out(), 7000)
    return finish(room(x, 0.06, tail=0.25))


def fill():
    dur = 0.95

    def tdist():
        u = S.rng().uniform()
        return dur * (u ** 0.85) * 0.92
    x = grains(dur, 260, 1300, 4200, (0.002, 0.007), tdist, q=2.5) * 0.9
    x += grains(dur, 90, 450, 1100, (0.004, 0.012), tdist, q=2.0) * 0.8
    n = len(x)
    x *= np.clip(np.linspace(0, 1, n) / 0.06, 0, 1) * np.clip((1 - np.linspace(0, 1, n)) / 0.25, 0, 1)
    x = peak_eq(peak_eq(x, 330, 4, 9), 880, 4, 6)   # inside a wooden trough
    x = lowpass(x, 6500)
    mx = Mix(1.2)
    mx.at(0, x)
    mx.at(0.0, wood(210, 0.3, taus=(0.08, 0.03, 0.015)), 0.25)
    return finish(room(mx.out(), 0.08, tail=0.4))


def egg():
    mx = Mix(1.6)
    mx.at(0, wood(240, 0.3, ratios=(1, 2.45, 3.9), taus=(0.07, 0.035, 0.015)), 0.8)
    mx.at(0, thump(140, 0.2, tau=0.04, drop=1.4, nz=0.3), 0.4)
    n = ns(1.25)
    t = tvec(n)
    hum = np.zeros(n)
    for m in ['F4', 'A4', 'C5']:
        f = hz(m) * (1 + 0.003 * np.sin(2 * np.pi * 4.5 * t))
        hum += wt(table([1, 0.15, 0.05]), f, n)
    hum *= adsr(n, 0.25, 0.4, 0.7, 0.5, hold=0.7)
    mx.at(0.06, hum, 0.22)
    mx.at(0.3, glock(hz('C7'), 0.25))
    return finish(room(mx.out(), 0.15, tail=0.6), maxlen=1.8)


def shake():
    dur = 0.85
    n = ns(dur)
    env = np.zeros(n)
    for _ in range(26):
        t0 = S.rng().uniform(0, dur * 0.8)
        L = ns(S.rng().uniform(0.02, 0.07))
        s = ns(t0)
        e = min(n, s + L)
        env[s:e] += np.hanning(L)[:e - s] * S.rng().uniform(0.4, 1.0)
    env *= np.clip((1 - np.linspace(0, 1, n)) / 0.4, 0, 1)
    x = bandpass(noise(n), 4200, 0.7) * env
    x += bandpass(noise(n), 1600, 0.9) * env * 0.5
    x = lowpass(x, 8000)
    return finish(room(x, 0.05, tail=0.2), -7)


def scoop():
    mx = Mix(0.8)
    n = ns(0.28)
    u = np.linspace(0, 1, n)
    fc = 350 + 1300 * np.sin(np.pi * u ** 0.7)
    sq = bandpass(noise(n), fc, 3.5) * np.sin(np.pi * u) ** 1.5
    mx.at(0, sq, 0.9)
    mx.at(0.02, blip(320, 160, 0.14, tau=0.06, harm=0.25), 0.6)
    mx.at(0.31, blip(480, 1100, 0.09, tau=0.035, harm=0.2), 0.9)
    return finish(room(mx.out(), 0.08, tail=0.4))


def plant():
    mx = Mix(0.6)
    for t, g, f in [(0, 1.0, 100), (0.19, 0.85, 92)]:
        mx.at(t, thump(f, 0.18, tau=0.045, drop=1.3, nz=0.8, nzf=380), g)
        mx.at(t, grains(0.05, 10, 1500, 3500, (0.002, 0.004)), 0.15 * g)
    return finish(room(mx.out(), 0.04, tail=0.25))


def water():
    dur = 0.9
    n = ns(dur)
    u = np.linspace(0, 1, n)
    hiss = bandpass(noise(n), 4800, 0.6) * np.sin(np.pi * np.clip(u * 1.1, 0, 1)) ** 0.8 * 0.5
    mx = Mix(1.2)
    mx.at(0, lowpass(hiss, 8000))
    for _ in range(26):
        t = S.rng().uniform(0.02, dur * 0.85)
        f = S.rng().uniform(1400, 3300)
        mx.at(t, blip(f, f * 1.7, 0.02, tau=0.008, harm=0.0, curve=1.0), S.rng().uniform(0.2, 0.5))
    return finish(room(mx.out(), 0.1, tail=0.4), -7)


def harvest():
    mx = Mix(1.2)
    mx.at(0, blip(240, 620, 0.09, tau=0.045, harm=0.3, curve=2.0))
    mx.at(0, swish(0.12, 2500, 4000, q=1.0) * 0.5)
    for i, m in enumerate(['G6', 'B6', 'D7']):
        mx.at(0.12 + i * 0.07, glock(hz(m), 0.35))
    return finish(room(mx.out(), 0.15, tail=0.6), maxlen=1.4)


def place():
    mx = Mix(1.4)
    mx.at(0, wood(175, 0.4, taus=(0.11, 0.05, 0.02)))
    mx.at(0, thump(90, 0.25, tau=0.05, drop=1.4, nz=0.4), 0.6)
    mx.at(0.09, fm_bell(hz('E6'), 0.45, ratio=3.5, index=1.0, tau=0.7), 0.5)
    return finish(room(mx.out(), 0.12, tail=0.6), maxlen=1.5)


def throw():
    n = ns(0.42)
    u = np.linspace(0, 1, n)
    f = 450 + 1500 * np.sin(np.pi * np.clip(u * 0.9, 0, 1)) ** 2
    x = bandpass(noise(n), f, 1.4) * np.sin(np.pi * u ** 0.8) ** 2
    return finish(room(lowpass(x, 5000), 0.05, tail=0.2), -7)


def coin_ping(f, vel=0.7):
    return modal(f, 0.6, [1, 2.37, 4.09, 5.9], [1, 0.45, 0.2, 0.08], [0.18, 0.09, 0.05, 0.03],
                 attack=0.0005) * vel


def coins():
    mx = Mix(1.0)
    for t, f, v in [(0, 2350, 0.8), (0.05, 2650, 0.6), (0.09, 2200, 0.7), (0.15, 2900, 0.55),
                    (0.22, 2500, 0.5)]:
        mx.at(t, coin_ping(f * S.rng().uniform(0.98, 1.02), v))
    mx.at(0.25, sparkle(2, 96, 103, 0.12, 0.25, up=True))
    x = lowpass(mx.out(), 9000)
    return finish(room(x, 0.12, tail=0.5), maxlen=1.5)


def buy():
    mx = Mix(1.6)
    mx.at(0, coin_ping(2400, 0.5))
    mx.at(0.04, coin_ping(2750, 0.4))
    mx.at(0.06, fm_bell(hz('C6'), 0.7, ratio=2.0, index=1.0, tau=0.9))
    mx.at(0.18, fm_bell(hz('G6'), 0.75, ratio=2.0, index=1.0, tau=1.0))
    x = lowpass(mx.out(), 9000)
    return finish(room(x, 0.15, tail=0.6), maxlen=1.8)


def ui():
    x = fade(marimba(hz('G5'), 0.9, hard=0.45)[:ns(0.5)], 0, 0.2)
    return finish(room(x, 0.06, tail=0.3), -6)


def ui_move():
    x = marimba(hz('C6'), 0.6, hard=0.2)[:ns(0.16)]
    return finish(fade(x, 0, 0.06), -10)


def crack(f, g=1.0):
    n = ns(0.05)
    b = bandpass(noise(n), f, 3.0) * perc(n, 0.0004, 0.005)
    tick = modal(f * 0.7, 0.05, [1, 1.7, 2.9], [1, 0.5, 0.25], [0.012, 0.007, 0.004], attack=0.0004)
    return (b * 1.2 + tick * 0.6) * g


def hatch():
    mx = Mix(3.0)
    for t, f, g in [(0, 2600, 0.45), (0.26, 2300, 0.6), (0.42, 2900, 0.7), (0.52, 2400, 0.8)]:
        mx.at(t, crack(f, g))
        mx.at(t + 0.012, crack(f * 1.2, g * 0.5))
    mx.at(0.72, blip(300, 720, 0.1, tau=0.04, harm=0.25), 0.8)
    mx.at(0.72, thump(120, 0.15, tau=0.04, nz=0.2), 0.4)
    n = ns(0.24)
    f0 = glide(950, 1450, 0.24, 1.5)
    mx.at(0.84, voice(f0, [(0, 'i'), (1, 'i')], scale=1.6) * adsr(n, 0.02, 0.1, 0.8, 0.08), 0.9)
    for i, m in enumerate(['C6', 'E6', 'G6', 'C7']):
        mx.at(1.15 + i * 0.08, glock(hz(m), 0.55))
    for m in ['C6', 'E6', 'G6']:
        mx.at(1.45, fm_bell(hz(m), 0.3, ratio=2.0, index=0.8, tau=0.9), 0.5)
    mx.at(1.5, sparkle(4, 96, 103, 0.4, 0.25))
    x = lowpass(mx.out(), 9000)
    return finish(room(x, 0.15, tail=0.8), maxlen=2.8)


def grow():
    dur = 1.5
    n = ns(dur)
    t = tvec(n)
    u = np.linspace(0, 1, n)
    x = np.zeros(n)
    for i in range(10):
        f0 = S.rng().uniform(500, 1100)
        f = f0 * 2 ** (1.6 * u ** 1.4)
        trem = 0.6 + 0.4 * np.sin(2 * np.pi * S.rng().uniform(9, 14) * t + S.rng().uniform(0, 6))
        x += np.sin(2 * np.pi * cycles(f, n)) * trem / 10
    x *= np.sin(np.pi * u ** 0.6) ** 2
    mx = Mix(2.5)
    mx.at(0, x, 0.55)
    pool = [m for m in range(79, 103) if m % 12 in SPARK_PC]
    for i, m in enumerate(pool[::2][:10]):
        mx.at(0.05 + i * 0.12, glock(hz(m), 0.3 + 0.03 * i))
    return finish(room(mx.out(), 0.25, size=0.7, tail=1.0), maxlen=2.4)


def mission():
    mx = Mix(2.6)
    step = 0.105
    for i, m in enumerate(['C5', 'A4', 'C5', 'F5']):
        mx.at(i * step, marimba(hz(m), 0.85, hard=0.5))
        mx.at(i * step, glock(hz(m) * 2, 0.25))
    t = 4 * step + 0.02
    for m in ['F4', 'A4', 'C5', 'F5']:
        mx.at(t, kalimba(hz(m), 0.6))
        mx.at(t, fm_bell(hz(m) * 2, 0.25, ratio=2.0, index=0.7, tau=0.9))
    mx.at(t, bass(hz('F2'), 0.6, 0.5), 0.6)
    mx.at(t + 0.15, sparkle(5, 91, 105, 0.5, 0.28, up=True))
    x = lowpass(mx.out(), 10000)
    return finish(room(x, 0.15, tail=0.8), maxlen=2.2)


def heart():
    mx = Mix(1.8)
    for t, m in [(0, 'E6'), (0.17, 'A6')]:
        mx.at(t, fm_bell(hz(m), 0.7, ratio=2.0, index=0.9, tau=0.8))
        mx.at(t, sine(hz(m) / 2, ns(0.8)) * perc(ns(0.8), 0.01, 0.25), 0.25)
    return finish(room(mx.out(), 0.18, tail=0.8), maxlen=1.8)


def yawn():
    dur = 1.45
    n = ns(dur)
    u = np.linspace(0, 1, n)
    f0 = np.where(u < 0.22, 360 + 60 * (u / 0.22), 420 * (175 / 420) ** ((np.clip(u - 0.22, 0, 1) / 0.78) ** 0.9))
    x = voice(f0, [(0, 'a'), (0.45, 'a'), (0.7, 'o'), (0.86, 'u'), (1, 'm')], scale=1.25,
              breath=0.05)
    x *= adsr(n, 0.18, 0.5, 0.8, 0.35)
    return finish(room(x, 0.08, tail=0.4))


def step_grass(k):
    S.seed(700 + k)
    mx = Mix(0.25)
    n = ns(0.12)
    fc = [2300, 2700, 2000][k - 1]
    sw = bandpass(noise(n), fc, 0.8) * perc(n, 0.006, 0.03)
    mx.at(0, sw, 1.0)
    mx.at(0.004, grains(0.06, 8, 1800, 4500, (0.002, 0.005)), 0.45)
    mx.at(0, thump(80 + 8 * k, 0.12, tau=0.03, drop=1.2, nz=0.6, nzf=250), 0.18)
    return finish(lowpass(mx.out(), 6000), -12)


def door():
    mx = Mix(1.0)
    mx.at(0, modal(2100, 0.06, [1, 1.6, 2.7], [1, 0.4, 0.2], [0.012, 0.008, 0.004], attack=0.0004), 0.5)
    mx.at(0.03, modal(1500, 0.06, [1, 1.6, 2.7], [1, 0.4, 0.2], [0.012, 0.008, 0.004]), 0.35)
    mx.at(0.06, lowpass(swish(0.36, 350, 900, q=0.9), 1500), 0.5)
    mx.at(0.4, wood(150, 0.4, taus=(0.1, 0.045, 0.02)), 0.8)
    mx.at(0.4, thump(85, 0.2, tau=0.04, nz=0.3), 0.4)
    return finish(room(mx.out(), 0.1, tail=0.4))


def splash():
    mx = Mix(1.2)
    n = ns(0.5)
    u = np.linspace(0, 1, n)
    body = lowpass(noise(n), 6000 * (0.12 ** u)) * perc(n, 0.004, 0.11)
    mx.at(0, body, 1.4)
    mx.at(0, blip(180, 380, 0.08, tau=0.04, harm=0.2), 0.7)
    for _ in range(12):
        f = S.rng().uniform(900, 2600)
        mx.at(S.rng().uniform(0.08, 0.5), blip(f, f * 1.8, 0.025, tau=0.009, harm=0, curve=1.0),
              S.rng().uniform(0.15, 0.4))
    return finish(room(lowpass(mx.out(), 8000), 0.1, tail=0.4))


# ---------------------------------------------------------------- dino voices

def chirps(spec, scale, vowel='i'):
    """spec: list of (t, dur, f_start, f_peak, f_end, gain)."""
    mx = Mix(1.5)
    for t, d, a, b, c, g in spec:
        n = ns(d)
        u = np.linspace(0, 1, n)
        f0 = np.where(u < 0.4, a * (b / a) ** (u / 0.4), b * (c / b) ** ((u - 0.4) / 0.6))
        x = voice(f0, [(0, vowel), (1, vowel)], scale=scale) * adsr(n, 0.008, 0.05, 0.8, d * 0.3)
        mx.at(t, x, g)
    return mx.out()


def voice_tiny(k):
    if k == 1:
        x = chirps([(0, 0.07, 1800, 2700, 2300, 1), (0.1, 0.07, 1900, 2900, 2400, 0.9),
                    (0.2, 0.09, 2000, 3100, 2200, 0.8)], 1.9)
    else:
        n = ns(0.36)
        t = tvec(n)
        f0 = (2100 + 500 * t / 0.36) * (1 + 0.09 * np.sin(2 * np.pi * 26 * t))
        x = voice(f0, [(0, 'i'), (1, 'e')], scale=1.9) * adsr(n, 0.01, 0.1, 0.8, 0.08)
        x *= 0.6 + 0.4 * np.sin(2 * np.pi * 26 * t + 1) ** 2
    return finish(room(lowpass(x, 9000), 0.06, tail=0.3))


def voice_small(k):
    if k == 1:
        x = chirps([(0, 0.13, 650, 1150, 850, 1), (0.17, 0.16, 700, 1250, 800, 0.9)], 1.35, 'e')
    else:
        n = ns(0.5)
        t = tvec(n)
        u = t / 0.5
        f0 = (820 + 120 * np.sin(np.pi * u)) * (1 + 0.07 * np.sin(2 * np.pi * 18 * t))
        f0 = np.where(u > 0.75, f0 * (1 + 0.5 * (u - 0.75) / 0.25), f0)
        x = voice(f0, [(0, 'e'), (0.6, 'i'), (1, 'i')], scale=1.35) * adsr(n, 0.02, 0.1, 0.85, 0.08)
        x *= 0.65 + 0.35 * np.sin(2 * np.pi * 18 * t) ** 2
    return finish(room(x, 0.08, tail=0.3))


def voice_mid(k):
    if k == 1:
        n = ns(0.6)
        u = np.linspace(0, 1, n)
        f0 = 165 + 40 * np.sin(np.pi * u ** 0.7) - 15 * u
        x = voice(f0, [(0, 'u'), (0.35, 'a'), (0.75, 'o'), (1, 'u')], scale=1.0, tilt=0.9)
        x *= adsr(n, 0.04, 0.2, 0.85, 0.15)
    else:
        n = ns(0.75)
        t = tvec(n)
        u = t / 0.75
        f0 = 120 + 30 * np.sin(np.pi * u) - 10 * u
        x = voice(f0, [(0, 'm'), (0.3, 'u'), (0.7, 'o'), (1, 'm')], scale=0.95)
        x *= (0.7 + 0.3 * np.sin(2 * np.pi * 20 * t) ** 2) * adsr(n, 0.08, 0.3, 0.85, 0.2)
    return finish(room(lowpass(x, 5000), 0.1, tail=0.4))


def voice_big(k):
    if k == 1:
        dur = 1.15
        n = ns(dur)
        t = tvec(n)
        u = t / dur
        f0 = 72 + 16 * np.sin(np.pi * u ** 0.8) - 8 * u
        x = voice(f0, [(0, 'r'), (0.25, 'r'), (0.5, 'u'), (0.8, 'u'), (1, 'm')], scale=0.68,
                  tilt=1.1, breath=0.015)
        roll = np.where(u < 0.45, 0.55 + 0.45 * np.sin(2 * np.pi * 22 * t) ** 2, 1.0)
        x *= roll * adsr(n, 0.08, 0.4, 0.85, 0.3)
    else:
        dur = 1.3
        n = ns(dur)
        t = tvec(n)
        u = t / dur
        f0 = (92 + 22 * np.sin(np.pi * u ** 0.9)) * (1 + 0.012 * np.sin(2 * np.pi * 5 * t) * u)
        x = voice(f0, [(0, 'o'), (0.5, 'o'), (0.8, 'u'), (1, 'm')], scale=0.72, tilt=1.0)
        x *= adsr(n, 0.12, 0.4, 0.85, 0.35)
    return finish(room(lowpass(x, 3500), 0.12, size=0.6, tail=0.6))


def voice_baby(k):
    if k == 1:
        n = ns(0.26)
        f0 = glide(880, 1320, 0.26, 2.0)
        x = voice(f0, [(0, 'i'), (1, 'i')], scale=1.6) * adsr(n, 0.02, 0.1, 0.8, 0.07)
    else:
        x = chirps([(0, 0.13, 1050, 1150, 820, 1), (0.18, 0.15, 1000, 1100, 760, 0.85)], 1.6, 'i')
    return finish(room(x, 0.08, tail=0.3))


# ---------------------------------------------------------------- extras

def crest():
    """Parasaurolophus crest toot (the dino that 'plays music')."""
    mx = Mix(1.6)
    for t, m, d in [(0, 'G3', 0.32), (0.36, 'C4', 0.6)]:
        n = ns(d)
        tt = tvec(n)
        f0 = hz(m) * (1 + 0.006 * np.sin(2 * np.pi * 5 * tt) * np.clip(tt / 0.2, 0, 1))
        x = voice(f0, [(0, 'u'), (1, 'o')], scale=0.9, tilt=1.4) * adsr(n, 0.05, 0.2, 0.85, 0.12)
        mx.at(t, x)
    return finish(room(lowpass(mx.out(), 4000), 0.2, size=0.65, tail=0.8), maxlen=2.0)


def ball():
    """Rubber ball bounce: boing."""
    n = ns(0.45)
    t = tvec(n)
    f = 170 * (1 + 0.35 * np.exp(-t / 0.05) + 0.06 * np.sin(2 * np.pi * 11 * t) * np.exp(-t / 0.15))
    x = np.sin(2 * np.pi * cycles(f, n)) * perc(n, 0.002, 0.12)
    x += 0.2 * np.sin(4 * np.pi * cycles(f, n)) * perc(n, 0.002, 0.05)
    mx = Mix(0.6)
    mx.at(0, x)
    mx.at(0, thump(90, 0.15, tau=0.03, nz=0.3), 0.5)
    return finish(room(mx.out(), 0.05, tail=0.3))


SOUNDS = {
    'slot': slot, 'drop': drop, 'pickup': pickup, 'pet': pet, 'eat': eat, 'nope': nope,
    'brush': brush, 'happy': happy, 'photo': photo, 'fill': fill, 'egg': egg, 'shake': shake,
    'scoop': scoop, 'plant': plant, 'water': water, 'harvest': harvest, 'place': place,
    'throw': throw, 'coins': coins, 'buy': buy, 'ui': ui, 'ui_move': ui_move, 'hatch': hatch,
    'grow': grow, 'mission': mission, 'heart': heart, 'yawn': yawn, 'door': door,
    'splash': splash, 'crest': crest, 'ball': ball,
}
for _k in (1, 2, 3):
    SOUNDS['step_grass_%d' % _k] = (lambda k: lambda: step_grass(k))(_k)
for _sz, _fn in [('tiny', voice_tiny), ('small', voice_small), ('mid', voice_mid),
                 ('big', voice_big), ('baby', voice_baby)]:
    for _k in (1, 2):
        SOUNDS['voice_%s_%d' % (_sz, _k)] = (lambda f, k: lambda: f(k))(_fn, _k)


def main(names):
    os.makedirs(OUT, exist_ok=True)
    dump = os.environ.get('WAV')
    if dump:
        os.makedirs(SCRATCH, exist_ok=True)
    for i, name in enumerate(sorted(SOUNDS)):
        if names and name not in names:
            continue
        S.seed(1000 + i * 7919)
        x = SOUNDS[name]()
        write_ogg(os.path.join(OUT, name + '.ogg'), x, q=4)
        if dump:
            write_wav(os.path.join(SCRATCH, name + '.wav'), x)
        print('%-16s %5.2f s  peak %6.1f dBFS' % (name, len(x) / SR, db(peak(x))))


if __name__ == '__main__':
    main(set(sys.argv[1:]))
