"""species_meat.py - the gentle, goofy meat eaters of Tommy's Dino Zoo:
spino (Spinosaurus), dilo (Dilophosaurus), carno (Carnotaurus) and compy
(Compsognathus). Merged into dinos.py automatically; build with

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P dinos.py -- \\
        --only spino_baby,spino_juv,spino_adult,egg_spino

Never scary: round heads, big eyes, smiles, at most two tiny blunt fangs.

  spino  2.0 m  peach with a big turquoise sail (ribbed); long croc snout with
                a round nose knob; flat paddle tail. `play` = a fishing swipe
                (leans over the water, scoops with the right paw, proud grin).
  dilo   1.2 m  butter yellow, two pink head crests and a pink neck frill on
                its own bone `frill` (scale: folded small in every action,
                opens wide in `happy` and `call`, half open in `pet`).
  carno  1.6 m  cherry red, little bull horns, tiny tiny arms, long sprinter
                legs. `play` = a dash that skids to a stop braking with the
                tail; extra one-shot action `skid` (0.6 s) for the game to
                play when a run stops (starts in run lean, ends at rest).
  compy  0.35 m bubblegum pink with mint stripes, a tiny head tuft; lives in
                groups of 3 and follows Tommy. `walk` and `run` are hoppy
                bounding gaits (both feet nearly together, airborne phase).

Walk / run speeds each model was animated for (m/s; root stays in place, the
game moves the node at exactly this speed; cycle length in seconds):

  model         walk m/s (cycle s)   run m/s (cycle s)
  spino_baby    0.80 (0.47)          1.80 (0.43)
  spino_juv     1.00 (0.57)          2.20 (0.53)
  spino_adult   1.30 (0.73)          2.80 (0.70)
  dilo_baby     0.80 (0.37)          2.20 (0.27)
  dilo_juv      1.10 (0.40)          2.90 (0.30)
  dilo_adult    1.40 (0.53)          3.60 (0.40)
  carno_baby    0.80 (0.63)          2.60 (0.43)
  carno_juv     1.20 (0.63)          3.40 (0.53)
  carno_adult   1.60 (0.80)          4.20 (0.70)
  compy_baby    0.80 (0.27)          2.00 (0.27)   hops
  compy_juv     1.00 (0.27)          2.50 (0.27)   hops
  compy_adult   1.20 (0.37)          3.00 (0.27)   hops

Planted feet verified in Blender to move back at exactly these speeds
(compy: bounding hops, contact is 1-2 frames, same stride formula).
(the build prints the exact numbers: "[dino]   speed walk ...").
Animations: the 12 of ART-SPEC (idle* walk* run* eat drink sleep* happy pet
sit* call play sad*), 30 fps, every bone keyed every frame; carno adds `skid`.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dino_lib as DL  # noqa: E402
from mathutils import Vector as V  # noqa: E402

UP = DL.UP
FWD = DL.FWD
lerp, env, tl, wave, smooth = DL.lerp, DL.env, DL.tl, DL.wave, DL.smooth
TAU = DL.TAU


# ============================================================ local features
# Registered into DL.FEATURES at import (names prefixed meat_), so the shared
# library file only needed two tiny hooks (pre_rig, extra anims).

def _torso_top(D, f, start, end):
    """Point on the top line of the torso, f in [0, 1] from front to back."""
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = DL._rotm(L['torso_rot_deg'])
    phi = lerp(math.radians(start), math.radians(end), f)
    return Ct + Rt @ V((0, -tr[1] * math.cos(phi), tr[2] * math.sin(phi)))


def meat_sail(D, height=1.0, start=40, end=150, ribs=6, dip=0.10, lean=0.18, mat='accent',
              rib_mat='spots', thick=0.07):
    """Spino sail: a tall rounded slab along the back (start/end = angles over
    the torso's top, 0 = nose end, 180 = tail end), scalloped between the
    spines; the spines are slim tubes that show on both faces."""
    L = D.L
    tr = L['torso_r']
    H = height * tr[2] * D.A['plate']
    sink = tr[2] * 0.25

    def hgt(u):
        h = H * math.sin(math.pi * u) ** 0.65
        return h * (1 - dip * (0.5 + 0.5 * math.cos(TAU * ribs * u)))

    def fn(u, v):
        b = _torso_top(D, u, start, end)
        h = hgt(u)
        return b - UP * sink + UP * v * (h + sink) + V((0, v * v * h * lean, 0))
    th = tr[0] * thick
    D.add(DL.slab('sail', D.m(mat), fn, D.lod(28, 12), 5, th, ref=V((1, 0, 0))), DL._torso_skin(D))
    for i in range(ribs):
        u = (i + 0.5) / ribs
        pts = [fn(u, v) for v in (0.25, 0.6, 0.93)]
        D.add(DL.tube('rib', D.m(rib_mat), pts, [th * 0.95, th * 0.85, th * 0.5], seg=6, sub=2,
                      cap='end'), DL._torso_skin(D))


def meat_crests(D, h=0.62, gap=0.30, back=0.30, lean=0.12, thick=0.11, mat='accent', stripe=True):
    """Dilo's two thin half-moon crests on top of the snout and head."""
    L = D.L
    hc, hr, snc, snr = L['head_c'], L['head_r'], L['snout_c'], L['snout_r']
    H = h * hr[2] * D.A['crest']
    a = snc + FWD * snr[1] * 0.50 + UP * snr[2] * 0.55
    b = hc + UP * hr[2] * 0.72 + V((0, hr[1] * back, 0))
    for side in (1, -1):
        x = V((side * gap * hr[0], 0, 0))

        def fn(u, v, x=x, side=side):
            base = a.lerp(b, u) + UP * hr[2] * 0.18 * math.sin(math.pi * u) + x * (1 - 0.25 * v)
            hh = H * math.sin(math.pi * u ** 0.85) ** 0.8
            return base - UP * H * 0.25 + UP * v * (hh + H * 0.25) + V((side * v * hh * lean, 0, 0))
        cr = D.add(DL.slab('crest', D.m(mat), fn, D.lod(14, 8), 4, hr[0] * thick, ref=V((side, 0, 0))),
                   ('rigid', 'head'))
        if stripe and D.age != 'baby':
            for u in (0.42, 0.68):
                p = V(fn(u, 0.62))
                D.add(DL.decal('cstripe', D.m('spots'), cr, p + V((side * 0.05, 0, 0)), V((side, 0, 0)),
                               H * 0.09, H * 0.30, u_axis=V((0, 1, 0)), lift=0.0015, seg=8, nr=1),
                      ('rigid', 'head'))


def _dilo_frill_frame(D, back=0.55, drop=0.05):
    L = D.L
    pts = L['neck_pts']
    d = (pts[-1] - pts[-2]).normalized()
    hr = L['head_r']
    c = L['head_base'] - d * hr[1] * back - UP * hr[2] * drop
    up = (UP - d * d.dot(UP)).normalized()
    x = d.cross(up).normalized()        # = world +X when the neck faces -Y
    if x.x < 0:
        x = -x
    return c, d, up, x


def dilo_frill_bone(D, back=0.55):
    c, d, up, x = _dilo_frill_frame(D, back)
    par = 'neck_%d' % (len(D.L['neck_pts']) - 1)
    D.extra_bones.append(('frill', c, c + d * D.L['neck_r'] * 1.2, par, UP))


def meat_neck_frill(D, r=1.45, span_deg=250, cup=0.32, scallops=9, scallop=0.08, back=0.55,
                    mat='accent', stripes=7, thick=0.10):
    """Dilo's neck frill: a scalloped fan collar round the neck behind the
    head, cupped forward to frame the face. Rigid on bone `frill` (scaled
    small = folded, 1 = open)."""
    L = D.L
    c, d, up, x = _dilo_frill_frame(D, back)
    hr = L['head_r']
    rin = L['neck_r'] * 0.7
    R = r * max(hr) * D.A['frill']
    span = math.radians(span_deg)

    def fn(u, v):
        a = -span / 2 + span * u
        rho = lerp(rin, R, v) * (1 + scallop * math.cos(scallops * a) * v ** 2)
        k = (rho - rin) / (R - rin)
        return c + (x * math.sin(a) + up * math.cos(a)) * rho + d * cup * R * k * k
    fr = D.add(DL.slab('nfrill', D.m(mat), fn, D.lod(30, 16), D.lod(6, 4), max(hr) * thick, ref=d),
               ('rigid', 'frill'))
    for i in range(stripes):
        u = (i + 0.5) / stripes
        a = -span / 2 + span * u
        rad = x * math.sin(a) + up * math.cos(a)
        p = V(fn(u, 0.68))
        D.add(DL.decal('fstripe', D.m('spots'), fr, p + d * R * 0.2, d, R * 0.20, R * 0.055,
                       u_axis=rad, lift=0.002, seg=10, nr=1), ('rigid', 'frill'))


def meat_tuft(D, n=3, size=0.45, mat='accent'):
    """A tiny soft feather tuft on top of the head (compy)."""
    L = D.L
    hc, hr = L['head_c'], L['head_r']
    k = D.A['crest']
    for i in range(n):
        xo = (-1 + 2 * i / max(n - 1, 1)) * 0.35
        p, nn = DL.on_ell(hc, hr, xo * 40, 70)
        ln = size * hr[2] * k * (1.0 if xo == 0 else 0.8)
        b = p - nn * hr[2] * 0.06
        m1 = b + V((xo * ln * 0.4, ln * 0.25, ln * 0.6))
        t = b + V((xo * ln * 0.9, ln * 0.75, ln * 0.85))
        D.add(DL.tube('tuft', D.m(mat), [b, m1, t], [hr[2] * 0.11 * k, hr[2] * 0.08 * k, hr[2] * 0.015],
                      seg=6, sub=2, cap='end', flat=[0.5, 0.45, 0.4], nrm=V((1, 0, 0))), ('rigid', 'head'))


DL.FEATURES.update({'meat_sail': meat_sail, 'meat_crests': meat_crests,
                    'meat_neck_frill': meat_neck_frill, 'meat_tuft': meat_tuft})


# ============================================================ local motions

def _pose_feet_rest(M, P):
    for lg in M.D.legs:
        P.feet[lg['tag']] = (lg['ankle'].copy(), 0.0)


def spino_play(M):
    """Fishing swipe: peer at the water, scoop with the right paw out to the
    side, lift the catch to its grin, wag."""
    T = 0.8
    D = M.D

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        peer = env(t, 0.0, 0.16, 0.34, 0.52)           # leaning over, eyes on the fish
        wind = env(t, 0.04, 0.18, 0.22, 0.32)          # paw up, forward and out
        swipe = env(t, 0.22, 0.34, 0.40, 0.52)         # the scoop down and across
        show = env(t, 0.44, 0.56, 0.68, 0.80)          # catch lifted to the grin
        P.r('root', 12 * peer - 6 * show, -10 * peer + 8 * swipe, 0)
        P.at('root', (0, -M.H * 0.02 * peer, -M.legl * 0.10 * peer))
        M.spread(P, D.neck, 14 * peer - 12 * show, -10 * peer + 6 * show)
        P.r('head', 18 * peer - 10 * show, -12 * peer + 8 * swipe + 10 * show, 8 * show)
        P.r('arm.R', -85 * wind + 40 * swipe - 70 * show, -15 * swipe + 20 * show, 55 * wind - 25 * swipe)
        P.r('forearm.R', -30 * wind + 10 * swipe - 70 * show, 0, 0)
        P.r('arm.L', -25 * peer - 20 * show, 0, -10 * peer)
        P.r('forearm.L', -20 * peer - 25 * show, 0, 0)
        P.sc('root', (1 + 0.05 * swipe, 1, 1 - 0.05 * swipe + 0.03 * show))
        M.spread(P, D.tail, 10 * peer - 4 * show)
        M.tail(P, t, 0.4, yaw=8 + 18 * show, lag=0.6)
        P.jaw = 4 * peer + 26 * show
        P.lid = env(t, 0.30, 0.34, 0.38, 0.44) + 0.7 * env(t, 0.58, 0.62, 0.70, 0.76)
        return P
    return T, g


def carno_play(M):
    """A short dash that skids to a stop braking with the tail."""
    T = 0.8
    D = M.D
    H = M.H

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        crouch = env(t, 0.0, 0.10, 0.12, 0.22)
        dash = env(t, 0.12, 0.26, 0.30, 0.42)
        skid = env(t, 0.30, 0.42, 0.56, 0.74)
        wob = math.sin(TAU * (t - 0.44) * 6) * env(t, 0.44, 0.5, 0.6, 0.76)
        fwd = H * 0.10 * smooth((t - 0.12) / 0.28) * (1 - smooth((t - 0.5) / 0.3))
        P.at('root', (0, -fwd, -M.legl * (0.10 * crouch + 0.13 * skid)))
        P.r('root', 10 * crouch + 14 * dash - 18 * skid, 0, 3 * wob)
        M.spread(P, D.neck, -6 * dash + 10 * skid)
        P.r('head', -8 * dash + 12 * skid, 0, 6 * wob)
        # feet: scramble during the dash, then shoved ahead in the skid
        for lg in D.legs:
            a0 = lg['ankle']
            s = lg['side']
            step = math.sin(TAU * (t - 0.12) / 0.15 + (0 if s > 0 else math.pi)) * dash
            y = a0.y + H * 0.06 * step - fwd - H * 0.13 * skid * (1.0 if s > 0 else 0.8)
            z = a0.z + max(0.0, step) * M.legl * 0.18
            P.feet[lg['tag']] = (V((a0.x * (1 + 0.25 * skid), y, z)), -22 * skid)
        # tail hammers down to brake, then swishes
        M.spread(P, D.tail, 8 * dash - 26 * skid)
        M.tail(P, t, 0.3, yaw=6 + 10 * skid, lag=0.6)
        # tiny arms windmill
        P.r('arm.L', -40 * dash - 60 * skid + 25 * math.sin(TAU * t * 5), 0, 20 * skid)
        P.r('arm.R', -40 * dash - 60 * skid + 25 * math.sin(TAU * t * 5 + 2), 0, 20 * skid)
        P.jaw = 8 * dash + 24 * skid
        P.lid = 0.5 * crouch + env(t, 0.66, 0.70, 0.72, 0.78)
        P.sc('root', (1 + 0.04 * skid, 1, 1 - 0.05 * skid))
        return P
    return T, g


def carno_skid(M):
    """Extra one-shot: from a run lean to a skidding stop, settling at rest."""
    T = 0.6
    D = M.D
    H = M.H

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        run = 1 - smooth(t / 0.15)
        skid = env(t, 0.0, 0.14, 0.26, 0.55)
        wob = math.sin(TAU * (t - 0.2) * 5) * env(t, 0.2, 0.28, 0.4, 0.58)
        P.at('root', (0, 0, -M.legl * 0.14 * skid))
        P.r('root', 9 * run - 16 * skid, 0, 3 * wob)
        M.spread(P, D.neck, -6 * run + 10 * skid)
        P.r('head', -4 * run + 12 * skid, 0, 7 * wob)
        for lg in D.legs:
            a0 = lg['ankle']
            s = lg['side']
            stride = (H * 0.10 if s > 0 else -H * 0.10) * run
            y = a0.y + stride - H * 0.12 * skid * (1.0 if s > 0 else 0.75)
            P.feet[lg['tag']] = (V((a0.x * (1 + 0.2 * skid), y, a0.z)), -20 * skid)
        M.spread(P, D.tail, -8 * run - 24 * skid)
        M.tail(P, t, 0.3, yaw=8 * skid, lag=0.6)
        P.r('arm.L', -50 * skid + 15 * math.sin(TAU * t * 6), 0, 18 * skid)
        P.r('arm.R', -50 * skid + 15 * math.sin(TAU * t * 6 + 2), 0, 18 * skid)
        P.jaw = 4 * run + 20 * skid
        P.lid = env(t, 0.42, 0.46, 0.48, 0.54)
        return P
    return T, g


def hop_gait(kind, length=2.4, duty=0.42, hop=0.22, stagger=0.06, crouch=0.07):
    """Hoppy bounding gait: both feet almost together, an airborne phase.
    `length` = distance per hop in leg lengths; duty = ground fraction."""
    def f(M):
        D = M.D
        v = D.spec['speeds'][D.age][0 if kind == 'walk' else 1]
        F = max(8, int(round(M.legl * length / v * DL.FPS)))
        T = F / DL.FPS
        du = min(duty, 0.85 * M.legl / (v * T))     # keep the planted stride reachable
        S = v * T * du
        D.speeds[kind] = (v, T)
        hh = M.legl * hop
        lift = M.legl * 0.10

        def air(u):
            u = u % 1.0
            if u >= du:
                return hh * math.sin(math.pi * (u - du) / (1 - du)), 1
            return -M.legl * crouch * math.sin(math.pi * u / du), 0

        def g(t):
            P = M.base(t, T, breath=1, amp=0.2)
            u = t / T
            z0, fly = air(u + 0.5 * stagger)
            for lg in D.legs:
                ph = (u + (0.0 if lg['tag'] == 'L' else stagger)) % 1.0
                a0 = lg['ankle']
                if ph < du:
                    s = ph / du
                    y = a0.y - S / 2 + S * s
                    z = a0.z
                    pitch = 0.0
                    if s > 0.7:
                        pitch = 22 * smooth((s - 0.7) / 0.3)
                        z += (lg['toe'] - lg['ankle']).length * math.sin(math.radians(pitch)) * 0.5
                else:
                    s = (ph - du) / (1 - du)
                    y = a0.y + S / 2 - S * (0.5 - 0.5 * math.cos(math.pi * s))
                    z = a0.z + max(z0, 0.0) * 0.92 + lift * math.sin(math.pi * s)
                    pitch = 22 * (1 - s) ** 2 - 18 * math.sin(math.pi * s) * s
                P.feet[lg['tag']] = (V((a0.x, y, z)), pitch)
            P.at('root', (0, 0, z0))
            c = z0 / hh
            P.sc('root', (1 - 0.05 * c, 1, 1 + 0.07 * c))
            ph2 = TAU * u
            P.r('root', (2 if kind == 'walk' else 8) - 7 * math.sin(ph2 + 0.6), 0, 3 * math.sin(ph2 / 1))
            M.spread(P, D.neck, 4 * math.sin(ph2 + 1.0))
            P.r('head', 4 * math.sin(ph2 + 1.2) - (2 if kind == 'walk' else 6), 0, 0)
            M.spread(P, D.tail, 10 * math.sin(ph2 + 2.0) - (0 if kind == 'walk' else 6))
            M.tail(P, t, T * 2, yaw=6, lag=0.6)
            M.arms(P, -25 - 10 * math.sin(ph2 + 0.8), 0, 6, fp=-20)
            P.jaw = 6.0 if kind == 'run' else 3.0
            return P
        return T, g
    return f


# dilo frill: folded small in every action, open in happy / call (half in pet)
FRILL_CLOSED = (0.6, 0.7, 0.6)


def _frill_open(name, t, T):
    if name == 'happy':
        return env(t, 0.02, 0.16, 0.80, 0.98)
    if name == 'call':
        return env(t, 0.10, 0.26, 0.78, 0.96)
    if name == 'pet':
        return 0.55 * env(t, 0.25, 0.45, 0.9, 1.15)
    return 0.0


def _frill_post(name, t, T, P):
    o = _frill_open(name, t, T)
    flut = 1 + 0.05 * o * math.sin(TAU * t * 9)
    P.scl['frill'] = V(tuple(lerp(c, 1.0, o) * (flut if i != 1 else 1)
                             for i, c in enumerate(FRILL_CLOSED)))


def _jaw_post(k):
    """Long snouts open less (a croc jaw opened wide is a shovel, not cute)."""
    def f(name, t, T, P):
        P.jaw *= k
    return f


def wrapped(inner, post):
    """spec['anims'] for every action (ART-SPEC list + extra names in
    `inner`), each from `inner` or the generic Moves, passed through
    post(name, t, T, pose) on every frame."""
    names = list(DL.ANIMS) + [k for k in inner if k not in DL.ANIMS]

    def mk(name):
        def f(M):
            T, g = inner[name](M) if name in inner else getattr(M, name)()

            def g2(t):
                P = g(t)
                post(name, t, T, P)
                return P
            return T, g2
        return f
    return {n: mk(n) for n in names}


# ============================================================ species

EYE_PAL = dict(horn='#fbf3e0', eye_white='#ffffff', pupil='#241c30', mouth='#6a2840',
               tongue='#f58aa4', blush='#ff9ab8')

SPINO = dict(
    id='spino', plan='biped', height=2.0, lod=0.9, age_tweak={'baby': dict(lod=0.6)},
    pal=dict(body='#f4a088', belly='#fdf0dc', accent='#3fc2c4', spots='#2a8f9c', **EYE_PAL),
    torso=(0.34, 0.50, 0.34), tilt_deg=18, t_fwd=0.18, leg=0.36, leg_r=0.11, knee=0.2,
    thigh_r=1.8, foot_len=1.6, arm_len=0.85, arm_r=0.17, arm_z=0.02,
    neck_len=0.30, neck_deg=70, neck_deg2=26, neck_n=2, neck_r=0.55,
    head=dict(r=(0.24, 0.27, 0.23), off=(0.42, 0.18), snout=(0.60, 1.08, 0.50),
              snout_fwd=0.50, snout_drop=0.28, snout_taper=(0.05, 0.06), teeth=True,
              smile=dict(width=74, z=-0.34, curl=0.26), nostril_el=40),
    eye=dict(r=0.30, az=34, el=28, flat=0.5, gaze=0.2),
    tail=dict(len=1.05, r=0.46, n=4, droop_deg=12, droop2_deg=-4, tip=0.2, flat=1.25),
    toes=3,
    parts=[
        ('meat_sail', dict(height=1.25, start=38, end=158, ribs=5, dip=0.06)),
        ('bump', dict(on='snout', az=0, el=28, r=(0.30, 0.28, 0.24), mat='body')),
        ('spots', dict(mat='accent', spots=[(140, 30, 0.14), (220, 30, 0.14), (118, 10, 0.11),
                                            (242, 10, 0.11), (100, 32, 0.09), (260, 32, 0.09)])),
        ('ridge', dict(n=0, size=0.30, tail=5)),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}, sleep_fwd=0.38),
    speeds={'baby': (0.8, 1.8), 'juv': (1.0, 2.2), 'adult': (1.3, 2.8)},
    anims=wrapped({'play': spino_play}, _jaw_post(0.6)),
)

DILO = dict(
    id='dilo', plan='biped', height=1.2, lod=0.92,
    pal=dict(body='#f6d457', belly='#fff3d8', accent='#ff5fa6', spots='#e8782e', **EYE_PAL),
    torso=(0.23, 0.31, 0.24), tilt_deg=24, t_fwd=0.22, leg=0.36, leg_r=0.068, knee=0.24,
    thigh_r=1.85, foot_len=1.8, arm_len=0.62, arm_r=0.16, arm_z=-0.04,
    neck_len=0.22, neck_deg=72, neck_deg2=30, neck_n=2, neck_r=0.50,
    head=dict(r=(0.21, 0.24, 0.21), off=(0.40, 0.22), snout=(0.62, 0.86, 0.52),
              snout_fwd=0.50, snout_drop=0.22, snout_taper=(0.24, 0.10),
              smile=dict(width=70, z=-0.32, curl=0.28)),
    eye=dict(r=0.30, az=38, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.80, r=0.50, n=4, droop_deg=12, droop2_deg=-12, tip=0.2, flat=0.85),
    toes=3,
    pre_rig=[dilo_frill_bone],
    anims=wrapped({}, _frill_post),
    parts=[
        ('meat_crests', dict(h=1.05, gap=0.17, lean=0.55)),
        ('meat_neck_frill', dict()),
        ('spots', dict(spots=[(180, 70, 0.22), (150, 50, 0.17), (210, 50, 0.17), (165, 30, 0.13),
                              (195, 30, 0.13), (120, 35, 0.12), (240, 35, 0.12)])),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}),
    speeds={'baby': (0.8, 2.2), 'juv': (1.1, 2.9), 'adult': (1.4, 3.6)},
)

CARNO = dict(
    id='carno', plan='biped', height=1.6, lod=0.92,
    age_tweak={'baby': dict(lod=0.6, head=1.40), 'juv': dict(head=1.16)},
    pal=dict(body='#e2565f', belly='#fde6cf', accent='#ffcf4c', spots='#a8343f', **EYE_PAL),
    torso=(0.29, 0.40, 0.30), tilt_deg=20, t_fwd=0.2, leg=0.56, leg_r=0.09, knee=0.24,
    thigh_r=1.9, foot_len=1.7, arm_len=0.24, arm_r=0.12, arm_z=-0.05,
    neck_len=0.13, neck_deg=58, neck_deg2=25, neck_n=2, neck_r=0.66,
    head=dict(r=(0.26, 0.26, 0.26), off=(0.40, 0.22), snout=(0.80, 0.56, 0.64),
              snout_fwd=0.46, snout_drop=0.18, snout_taper=(0.10, 0.06), teeth=True,
              smile=dict(width=78, z=-0.30, curl=0.30)),
    eye=dict(r=0.29, az=38, el=18, flat=0.5, gaze=0.2),
    tail=dict(len=0.85, r=0.52, n=4, droop_deg=10, droop2_deg=-10, tip=0.2, flat=0.85),
    toes=3,
    parts=[
        ('horns', dict(horns=[dict(az=30, el=62, len=0.62, r=0.16, dir=(0.6, 0.1, 0.8),
                                   curl=(0.5, -0.2, 0.8), mirror=True)])),
        ('ridge', dict(n=6, size=0.16, start=0.2, end=0.9, tail=3)),
        ('spots', dict(spots=[(120, 20, 0.12), (240, 20, 0.12), (140, 45, 0.10), (220, 45, 0.10),
                              (105, -5, 0.09), (255, -5, 0.09)])),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}, run_duty=0.32),
    speeds={'baby': (0.8, 2.6), 'juv': (1.2, 3.4), 'adult': (1.6, 4.2)},
    anims={'play': carno_play, 'skid': carno_skid},
)

COMPY = dict(
    id='compy', plan='biped', height=0.35,
    pal=dict(body='#f6a6c6', belly='#fff1e4', accent='#56d0ad', spots='#3fb898', **EYE_PAL),
    torso=(0.19, 0.24, 0.20), tilt_deg=24, t_fwd=0.22, leg=0.32, leg_r=0.06, knee=0.24,
    thigh_r=1.9, foot_len=1.8, arm_len=0.6, arm_r=0.16, arm_z=-0.05,
    neck_len=0.17, neck_deg=72, neck_deg2=35, neck_n=2, neck_r=0.5,
    head=dict(r=(0.21, 0.23, 0.20), off=(0.40, 0.25), snout=(0.60, 0.72, 0.52),
              snout_fwd=0.5, snout_drop=0.22, snout_taper=(0.26, 0.12),
              smile=dict(width=70, z=-0.32, curl=0.30)),
    eye=dict(r=0.33, az=38, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.78, r=0.46, n=4, droop_deg=10, droop2_deg=-16, tip=0.2, flat=0.85),
    toes=3, lod=0.8,
    parts=[
        ('meat_tuft', dict(n=3)),
        ('spots', dict(mat='accent', spots=[(180, 78, 0.24), (150, 52, 0.17), (210, 52, 0.17),
                                            (180, 45, 0.15), (125, 25, 0.12), (235, 25, 0.12)])),
        ('stripes', dict(n=0, tail=3)),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}, hop=0.3),
    speeds={'baby': (0.8, 2.0), 'juv': (1.0, 2.5), 'adult': (1.2, 3.0)},
    anims={'walk': hop_gait('walk', length=3.6, duty=0.32, hop=0.38),
           'run': hop_gait('run', length=6.0, duty=0.22, hop=0.45, stagger=0.1, crouch=0.10)},
)

SPECIES = {'spino': SPINO, 'dilo': DILO, 'carno': CARNO, 'compy': COMPY}
EGGS = {'spino': dict(shell='#fde3d6', spots='#3fc2c4'),
        'dilo': dict(shell='#fff2c2', spots='#ff5fa6'),
        'carno': dict(shell='#fde6dc', spots='#e2565f'),
        'compy': dict(shell='#fde4ef', spots='#56d0ad')}
