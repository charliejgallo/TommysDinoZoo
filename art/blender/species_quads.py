"""species_quads.py - Stegosaurus, Ankylosaurus, Protoceratops and
Pachycephalosaurus for Tommy's Dino Zoo (merged into dinos.py, which builds
them with dino_lib):

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P dinos.py -- \\
        --only stego_baby,stego_juv,stego_adult,egg_stego

  stego   yellow, pink leaf plates (the `accent` material, so the game can
          tint them when it is happy), two pairs of blunt round tail spikes.
  ankylo  coral, a round armoured dome with soft butter knobs (scutes), round
          side bumps and a club tail like a ball; curls into a ball in `pet`.
  proto   bubblegum pink, small mint frill, beak, chubby; digs in `play`.
  pachy   sky-blue biped with a big golden dome ringed by knobs; headbutts
          the ball in `play`.

Heights (top of the model, plates/dome included): stego 1.5, ankylo 1.0,
proto 0.6, pachy 1.0 m for adults; babies 45 %, juveniles 70 %.

Walk / run speeds each model was animated for (m/s, cycle in s; the root
stays in place, the game moves the node at this speed; feet do not slide):

  model           walk m/s (cycle s)   run m/s (cycle s)
  stego_baby      0.80 (0.47)          1.60 (0.40)
  stego_juv       0.90 (0.60)          1.90 (0.50)
  stego_adult     1.10 (0.70)          2.20 (0.60)
  ankylo_baby     0.70 (0.33)          1.40 (0.30)
  ankylo_juv      0.85 (0.40)          1.70 (0.37)
  ankylo_adult    1.00 (0.47)          2.00 (0.43)
  proto_baby      0.70 (0.33)          1.50 (0.30)
  proto_juv       0.80 (0.40)          1.80 (0.33)
  proto_adult     0.90 (0.47)          2.10 (0.40)
  pachy_baby      0.80 (0.40)          2.00 (0.30)
  pachy_juv       1.00 (0.47)          2.60 (0.33)
  pachy_adult     1.20 (0.57)          3.20 (0.40)

(the cycle times are what the build printed; rebuild with --only to see them.)

Personality in the animations (spec['anims'], see dino_lib.animate):
  ankylo pet   tucks its head, curls the club tail round and giggles (a ball)
  proto  play  nose down, scratches the ground with both front feet, tail up
  pachy  play  rears back and bonks the ball with the dome, eyes squeezed shut
Local parts (registered in dino_lib.FEATURES at import, prefixed q_):
  q_tailspikes, q_scutes, q_sidebumps, q_club, q_dome.
"""
import math
import os
import sys

from mathutils import Vector as V

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dino_lib as DL  # noqa: E402

UP = V((0, 0, 1))
FWD = V((0, -1, 0))

# ---------------------------------------------------------------- helpers


def _along(pts, f):
    """Point and direction at fraction f along a polyline."""
    k = DL.clamp(f, 0.0, 1.0) * (len(pts) - 1)
    j = min(int(k), len(pts) - 2)
    p = pts[j].lerp(pts[j + 1], k - j)
    return p, (pts[j + 1] - pts[j]).normalized(), j


def _tail_r(D, f):
    tip = D.spec['tail'].get('tip', 0.16)
    return D.L['tail_r'] * DL.lerp(1.0, tip, f ** 0.9)


def _torso_pt(D, az, el, sc=1.0):
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = DL._rotm(L['torso_rot_deg'])
    p, n = DL.on_ell(V((0, 0, 0)), tuple(x * sc for x in tr), az, el)
    return Ct + Rt @ p, (Rt @ n).normalized()


# ---------------------------------------------------------------- local parts


def f_tailspikes(D, pairs=2, at=0.72, gap=0.13, length=2.6, r=0.55, mat='accent'):
    """Thagomizer, kid-safe: pairs of short fat spikes with round tips near
    the tail end (length and r are fractions of the local tail radius)."""
    pts = D.L['tail_pts']
    k = D.A['plate']
    for i in range(pairs):
        f = at + gap * i
        p, d, j = _along(pts, f)
        rt = _tail_r(D, f) * D.spec['tail'].get('flat', 0.85)
        bone = D.tail[min(j, len(D.tail) - 1)]
        for sd in (1, -1):
            out = V((sd * 0.80, 0.0, 0.62)) + d * (0.35 + 0.15 * i)
            out.normalize()
            ln = length * rt * k * (1.0 - 0.12 * i)
            rb = r * rt * (0.8 + 0.2 * k)
            b = p + out * rt * 0.45
            DL_t = DL.tube('tspike', D.m(mat), [b, b + out * ln * 0.55, b + out * ln + d * ln * 0.12],
                           [rb, rb * 0.72, rb * 0.48], seg=D.lod(10, 8), cap='end', sub=3)
            D.add(DL_t, ('rigid', bone))


def f_scutes(D, rows=((30, 7, 0.20), (52, 6, 0.21), (74, 4, 0.20)), span_lo=15, span_hi=165,
             mat='accent', height=0.55, top=4):
    """Soft round knobs over the dome of the back: rows of (elevation deg,
    count, size as a fraction of the torso height radius); each row runs on
    both sides from azimuth span_lo (near the front) to span_hi (near the
    tail); `top` knobs run along the spine."""
    tr = D.L['torso_r']
    k = 0.75 + 0.25 * D.A['plate']
    for el, n, sz in rows:
        for i in range(n):
            u = (i + 0.5) / n
            for sd in (1, -1):
                az = sd * DL.lerp(span_lo, span_hi, u)      # front (0) .. back (180)
                p, nrm = _torso_pt(D, az, el)
                s = sz * tr[2] * k * (0.8 + 0.2 * math.sin(math.pi * u))
                D.add(DL.ell('scute', D.m(mat), p + nrm * s * 0.12, (s, s, s * height),
                             rot=DL.frame(nrm, UP), seg=D.lod(10, 8), rings=D.lod(6, 5)),
                      DL._torso_skin(D))
    if top:                         # a row along the spine
        sz = rows[-1][2] * 1.05
        for i in range(top):
            u = (i + 0.5) / top
            el = 90 - 50 * abs(2 * u - 1)
            p, nrm = _torso_pt(D, 0 if u < 0.5 else 180, el)
            s = sz * tr[2] * k
            D.add(DL.ell('scute', D.m(mat), p + nrm * s * 0.12, (s, s, s * height),
                         rot=DL.frame(nrm, UP), seg=D.lod(10, 8), rings=D.lod(6, 5)), DL._torso_skin(D))


def f_sidebumps(D, n=4, el=8, size=0.20, mat='horn'):
    """Round blunt bumps along the sides of the armour (ankylo)."""
    tr = D.L['torso_r']
    k = D.A['plate']
    if k < 0.6:
        return
    for i in range(n):
        u = (i + 0.5) / n
        for sd in (1, -1):
            p, nrm = _torso_pt(D, sd * DL.lerp(40, 150, u), el)
            s = size * tr[2] * k
            d = (nrm + V((0, 0.35, 0.15))).normalized()
            D.add(DL.tube('sbump', D.m(mat), [p - nrm * s * 0.3, p + d * s * 1.1],
                          [s * 0.75, s * 0.42], seg=D.lod(10, 8), cap='end', sub=2),
                  DL._torso_skin(D))


def f_club(D, size=2.3, mat='accent', knobs=True):
    """The tail club: a round ball (two soft lobes) at the tail tip."""
    pts = D.L['tail_pts']
    d = (pts[-1] - pts[-2]).normalized()
    rt = _tail_r(D, 1.0)
    k = 0.7 + 0.3 * D.A['plate']
    R = rt * size * k
    c = pts[-1] + d * R * 0.55
    bone = D.tail[-1]
    D.add(DL.ell('club', D.m(mat), c, (R * 1.18, R * 1.0, R * 0.82), seg=D.lod(18, 12),
                 rings=D.lod(10, 8)), ('rigid', bone))
    if knobs and D.age != 'baby':
        for sd in (1, -1):
            p = c + V((sd * R * 0.98, 0, R * 0.05))
            D.add(DL.ell('cknob', D.m(mat), p, (R * 0.42, R * 0.48, R * 0.4), seg=D.lod(12, 8),
                         rings=D.lod(8, 6)), ('rigid', bone))


def f_dome(D, r=(0.98, 1.0, 0.78), el=54, mat='accent', knobs=11, knob_mat='horn',
           snout_knobs=3, knob=0.13):
    """Pachy's dome: a big round cap on the head, ringed by soft knobs at the
    back and sides, a few small ones on the snout (r: head-radius fractions)."""
    L = D.L
    hc, hr = L['head_c'], L['head_r']
    k = D.A['crest']
    p, n = DL.on_ell(hc, hr, 0, el)
    m = sum(hr) / 3
    rr = (m * r[0] * k, m * r[1] * k, m * r[2] * k)
    c = p - n * rr[2] * 0.42
    D.add(DL.ell('dome', D.m(mat), c, rr, rot=DL.frame(n, FWD), seg=D.lod(24), rings=D.lod(14)),
          ('rigid', 'head'))
    D.ref['dome'] = (c, rr, n)
    ks = knob * m * (0.7 + 0.3 * D.A['plate'])
    if D.age == 'baby':
        knobs = max(5, knobs - 4)
    for i in range(knobs):
        u = i / max(knobs - 1, 1)
        az = DL.lerp(-150, 150, u)
        if abs(az) < 40:
            continue
        q, qn = DL.on_ell(hc, hr, az, 18 + 10 * math.cos(math.radians(az)))
        s = ks * (0.85 + 0.3 * abs(math.sin(math.radians(az))))
        D.add(DL.ell('knob', D.m(knob_mat), q + qn * s * 0.15, (s, s, s * 0.85),
                     rot=DL.frame(qn, UP), seg=8, rings=6), ('rigid', 'head'))
    snc, snr = L['snout_c'], L['snout_r']
    for i in range(snout_knobs if D.age != 'baby' else 0):
        az = (-1 + 2 * i / max(snout_knobs - 1, 1)) * 22
        q, qn = DL.on_ell(snc, snr, az, 62 - abs(az) * 0.5)
        s = ks * 0.6
        D.add(DL.ell('sknob', D.m(knob_mat), q + qn * s * 0.1, (s, s, s * 0.8),
                     rot=DL.frame(qn, UP), seg=8, rings=5), ('rigid', 'head'))


for _k, _f in (('q_tailspikes', f_tailspikes), ('q_scutes', f_scutes), ('q_sidebumps', f_sidebumps),
               ('q_club', f_club), ('q_dome', f_dome)):
    DL.FEATURES.setdefault(_k, _f)


# ---------------------------------------------------------------- animations
# Each takes the dino_lib.Moves instance and returns (seconds, gen(t) -> Pose).
# One-shots start and end at the plain standing pose.


def _fold_feet(M, P, w, out=1.25):
    """Quad: lerp the feet from planted to folded beside the body by w."""
    L = M.D.L
    tr = L['torso_r']
    for lg in M.D.legs:
        a = lg['ankle']
        if lg['front']:
            f = V((a.x * 1.12, a.y - tr[1] * 0.25, lg['foot_h']))
        else:
            f = V((a.x * out, a.y + tr[1] * 0.08, lg['foot_h']))
        P.feet[lg['tag']] = (a.lerp(f, w), -8 * w)


def ankylo_pet(M):
    """Shy when tickled: lies down, tucks the head, curls the club tail round
    its side, rounds up and giggles - a little armoured ball."""
    T = 1.2
    D = M.D
    L = D.L
    tr = L['torso_r']
    drop = (L['torso_c'].z - tr[2] * 0.8) - 0.01 * M.H

    def g(t):
        P = M.base(t, T, breath=1, amp=0.4)
        w = DL.tl(t, [(0, 0), (0.28, 1), (0.95, 1), (1.2, 0)])
        gig = DL.env(t, 0.3, 0.4, 0.85, 0.98)
        P.at('root', (0, 0, -drop * w))
        _fold_feet(M, P, w)
        M.spread(P, D.neck, 18 * w)
        P.r('head', 30 * w, 8 * w, 10 * w)
        for i, b in enumerate(D.tail):
            P.r(b, -4 * w, 26 * w + 4 * gig * math.sin(DL.TAU * t * 6 - i), 0)
        P.r('root', 0, 4 * w, 4.5 * gig * math.sin(DL.TAU * t * 5))
        P.sc('root', (1 + 0.05 * w, 1 - 0.07 * w, 1 + 0.03 * w + 0.02 * gig * math.sin(DL.TAU * t * 10)))
        P.lid = DL.tl(t, [(0, 0), (0.2, 0), (0.32, 1), (1.0, 1), (1.12, 0), (1.2, 0)])
        P.jaw = 10 * gig * (0.5 + 0.5 * math.sin(DL.TAU * t * 10))
        return P
    return T, g


def proto_play(M):
    """Digs: nose down, front feet scratch the ground in turn, tail up and
    wagging (in the game it digs up a little treasure)."""
    T = 0.8
    D = M.D
    S = M.legl * 0.55
    lift = M.legl * 0.28

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        w = DL.tl(t, [(0, 0), (0.14, 1), (0.66, 1), (0.8, 0)])
        P.r('root', 7 * w, 0, 0)
        P.at('root', (0, -M.legl * 0.05 * w, -M.legl * 0.10 * w))
        M.spread(P, D.neck, 10 * w)
        P.r('head', 16 * w, 0, 3 * math.sin(DL.TAU * t * 5) * w)
        for lg in D.legs:
            a = lg['ankle']
            if not lg['front']:
                continue
            ph = 0.0 if lg['side'] > 0 else 0.5
            k = (t * 5.0 + ph) % 1.0
            e = DL.env(t, 0.1, 0.18, 0.62, 0.7)
            # reach forward and up, then drag back along the ground
            y = a.y - S * 0.5 * math.cos(DL.TAU * k) * e
            z = a.z + lift * max(0.0, -math.sin(DL.TAU * k)) * e
            P.feet[lg['tag']] = (V((a.x, y, z)), -25 * e * max(0.0, -math.sin(DL.TAU * k)))
        M.spread(P, D.tail, 16 * w)
        M.tail(P, t, 0.2, yaw=16 * w, lag=0.5)
        P.jaw = 6 * w
        P.lid = DL.env(t, 0.2, 0.26, 0.6, 0.66) * 0.55
        return P
    return T, g


def pachy_play(M):
    """Headbutts the ball: rears back, then bonks forward with the dome
    (head pitched down so the dome leads), squash on impact."""
    T = 0.8
    D = M.D

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        wind = DL.env(t, 0.0, 0.2, 0.24, 0.36)
        butt = DL.env(t, 0.28, 0.4, 0.48, 0.76)
        hit = DL.env(t, 0.37, 0.41, 0.43, 0.54)
        P.at('root', (0, M.H * (0.03 * wind - 0.08 * butt), -M.legl * (0.05 * wind + 0.08 * butt)))
        P.r('root', -8 * wind + 18 * butt, 0, 0)
        M.spread(P, D.neck, -16 * wind + 14 * butt)
        P.r('head', -12 * wind + 42 * butt, 0, 0)
        P.sc('root', (1 + 0.05 * hit, 1 - 0.05 * hit, 1 - 0.04 * hit))
        P.r('head', 0, 0, 0, post=True)
        M.spread(P, D.tail, 10 * wind - 14 * butt)
        M.tail(P, t, 0.27, yaw=14, lag=0.5)
        M.arms(P, 25 * butt - 20 * wind, 0, 12 * butt, fp=-20 * wind)
        P.jaw = 12 * wind + 6 * DL.env(t, 0.55, 0.65, 0.7, 0.8)
        P.lid = DL.env(t, 0.34, 0.39, 0.5, 0.6)
        return P
    return T, g


# ---------------------------------------------------------------- species
_EYES = dict(eye_white='#ffffff', pupil='#2b2033', mouth='#6e2c48', tongue='#f48aa2')

# Stegosaurus: sunny yellow with pink leaf plates (accent: the game can tint
# them when it is happy), orange spots, two pairs of round tail spikes.
STEGO = dict(
    id='stego', plan='quad', height=1.5, lod=0.9,
    pal=dict(body='#f5cf62', belly='#fbf0d6', accent='#ff8fae', spots='#f39a3a',
             horn='#fdf1d8', blush='#ff8fa6', **_EYES),
    torso=(0.33, 0.52, 0.36), leg=0.25, fleg=0.17, leg_r=0.10, fleg_r=0.85, knee=0.05,
    hip_y=0.48, sh_y=0.55, neck_z=0.05,
    neck_len=0.12, neck_deg=-2, neck_deg2=8, neck_n=1, neck_r=0.50,
    head=dict(r=(0.23, 0.25, 0.22), off=(0.40, 0.25), snout=(0.66, 0.62, 0.58),
              snout_fwd=0.58, snout_drop=0.28, smile=dict(width=62, z=-0.30, curl=0.24)),
    eye=dict(r=0.30, az=42, el=16, flat=0.5, gaze=0.18),
    tail=dict(len=0.72, r=0.50, n=4, droop_deg=14, droop2_deg=-14, tip=0.30),
    parts=[
        ('plates', dict(n=9, size=0.78, start=0.04, end=0.98)),
        ('q_tailspikes', dict(pairs=2, at=0.74, gap=0.15)),
        ('spots', dict(spots=[(80, 35, 0.16), (280, 35, 0.16), (120, 20, 0.13), (240, 20, 0.13),
                              (55, 25, 0.12), (305, 25, 0.12), (150, 40, 0.13), (210, 40, 0.13)])),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}),
    speeds={'baby': (0.8, 1.6), 'juv': (0.9, 1.9), 'adult': (1.1, 2.2)},
)

# Ankylosaurus: coral, low and wide; a round dome of armour with butter knobs,
# cream side bumps and a ball club. Curls into a ball when tickled.
ANKYLO = dict(
    id='ankylo', plan='quad', height=1.0, lod=0.9,
    pal=dict(body='#ef8f7c', belly='#fbeedb', accent='#ffd98c', spots='#d86e60',
             horn='#fdf1d8', blush='#ff7fa0', **_EYES),
    torso=(0.44, 0.48, 0.30), leg=0.13, leg_r=0.10, knee=0.04, leg_x=0.62,
    neck_len=0.06, neck_deg=12, neck_deg2=6, neck_n=1, neck_r=0.55, neck_z=0.10,
    head=dict(r=(0.28, 0.26, 0.23), off=(0.42, 0.2), snout=(0.70, 0.50, 0.58),
              snout_fwd=0.55, snout_drop=0.30, cheeks=(0.60, 0.10, 0.25, 0.38),
              smile=dict(width=66, z=-0.30, curl=0.24)),
    eye=dict(r=0.28, az=42, el=18, flat=0.5, gaze=0.18),
    tail=dict(len=0.62, r=0.38, n=3, droop_deg=14, droop2_deg=-4, tip=0.42),
    parts=[
        ('q_scutes', dict()),
        ('q_sidebumps', dict(n=4)),
        ('q_club', dict(size=2.2)),
        ('horns', dict(horns=[dict(az=62, el=30, len=0.5, r=0.17, dir=(0.75, 0.35, 0.45),
                                   curl=(0.6, 0.6, 0.2), mirror=True)])),
    ],
    moves=dict(stance={'head': (-2, 0, 0)}, hop=0.18, lift=1.2),
    anims={'pet': ankylo_pet},
    speeds={'baby': (0.7, 1.4), 'juv': (0.85, 1.7), 'adult': (1.0, 2.0)},
)

# Protoceratops: bubblegum pink, chubby digger with a small mint frill and a
# beak. Digs in `play`.
PROTO = dict(
    id='proto', plan='quad', height=0.6, lod=0.85,
    pal=dict(body='#f5a3c8', belly='#fcefe0', accent='#7fd8bf', spots='#e4669a',
             horn='#fdf1d8', blush='#ff7fa6', **_EYES),
    torso=(0.31, 0.36, 0.31), leg=0.17, leg_r=0.09, knee=0.05,
    neck_len=0.08, neck_deg=30, neck_n=1, neck_r=0.52,
    head=dict(r=(0.30, 0.30, 0.28), off=(0.40, 0.28), snout=(0.60, 0.60, 0.60),
              snout_fwd=0.58, snout_drop=0.30, cheeks=(0.56, 0.12, 0.25, 0.42)),
    eye=dict(r=0.28, az=40, el=16, flat=0.5, gaze=0.18),
    tail=dict(len=0.40, r=0.50, n=3, droop_deg=24, droop2_deg=0, tip=0.20),
    parts=[
        ('frill', dict(r=1.05, tilt_deg=52, span_deg=200, scallops=5, scallop=0.08, up=0.42,
                       back=0.40, cup=0.12, wrap=0.30, thick=0.2, spots=5)),
        ('beak', dict(size=0.85)),
        ('bump', dict(on='snout', az=0, el=62, r=(0.24, 0.32, 0.20), mat='body')),
        ('spots', dict(spots=[(180, 62, 0.24), (150, 42, 0.18), (210, 42, 0.18),
                              (120, 26, 0.14), (240, 26, 0.14), (165, 82, 0.15)])),
    ],
    moves=dict(stance={'head': (-6, 0, 0)}, walk_reach=0.46),
    anims={'play': proto_play},
    speeds={'baby': (0.7, 1.5), 'juv': (0.8, 1.8), 'adult': (0.9, 2.1)},
)

# Pachycephalosaurus: sky-blue biped, a big golden dome ringed with knobs.
# Bonks the ball with the dome in `play`.
PACHY = dict(
    id='pachy', plan='biped', height=1.0,
    pal=dict(body='#84c6ec', belly='#f7efd8', accent='#ffc65c', spots='#5a9dd6',
             horn='#fdf1d8', blush='#ff9ab8', **_EYES),
    torso=(0.25, 0.31, 0.26), tilt_deg=22, t_fwd=0.2, leg=0.32, leg_r=0.08, knee=0.22,
    thigh_r=1.85, foot_len=1.6, arm_len=0.55, arm_r=0.15, arm_z=-0.02,
    neck_len=0.13, neck_deg=70, neck_deg2=30, neck_n=2, neck_r=0.55,
    head=dict(r=(0.26, 0.27, 0.25), off=(0.40, 0.22), snout=(0.62, 0.58, 0.52),
              snout_fwd=0.52, snout_drop=0.30, snout_taper=(0.16, 0.08),
              smile=dict(width=66, z=-0.30, curl=0.26)),
    eye=dict(r=0.28, az=42, el=14, flat=0.5, gaze=0.2),
    tail=dict(len=0.85, r=0.44, n=4, droop_deg=10, droop2_deg=-10, tip=0.18, flat=0.85),
    toes=3,
    parts=[
        ('q_dome', dict()),
        ('stripes', dict(n=3, width=0.12, length=0.7, start=0.3, end=0.85, tail=3)),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}),
    anims={'play': pachy_play},
    speeds={'baby': (0.8, 2.0), 'juv': (1.0, 2.6), 'adult': (1.2, 3.2)},
)

SPECIES = {'stego': STEGO, 'ankylo': ANKYLO, 'proto': PROTO, 'pachy': PACHY}
EGGS = {
    'stego': dict(shell='#fdf3cf', spots='#ff97b2'),
    'ankylo': dict(shell='#fbe6dc', spots='#ec8a76'),
    'proto': dict(shell='#fdebf4', spots='#7fd2bb'),
    'pachy': dict(shell='#e6f3fb', spots='#f5b84a'),
}
