#!/usr/bin/env python3
"""Tiny procedural synth for Tommy's Dino Zoo. numpy only, no samples.

Everything works on float64 numpy arrays at SR. Mono signals are 1-D,
stereo signals are shaped (2, n).

  oscillators   sine, wavetable (additive, band-limited), noise (white/pink/brown)
  envelopes     adsr, perc, fades
  filters       RBJ biquads (static: exact frequency response applied by FFT;
                swept: block-wise exact recursion), one-pole
  instruments   marimba, kalimba, music box, glockenspiel (modal), FM bell,
                FM electric piano, Karplus-Strong pluck, round bass, soft pad,
                breathy flute, shaker, soft kick, woodblock, formant voice
  space         Schroeder/Freeverb reverb (combs + allpasses, vectorised by
                delay-length blocks), constant-power panning
  levels        peak normalise, BS.1770 integrated loudness (K-weighted, gated)
  sequencing    note names, chord symbols, "C5:1 A4:.5 r:1" strings, Song
                (beats -> samples, sends, loop folding of tails)
  output        write_ogg / write_wav through ffmpeg / wave
"""
import math
import re
import subprocess
import wave

import numpy as np

SR = 44100
_rng = np.random.default_rng(1)


def seed(s):
    global _rng
    _rng = np.random.default_rng(s)


def rng():
    return _rng


def ns(sec):
    return max(0, int(round(sec * SR)))


def tvec(n):
    return np.arange(n) / SR


def db(x):
    return 20 * np.log10(max(float(x), 1e-12))


def undb(d):
    return 10 ** (d / 20)


# ---------------------------------------------------------------- pitch

_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
_NOTE_RE = re.compile(r'^([A-G])([#b]?)(-?\d+)$')


def note(name):
    """'C4' -> 60, 'F#5' -> 78, 'Bb3' -> 58."""
    m = _NOTE_RE.match(name)
    if not m:
        raise ValueError('bad note %r' % name)
    pc = _PC[m.group(1)] + {'#': 1, 'b': -1, '': 0}[m.group(2)]
    return 12 * (int(m.group(3)) + 1) + pc


def mtof(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def hz(x):
    return float(mtof(note(x))) if isinstance(x, str) else float(mtof(x))


# ---------------------------------------------------------------- oscillators

def _farr(freq, n):
    return np.broadcast_to(np.asarray(freq, float), (n,))


def cycles(freq, n, ph0=0.0):
    """Running phase in cycles for a (possibly per-sample) frequency."""
    f = _farr(freq, n)
    c = np.empty(n)
    c[0] = 0.0
    if n > 1:
        np.cumsum(f[:-1], out=c[1:])
    return ph0 + c / SR


def sine(freq, n, ph0=0.0):
    return np.sin(2 * np.pi * cycles(freq, n, ph0))


TBL = 4096


def table(amps, phases=None):
    """One period of an additive waveform: amps[k-1] for harmonic k."""
    amps = np.asarray(amps, float)
    k = np.arange(1, len(amps) + 1)[:, None]
    x = np.arange(TBL)[None, :] / TBL
    ph = 0 if phases is None else np.asarray(phases, float)[:, None]
    return (amps[:, None] * np.sin(2 * np.pi * k * x + ph)).sum(0)


def harmonics(f0, kind='saw', fc=None, slope=4, maxf=0.45 * SR, kmax=256):
    """Harmonic amplitudes of a band-limited waveform with optional spectral
    low-pass at fc (a 'filter' baked into the additive table)."""
    K = int(max(1, min(kmax, maxf // max(f0, 1.0))))
    k = np.arange(1, K + 1, dtype=float)
    if kind == 'saw':
        a = 1 / k
    elif kind == 'square':
        a = (k % 2 == 1) / k
    elif kind == 'tri':
        a = (k % 2 == 1) / k ** 2 * np.where(((k - 1) // 2) % 2 == 0, 1, -1)
    else:
        raise ValueError(kind)
    if fc:
        a = a / np.sqrt(1 + (k * f0 / fc) ** slope)
    return a


def wt(tb, freq, n, ph0=0.0):
    """Wavetable oscillator with linear interpolation."""
    c = cycles(freq, n, ph0) % 1.0
    idx = c * TBL
    i0 = idx.astype(np.int64)
    fr = idx - i0
    return tb[i0] * (1 - fr) + tb[(i0 + 1) % TBL] * fr


def noise(n, color='white'):
    w = _rng.standard_normal(n)
    if color == 'white' or n < 4:
        return w * 0.3
    W = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    W *= (1 / np.sqrt(f)) if color == 'pink' else (1 / f)
    x = np.fft.irfft(W, n)
    return x / (np.std(x) + 1e-12) * 0.3


# ---------------------------------------------------------------- envelopes

def ramp_in(n, a):
    """Raised-cosine 0..1 over `a` seconds, then 1."""
    m = ns(a)
    e = np.ones(n)
    if m > 0:
        m2 = min(m, n)
        e[:m2] = 0.5 - 0.5 * np.cos(np.pi * np.arange(m2) / m)
    return e


def perc(n, a=0.002, tau=0.3):
    return ramp_in(n, a) * np.exp(-np.maximum(tvec(n) - a, 0) / tau)


def adsr(n, a=0.01, d=0.2, s=0.7, r=0.2, hold=None):
    """Attack (raised cosine) / exponential decay to s / release.
    `hold` = seconds the key is down (default: n minus release)."""
    t = tvec(n)
    g = min(n, ns(hold) if hold is not None else n - ns(r))
    e = s + (1 - s) * np.exp(-np.maximum(t - a, 0) / max(d / 3, 1e-4))
    e *= ramp_in(n, a)
    if g < n:
        l0 = e[g - 1] if g > 0 else 0.0
        e[g:] = l0 * np.exp(-(t[g:] - t[g]) / max(r / 5, 1e-4))
    return fade(e, 0, 0.004)


def fade(x, fin=0.002, fout=0.01):
    x = np.array(x, float, copy=True)
    n = x.shape[-1]
    a, b = min(ns(fin), n), min(ns(fout), n)
    if a > 0:
        x[..., :a] *= np.linspace(0, 1, a, endpoint=False)
    if b > 0:
        x[..., n - b:] *= np.linspace(1, 0, b)
    return x


# ---------------------------------------------------------------- filters

def rbj(kind, f, q=0.7071, gain_db=0.0):
    """RBJ cookbook biquad. f/q may be arrays (one set per element)."""
    f = np.clip(np.asarray(f, float), 5.0, 0.49 * SR)
    w0 = 2 * np.pi * f / SR
    cw, sw = np.cos(w0), np.sin(w0)
    al = sw / (2 * np.asarray(q, float))
    A = 10 ** (gain_db / 40)
    one = np.ones_like(cw)
    if kind == 'lp':
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'hp':
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'bp':
        b = [al, 0 * cw, -al]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'notch':
        b = [one, -2 * cw, one]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'peak':
        b = [1 + al * A, -2 * cw, 1 - al * A]; a = [1 + al / A, -2 * cw, 1 - al / A]
    elif kind in ('ls', 'hs'):
        sA = 2 * np.sqrt(A) * al
        s = 1 if kind == 'ls' else -1
        b = [A * ((A + 1) - s * (A - 1) * cw + sA),
             s * 2 * A * ((A - 1) - s * (A + 1) * cw),
             A * ((A + 1) - s * (A - 1) * cw - sA)]
        a = [(A + 1) + s * (A - 1) * cw + sA,
             -s * 2 * ((A - 1) + s * (A + 1) * cw),
             (A + 1) + s * (A - 1) * cw - sA]
    else:
        raise ValueError(kind)
    b = np.array(b, float); a = np.array(a, float)
    return b / a[0], a / a[0]


def lfilter_fft(b, a, x, pad=32768):
    """Static IIR filter (2nd order max) applied through its exact frequency
    response. Causal; the zero padding absorbs the decaying tail."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    nfft = 1 << int(math.ceil(math.log2(n + pad)))
    z1 = np.exp(-2j * np.pi * np.arange(nfft // 2 + 1) / nfft)
    b = list(b) + [0] * (3 - len(b)); a = list(a) + [0] * (3 - len(a))
    H = (b[0] + b[1] * z1 + b[2] * z1 ** 2) / (a[0] + a[1] * z1 + a[2] * z1 ** 2)
    return np.fft.irfft(np.fft.rfft(x, nfft) * H, nfft)[..., :n]


def biquad_tv(x, kind, f, q=0.7071, gain_db=0.0, B=64):
    """Swept biquad: coefficients change every B samples, recursion solved
    per block exactly (FIR part + all-pole impulse response + state)."""
    x = np.asarray(x, float)
    n = len(x)
    nb = (n + B - 1) // B
    centers = np.minimum(np.arange(nb) * B + B // 2, n - 1)
    fv = np.asarray(f, float)
    fv = fv[centers] if fv.ndim else np.full(nb, float(fv))
    qv = np.asarray(q, float)
    qv = qv[centers] if qv.ndim else np.full(nb, float(qv))
    bb, aa = rbj(kind, fv, qv, gain_db)
    xp = np.concatenate([[0.0, 0.0], x])
    y = np.zeros(n)
    y1 = y2 = 0.0
    k = np.arange(B + 1)
    for i in range(nb):
        s = i * B; e = min(s + B, n); m = e - s
        b0, b1, b2 = bb[:, i]; a1, a2 = aa[1, i], aa[2, i]
        v = b0 * xp[s + 2:e + 2] + b1 * xp[s + 1:e + 1] + b2 * xp[s:e]
        v[0] += -a1 * y1 - a2 * y2
        if m > 1:
            v[1] += -a2 * y1
        r = np.sqrt(complex(a1 * a1 - 4 * a2))
        p1, p2 = (-a1 + r) / 2, (-a1 - r) / 2
        kk = k[:m]
        if abs(p1 - p2) < 1e-9:
            g = ((kk + 1) * p1 ** kk).real
        else:
            g = ((p1 ** (kk + 1) - p2 ** (kk + 1)) / (p1 - p2)).real
        yb = np.convolve(v, g)[:m]
        y[s:e] = yb
        y2 = yb[-2] if m > 1 else y1
        y1 = yb[-1]
    return y


def _filt(kind, x, f, q, gain_db=0.0):
    if np.ndim(f) == 0 and np.ndim(q) == 0:
        b, a = rbj(kind, f, q, gain_db)
        return lfilter_fft(b, a, x)
    if np.ndim(x) == 2:
        return np.stack([biquad_tv(c, kind, f, q, gain_db) for c in x])
    return biquad_tv(x, kind, f, q, gain_db)


def lowpass(x, f, q=0.7071):
    return _filt('lp', x, f, q)


def highpass(x, f, q=0.7071):
    return _filt('hp', x, f, q)


def bandpass(x, f, q=1.0):
    return _filt('bp', x, f, q)


def peak_eq(x, f, q, gain_db):
    return _filt('peak', x, f, q, gain_db)


def shelf(x, kind, f, gain_db, q=0.7071):
    return _filt(kind, x, f, q, gain_db)


def onepole_lp(x, f):
    p = math.exp(-2 * math.pi * f / SR)
    return lfilter_fft([1 - p], [1, -p], x)


# ---------------------------------------------------------------- space

def pan(x, p=0.0):
    """Constant-power pan, p in [-1, 1]."""
    th = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)])


def to_stereo(x, p=0.0):
    return x if np.ndim(x) == 2 else pan(x, p)


def _comb(x, D, g, damp):
    """Feedback comb y[n] = x[n] + g*((1-d)y[n-D] + d*y[n-D-1]); output is
    the delay-line read (Freeverb style). Vectorised in blocks of D."""
    n = len(x)
    P = D + 1
    y = np.zeros(n + P)
    for s in range(0, n, D):
        e = min(s + D, n)
        y[P + s:P + e] = x[s:e] + g * ((1 - damp) * y[P + s - D:P + e - D]
                                       + damp * y[P + s - D - 1:P + e - D - 1])
    return y[P - D:P - D + n]


def _allpass(x, D, g=0.5):
    n = len(x)
    buf = np.zeros(n + D)
    for s in range(0, n, D):
        e = min(s + D, n)
        buf[D + s:D + e] = x[s:e] + g * buf[s:e]
    return buf[:n] - x


_COMBS = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
_APS = [556, 441, 341, 225]


def reverb(x, room=0.8, damp=0.3, predelay=0.02, spread=23, hp=180, lp=9000):
    """Freeverb-like stereo reverb. Input mono or stereo, returns stereo wet."""
    st = to_stereo(x)
    mono = st.sum(0) * 0.5
    mono = highpass(mono, hp)
    mono = lowpass(mono, lp)
    pd = ns(predelay)
    mono = np.concatenate([np.zeros(pd), mono])[:st.shape[1]]
    g = room * 0.28 + 0.7
    out = []
    for ch in range(2):
        off = spread * ch
        acc = np.zeros_like(mono)
        for D in _COMBS:
            acc += _comb(mono, D + off, g, damp)
        for D in _APS:
            acc = _allpass(acc, D + off)
        out.append(acc)
    return np.stack(out) * 0.06


# ---------------------------------------------------------------- levels

def peak(x):
    return float(np.max(np.abs(x))) if np.size(x) else 0.0


def normalize(x, dbfs=-6.0):
    p = peak(x)
    return x if p == 0 else x * (undb(dbfs) / p)


def loudness(x):
    """Integrated loudness (LUFS), ITU-R BS.1770-4: K-weighting + gating."""
    st = np.atleast_2d(np.asarray(x, float))
    b1, a1 = _kshelf()
    b2, a2 = rbj('hp', 38.13547087613982, 0.5003270373253953)
    y = lfilter_fft(b2, a2, lfilter_fft(b1, a1, st))
    blk, hop = ns(0.4), ns(0.1)
    n = y.shape[1]
    if n < blk:
        ms = np.array([(y ** 2).mean(1).sum()])
    else:
        c = np.cumsum(np.pad(y ** 2, ((0, 0), (1, 0))), axis=1)
        starts = np.arange(0, n - blk + 1, hop)
        ms = ((c[:, starts + blk] - c[:, starts]) / blk).sum(0)
    lk = -0.691 + 10 * np.log10(ms + 1e-20)
    g = ms[lk > -70]
    if len(g) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(g.mean()) - 10
    g2 = ms[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(g2.mean()))


def _kshelf():
    G, Q, fc = 3.99984385397, 0.7071752369554193, 1681.9744509555319
    A = 10 ** (G / 40); w0 = 2 * np.pi * fc / SR
    al = np.sin(w0) / (2 * Q); cw = np.cos(w0); sA = 2 * np.sqrt(A) * al
    b = [A * ((A + 1) + (A - 1) * cw + sA), -2 * A * ((A - 1) + (A + 1) * cw),
         A * ((A + 1) + (A - 1) * cw - sA)]
    a = [(A + 1) - (A - 1) * cw + sA, 2 * ((A - 1) - (A + 1) * cw),
         (A + 1) - (A - 1) * cw - sA]
    return np.array(b) / a[0], np.array(a) / a[0]


def soft_limit(x, ceiling_db=-1.0):
    """Gentle tanh knee above ~-6 dB under the ceiling (rarely engages)."""
    c = undb(ceiling_db)
    k = c * 0.5
    ax = np.abs(x)
    over = ax > k
    y = x.copy()
    y[over] = np.sign(x[over]) * (k + (c - k) * np.tanh((ax[over] - k) / (c - k)))
    return y


# ---------------------------------------------------------------- instruments

def modal(f, dur, ratios, amps, taus, attack=0.001, detune=0.0):
    """Sum of exponentially decaying sinusoids (struck bars, tines, bells)."""
    n = ns(dur)
    t = tvec(n)
    out = np.zeros(n)
    for r, a, tau in zip(ratios, amps, taus):
        fr = f * r
        if fr >= 0.45 * SR or a == 0:
            continue
        ph = _rng.uniform(0, 2 * np.pi) if r != 1 else 0.0
        out += a * np.exp(-t / tau) * np.sin(2 * np.pi * fr * t + ph)
        if detune:
            out += a * 0.35 * np.exp(-t / tau) * np.sin(2 * np.pi * fr * (1 + detune) * t + ph)
    return out * ramp_in(n, attack)


def _ring(tau, cap=4.0):
    return min(cap, tau * 6.5)


def marimba(f, vel=0.8, hard=0.4):
    tau = float(np.clip(0.55 * (440 / f) ** 0.7, 0.12, 1.5))
    hv = hard * (0.5 + 0.5 * vel)
    x = modal(f, _ring(tau, 3.0), [1, 3.98, 9.88],
              [1, 0.10 + 0.30 * hv, 0.02 + 0.10 * hv],
              [tau, tau * 0.22, tau * 0.07], attack=0.0035 - 0.002 * hv)
    m = ns(0.006)
    click = lowpass(noise(m) * np.hanning(m), 1200 + 2500 * hv) * 0.25 * hv
    x[:m] += click
    return x * vel


def kalimba(f, vel=0.8):
    tau = float(np.clip(1.3 * (300 / f) ** 0.5, 0.35, 2.0))
    x = modal(f, _ring(tau, 4.0), [1, 6.08, 16.4], [1, 0.10 * vel + 0.03, 0.025],
              [tau, 0.11, 0.03], attack=0.0012)
    # tiny thumb thump
    m = ns(0.02)
    x[:m] += lowpass(noise(m) * np.hanning(m), 500) * 0.15
    return x * vel


def musicbox(f, vel=0.8):
    tau = float(np.clip(1.9 * (600 / f) ** 0.45, 0.5, 2.6))
    x = modal(f, _ring(tau, 4.5), [1, 2.0, 5.97, 9.6], [1, 0.10, 0.22 * vel + 0.05, 0.05],
              [tau, tau * 0.3, 0.16, 0.05], attack=0.0006, detune=0.0012)
    m = ns(0.004)
    x[:m] += highpass(noise(m), 2500) * 0.08
    return x * vel


def glock(f, vel=0.8):
    tau = float(np.clip(1.4 * (1000 / f) ** 0.3, 0.4, 2.2))
    x = modal(f, _ring(tau, 3.5), [1, 2.76, 5.40, 8.93], [1, 0.22, 0.08, 0.03],
              [tau, 0.3, 0.1, 0.04], attack=0.0008)
    return x * vel


def fm_bell(f, vel=0.8, ratio=3.5, index=1.6, tau=1.4, dur=None):
    n = ns(dur if dur else min(5.0, tau * 5))
    t = tvec(n)
    mod = index * vel * np.exp(-t / (tau * 0.35)) * np.sin(2 * np.pi * f * ratio * t)
    x = np.sin(2 * np.pi * f * t + mod) * np.exp(-t / tau)
    x += 0.25 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / (tau * 0.4))
    return x * ramp_in(n, 0.002) * vel


def ep(f, dur, vel=0.7):
    """FM electric piano (ratio 1 body + short high tine)."""
    rel = 0.35
    tau = float(np.clip(2.2 * (260 / f) ** 0.5, 0.8, 3.5))
    n = ns(dur + rel)
    t = tvec(n)
    idx = (0.4 + 1.1 * vel) * np.exp(-t / 0.5) + 0.15
    body = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    tine = 0.05 * vel * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t / 0.04)
    env = np.exp(-t / tau) * adsr(n, 0.003, 0.01, 1.0, rel, hold=dur)
    return (body * env + tine * ramp_in(n, 0.001)) * vel


def pluck(f, dur, vel=0.8, bright=0.5, t60=1.6, pick=0.22, damp=None):
    """Karplus-Strong string, blockwise recursion, pitch fixed by resampling."""
    rel = 0.06
    n = ns(dur + rel)
    a = 0.5 + 0.45 * bright if damp is None else damp   # 0.5 = darkest loop
    N = max(2, int(SR / f - (1 - a)))
    f_act = SR / (N + (1 - a))
    ratio = f / f_act
    total = int(n * ratio) + N + 4
    exc = noise(N)
    exc = lowpass(exc, 800 + 7000 * bright * vel)
    pk = max(1, int(pick * N))
    exc = exc - np.roll(exc, pk) * 0.8
    exc /= peak(exc) + 1e-9
    rho = 10 ** (-3 * (N + 1 - a) / (SR * t60))
    y = np.zeros(total + 1)
    y[1:N + 1] = exc
    for s in range(N, total, N):
        e = min(s + N, total)
        y[1 + s:1 + e] = rho * (a * y[1 + s - N:1 + e - N] + (1 - a) * y[s - N:e - N])
    y = y[1:]
    out = np.interp(np.arange(n) * ratio, np.arange(total), y)
    env = np.ones(n)
    g = ns(dur)
    if g < n:
        env[g:] = np.linspace(1, 0, n - g) ** 2
    return out * env * vel * ramp_in(n, 0.0008)


def bass(f, dur, vel=0.8, tone=0.3):
    rel = 0.09
    n = ns(dur + rel)
    t = tvec(n)
    body = wt(table([1, 0.28, 0.08, 0.03]), f, n)
    knock = wt(table([0, 0.6 * tone + 0.2, 0.5 * tone, 0.35 * tone, 0.2 * tone]), f, n)
    env = adsr(n, 0.006, 0.6, 0.55, rel, hold=dur)
    x = body * env + knock * np.exp(-t / 0.06) * ramp_in(n, 0.004)
    return x * vel


def pad(f, dur, vel=0.6, fc=1500, attack=0.9, release=1.6, detune_c=7, voices=3,
        width=0.7, kind='saw'):
    """Soft detuned additive pad -> stereo (2, n)."""
    n = ns(dur + release)
    env = adsr(n, attack, 0.6, 0.85, release, hold=dur)
    tb = table(harmonics(f * 1.01, kind, fc=fc, slope=4, maxf=min(0.45 * SR, fc * 6)))
    out = np.zeros((2, n))
    t = tvec(n)
    for v in range(voices):
        dv = (v - (voices - 1) / 2) / max(1, (voices - 1) / 2)
        cents = dv * detune_c
        lfo = 1 + 0.0012 * np.sin(2 * np.pi * (0.13 + 0.07 * v) * t + _rng.uniform(0, 6.28))
        x = wt(tb, f * 2 ** (cents / 1200) * lfo, n, _rng.uniform())
        out += pan(x, dv * width)
    return out * env * vel / voices


def flute(f, dur, vel=0.7, vib=0.004, breath=0.05):
    """Soft ocarina/flute lead: few harmonics, delayed vibrato, breath."""
    rel = 0.16
    n = ns(dur + rel)
    t = tvec(n)
    vib_env = np.clip((t - 0.25) / 0.4, 0, 1)
    fv = f * (1 + vib * vib_env * np.sin(2 * np.pi * 5.1 * t))
    x = wt(table([1, 0.18, 0.06, 0.02]), fv, n)
    env = adsr(n, 0.07, 0.3, 0.85, rel, hold=dur)
    b = bandpass(noise(n), min(f * 2.0, 6000), 1.2) * breath * (0.6 + 0.8 * np.exp(-t / 0.08))
    return (x + b) * env * vel


def shaker(vel=0.6, length=0.11, bright=1.0):
    n = ns(length)
    x = highpass(bandpass(noise(n), 6500 * bright, 0.9), 2800)
    env = ramp_in(n, 0.008) * np.exp(-np.maximum(tvec(n) - 0.008, 0) / 0.028)
    return fade(x * env * vel * 3, 0, 0.01)


def kick_soft(vel=0.6):
    n = ns(0.35)
    t = tvec(n)
    f = 50 + 70 * np.exp(-t / 0.03)
    x = np.sin(2 * np.pi * cycles(f, n)) * np.exp(-t / 0.13) * ramp_in(n, 0.002)
    return lowpass(x, 300) * vel


def woodblock(f=880, vel=0.6):
    return modal(f, 0.18, [1, 2.57, 4.1], [1, 0.35, 0.1], [0.045, 0.02, 0.01],
                 attack=0.0005) * vel


VOWELS = {  # (formant Hz, bandwidth Hz, gain)
    'a': [(730, 90, 1.0), (1090, 110, 0.5), (2440, 160, 0.22)],
    'e': [(530, 80, 1.0), (1840, 120, 0.45), (2480, 170, 0.22)],
    'i': [(300, 70, 1.0), (2290, 130, 0.35), (3010, 180, 0.2)],
    'o': [(500, 80, 1.0), (850, 100, 0.6), (2500, 160, 0.10)],
    'u': [(320, 70, 1.0), (800, 90, 0.35), (2240, 150, 0.06)],
    'm': [(260, 60, 1.0), (1300, 220, 0.05), (2300, 260, 0.02)],
    'r': [(450, 90, 1.0), (1150, 130, 0.35), (1700, 180, 0.15)],
}


def voice(f0, path, scale=1.0, tilt=1.0, breath=0.0, kmax=120):
    """Additive formant voice. f0: per-sample pitch array. path: list of
    (fraction 0..1, vowel key). Harmonic k gets the vocal-tract resonance
    magnitude at k*f0(t), so vowels morph smoothly with no filter state."""
    f0 = np.asarray(f0, float)
    n = len(f0)
    fr = np.linspace(0, 1, n)
    pos = [p for p, _ in path]
    F = np.zeros((3, n)); BW = np.zeros((3, n)); G = np.zeros((3, n))
    for i in range(3):
        F[i] = np.interp(fr, pos, [VOWELS[v][i][0] * scale for _, v in path])
        BW[i] = np.interp(fr, pos, [VOWELS[v][i][1] * scale for _, v in path])
        G[i] = np.interp(fr, pos, [VOWELS[v][i][2] for _, v in path])
    ph = 2 * np.pi * cycles(f0, n)
    K = int(min(kmax, 0.47 * SR // max(f0.min(), 20)))
    out = np.zeros(n)
    for k in range(1, K + 1):
        fk = k * f0
        lim = np.clip((0.46 * SR - fk) / (0.03 * SR), 0, 1)
        if not lim.any():
            break
        res = 0.02
        for i in range(3):
            res = res + G[i] / np.sqrt(1 + ((fk * fk - F[i] ** 2) / (fk * BW[i])) ** 2)
        out += res * lim * k ** -tilt * np.sin(k * ph)
    if breath:
        out += bandpass(noise(n), float(F[1].mean()), 1.5) * breath
    return out


# ---------------------------------------------------------------- sequencing

def parse(seq):
    """'C5:1 A4:.5 r:1 | E5+G5:2' -> [(beat, [midi..], dur_beats)], length."""
    beat, out = 0.0, []
    for tok in seq.replace('|', ' ').split():
        name, d = tok.split(':')
        if '/' in d:
            p, q = d.split('/'); d = float(p) / float(q)
        d = float(d)
        if name not in ('r', '-'):
            out.append((beat, [note(x) for x in name.split('+')], d))
        beat += d
    return out, beat


QUAL = {'': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10], 'maj7': [0, 4, 7, 11],
        'm7': [0, 3, 7, 10], 'sus4': [0, 5, 7], 'sus2': [0, 2, 7], '7sus4': [0, 5, 7, 10],
        '6': [0, 4, 7, 9], 'm6': [0, 3, 7, 9], 'add9': [0, 4, 7, 14], 'dim': [0, 3, 6],
        '9': [0, 4, 7, 10, 14], 'maj9': [0, 4, 7, 11, 14], 'm9': [0, 3, 7, 10, 14]}
_CH_RE = re.compile(r'^([A-G])([#b]?)([a-z0-9]*)(?:/([A-G])([#b]?))?$')


class Chord:
    def __init__(self, sym):
        m = _CH_RE.match(sym)
        if not m or m.group(3) not in QUAL:
            raise ValueError('bad chord %r' % sym)
        acc = {'#': 1, 'b': -1, '': 0}
        self.sym = sym
        self.root = (_PC[m.group(1)] + acc[m.group(2)]) % 12
        self.iv = QUAL[m.group(3)]
        self.pcs = [(self.root + i) % 12 for i in self.iv]
        self.bass = (_PC[m.group(4)] + acc[m.group(5)]) % 12 if m.group(4) else self.root

    def tones(self, lo, hi):
        return [m for m in range(lo, hi + 1) if m % 12 in self.pcs]

    def voicing(self, center, count=4):
        c = sorted(self.tones(center - 12, center + 12), key=lambda m: abs(m - center))
        return sorted(c[:count])

    def bass_note(self, lo=36):
        return lo + (self.bass - lo) % 12

    def fifth(self, lo=36):
        return self.bass_note(lo) + 7 if self.bass == self.root else self.bass_note(lo) + 12

    def pc(self, i, octave):
        """i-th chord tone (0 = root) in the given octave."""
        iv = self.iv[i % len(self.iv)] + 12 * (i // len(self.iv))
        return 12 * (octave + 1) + self.root + iv


def bars(prog):
    """'F | Am | Bb C | F' -> [[(Chord, start_beat_in_bar, beats)], ...] for 4/4
    (beats per bar given later via meter)."""
    return [s.split() for s in prog.split('|')]


class Song:
    """Beat-based mix buffer with a reverb send. For loops, the tail that
    rings past the loop end is folded back onto the start, so the file
    wraps around with no click and no missing reverb."""

    def __init__(self, bpm, nbars, meter=4, tail=8.0, loop=True, rit=None):
        self.bpm, self.meter, self.loop = bpm, meter, loop
        self.spb = 60.0 / bpm
        self.beats = nbars * meter
        self.rit = rit  # (start_beat, end_bpm) linear slowdown to the end
        self.L = ns(self.sec_at(self.beats))
        self.N = self.L + ns(tail)
        self.dry = np.zeros((2, self.N))
        self.send = np.zeros((2, self.N))

    def sec_at(self, beat):
        if not self.rit or beat <= self.rit[0]:
            return beat * self.spb
        b0, end_bpm = self.rit
        span = max(self.beats - b0, 1e-9)
        bb = np.linspace(b0, beat, 200)
        bpm = self.bpm + (end_bpm - self.bpm) * np.clip((bb - b0) / span, 0, 1)
        return b0 * self.spb + np.trapezoid(60.0 / bpm, bb)

    def dur(self, beat, beats):
        return self.sec_at(beat + beats) - self.sec_at(beat)

    def add(self, beat, sig, gain=1.0, pan_=0.0, rev=0.25, jitter=0.006):
        st = to_stereo(np.asarray(sig, float), pan_) * gain
        start = ns(self.sec_at(beat))
        if jitter and beat > 0:
            start += ns(_rng.uniform(0, jitter))
        end = min(self.N, start + st.shape[1])
        m = end - start
        if m <= 0:
            return
        self.dry[:, start:end] += st[:, :m]
        if rev:
            self.send[:, start:end] += st[:, :m] * rev

    def render(self, room=0.82, damp=0.35, wet=1.0, hp=35, lp=13000, predelay=0.025):
        mix = self.dry + reverb(self.send, room, damp, predelay) * wet
        mix = lowpass(highpass(mix, hp), lp)
        if not self.loop:
            return mix
        tail = self.N - self.L
        mix[:, -ns(0.4):] *= np.linspace(1, 0, ns(0.4))
        out = mix[:, :self.L].copy()
        out[:, :tail] += mix[:, self.L:]
        return out


# ---------------------------------------------------------------- output

def write_wav(path, x):
    st = np.atleast_2d(x)
    d = (_rng.uniform(-0.5, 0.5, st.shape) + _rng.uniform(-0.5, 0.5, st.shape)) / 32768
    pcm = np.clip(np.round((st + d) * 32767), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(st.shape[0]); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.T.tobytes())


def write_ogg(path, x, q=4):
    st = np.atleast_2d(np.asarray(x, np.float32))
    raw = np.ascontiguousarray(st.T).tobytes()
    cmd = ['ffmpeg', '-loglevel', 'error', '-y', '-f', 'f32le', '-ar', str(SR),
           '-ac', str(st.shape[0]), '-i', '-', '-c:a', 'libvorbis', '-q:a', str(q),
           '-map_metadata', '-1', path]
    subprocess.run(cmd, input=raw, check=True)


def read_audio(path):
    """Decode any file through ffmpeg -> (channels, n) float32 at SR."""
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-f', 'f32le',
                        '-ar', str(SR), '-'], capture_output=True, check=True)
    info = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=channels',
                           '-of', 'csv=p=0', path], capture_output=True, text=True)
    ch = int(info.stdout.strip().split()[0])
    return np.frombuffer(p.stdout, np.float32).reshape(-1, ch).T
