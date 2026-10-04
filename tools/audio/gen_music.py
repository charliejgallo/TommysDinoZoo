#!/usr/bin/env python3
"""Generate the music of Tommy's Dino Zoo into game/assets/music/*.ogg.

Original tunes, all synthesised (synth.py). The loops are rendered with an
extra tail and the tail is folded back onto the start, so every file wraps
around seamlessly (reverb and ringing notes included). Levels are set to
about -18 LUFS: a quiet bed under the sound effects.

    python3 tools/audio/gen_music.py              # all
    python3 tools/audio/gen_music.py day night    # only these
    WAV=1 ...                                     # also dump WAVs to scratch

The hook (title, bars 3-4: C A C F | E D C A in F major) comes back in the
night lullaby, the summary phrase and the 'mission' jingle.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth as S  # noqa: E402
from synth import (Chord, Song, bass, ep, flute, fm_bell, glock, hz, kalimba,  # noqa: E402
                   kick_soft, marimba, musicbox, ns, pad, parse, pluck, shaker, woodblock)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'game', 'assets', 'music')
SCRATCH = os.environ.get('AUDIO_SCRATCH', '/private/tmp/claude-501/-Users-charlie-Dropbox-ClaudeCode/'
                         'bea4eb56-79a2-4f4b-8313-37463248a60c/scratchpad/audio')
TARGET_LUFS = -18.0

INST = {
    'marimba': lambda f, d, v: marimba(f, v, hard=0.3),
    'xylo': lambda f, d, v: marimba(f, v, hard=0.75),
    'kalimba': lambda f, d, v: kalimba(f, v),
    'musicbox': lambda f, d, v: musicbox(f, v),
    'glock': lambda f, d, v: glock(f, v),
    'bell': lambda f, d, v: fm_bell(f, v, ratio=3.5, index=0.9, tau=1.1),
    'sweetbell': lambda f, d, v: fm_bell(f, v, ratio=2.0, index=0.8, tau=1.3),
    'ep': lambda f, d, v: ep(f, d, v),
    'flute': lambda f, d, v: flute(f, d, v),
    'pluck': lambda f, d, v: pluck(f, d, v, bright=0.45, t60=1.3),
    'harp': lambda f, d, v: pluck(f, max(d, 1.4), v, bright=0.3, t60=2.6, pick=0.3),
    'bass': lambda f, d, v: bass(f, d, v),
    'pizz': lambda f, d, v: pluck(f, min(d, 0.3), v, bright=0.25, t60=0.6, pick=0.4),
}


def hv(v, spread=0.12):
    """Humanised velocity."""
    return v * S.rng().uniform(1 - spread, 1 + spread * 0.4)


# ---------------------------------------------------------------- building blocks

def timeline(song, prog, bar0=0):
    """'F | Am | Bb C' -> [(beat, Chord, beats)] starting at bar0."""
    out = []
    for i, bar in enumerate(prog.split('|')):
        syms = bar.split()
        for j, sym in enumerate(syms):
            out.append(((bar0 + i) * song.meter + j * song.meter / len(syms), Chord(sym),
                        song.meter / len(syms)))
    return out


def melody(song, seq, bar, inst, gain=0.5, pan=0.0, rev=0.3, vel=0.8, octave=0, legato=0.95,
           accent=None):
    notes, _ = parse(seq)
    b0 = bar * song.meter
    for b, ms, d in notes:
        v = vel
        if accent and (b % song.meter) == 0:
            v *= accent
        for m in ms:
            sig = INST[inst](hz(m + 12 * octave), song.dur(b0 + b, d) * legato, hv(v))
            song.add(b0 + b, sig, gain, pan, rev)


def arp(song, tl, pattern, inst, octave=4, gain=0.3, pan=0.0, rev=0.3, step=0.5, vels=None,
        dur=None, bars=None):
    """Broken chords: pattern = chord-tone indices per step (None = rest)."""
    for beat, ch, beats in tl:
        if bars and not (bars[0] * song.meter <= beat < bars[1] * song.meter):
            continue
        k = 0
        t = 0.0
        while t < beats - 1e-6:
            i = pattern[k % len(pattern)]
            if i is not None:
                v = vels[k % len(vels)] if vels else 0.7
                f = S.mtof(ch.pc(i, octave))
                d = song.dur(beat + t, dur if dur else step)
                song.add(beat + t, INST[inst](float(f), d, hv(v)), gain, pan, rev)
            k += 1
            t += step


def bassline(song, tl, pattern, inst='bass', gain=0.5, lo=36, rev=0.1, bars=None):
    """pattern: [(beat, 'R'|'5'|'8', beats, vel)] relative to each chord."""
    for beat, ch, beats in tl:
        if bars and not (bars[0] * song.meter <= beat < bars[1] * song.meter):
            continue
        for ob, which, d, v in pattern:
            if ob >= beats - 1e-6:
                continue
            m = {'R': ch.bass_note(lo), '5': ch.fifth(lo), '8': ch.bass_note(lo) + 12}[which]
            dd = min(d, beats - ob)
            song.add(beat + ob, INST[inst](hz(m), song.dur(beat + ob, dd), hv(v, 0.08)), gain, 0, rev)


def pads(song, tl, center=60, count=4, gain=0.2, fc=1400, rev=0.4, bars=None, kind='saw',
         attack=0.8):
    for beat, ch, beats in tl:
        if bars and not (bars[0] * song.meter <= beat < bars[1] * song.meter):
            continue
        d = song.dur(beat, beats) + 0.15
        for m in ch.voicing(center, count):
            song.add(beat, pad(hz(m), d, 0.6, fc=fc, attack=attack, kind=kind), gain, 0, rev,
                     jitter=0)


def chords_on(song, tl, hits, inst, center=62, count=3, gain=0.25, rev=0.3, spread=0.012,
              bars=None, pan=0.0):
    """Block chords at hits = [(beat, beats, vel)] (slightly rolled)."""
    for beat, ch, beats in tl:
        if bars and not (bars[0] * song.meter <= beat < bars[1] * song.meter):
            continue
        for ob, d, v in hits:
            if ob >= beats - 1e-6:
                continue
            for j, m in enumerate(ch.voicing(center, count)):
                sig = INST[inst](hz(m), song.dur(beat + ob, d), hv(v))
                song.add(beat + ob + j * spread / song.spb, sig, gain, pan + 0.2 * (j - 1), rev,
                         jitter=0.004)


UKE_STRUM = [(0, 'D', 0.9), (1, 'D', 0.65), (1.5, 'U', 0.45), (2.5, 'U', 0.5), (3, 'D', 0.7),
             (3.5, 'U', 0.45)]


def uke(song, tl, pattern=UKE_STRUM, gain=0.25, center=67, rev=0.25, bars=None, mute=0.0):
    """Ukulele-ish strums: 4 KS strings, down = low->high, up = high->low."""
    for beat, ch, beats in tl:
        if bars and not (bars[0] * song.meter <= beat < bars[1] * song.meter):
            continue
        notes = ch.voicing(center, 4)
        for ob, dirn, v in pattern:
            if ob >= beats - 1e-6:
                continue
            order = notes if dirn == 'D' else notes[::-1]
            # ring until the next strum
            nxt = min([p[0] for p in pattern if p[0] > ob] + [beats])
            d = song.dur(beat + ob, nxt - ob) * (1 - mute) + 0.05
            for j, m in enumerate(order):
                sig = pluck(hz(m), d, hv(v) * (0.85 if dirn == 'U' else 1), bright=0.35, t60=1.2,
                            pick=0.18)
                song.add(beat + ob + j * 0.014 / song.spb, sig, gain, -0.25 + 0.17 * j, rev,
                         jitter=0.003)


def fingerpick(song, tl, gain=0.25, center=64, rev=0.3, bars=None):
    order = [0, 2, 1, 3, 2, 1, 3, 2]
    for beat, ch, beats in tl:
        if bars and not (bars[0] * song.meter <= beat < bars[1] * song.meter):
            continue
        notes = ch.voicing(center, 4)
        t = 0.0
        k = 0
        while t < beats - 1e-6:
            m = notes[order[k % 8]] if k % 8 else ch.bass_note(48)
            sig = pluck(hz(m), song.dur(beat + t, 1.0), hv(0.65 if k % 2 == 0 else 0.5),
                        bright=0.3, t60=1.6)
            song.add(beat + t, sig, gain, -0.3 + 0.2 * (k % 4), rev)
            t += 0.5
            k += 1


def shakers(song, bar0, bar1, vels=(0.35, 0.6), step=0.5, gain=0.25, swing=0.0, pan=0.35):
    bank = [shaker(1.0, 0.11, b) for b in (0.9, 1.0, 1.1, 0.95)]
    b = bar0 * song.meter
    k = 0
    while b < bar1 * song.meter - 1e-6:
        sw = swing * step if k % 2 else 0
        song.add(b + sw, bank[k % 4] * hv(vels[k % len(vels)], 0.15), gain, pan, 0.08,
                 jitter=0.004)
        b += step
        k += 1


def kicks(song, bar0, bar1, beats=(0, 2), gain=0.3):
    k = kick_soft(0.8)
    for bar in range(bar0, bar1):
        for b in beats:
            song.add(bar * song.meter + b, k, gain, 0, 0.0, jitter=0)


def finish_song(song, name, room=0.8, damp=0.35, wet=1.0, fade_out=None):
    x = song.render(room=room, damp=damp, wet=wet)
    if fade_out:
        n = ns(fade_out)
        x[:, -n:] *= np.linspace(1, 0, n) ** 2
    lu = S.loudness(x)
    x = x * S.undb(TARGET_LUFS - lu)
    if S.peak(x) > S.undb(-1.5):
        x = S.soft_limit(x, -1.0)
    return x


# ---------------------------------------------------------------- tracks

def title():
    """F major, 80 bpm, 20 bars (60 s). Warm and inviting: the main hook."""
    s = Song(80, 20)
    prog = ('Fmaj7 | Bbmaj7 | F | Am | Bb | F | Dm | Gm | Bb C | F | '
            'Bb | C | Am | Dm | Gm | C | Am Dm | Gm C | Fmaj7 | Gm7 C7sus4')
    tl = timeline(s, prog)
    pads(s, tl, center=58, gain=0.16, fc=1100)
    # intro: slow kalimba arpeggio + music box glints
    arp(s, tl, [0, 2, 3, 4], 'kalimba', 4, gain=0.32, step=1.0, vels=[0.7, 0.5, 0.6, 0.5],
        bars=(0, 2))
    melody(s, 'r:2 A5:1 C6:1 | r:2 D6:1 F6:1', 0, 'musicbox', gain=0.18, pan=0.3, vel=0.6)
    # A: flute sings the hook over warm low marimba
    bassline(s, tl, [(0, 'R', 2, 0.8), (2, '5', 1.8, 0.6)], gain=0.42, bars=(2, 20))
    arp(s, tl, [0, 2, 3, 2, 4, 2, 3, 2], 'marimba', 3, gain=0.3, pan=-0.2,
        vels=[0.75, 0.45, 0.55, 0.45, 0.6, 0.45, 0.55, 0.45], bars=(2, 10))
    melody(s, 'C5:1 A4:.5 C5:.5 F5:2 | E5:1.5 D5:.5 C5:1 A4:1 | D5:1 Bb4:.5 D5:.5 F5:1 D5:1 | '
              'C5:3 r:1 | A4:1 D5:.5 E5:.5 F5:1 A5:1 | G5:1.5 F5:.5 D5:1 Bb4:1 | '
              'A4:1 Bb4:1 C5:1 E5:1 | F5:3 r:1', 2, 'flute', gain=0.42, pan=0.1, rev=0.35)
    # B: harp-like plucks under a soft electric piano + glock answer
    arp(s, tl, [0, 2, 3, 2, 4, 2, 3, 2], 'harp', 3, gain=0.62, pan=-0.25,
        vels=[0.75, 0.45, 0.55, 0.45, 0.6, 0.45, 0.55, 0.45], bars=(10, 18))
    mB = ('D5:1.5 C5:.5 Bb4:1 D5:1 | C5:1.5 Bb4:.5 A4:1 G4:1 | A4:1 C5:1 E5:1.5 D5:.5 | '
          'D5:3 r:1 | Bb4:1 D5:.5 G5:.5 F5:1 D5:1 | E5:1 G5:1 C5:2 | C5:1 E5:1 F5:1 A5:1 | '
          'G5:1.5 F5:.5 E5:1 G5:1 | F5:3 r:1')
    melody(s, mB, 10, 'ep', gain=0.4, pan=0.15, vel=0.65)
    melody(s, mB, 10, 'glock', gain=0.07, pan=0.4, vel=0.5, octave=1)
    # coda: kalimba echoes the hook, back to the top
    arp(s, tl, [0, 2, 3, 2], 'kalimba', 4, gain=0.22, step=1.0, vels=[0.6, 0.45, 0.5, 0.45],
        bars=(18, 19))
    melody(s, 'r:1 C5:.5 A4:.5 C5:1 F5:1', 19, 'kalimba', gain=0.32, pan=-0.1, vel=0.65)
    return finish_song(s, 'title', room=0.85)


def morning():
    """G major, 96 bpm, 24 bars (60 s). Bright marimba/kalimba, light shaker."""
    s = Song(96, 24)
    A = 'G | Em | C | D | G | Em | Am D | G'
    B = 'C | D | Bm | Em | C | D | G/B C | D'
    C = 'G | C | G | D | Em | C | Am | D'
    tl = timeline(s, ' | '.join([A, B, C]))
    bassline(s, tl, [(0, 'R', 1.0, 0.85), (1.5, 'R', 0.4, 0.5), (2, '5', 1.0, 0.75),
                     (3.5, 'R', 0.4, 0.5)], gain=0.4)
    # A: marimba melody, kalimba off-beat chords
    melody(s, 'B4:.5 D5:.5 G5:1 F#5:.5 E5:.5 D5:1 | E5:.5 G5:.5 B5:1 A5:.5 G5:.5 E5:1 | '
              'C5:.5 E5:.5 G5:1 E5:.5 D5:.5 C5:1 | D5:.5 E5:.5 F#5:.5 A5:.5 G5:1 F#5:1 | '
              'B4:.5 D5:.5 G5:1 F#5:.5 E5:.5 D5:1 | E5:.5 G5:.5 B5:1 C6:.5 B5:.5 G5:1 | '
              'A5:.5 G5:.5 E5:.5 C5:.5 D5:.5 E5:.5 F#5:1 | G5:2 r:2', 0, 'xylo', gain=0.36,
           pan=0.1, vel=0.75, rev=0.25)
    chords_on(s, tl, [(1, 0.5, 0.5), (3, 0.5, 0.45)], 'kalimba', center=67, count=2, gain=0.24,
              bars=(0, 8), pan=-0.3)
    # B: kalimba sings, marimba rolls 8ths, a breath of pad
    arp(s, tl, [0, 2, 3, 2, 1, 2, 3, 2], 'marimba', 4, gain=0.2, pan=-0.3,
        vels=[0.7, 0.4, 0.5, 0.4, 0.55, 0.4, 0.5, 0.4], bars=(8, 24))
    melody(s, 'E5:1.5 D5:.5 C5:1 G4:1 | F#4:1 A4:1 D5:2 | F#5:1.5 E5:.5 D5:1 B4:1 | '
              'E5:3 r:1 | G5:1.5 E5:.5 C5:1 E5:1 | F#5:1 E5:1 D5:1 A4:1 | '
              'B4:1 D5:1 C5:1 E5:1 | D5:2 r:2', 8, 'kalimba', gain=0.33, pan=0.15, vel=0.8)
    pads(s, tl, center=62, gain=0.08, fc=1300, bars=(8, 24))
    # C: breakdown, glockenspiel motif, kalimba off-beats again
    chords_on(s, tl, [(1, 0.5, 0.45), (3, 0.5, 0.4)], 'kalimba', center=67, count=2, gain=0.2,
              bars=(16, 24), pan=-0.3)
    melody(s, 'r:2 D6:1 B5:1 | C6:2 r:2 | r:2 B5:1 G5:1 | A5:2 r:2 | r:2 G5:1 E5:1 | '
              'E5:2 r:2 | r:2 C6:1 A5:1 | F#5:2 A5:1 r:1', 16, 'glock', gain=0.22, pan=0.35,
           vel=0.6)
    shakers(s, 0, 16, vels=(0.3, 0.6), gain=0.4, swing=0.08)
    shakers(s, 20, 24, vels=(0.25, 0.5), gain=0.34, swing=0.08)
    kicks(s, 0, 16, beats=(0,), gain=0.22)
    return finish_song(s, 'morning', room=0.75)


def day():
    """D major, 90 bpm, 24 bars (64 s). Ukulele strums, bass, soft bells."""
    s = Song(90, 24)
    A = 'D | Bm | G | A | D | F#m | G | A'
    B = 'G | A | F#m | Bm | Em7 | A | D/F# G | A7sus4 A7'
    C = 'D | G | D | A | Bm | G | Em7 | A7'
    tl = timeline(s, ' | '.join([A, B, C]))
    bassline(s, tl, [(0, 'R', 1.4, 0.85), (2, '5', 0.9, 0.65), (3, '8', 0.9, 0.5)], gain=0.42)
    uke(s, tl, gain=0.36, bars=(0, 16))
    fingerpick(s, tl, gain=0.44, bars=(16, 24))
    # A: little bell answers at the end of every second bar
    melody(s, 'r:4 | r:2 F#5:.5 D5:.5 B4:1 | r:4 | r:2 E5:.5 C#5:.5 A4:1 | r:4 | '
              'r:2 A5:.5 F#5:.5 C#5:1 | r:4 | r:2 C#6:.5 A5:.5 E5:1', 0, 'bell', gain=0.25,
           pan=0.3, vel=0.6, rev=0.4)
    # B: the bells carry the tune
    melody(s, 'B4:1 D5:1 G5:1.5 F#5:.5 | E5:1 C#5:1 A4:2 | A4:1 C#5:1 F#5:1.5 E5:.5 | '
              'D5:3 r:1 | G5:1 F#5:.5 E5:.5 D5:1 B4:1 | C#5:1 E5:1 A5:2 | '
              'F#5:1 A5:1 G5:1 B5:1 | A5:2 G5:1 E5:1', 8, 'bell', gain=0.36, pan=0.15, vel=0.75,
           rev=0.35)
    melody(s, 'B4:1 D5:1 G5:1.5 F#5:.5 | E5:1 C#5:1 A4:2 | A4:1 C#5:1 F#5:1.5 E5:.5 | '
              'D5:3 r:1 | G5:1 F#5:.5 E5:.5 D5:1 B4:1 | C#5:1 E5:1 A5:2 | '
              'F#5:1 A5:1 G5:1 B5:1 | A5:2 G5:1 E5:1', 8, 'marimba', gain=0.14, pan=-0.2,
           vel=0.6, octave=-1)
    # C: fingerpicking + a soft flute
    melody(s, 'F#5:2 E5:1 D5:1 | B4:3 r:1 | A4:1 D5:1 F#5:1 A5:1 | G5:2 E5:2 | '
              'F#5:1.5 E5:.5 D5:1 B4:1 | D5:2 B4:2 | E5:1 G5:1 B5:1 G5:1 | A5:2 r:2', 16,
           'flute', gain=0.3, pan=0.1, rev=0.4, vel=0.7)
    pads(s, tl, center=62, gain=0.07, fc=1200, bars=(16, 24))
    shakers(s, 8, 24, vels=(0.3, 0.55), gain=0.36, swing=0.12)
    kicks(s, 8, 16, beats=(0, 2), gain=0.2)
    return finish_song(s, 'day', room=0.75)


def evening():
    """Bb major, 75 bpm, 20 bars (64 s). Warmer: electric piano, pad, flute."""
    s = Song(75, 20)
    A = 'Ebmaj7 | Dm7 | Cm7 | Bbmaj7 | Ebmaj7 | Dm7 Gm7 | Cm7 | F7sus4'
    B = 'Gm7 | Ebmaj7 | Bbmaj7 | F/A | Gm7 | Ebmaj7 | Cm7 | F7sus4'
    C = 'Ebmaj7 | Bbmaj7/D | Cm7 | F7sus4'
    tl = timeline(s, ' | '.join([A, B, C]))
    pads(s, tl, center=58, gain=0.13, fc=900, attack=1.2)
    chords_on(s, tl, [(0, 2.4, 0.5), (2.5, 1.4, 0.38)], 'ep', center=62, count=4, gain=0.22,
              spread=0.02)
    bassline(s, tl, [(0, 'R', 2, 0.8), (2.5, '5', 1.4, 0.55)], gain=0.4, lo=34)
    # A: flute, long notes
    melody(s, 'G5:2 F5:1 D5:1 | F5:3 r:1 | Eb5:1.5 D5:.5 C5:1 Bb4:1 | D5:3 r:1 | '
              'G5:1 Bb5:1 G5:1 F5:1 | F5:1 A5:1 G5:1 D5:1 | Eb5:2 C5:1 Bb4:1 | C5:3 r:1', 0,
           'flute', gain=0.34, pan=0.1, rev=0.45, vel=0.65)
    # B: no lead, kalimba arpeggios + music-box glints
    arp(s, tl, [0, 2, 3, 4, 3, 2, 1, 2], 'kalimba', 4, gain=0.26, pan=0.2,
        vels=[0.7, 0.45, 0.55, 0.6, 0.5, 0.45, 0.5, 0.45], bars=(8, 16))
    melody(s, 'r:3 D6:1 | r:4 | r:3 F6:1 | r:4 | r:3 D6:1 | r:4 | r:2 G6:1 Eb6:1 | r:4', 8,
           'musicbox', gain=0.12, pan=-0.35, vel=0.5)
    # C: electric piano sings a short answer
    melody(s, 'Bb4:2 C5:1 D5:1 | F5:4 | Eb5:2 D5:1 C5:1 | C5:2 r:2', 16, 'ep', gain=0.36,
           pan=0.15, vel=0.62, octave=1)
    shakers(s, 8, 16, vels=(0.2, 0.35), step=1.0, gain=0.26, pan=0.4)
    return finish_song(s, 'evening', room=0.88, damp=0.45)


def night():
    """C major, 66 bpm in 3/4, 24 bars (65 s). Music-box lullaby, very soft."""
    s = Song(66, 24, meter=3)
    A = 'C | G/B | Am | Em/G | F | C/E | Dm7 | G7'
    A2 = 'C | G/B | Am | Em/G | F | G | C | C'
    B = 'F | C | F | G | Am | F | Dm7 | G7'
    tl = timeline(s, ' | '.join([A, A2, B]))
    pads(s, tl, center=57, gain=0.12, fc=700, kind='tri', attack=1.5)

    def waltz(bars, inst, gain):
        for beat, ch, beats in tl:
            if not (bars[0] * 3 <= beat < bars[1] * 3):
                continue
            s.add(beat, INST[inst](hz(ch.bass_note(48)), s.dur(beat, 3), hv(0.5)), gain, -0.2, 0.4)
            v = ch.voicing(64, 2)
            for b in (1, 2):
                for m in v:
                    s.add(beat + b, INST[inst](hz(m), s.dur(beat + b, 1), hv(0.32)), gain, 0.2, 0.4)

    tune = ('E5:1 G5:1 E5:1 | D5:2 G4:1 | C5:1 E5:1 A5:1 | G5:3 | A5:1 G5:1 F5:1 | '
            'E5:1 D5:1 C5:1 | D5:1.5 E5:.5 F5:1 | D5:3')
    melody(s, tune, 0, 'musicbox', gain=0.4, pan=0.1, vel=0.7, rev=0.45)
    waltz((0, 8), 'musicbox', 0.24)
    # A': kalimba an octave lower, music box keeps the waltz
    melody(s, 'E5:1 G5:1 E5:1 | D5:2 G4:1 | C5:1 E5:1 A5:1 | G5:3 | A5:1 C6:1 A5:1 | '
              'G5:1 F5:1 D5:1 | C5:3 | r:3', 8, 'kalimba', gain=0.42, pan=-0.1, vel=0.7,
           octave=-1, rev=0.45)
    waltz((8, 16), 'musicbox', 0.19)
    # B: the title hook as a lullaby, with a soft round bass
    melody(s, 'C5:1 A4:.5 C5:.5 F5:1 | E5:1.5 D5:.5 C5:1 | A5:1.5 G5:.5 F5:1 | D5:2 r:1 | '
              'C5:1 E5:1 A5:1 | A5:1.5 G5:.5 F5:1 | F5:1 E5:1 D5:1 | B4:2 r:1', 16, 'musicbox',
           gain=0.4, pan=0.1, vel=0.7, rev=0.45)
    bassline(s, tl, [(0, 'R', 2.8, 0.6)], gain=0.3, lo=36, bars=(16, 24))
    arp(s, tl, [None, 1, 2], 'kalimba', 4, gain=0.24, step=1.0, vels=[0, 0.4, 0.35],
        bars=(16, 24))
    return finish_song(s, 'night', room=0.9, damp=0.5)


def shop():
    """C major, 120 bpm, 16 bars (32 s). Bouncy oom-pah with xylophone."""
    s = Song(120, 16)
    A = 'C | Am | F | G | C | Am | D7 | G'
    B = 'F | G | Em | Am | Dm | G | C | G7'
    tl = timeline(s, ' | '.join([A, B]))
    bassline(s, tl, [(0, 'R', 0.5, 0.9), (2, '5', 0.5, 0.75)], inst='pizz', gain=0.75, lo=40,
             rev=0.08)
    bassline(s, tl, [(0, 'R', 0.45, 0.6), (2, '5', 0.45, 0.5)], gain=0.25, lo=40, rev=0.0)
    uke(s, tl, pattern=[(1, 'D', 0.7), (3, 'D', 0.65)], gain=0.32, center=64, mute=0.6)
    melody(s, 'C5:.5 E5:.5 G5:.5 E5:.5 C6:1 G5:1 | A5:.5 G5:.5 E5:.5 C5:.5 A4:2 | '
              'F5:.5 A5:.5 C6:1 A5:.5 F5:.5 A5:1 | G5:1 D5:1 B4:.5 C5:.5 D5:1 | '
              'C5:.5 E5:.5 G5:.5 E5:.5 C6:1 G5:1 | A5:.5 B5:.5 C6:.5 A5:.5 E5:2 | '
              'F#5:.5 A5:.5 D6:.5 C6:.5 A5:1 F#5:1 | G5:.5 r:.5 D5:.5 r:.5 G4:1 r:1', 0, 'xylo',
           gain=0.42, pan=0.1, vel=0.8, legato=0.6)
    mB = ('A5:1 C6:.5 A5:.5 F5:1 r:1 | B5:1 D6:.5 B5:.5 G5:1 r:1 | '
          'G5:.5 E5:.5 B4:.5 E5:.5 G5:1 B5:1 | C6:1 B5:.5 A5:.5 E5:1 r:1 | '
          'F5:.5 E5:.5 D5:.5 F5:.5 A5:1 r:1 | B5:.5 A5:.5 G5:.5 B5:.5 D6:1 r:1 | '
          'C6:.5 G5:.5 E5:.5 G5:.5 C6:1 r:1 | D6:.5 B5:.5 G5:.5 F5:.5 D5:1 B4:1')
    melody(s, mB, 8, 'glock', gain=0.2, pan=0.35, vel=0.6)
    melody(s, mB, 8, 'marimba', gain=0.36, pan=-0.05, vel=0.75)
    wb = woodblock(950, 0.7)
    wb2 = woodblock(720, 0.6)
    for bar in range(16):
        s.add(bar * 4 + 1.5, wb, 0.22, 0.4, 0.1)
        s.add(bar * 4 + 3.5, wb2, 0.22, 0.4, 0.1)
    shakers(s, 0, 16, vels=(0.25, 0.5), gain=0.34, swing=0.1, pan=-0.35)
    kicks(s, 0, 16, beats=(0, 2), gain=0.25)
    return finish_song(s, 'shop', room=0.6)


def summary():
    """F major lullaby phrase, 70 bpm slowing to 54, ~20 s, no loop."""
    s = Song(70, 5, tail=4.5, loop=False, rit=(10, 52))
    tl = timeline(s, 'F | Am | Bb | C7sus4 C7 | F')
    pads(s, tl, center=58, gain=0.14, fc=900, kind='tri', attack=1.0)
    melody(s, 'C5:1 A4:.5 C5:.5 F5:2 | E5:1.5 D5:.5 C5:1 A4:1 | D5:1 Bb4:.5 D5:.5 F5:1 D5:1 | '
              'C5:1.5 Bb4:.5 A4:1 G4:1 | F4:4', 0, 'musicbox', gain=0.45, vel=0.75, rev=0.45)
    melody(s, 'r:16 F5:4', 0, 'glock', gain=0.1, pan=0.3, vel=0.5)
    arp(s, tl, [0, 2, 3, 2], 'kalimba', 3, gain=0.22, step=1.0, vels=[0.6, 0.4, 0.45, 0.4],
        bars=(0, 4))
    bassline(s, tl, [(0, 'R', 3.8, 0.6)], gain=0.3, lo=36)
    # final rolled chord + a few stars
    for j, m in enumerate(['F3', 'C4', 'F4', 'A4', 'C5', 'G5']):
        s.add(16 + j * 0.12, kalimba(hz(m), 0.55), 0.22, -0.3 + 0.12 * j, 0.5, jitter=0)
    for j, m in enumerate(['C7', 'A6', 'F6']):
        s.add(17.5 + j * 0.5, glock(hz(m), 0.3), 0.08, 0.3, 0.6, jitter=0)
    return finish_song(s, 'summary', room=0.88, damp=0.45, fade_out=1.5)


TRACKS = {'title': title, 'morning': morning, 'day': day, 'evening': evening, 'night': night,
          'shop': shop, 'summary': summary}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    dump = os.environ.get('WAV')
    if dump:
        os.makedirs(SCRATCH, exist_ok=True)
    for i, (name, fn) in enumerate(TRACKS.items()):
        if names and name not in names:
            continue
        S.seed(4242 + i)
        x = fn()
        q = 4
        write = os.path.join(OUT, name + '.ogg')
        S.write_ogg(write, x, q=q)
        if dump:
            S.write_wav(os.path.join(SCRATCH, name + '.wav'), x)
        print('%-8s %6.2f s  %5.1f LUFS  peak %5.1f dBFS  %4d KB' % (
            name, x.shape[1] / S.SR, S.loudness(x), S.db(S.peak(x)), os.path.getsize(write) // 1024))


if __name__ == '__main__':
    main(set(sys.argv[1:]))
