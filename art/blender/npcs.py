"""npcs.py - the neighbours of Tommy's Dino Zoo, built, rigged and animated
procedurally on top of tommy.py (same bones, same 17 animations + 2 more).

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P npcs.py -- \
        [--out ../../game/assets/models] [--only nat,juampi,juan,kid_a,kid_b,kid_c] [--check]

Writes `npc_<id>.glb`: one skinned mesh + armature + actions, hats, glasses,
tools and hair built in (no separate attach files).

How it works
  tommy.py is imported as a module (its build only runs as a script). Its
  rig, IK solver and every animation read module globals for the body
  (HEAD_C, HIP, KNEE, ANKLE, SHOULDER, arm lengths, shoe tables, CARRY,
  SIT_ROOT...), so `apply_body()` rewrites those globals for each NPC and
  sets tommy's retarget hooks: RETARGET maps the hand targets Tommy's
  animations were written for (pet, give, use, dig, pickup, carry) onto the
  new torso, LEGK scales crouch/jump depths, GAITS sets each body's walk/run
  and POSTURE adds a constant stoop (Juan). Bone names, animation names and
  lengths are Tommy's. The heads reuse Tommy's face builders (eyes, lids,
  open mouth, brows, nose, ears), scaled by the head size.

Characters (rest height to the top of hair/hat; materials = palette roles)
  npc_nat     Doctora Nat     1.52 m  curly ponytail, round glasses, lab coat   8976 tris, 13 mats
  npc_juampi  Tio Juampi      1.61 m  backwards cap, beard, overalls, tools     8988 tris, 14 mats
  npc_juan    Abuelo Juan     1.44 m  flat cap, moustache, cardigan, stooped    8786 tris, 13 mats
  npc_kid_a   visiting kid    0.99 m  pigtails, yellow raincoat, rain boots     7922 tris, 11 mats
  npc_kid_b   visiting kid    1.05 m  glasses, dino hoodie (hood up, spikes)    7990 tris, 13 mats
  npc_kid_c   visiting kid    1.00 m  sun hat, overalls, bob                    7678 tris, 13 mats
  The kids use Tommy's exact proportions (and so his exact animation data,
  except sit/sleep heights, settled on their clothes). Abuelo Juan has no
  cane: it would be in his hand in every shared animation (run, dig...).
  Coats (Nat, kid A) are skinned partly to the thighs below the hips so the
  skirt follows the legs in walk/run/sit.

Animations (30 fps, root in place): Tommy's 17 (idle, walk, run, pickup,
carry_idle, carry_walk, pet, pet_low, give, use, dig, happy, wave, yawn,
sleep, sit, talk) with the same names and lengths, plus
  point      1.2 s   points forward with the right arm while talking, fist on hip
  think      1.6 s   hand on chin, other arm across the belly, "hmm", then "aha"
Walk / run: every NPC is animated for Tommy's speeds and cycle lengths,
walk 1.6 m/s (0.5 s cycle), run 3.5 m/s (0.4 s cycle), so the game's
`rig.loop("walk", speed / 1.6)` keeps the feet planted at any speed. The
grown-ups take longer, calmer steps in the same cycle (stance 42 %), Juan
shuffles (low foot lift, more lean).

Export: the actions are rewritten as quaternion keys before export
(tommy.quaternion_actions): Blender 3.3's exporter with the size
optimisation otherwise drops constant rotation channels (held poses).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdz_common as C  # noqa: E402
import tommy as T  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

A = C.args()
OUT = A.get('out', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'game', 'assets', 'models'))
V, MB, lerp, clamp, smoothstep, trk = T.V, T.MB, T.lerp, T.clamp, T.smoothstep, T.trk
RX, RY, RZ = T.RX, T.RY, T.RZ
TAU = T.TAU
PI = math.pi

# Tommy's globals, restored before every NPC
_GLOBALS = ['HEAD_C', 'HX', 'HY', 'HZU', 'HZD', 'ROOT_H', 'HIP_X', 'HIP', 'KNEE', 'ANKLE', 'TOE',
            'SOLE_Z', 'SHOULDER', 'L_UP', 'L_FORE', 'L_HAND', 'HEAD_BONE', 'GRIP', 'SHOE', 'SOLE',
            'HEEL_PIV', 'TOE_PIV', 'CARRY', 'SIT_ROOT', 'SLEEP_ROOT', 'RETARGET', 'LEGK', 'POSTURE',
            'GAITS']


def _snap(x):
    if isinstance(x, Vector):
        return x.copy()
    if isinstance(x, dict):
        return {k: _snap(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_snap(v) for v in x]
    return x


ORIG = {k: _snap(getattr(T, k)) for k in _GLOBALS}


# ===========================================================================
# Body proportions
# ===========================================================================

class Body:
    """Scale factors against Tommy (1.0 = Tommy).
    kH head size, kL leg length, kT torso length, kW shoulder width,
    kHip hip width, kD torso depth (hand targets in front of the body),
    kA arm length, kHand hand size, kR limb thickness, foot (x, y, z)."""

    def __init__(self, kH=1.0, kL=1.0, kT=1.0, kW=1.0, kHip=1.0, kD=1.0, kA=1.0, kHand=1.0, kR=1.0,
                 foot=(1.0, 1.0, 1.0), low=1.0, gaits=None, posture=None):
        self.kH, self.kL, self.kT, self.kW, self.kHip, self.kD = kH, kL, kT, kW, kHip, kD
        self.kA, self.kHand, self.kR, self.foot, self.low = kA, kHand, kR, foot, low
        self.gaits = gaits
        self.posture = posture or {}
        self.ident = all(abs(x - 1.0) < 1e-9 for x in (kH, kL, kT, kW, kHip, kD, kA, kHand) + tuple(foot))
        fx, fy, fz = foot
        self.ankle = 0.068 * fz
        self.knee = self.ankle + 0.115 * kL
        self.hip = self.knee + 0.117 * kL
        self.root = self.hip + 0.010 * kL
        r = self.root
        self.spine = r + 0.06 * kT
        self.chest = r + 0.14 * kT
        self.shoulder = r + 0.195 * kT
        self.neck = r + 0.245 * kT
        self.headbone = self.neck + 0.045 * kT
        self.headc = self.headbone + 0.168 * kH
        self.top = self.headc + 0.200 * kH

    def tz(self, z):
        """Tommy-space height -> this body (piecewise linear on landmarks)."""
        a = [0.0, 0.068, 0.183, 0.31, 0.45, 0.505, 0.555, 0.60, 0.768, 0.968]
        b = [0.0, self.ankle, self.knee, self.root, self.chest, self.shoulder, self.neck, self.headbone,
             self.headc, self.top]
        if z <= a[1]:
            i = 0
        elif z >= a[-2]:
            i = len(a) - 2
        else:
            i = max(k for k in range(len(a) - 1) if a[k] <= z)
        return b[i] + (z - a[i]) * (b[i + 1] - b[i]) / (a[i + 1] - a[i])

    def rt(self, p, low=False):
        k = smoothstep(0.20, 0.42, p.z)
        kx = lerp(self.kHip, self.kW, k)
        z = p.z * self.low if low else self.tz(p.z)
        return V(p.x * kx, p.y * self.kD, z)


def apply_body(b):
    for k, v in ORIG.items():
        setattr(T, k, _snap(v))
    if b.ident:
        return
    fx, fy, fz = b.foot
    T.HX, T.HY, T.HZU, T.HZD = (x * b.kH for x in (ORIG['HX'], ORIG['HY'], ORIG['HZU'], ORIG['HZD']))
    T.HEAD_C = V(0, ORIG['HEAD_C'].y * b.kH, b.headc)
    T.HEAD_BONE = V(0, 0, b.headbone)
    T.ROOT_H = V(0, 0, b.root)
    T.HIP_X = 0.070 * b.kHip
    T.HIP = V(T.HIP_X, 0.0, b.hip)
    T.KNEE = V(T.HIP_X, -0.012 * b.kL, b.knee)
    T.ANKLE = V(T.HIP_X, 0.0, b.ankle)
    T.TOE = V(T.HIP_X, -0.120 * fy, 0.022 * fz)
    T.SOLE_Z = -b.ankle
    T.SHOULDER = V(0.128 * b.kW, 0.004, b.shoulder)
    T.L_UP, T.L_FORE, T.L_HAND = 0.100 * b.kA, 0.092 * b.kA, 0.070 * b.kHand
    T.GRIP = 0.036 * b.kHand
    T.SHOE = [(y * fy, hw * fx, top * fz, bot * fz) for y, hw, top, bot in ORIG['SHOE']]
    T.SOLE = [(y * fy, hw * fx) for y, hw in ORIG['SOLE']]
    T.HEEL_PIV = V(0, 0.060 * fy, T.SOLE_Z)
    T.TOE_PIV = V(0, -0.135 * fy, T.SOLE_Z)     # nearer the tip: big shoes in the run toe-off
    T.RETARGET = b.rt
    T.LEGK = b.kL
    T.POSTURE = dict(b.posture)
    T.CARRY = {k: b.rt(v) for k, v in ORIG['CARRY'].items()}
    if b.gaits:
        T.GAITS = b.gaits
    # sitting: the bottom of the pelvis just on the ground; legs forward
    T.SIT_ROOT = V(0, 0.07 * b.kL, -(b.root - 0.09 * b.kT))
    # lying on the side: body length along X scales with the height
    T.SLEEP_ROOT = V(0.20 * b.top / 0.968, 0.14 * b.kL, -(b.root - 0.189 * b.kW))


# ===========================================================================
# Small mesh helpers (on top of tommy's MB / loft / tube / blob / strip)
# ===========================================================================

def side_pt(p, s):
    return V(s * p.x, p.y, p.z)


def ring(z, hw, fr, bk, n=30, e=2.3, mod=None, cx=0.0, cy=0.0):
    """Superellipse ring at height z, front (-Y) depth fr, back bk.
    k = 0 at +X (his left), k = n/4 at the front centre."""
    pts = []
    ex = 2.0 / e
    for k in range(n):
        th = TAU * k / n
        cs, sn = math.cos(th), math.sin(th)
        x = math.copysign(abs(cs) ** ex, cs) * hw
        y = math.copysign(abs(sn) ** ex, sn) * (fr if sn > 0 else bk)
        r = mod(z, th) if mod else 1.0
        pts.append(V(cx + x * r, cy - y * r, z))
    return pts


def torso_loft(mb, prof, zs, key_fn, n=30, e=2.3, mod=None, cap0=None, cap1=None, cap_keys=(None, None)):
    rings = []
    for z in zs:
        hw, fr, bk = T.interp_rows(prof, z)
        rings.append(ring(z, hw, fr, bk, n, e, mod))
    return T.loft(mb, rings, key_fn, cap0=cap0, cap1=cap1, cap_keys=cap_keys)


def grid_mb(mb, rows, key_fn, closed_u=False):
    T.grid_faces(mb, rows, key_fn, closed=closed_u)


def bvh_of(mb):
    return BVHTree.FromPolygons([tuple(v) for v in mb.v], mb.f)


def patch(mb, bvh, fn, na, nb, off, key, side=-1, key_fn=None):
    """A grid patch fn(a, b) -> (x, z) (a, b in 0..1) projected along Y onto
    the surface in `bvh` from the front (side -1) or the back (+1)."""
    rows = []
    for j in range(nb + 1):
        row = []
        for i in range(na + 1):
            x, z = fn(i / na, j / nb)
            hit = bvh.ray_cast(V(x, side * 0.9, z), V(0, -side, 0))
            if hit[0] is None:
                p, n = V(x, side * 0.05, z), V(0, side, 0)
            else:
                p, n = hit[0], (hit[1] if hit[1].y * side > 0 else -hit[1])
            row.append(mb.vert(p + n * off))
        rows.append(row)
    for j in range(nb):
        for i in range(na):
            a, b, c, d = rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]
            mb.face((a, b, c, d), key_fn(i, j) if key_fn else key)
    return rows


def snap_strip(mb, bvh, path, half_w, off, key, n=None):
    """A flat band following `path` (points near a surface), snapped to the
    nearest surface point and lifted `off` along its normal."""
    pts, ts = T.catmull(path, n or 4)
    rows_a, rows_b = [], []
    m = len(pts)
    for i, p in enumerate(pts):
        loc, nrm, _, _ = bvh.find_nearest(p)
        if loc is None:
            loc, nrm = p, V(0, 0, 1)
        tng = (pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]).normalized()
        side = tng.cross(nrm).normalized()
        w = half_w(i / (m - 1)) if callable(half_w) else half_w
        q = loc + nrm * off
        rows_a.append(mb.vert(q + side * w))
        rows_b.append(mb.vert(q - side * w))
    for i in range(m - 1):
        mb.face((rows_a[i], rows_a[i + 1], rows_b[i + 1], rows_b[i]), key)


def tube_k(mb, pts, radii, key_fn, n=12, cap0=False, cap1=False, capr=0.5):
    """tommy.tube with a key function key_fn(i, k) per face (checks)."""
    m = len(pts)
    Ts = []
    for i in range(m):
        d = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
        Ts.append(d.normalized() if d.length > 1e-9 else V(0, 0, 1))
    ref = V(0, 0, 1) if abs(Ts[0].z) < 0.9 else V(0, -1, 0)
    N = (ref - Ts[0] * ref.dot(Ts[0])).normalized()
    rows, frames = [], []
    for i, p in enumerate(pts):
        N = N - Ts[i] * N.dot(Ts[i])
        N.normalize()
        B = Ts[i].cross(N)
        r = radii[i]
        frames.append((N.copy(), B.copy()))
        rows.append([mb.vert(p + N * (r * math.cos(TAU * k / n)) + B * (r * math.sin(TAU * k / n)))
                     for k in range(n)])
    T.grid_faces(mb, rows, lambda i, k, c: key_fn(i, k))
    for use, idx, sgn in ((cap0, 0, -1), (cap1, m - 1, 1)):
        if not use:
            continue
        p, r, (N_, B_) = pts[idx], radii[idx], frames[idx]
        prev = rows[idx]
        for s in (1, 2):
            a = (PI / 2) * s / 3
            cur = [mb.vert(p + (N_ * math.cos(TAU * k / n) + B_ * math.sin(TAU * k / n)) * r * math.cos(a)
                           + Ts[idx] * sgn * r * capr * math.sin(a)) for k in range(n)]
            T.grid_faces(mb, [prev, cur], lambda i, k, c: key_fn(idx, k))
            prev = cur
        T.fan(mb, mb.vert(p + Ts[idx] * sgn * r * capr), prev, key_fn(idx, 0))
    return rows


def loop_tube(mb, pts, nrms, r, key, n=6):
    """Closed tube (torus-like) through pts; nrms orient the section."""
    m = len(pts)
    rows = []
    for i in range(m):
        tg = (pts[(i + 1) % m] - pts[i - 1]).normalized()
        N = nrms[i] - tg * nrms[i].dot(tg)
        N.normalize()
        B = tg.cross(N)
        rows.append([mb.vert(pts[i] + N * (r * math.cos(TAU * k / n)) + B * (r * math.sin(TAU * k / n)))
                     for k in range(n)])
    rows.append(rows[0])
    T.grid_faces(mb, rows, lambda i, k, c: key)


def scale_from(mb, i0, centre, k):
    """Scale the vertices added since index i0 about `centre`."""
    for i in range(i0, len(mb.v)):
        mb.v[i] = centre + (mb.v[i] - centre) * k


def remap(mb, j0, table):
    for j in range(j0, len(mb.fk)):
        mb.fk[j] = table.get(mb.fk[j], mb.fk[j])


def hp(u, v, off=0.0):
    return T.head_pt(u, v, off)


def hn(u, v):
    return T.head_nrm(u, v)


def head_space(mb, i0):
    """Vertices built around the origin (head centre) -> model space."""
    for i in range(i0, len(mb.v)):
        mb.v[i] = mb.v[i] + T.HEAD_C


# ===========================================================================
# Head pieces
# ===========================================================================

def face_extras(mb, nose=1.0, ears=True, ear=1.0, blush=1.0, blush_v=-0.06, cheeks=0.0):
    k = T.HX / ORIG['HX']
    i0 = len(mb.v)
    c = hp(0.0, -0.03, -0.004)
    T.ellipsoid(mb, c, (0.020, 0.017, 0.016), 'skin', rot=T.frame_z(hn(0.0, -0.03), V(1, 0, 0)), n=8, rings=5)
    scale_from(mb, i0, c, k * nose)
    if ears:
        for s in (-1, 1):
            u, v = s * 1.50, -0.05
            p = hp(u, v, -0.008)
            i0 = len(mb.v)
            T.ellipsoid(mb, p, (0.052, 0.036, 0.030), 'skin', rot=T.frame_z(hn(u, v), V(0, 0, 1)), n=10, rings=6)
            scale_from(mb, i0, p, k * ear)
    if cheeks:
        for s in (-1, 1):
            u, v = s * 0.62, -0.20
            p = hp(u, v, -0.012)
            T.ellipsoid(mb, p, (0.075 * k, 0.06 * k, cheeks * k), 'skin',
                        rot=T.frame_z(hn(u, v), V(0, 0, 1)), n=10, rings=6)
    for s in (-1, 1):
        T.blob(mb, s * 0.60, blush_v, 0.11 * blush, 0.065 * blush, 'blush', 0.002 + (cheeks * 0.55 if cheeks else 0),
               nr=2, na=14)


def lashes(mb, n=2):
    for s in (-1, 1):
        cu = s * T.EYE_U
        for j in range(n):
            th = math.radians(18 + 22 * j)
            u0 = cu + s * T.EYE_AU * 0.92 * math.cos(th) / math.cos(T.EYE_V)
            v0 = T.EYE_V + T.EYE_AV * 0.92 * math.sin(th)
            du, dv = s * (0.07 - 0.015 * j), 0.03 + 0.035 * j
            T.strip(mb, lambda t, u0=u0, v0=v0, du=du, dv=dv: (u0 + du * t, v0 + dv * t - 0.02 * t * t),
                    lambda t: 0.014 * (1 - t) + 0.003, 'pupil', 0.0035, n=3)


def brows(mb, key='hair', w=0.026, lift=0.12, length=0.30, arch=0.035, tilt=0.0):
    for s in (-1, 1):
        cu = s * T.EYE_U
        curve = (lambda t, cu=cu, s=s: (cu + s * (t - 0.5) * length,
                                         T.EYE_V + T.EYE_AV + lift + arch * (1 - ((t - 0.5) * 2) ** 2)
                                         + tilt * (t - 0.5)))
        T.strip(mb, curve, lambda t: w * (0.55 + 0.45 * math.sin(math.pi * t)), key, 0.003, n=8)


def hair_cap(mb, hairline, thick, key='hair', NU=64, TS=(0.15, 0.35, 0.55, 0.72, 0.85, 0.94, 1.0),
             tuck=0.02):
    """Tommy's hair shell with a custom hairline(u) and thickness(u, t)."""
    vt = PI / 2
    rows = []
    us = [-PI + TAU * i / NU for i in range(NU)]
    for t in TS:
        rows.append([mb.vert(hp(u, vt - t * (vt - hairline(u)), thick(u, t))) for u in us])
    rows.append([mb.vert(hp(u, hairline(u) + tuck, -0.004)) for u in us])
    T.grid_faces(mb, rows, lambda i, k, c: key)
    T.fan(mb, mb.vert(hp(0, vt, thick(0, 0))), rows[0], key)


def head_band(mb, u0, u1, vlo, vhi, thick, key, NU=20, NV=6, tuck=0.015):
    """A shell over part of the head: u in [u0, u1], v in [vlo(u), vhi(u)];
    thick(u, s) is the lift (s 0 bottom .. 1 top). Edges tuck under."""
    rows = []
    for j in range(-1, NV + 2):
        row = []
        for i in range(-1, NU + 2):
            a = clamp(i / NU, 0, 1)
            u = lerp(u0, u1, a)
            s = clamp(j / NV, 0, 1)
            v = lerp(vlo(u), vhi(u), s)
            edge = i < 0 or i > NU or j < 0 or j > NV
            if j < 0:
                v -= tuck
            elif j > NV:
                v += tuck
            if i < 0:
                u -= tuck / max(0.2, math.cos(v))
            elif i > NU:
                u += tuck / max(0.2, math.cos(v))
            off = -0.004 if edge else thick(u, s)
            row.append(mb.vert(hp(u, v, off)))
        rows.append(row)
    T.grid_faces(mb, rows, lambda i, k, c: key, closed=False)


def glasses(mb, key='glasses', ra=1.18, rb=1.12, off=0.020, r=0.0075, n_pts=18):
    k = T.HX / ORIG['HX']
    r *= k
    for s in (-1, 1):
        cu = s * T.EYE_U
        pts, nrm = [], []
        for i in range(n_pts):
            th = TAU * i / n_pts
            v = T.EYE_V - 0.01 + T.EYE_AV * rb * math.sin(th)
            u = cu + T.EYE_AU * ra * math.cos(th) / math.cos(v)
            pts.append(hp(u, v, off * k))
            nrm.append(hn(u, v))
        loop_tube(mb, pts, nrm, r, key, n=5)
        # temple arm back to the ear
        u_out = cu + s * T.EYE_AU * ra / math.cos(T.EYE_V)
        path = [hp(u_out + s * 0.02, T.EYE_V + 0.04, off * k * 0.8), hp(s * 0.95, T.EYE_V + 0.07, 0.014 * k),
                hp(s * 1.36, T.EYE_V + 0.03, 0.010 * k)]
        T.tube(mb, path, [r * 0.85] * 3, key, n=5, cap0=False)
    # bridge
    ub = T.EYE_U - T.EYE_AU * ra / math.cos(T.EYE_V)
    path = [hp(-ub - 0.01, T.EYE_V + 0.03, off * k), hp(0, T.EYE_V + 0.06, off * k * 1.25),
            hp(ub + 0.01, T.EYE_V + 0.03, off * k)]
    pts, _ = T.catmull(path, 3)
    T.tube(mb, pts, [r * 0.9] * len(pts), key, n=6, cap0=False, cap1=False)


def head_parts(arm, parts, hair_fn, extras_fn=None, face_kw=None, brow_kw=None, girl=False, eyes=True):
    """Head skin + face + lids + open mouth (Tommy's builders), then the
    character's hair/hat via hair_fn(mb) (rigid to `head`)."""
    mb = MB()
    T.head_skin(mb)
    face_extras(mb, **(face_kw or {}))
    h = T.to_object('n_head', mb)
    mb = MB()
    T.build_eyes(mb)
    brows(mb, **(brow_kw or {}))
    T.build_mouth(mb)
    if girl:
        lashes(mb)
    face = T.to_object('n_face', mb, recalc=False, out_from=T.HEAD_C)
    for o in (h, face):
        C.skin_rigid(o, 'head')
        parts.append(o)
    for s, sd in ((1, 'L'), (-1, 'R')):
        mb = MB()
        T.build_eyelid(mb, s)
        o = T.to_object('n_lid' + sd, mb, recalc=False, out_from=T.HEAD_C)
        C.skin_rigid(o, 'eyelid.' + sd)
        parts.append(o)
    mb = MB()
    T.build_mouth_open(mb)
    o = T.to_object('n_mouth_open', mb, recalc=False, out_from=T.HEAD_C)
    C.skin_rigid(o, 'mouth_open')
    parts.append(o)
    mb, ms = MB(), MB()
    hair_fn(mb, ms)      # mb: shells over the head (face out), ms: closed solids
    for nm, m, kw in (('n_hair', mb, dict(recalc=False, out_from=T.HEAD_C)), ('n_hair2', ms, {})):
        if m.f:
            o = T.to_object(nm, m, **kw)
            C.skin_rigid(o, 'head')
            parts.append(o)
    if extras_fn:
        mb = MB()
        extras_fn(mb)
        o = T.to_object('n_hx', mb)
        C.skin_rigid(o, 'head')
        parts.append(o)


# ===========================================================================
# Body pieces
# ===========================================================================

def tommy_prof(b, rows, wk=1.0, fk=1.0, bk=1.0, belly=0.0, broad=0.0):
    """Tommy's SHIRT / PELVIS profile rows re-proportioned to body b.
    belly: extra front depth (fraction) around the tummy; broad: extra width
    at the chest/shoulders (fraction)."""
    out = []
    for z, hw, fr, bkk in rows:
        s = (z - 0.31) / 0.245
        zz = b.root + (z - 0.31) * b.kT
        bel = belly * math.exp(-((s - 0.32) / 0.28) ** 2)
        brd = broad * smoothstep(0.15, 0.75, s) * (1 - 0.6 * smoothstep(0.85, 1.05, s))
        out.append((zz, hw * b.kW * wk * (1 + brd) * (1 + 0.5 * bel), fr * b.kD * fk * (1 + bel), bkk * b.kD * bk))
    return out


def zmap(b, z):
    return b.root + (z - 0.31) * b.kT


def neck(b, parts, arm, r=1.0):
    mb = MB()
    k = b.kR * r
    z0, z1 = zmap(b, 0.535), b.headbone
    T.tube(mb, [V(0, 0.004, z0), V(0, 0.004, z1), V(0, 0.0, z1 + 0.04 * b.kH)],
           [0.050 * k, 0.049 * k, 0.047 * k], 'skin', n=10)
    o = T.to_object('n_neck', mb)
    C.skin_near(o, arm, ['chest', 'neck', 'head'], power=4)
    parts.append(o)


def pelvis(b, parts, key, wk=1.0, fk=1.0, bk=1.0):
    mb = MB()
    prof = tommy_prof(b, T.PELVIS, wk, fk, bk)
    zs = [zmap(b, z) for z in [0.245, 0.252, 0.260, 0.274, 0.295, 0.320, 0.345]]
    rings = [ring(z, *T.interp_rows(prof, z), 20) for z in zs]
    T.loft(mb, rings, lambda i, k, c: key, cap0=V(0, 0, zmap(b, 0.240)), cap1=V(0, 0, zmap(b, 0.356)))
    o = T.to_object('n_pelvis', mb)
    C.skin_rigid(o, 'root')
    parts.append(o)
    return mb


def arm_pieces(b, parts, arm, sleeve_key, sleeve='short', cuff_key=None, sleeve_fn=None, skin_r=1.0,
               sleeve_r=1.0, roll=None):
    """Skin arm + sleeve (short: Tommy's; long: to the wrist; 'roll': to the
    elbow with a rolled cuff) + mitten hands."""
    k = b.kR
    for s, sd in ((1, 'L'), (-1, 'R')):
        sh, el, wr, tip = T.arm_rest(s)
        du = (el - sh).normalized()
        df = (wr - el).normalized()
        mb = MB()
        T.limb(mb, [sh - du * 0.012, el, wr + df * 0.014 * b.kA],
               [0.034 * k * skin_r, 0.031 * k * skin_r, 0.029 * k * skin_r], 'skin', per=4, n=10,
               cap0=False, cap1=False)
        o = T.to_object('n_arm' + sd, mb)
        C.skin_near(o, arm, ['upper_arm.' + sd, 'forearm.' + sd], power=4)
        parts.append(o)
        mb = MB()
        R = 0.054 * k * sleeve_r
        kf = sleeve_fn or (lambda i, kk: sleeve_key)
        if sleeve == 'short':
            tube_k(mb, [sh, sh + du * 0.030 * b.kA, sh + du * 0.050 * b.kA], [R, R * 0.98, R * 0.95], kf, n=12)
            T.tube(mb, [sh + du * 0.046 * b.kA, sh + du * 0.072 * b.kA], [R * 0.97, R * 0.955],
                   cuff_key or sleeve_key, n=12, cap0=False, capr=0.25)
            T.ellipsoid(mb, sh, (R, R, R), sleeve_key, n=12, rings=7)
            o = T.to_object('n_sleeve' + sd, mb)
            C.skin_rigid(o, 'upper_arm.' + sd)
            parts.append(o)
        elif sleeve == 'roll':
            # to just past the elbow, rolled cuff
            pts = [sh, sh + du * 0.5 * T.L_UP, el - du * 0.01, el + df * 0.25 * T.L_FORE]
            pts, _ = T.catmull(pts, 3)
            rr = [lerp(R, R * 0.80, i / (len(pts) - 1)) for i in range(len(pts))]
            tube_k(mb, pts, rr, kf, n=12)
            T.ellipsoid(mb, sh, (R, R, R), sleeve_key, n=12, rings=5)
            c0 = el + df * 0.22 * T.L_FORE
            T.tube(mb, [c0 - df * 0.03 * b.kA, c0, c0 + df * 0.03 * b.kA], [R * 0.84, R * 0.88, R * 0.84],
                   cuff_key or sleeve_key, n=12, cap0=False, cap1=False)
            o = T.to_object('n_sleeve' + sd, mb)
            C.skin_near(o, arm, ['upper_arm.' + sd, 'forearm.' + sd], power=4)
            parts.append(o)
        else:  # long
            pts = [sh, sh + du * 0.5 * T.L_UP, el, el + df * 0.5 * T.L_FORE, wr - df * 0.012 * b.kA]
            pts, _ = T.catmull(pts, 3)
            pts = pts[::2] if len(pts) > 9 else pts
            rr = [lerp(R, R * 0.74, (i / (len(pts) - 1)) ** 0.8) for i in range(len(pts))]
            tube_k(mb, pts, rr, kf, n=10)
            T.ellipsoid(mb, sh, (R, R, R), sleeve_key, n=10, rings=5)
            c0 = wr - df * 0.022 * b.kA
            T.tube(mb, [c0 - df * 0.022 * b.kA, c0, c0 + df * 0.010 * b.kA], [R * 0.78, R * 0.80, R * 0.76],
                   cuff_key or sleeve_key, n=10, cap0=False)
            o = T.to_object('n_sleeve' + sd, mb)
            C.skin_near(o, arm, ['upper_arm.' + sd, 'forearm.' + sd], power=4)
            parts.append(o)
        mb = MB()
        i0 = len(mb.v)
        mitten(mb, s)
        # build_hand sits at the (scaled) rest wrist with Tommy's sizes
        scale_from(mb, i0, wr, b.kHand)
        o = T.to_object('n_hand' + sd, mb)
        C.skin_rigid(o, 'hand.' + sd)
        parts.append(o)


def skin_skirt(o, arm, z0, z1, kmax=0.6, bones=('root', 'spine', 'chest')):
    """Torso weights, then below z0 blend towards the thighs (kmax at the
    hem z1) so a coat skirt follows the legs (walk, sit) instead of
    cutting through them."""
    C.skin_near(o, arm, list(bones), power=3)
    gs = {g.name: g for g in o.vertex_groups}
    for sd in 'LR':
        gs['thigh.' + sd] = o.vertex_groups.new(name='thigh.' + sd)
    for v in o.data.vertices:
        f = smoothstep(z0, z1, v.co.z)
        if f <= 0.0:
            continue
        w = f * kmax
        for g in v.groups:
            g.weight *= (1 - w)
        side = smoothstep(-0.04, 0.04, v.co.x)
        if side > 0:
            gs['thigh.L'].add([v.index], w * side, 'REPLACE')
        if side < 1:
            gs['thigh.R'].add([v.index], w * (1 - side), 'REPLACE')


def mitten(mb, s):
    """tommy.build_hand with fewer segments."""
    _, el, wr, tip = T.arm_rest(s)
    d = (tip - wr).normalized()
    rot = T.frame_z(d, V(s, 0, 0))
    fwd = rot @ V(0, 1, 0)
    if fwd.y > 0:
        fwd = -fwd
    c = wr + d * 0.036
    rr = Matrix((rot @ V(1, 0, 0), fwd, d)).transposed()
    T.ellipsoid(mb, c, (0.029, 0.038, 0.043), 'skin', rot=rr, n=10, rings=6)
    th = wr + d * 0.024 + fwd * 0.030 - (rot @ V(1, 0, 0)) * 0.006
    T.ellipsoid(mb, th, (0.014, 0.014, 0.022), 'skin', rot=rr @ RX(-25), n=6, rings=4)


def legs(b, parts, arm, key, r=1.0, cuff=True, shorts=None, skin_r=0.80, cuff_key=None, cuff_r=1.08):
    """Trouser legs hip -> ankle (Tommy's), or shorts to `shorts` (0..1 of
    the thigh) with bare legs below."""
    k = b.kR * r
    for s, sd in ((1, 'L'), (-1, 'R')):
        hip, kn, an = side_pt(T.HIP, s), side_pt(T.KNEE, s), side_pt(T.ANKLE, s)
        dshin = (an - kn).normalized()
        dth = (kn - hip).normalized()
        mb = MB()
        if shorts is None:
            c = an - dshin * 0.040 * b.kL
            T.limb(mb, [hip + V(0, 0, 0.035 * b.kL), hip, kn, c + dshin * 0.012 * b.kL],
                   [0.057 * k, 0.061 * k, 0.056 * k, 0.057 * k], key, per=4, n=12, cap0=False, cap1=False)
            o = T.to_object('n_leg' + sd, mb)
            C.skin_near(o, arm, ['thigh.' + sd, 'shin.' + sd], power=4)
            parts.append(o)
            if cuff:
                mb = MB()
                T.tube(mb, [c - dshin * 0.022 * b.kL, c, c + dshin * 0.006 * b.kL],
                       [0.064 * k * cuff_r / 1.08, 0.066 * k * cuff_r / 1.08, 0.061 * k * cuff_r / 1.08],
                       cuff_key or key, n=12, cap0=False, cap1=False)
                o = T.to_object('n_cuff' + sd, mb)
                C.skin_rigid(o, 'shin.' + sd)
                parts.append(o)
        else:
            end = hip + (kn - hip) * shorts
            T.limb(mb, [hip + V(0, 0, 0.035 * b.kL), hip, end], [0.064 * k, 0.068 * k, 0.070 * k], key,
                   per=3, n=12, cap0=False, cap1=False)
            T.tube(mb, [end - dth * 0.02 * b.kL, end, end + dth * 0.006 * b.kL],
                   [0.072 * k, 0.074 * k, 0.069 * k], cuff_key or key, n=12, cap0=False)
            o = T.to_object('n_shorts' + sd, mb)
            C.skin_near(o, arm, ['thigh.' + sd, 'shin.' + sd], power=6)
            parts.append(o)
            mb = MB()
            T.limb(mb, [hip + (kn - hip) * (shorts - 0.15), kn, an + V(0, 0, 0.01)],
                   [0.050 * k * skin_r / 0.8, 0.046 * k * skin_r / 0.8, 0.036 * k * skin_r / 0.8], 'skin',
                   per=4, n=10, cap0=False, cap1=False)
            o = T.to_object('n_shin' + sd, mb)
            C.skin_near(o, arm, ['thigh.' + sd, 'shin.' + sd], power=4)
            parts.append(o)


def shoe(b, parts, arm, upper='shoes', sole='shoe_sole', toe_key=None, lace_key=None, boot=0.0,
         boot_key=None, collar_key=None, collar=0.0, wide=1.0):
    """Tommy's chunky sneaker scaled to the body's foot; boot > 0 adds a
    shaft that height (m) up the shin."""
    fx, fy, fz = b.foot
    toe_key = toe_key or sole
    lace_key = lace_key or sole
    for s, sd in ((1, 'L'), (-1, 'R')):
        org = side_pt(T.ANKLE, s)
        mb = MB()
        rings = []
        for y, hw, top, bot in T.SHOE:
            zc = (top + bot) / 2
            rings.append([org + p for p in T.ring_pts(V(0, y, zc), V(1, 0, 0), V(0, 0, 1),
                                                       hw * wide, hw * wide, top - zc, zc - bot, 12, 2.5)])

        def key(i, k, c):
            c = c - org
            if c.y < -0.128 * fy and c.z < -0.030 * fz:
                return toe_key
            if abs(c.x) < 0.020 * fx and -0.065 * fy < c.y < -0.012 * fy and c.z > -0.022 * fz:
                return lace_key
            return upper
        T.loft(mb, rings, key, cap0=org + V(0, 0.072 * fy, -0.040 * fz), cap1=org + V(0, -0.154 * fy, -0.046 * fz),
               cap_keys=(upper, toe_key))
        zs = [(T.SOLE_Z, 0.94), (T.SOLE_Z + 0.002 * fz, 1.0), (T.SOLE_Z + 0.016 * fz, 1.0),
              (T.SOLE_Z + 0.020 * fz, 0.95)]
        rings = []
        for z, sc in zs:
            pts = []
            n = 14
            cy = (T.SOLE[0][0] + T.SOLE[-1][0]) / 2
            ry = (T.SOLE[0][0] - T.SOLE[-1][0]) / 2
            for k in range(n):
                th = TAU * k / n
                y = cy + ry * math.sin(th)
                hw = T.interp(sorted(T.SOLE), y) * wide
                x = hw * math.cos(th) / max(1e-3, abs(math.cos(th)) ** 0.35) * 0.98
                x = clamp(x, -hw, hw)
                pts.append(org + V(x * sc, cy + (y - cy) * sc, z))
            rings.append(pts)
        T.loft(mb, rings, lambda i, k, c: sole, cap0=org + V(0, -0.04 * fy, T.SOLE_Z - 0.001),
               cap1=org + V(0, -0.04 * fy, T.SOLE_Z + 0.021 * fz))
        o = T.to_object('n_shoe' + sd, mb)
        C.skin_rigid(o, 'foot.' + sd)
        parts.append(o)
        if boot > 0:
            mb = MB()
            kn = side_pt(T.KNEE, s)
            dsh = (kn - org).normalized()
            r0 = 0.050 * fx * wide
            pts = [org + V(0, 0.006 * fy, -0.012 * fz), org + dsh * boot * 0.5, org + dsh * boot]
            T.tube(mb, pts, [r0, r0 * 0.95, r0 * 0.98], boot_key or upper, n=12, cap0=False, cap1=not collar)
            if collar:
                c = org + dsh * boot
                T.tube(mb, [c - dsh * 0.012, c + dsh * collar * 0.5, c + dsh * collar],
                       [r0 * 1.06, r0 * 1.10, r0 * 1.02], collar_key or upper, n=12, cap0=False)
            o = T.to_object('n_boot' + sd, mb)
            C.skin_near(o, arm, ['shin.' + sd, 'foot.' + sd], power=4)
            parts.append(o)


# ===========================================================================
# Extra animations: point, think
# ===========================================================================

def breathe(p, t, period):
    b = T.sinw(t, period)
    p.root += V(0, 0, 0.002 * b - 0.003)
    p.add('spine', (-1.0 * b, 0, 0))
    p.add('chest', (-1.5 * b, 0, 0))
    p.add('neck', (0.8 * b, 0, 0))


def talk_mouth(t, env):
    flap = 0.5 + 0.5 * math.sin(TAU * 5.0 * t) * (0.7 + 0.3 * math.sin(TAU * 1.3 * t))
    m = env * (0.15 + 0.55 * flap)
    return (0.7 * m, 0.6 * m, m)


def a_point(t):
    """1.2 s: point forward (a bit to his right) with the right arm while
    talking, left hand on the hip; ends back at rest."""
    p = T.Pose()
    breathe(p, t, 1.2)
    up = trk(t, [(0, 0), (0.22, 1.06), (0.30, 1.0), (0.92, 1.0), (1.2, 0)])
    jab = trk(t, [(0, 0), (0.30, 0), (0.40, 1), (0.52, 0), (0.62, 0), (0.72, 1), (0.84, 0), (1.2, 0)])
    hip = trk(t, [(0, 0), (0.25, 1), (0.95, 1), (1.2, 0)])
    p.add('root', (0, 0, -6 * up))
    p.add('spine', (3 * up, 0, -4 * up))
    p.add('chest', (2 * up + 2 * jab, 2 * up, -6 * up))
    p.add('neck', (0, 0, -6 * up))
    p.add('head', (-4 * up + 3 * jab, 5 * up, -8 * up))
    p.mouth = talk_mouth(t, trk(t, [(0, 0.1), (0.2, 0.9), (0.95, 0.9), (1.1, 0), (1.2, 0)]))
    p.lid = [T.blink(t, 0.98)] * 2
    out, J = T.solve(p)
    Dc = J['D']['chest']
    sh = T.REST['upper_arm.R'][0]
    reach = (T.L_UP + T.L_FORE) * (0.86 + 0.06 * jab)
    d = V(-0.36, -1.0, 0.30).normalized()
    tgt_c = sh + d * reach
    rest = T.arm_rest(-1)[2] + V(0, -0.02, 0)
    p.hand['R'] = (Dc @ rest.lerp(tgt_c, min(up, 1.0)),
                   (Dc.to_3x3() @ V(-0.7, 0.3, -0.9)).normalized())
    p.r['hand.R'] = (lerp(0, -10, up), 0, lerp(0, 20, up))
    # left fist on the hip
    hp_ = T.RT(V(0.165, 0.0, 0.335))
    restL = T.arm_rest(1)[2]
    p.hand['L'] = (Dc @ restL.lerp(hp_, hip), (Dc.to_3x3() @ V(0.9, 0.6, 0.0)).normalized())
    p.r['hand.L'] = (lerp(0, 20, hip), 0, lerp(0, 60, hip))
    return p


def a_think(t):
    """1.6 s: hand to the chin, the other arm across the tummy, head tilted,
    eyes half closed, two little chin taps, then an 'aha' smile."""
    p = T.Pose()
    breathe(p, t, 1.6)
    k = trk(t, [(0, 0), (0.3, 1.0), (1.3, 1.0), (1.6, 0)])
    tap = trk(t, [(0, 0), (0.45, 0), (0.55, 1), (0.65, 0), (0.75, 1), (0.85, 0), (1.6, 0)])
    sway = math.sin(TAU * t / 1.6)
    p.root += V(0.008 * k * sway, 0, 0)
    p.add('root', (0, -2 * k, 0))
    p.add('spine', (-2 * k, 2 * k, 0))
    p.add('chest', (-1 * k, 2 * k, 4 * k))
    p.add('neck', (-4 * k, 0, 0))
    tilt = trk(t, [(0, 0), (0.35, 12), (1.1, 14), (1.3, 4), (1.6, 0)])
    p.add('head', (trk(t, [(0, 0), (0.35, -10), (1.1, -12), (1.3, 0), (1.6, 0)]), -tilt, 6 * k))
    lid = trk(t, [(0, 0), (0.3, 0.45), (1.1, 0.45), (1.2, 0), (1.6, 0)])
    p.lid = [lid, lid]
    aha = trk(t, [(0, 0), (1.12, 0), (1.22, 0.55), (1.42, 0.5), (1.6, 0)])
    p.mouth = (0.8 * aha, 0.6 * aha, aha)
    out, J = T.solve(p)
    Dc, Dh = J['D']['chest'], J['D']['head']
    chin = T.head_pt(0.0, -1.02, 0.0) + V(0, -0.045 * T.HX / 0.214, -0.035 * T.HX / 0.214)
    tgt = Dh @ (chin + V(0, 0, -0.012 * tap * T.HX / 0.214))
    rest = Dc @ (T.arm_rest(-1)[2] + V(0, -0.02, 0))
    p.hand['R'] = (rest.lerp(tgt, k), (Dc.to_3x3() @ V(-0.5, -0.2, -1.0)).normalized())
    p.r['hand.R'] = (lerp(0, -40, k), 0, lerp(0, 30, k))
    restL = Dc @ (T.arm_rest(1)[2] + V(0, -0.02, 0))
    acr = Dc @ T.RT(V(-0.035, -0.17, 0.40))
    p.hand['L'] = (restL.lerp(acr, k), (Dc.to_3x3() @ V(0.9, 0.3, -0.6)).normalized())
    p.r['hand.L'] = (lerp(0, 10, k), 0, lerp(0, -70, k))
    return p


EXTRA_ANIMS = [('point', 36, a_point), ('think', 48, a_think)]


# ===========================================================================
# Characters
# ===========================================================================

ADULT_GAITS = {   # same cycle lengths and speeds as Tommy (the game plays walk at speed/1.6)
    'walk': ((0.5, 1.6, 0.42, 0.10, 14, 22), dict(bob=0.014, base=-0.060, lean=3)),
    'run': ((0.4, 3.5, 0.24, 0.15, 6, 30), dict(bob=0.020, base=-0.070, lean=10, arm_amp=34, elbow=70)),
    'carry_walk': ((0.5, 1.6, 0.42, 0.09, 12, 20), dict(bob=0.012, base=-0.060, lean=1)),
}


# ---------------------------------------------------------------- Juampi

JUAMPI_COL = dict(skin='#eab48e', hair='#5b3a25', eye_white='#ffffff', pupil='#2b1d1a', mouth='#8c2f2b',
                  blush='#ff9a8a', cap='#f27a1a', cap_brim='#d55f0c', shirt='#3d9a4c',
                  shirt_stripe='#f2f5ee', overalls='#4c78bd', belt='#7b4a2a', metal='#b9c2cb',
                  shoes='#b0702f')
JUAMPI = Body(kH=1.14, kL=2.30, kT=1.75, kW=1.62, kHip=1.62, kD=1.55, kA=1.92, kHand=1.40, kR=1.50,
              foot=(1.42, 1.48, 1.30), low=1.25, gaits=ADULT_GAITS)


def juampi_hair(mb, ms):
    b = JUAMPI

    def hl(u):
        a = abs(u)
        v = T.interp([(0.0, 0.52), (0.6, 0.50), (1.0, 0.30), (1.25, 0.10), (1.38, -0.30), (1.50, -0.30),
                      (1.62, 0.05), (2.1, -0.20), (PI, -0.36)], a)
        return v - 0.06 * (0.5 + 0.5 * math.cos(14 * u)) * smoothstep(0.9, 0.3, a)

    hair_cap(mb, hl, lambda u, t: 0.006 + 0.008 * (1 - t) ** 0.8 * (1 + 0.3 * math.cos(14 * u)), NU=42,
             TS=(0.45, 0.72, 0.88, 1.0))
    # beard: chin + jaw up to the sideburns, a little moustache
    mv = T.MOUTH_V

    def lo(u):
        return -1.25 + 0.30 * smoothstep(0.0, 1.45, abs(u))

    def hi(u):
        a = abs(u)
        return T.interp([(0.0, mv - 0.12), (0.30, mv - 0.11), (0.55, mv - 0.09), (0.95, -0.30), (1.25, -0.30),
                         (1.40, -0.22), (1.48, -0.15)], a)

    head_band(mb, -1.48, 1.48, lo, hi,
              lambda u, s: (0.004 + 0.008 * math.sin(PI * min(1, s * 1.4)) ** 0.6) *
              (1 + 0.25 * math.cos(22 * u)) * (0.4 + 0.6 * smoothstep(1.48, 1.2, abs(u))),
              'hair', NU=24, NV=4)
    for s in (-1, 1):
        T.blob(mb, s * 0.105, mv + 0.075, 0.105, 0.036, 'hair',
               lambda rho: 0.004 + 0.007 * (1 - rho * rho), rot=s * 0.18, nr=2, na=14)
    # backwards cap: crown tipped forward (high on the forehead), bill at the back
    i0, i1 = len(ms.v), len(mb.v)
    Rc = RX(-12.0)
    T.crown(mb, Rc, 62.0, 'cap', n=28, rings=6, infl=T.CAP_INFL * b.kH)
    ax = (Rc @ V(0, 0, 1)).normalized()
    T.ellipsoid(ms, T.cap_pt(ax, T.CAP_INFL * b.kH), (0.021, 0.021, 0.011), 'cap', rot=T.frame_z(ax, V(1, 0, 0)),
                n=10, rings=5)
    T.bill(ms, Rc, 62.0, 56.0, 0.125 * b.kH, 32.0, 0.022, 0.013, 'cap_brim', 'cap_brim', fwd=90.0,
           infl=T.CAP_INFL * b.kH)
    head_space(ms, i0)
    head_space(mb, i1)
    # pencil behind his right ear
    u, v = -1.38, 0.12
    base = hp(u, v, 0.012)
    d = (V(0.0, 0.55, 0.85)).normalized()
    nrm = hn(u, v)
    d = (V(0.0, 0.8, 0.6)).normalized()
    p0 = base - d * 0.045 + nrm * 0.004
    p1 = base + d * 0.040
    T.tube(ms, [p0, p1], [0.0085, 0.0085], 'cap_brim', n=6, cap0=False, cap1=True, capr=0.3)
    tip = p0 - d * 0.026
    T.tube(ms, [p0, p0 - d * 0.018, tip], [0.0085, 0.004, 0.0012], 'skin', n=6, cap0=False, cap1=False)


def juampi_build(arm):
    b = JUAMPI
    parts = []
    head_parts(arm, parts, juampi_hair, face_kw=dict(nose=1.35, ear=1.0),
               brow_kw=dict(w=0.032, lift=0.07, length=0.32, arch=0.02, tilt=-0.03))
    neck(b, parts, arm, r=1.05)
    # checked shirt (green / white)
    mb = MB()
    prof = tommy_prof(b, T.SHIRT, belly=0.10, broad=0.06)
    zs = [zmap(b, z) for z in [0.325, 0.340, 0.36, 0.38, 0.40, 0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.538, 0.552]]
    torso_loft(mb, prof, zs, lambda i, k, c: 'shirt' if (i // 2 + k // 2) % 2 else 'shirt_stripe', n=32,
               cap0=V(0, 0, zmap(b, 0.327)), cap1=V(0, 0, zmap(b, 0.568)), cap_keys=('shirt', 'shirt'))
    bvh = bvh_of(mb)
    shirt = T.to_object('n_shirt', mb)
    C.skin_near(shirt, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(shirt)
    # overalls: pelvis, legs, bib + pocket, straps, buttons
    pv = pelvis(b, parts, 'overalls', wk=1.04, fk=1.06, bk=1.04)
    legs(b, parts, arm, 'overalls', r=0.88, cuff=True)
    mb = MB()
    zb0, zb1 = zmap(b, 0.335), zmap(b, 0.478)
    hw0, hw1 = 0.112 * b.kW, 0.092 * b.kW

    def bib(a, c):
        z = lerp(zb1, zb0, c)
        hw = lerp(hw1, hw0, c)
        return ((a - 0.5) * 2 * hw, z)
    patch(mb, bvh, bib, 8, 6, 0.006, 'overalls')

    def pocket(a, c):
        z = lerp(zmap(b, 0.452), zmap(b, 0.40), c)
        return ((a - 0.5) * 2 * 0.058 * b.kW, z)
    patch(mb, bvh, pocket, 4, 3, 0.011, 'overalls')
    for s in (-1, 1):
        # straps from the bib corners over the shoulders to the back
        x0 = s * (hw1 - 0.012 * b.kW)
        path = [V(x0, -0.2, zb1 - 0.01), V(s * 0.085 * b.kW, -0.06, zmap(b, 0.545)),
                V(s * 0.075 * b.kW, 0.03, zmap(b, 0.565)),
                V(s * 0.06 * b.kW, 0.15, zmap(b, 0.50)), V(s * 0.03 * b.kW, 0.2, zmap(b, 0.40)),
                V(0.0, 0.2, zmap(b, 0.34))]
        snap_strip(mb, bvh, path, 0.019 * b.kW, 0.006, 'overalls', n=5)
        bpt = bvh.ray_cast(V(x0, -0.9, zb1 - 0.022 * b.kT), V(0, 1, 0))[0]
        if bpt:
            T.ellipsoid(mb, bpt + V(0, -0.012, 0), (0.016, 0.009, 0.016), 'metal', n=10, rings=5)
    o = T.to_object('n_bib', mb, recalc=False, out_from=V(0, 0, zmap(b, 0.44)))
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    # tool belt: band round the hips, a pouch, hammer (his left), wrench (right)
    mb = MB()
    zbelt = zmap(b, 0.318)
    hw, fr, bk = T.interp_rows(tommy_prof(b, T.PELVIS, 1.04, 1.06, 1.04), zbelt)
    rings = [ring(zbelt + dz, hw * kk + 0.012, fr * kk + 0.012, bk * kk + 0.012, 24)
             for dz, kk in ((-0.026, 1.0), (-0.022, 1.04), (0.022, 1.04), (0.026, 1.0))]
    T.loft(mb, rings, lambda i, k, c: 'belt')
    for s in (-1, 1):
        # pouch on each hip
        cx = s * (hw + 0.03)
        T.ellipsoid(mb, V(cx, -0.03, zbelt - 0.05), (0.035, 0.055, 0.06), 'belt', n=7, rings=4)
    # hammer hangs from his left hip
    hx = hw + 0.055
    T.tube(mb, [V(hx, 0.035, zbelt + 0.02), V(hx, 0.035, zbelt - 0.17)], [0.012, 0.013], 'belt', n=6)
    T.ellipsoid(mb, V(hx, 0.035, zbelt + 0.035), (0.020, 0.055, 0.020), 'metal', n=8, rings=5)
    # wrench on his right hip
    wx = -(hw + 0.055)
    T.tube(mb, [V(wx, 0.04, zbelt + 0.0), V(wx, 0.04, zbelt - 0.15)], [0.010, 0.010], 'metal', n=6)
    jaw = [V(wx + 0.03 * math.cos(a), 0.04, zbelt - 0.17 + 0.03 * math.sin(a))
           for a in [math.radians(x) for x in range(-40, 230, 30)]]
    T.tube(mb, jaw, [0.010] * len(jaw), 'metal', n=6)
    o = T.to_object('n_belt', mb)
    C.skin_rigid(o, 'root')
    parts.append(o)
    arm_pieces(b, parts, arm, 'shirt', sleeve='roll', cuff_key='shirt_stripe',
               sleeve_fn=lambda i, k: 'shirt' if (i // 2 + k // 2) % 2 else 'shirt_stripe', skin_r=1.0,
               sleeve_r=1.0)
    shoe(b, parts, arm, upper='shoes', sole='belt', toe_key='belt', lace_key='belt', boot=0.075,
         collar=0.025, collar_key='belt')
    return parts


# ---------------------------------------------------------------- shared garment bits

def prof_tz(b, rows, kx=None, ky=None):
    """Rows (Tommy-space z, hw, front, back) -> body b (z through b.tz)."""
    kx = b.kW if kx is None else kx
    ky = b.kD if ky is None else ky
    return [(b.tz(z), hw * kx, fr * ky, bk * ky) for z, hw, fr, bk in rows]


def ang(c):
    """Angle of a point round the body axis: pi/2 = front centre."""
    return math.atan2(-c.y, c.x)


def lapels(mb, bvh, b, z_top, z_bot, x_top, w, off, key, s_list=(-1, 1), nb=8):
    """Two lapel bands along a V neckline from (+-x_top, z_top) to (0, z_bot)."""
    for s in s_list:
        def fn(a, c, s=s):
            z = lerp(z_top, z_bot, c)
            x = lerp(x_top, 0.004, c ** 0.9)
            return (s * (x + a * w * (1 - 0.5 * c)), z)
        patch(mb, bvh, fn, 2, nb, off, key)


def vpatch(mb, bvh, z_top, z_bot, x_top, off, key, nb=8):
    """A clean V (top down to a point) projected on the front."""
    def fn(a, c):
        z = lerp(z_top, z_bot, c)
        return ((a - 0.5) * 2 * x_top * (1 - c) ** 0.95, z)
    patch(mb, bvh, fn, 6, nb, off, key)


def button(mb, bvh, x, z, r, key, off=0.004, side=-1):
    hit = bvh.ray_cast(V(x, side * 0.9, z), V(0, -side, 0))
    if hit[0] is None:
        return
    n = hit[1] if hit[1].y * side > 0 else -hit[1]
    T.ellipsoid(mb, hit[0] + n * (off + r * 0.3), (r, r, r * 0.45), key, rot=T.frame_z(n, V(1, 0, 0)), n=7, rings=3)


# ---------------------------------------------------------------- Doctora Nat

NAT_COL = dict(skin='#a86f4c', hair='#6e4632', eye_white='#ffffff', pupil='#241614', mouth='#7c2a2c',
               blush='#e8786c', coat='#f5f7fa', shirt='#21b3a4', pants='#cdb27a', shoes='#8b5a34',
               shoe_sole='#4a3326', glasses='#5a2f3f', emblem='#f4ead2')
NAT = Body(kH=1.10, kL=2.15, kT=1.60, kW=1.36, kHip=1.45, kD=1.38, kA=1.80, kHand=1.25, kR=1.28,
           foot=(1.28, 1.36, 1.22), low=1.25, gaits=ADULT_GAITS)


def curl_bump(u, t, f=17.0):
    return (0.5 + 0.5 * math.cos(f * u + 5.0 * math.sin(7.0 * t))) * (0.6 + 0.4 * math.cos(9.0 * t + 2 * u))


def nat_hair(mb, ms):
    b = NAT
    k = b.kH

    def hl(u):
        a = abs(u)
        v = T.interp([(0.0, 0.66), (0.5, 0.62), (0.9, 0.40), (1.2, 0.22), (1.38, 0.14), (1.62, 0.16),
                      (2.2, -0.15), (PI, -0.40)], a)
        return v - 0.05 * (0.5 + 0.5 * math.cos(17 * u)) ** 1.5

    hair_cap(mb, hl, lambda u, t: (0.012 + 0.024 * (1 - t) ** 0.7) * (0.75 + 0.5 * curl_bump(u, t)) * k,
             NU=46, TS=(0.15, 0.38, 0.6, 0.78, 0.91, 1.0))
    # big puffy ponytail at the back of the crown
    anchor = hp(PI, 0.42, 0.02 * k)
    cen = anchor + V(0, 0.125, 0.02) * k
    puffs = [((0, 0, 0), (0.115, 0.105, 0.105)), ((0.06, -0.01, 0.055), (0.075, 0.07, 0.07)),
             ((-0.06, -0.01, 0.055), (0.075, 0.07, 0.07)), ((0.065, 0.02, -0.05), (0.075, 0.07, 0.07)),
             ((-0.065, 0.02, -0.05), (0.075, 0.07, 0.07)), ((0.0, 0.06, -0.075), (0.07, 0.065, 0.065)),
             ((0.0, 0.065, 0.035), (0.075, 0.07, 0.07))]
    for (dx, dy, dz), r in puffs:
        T.ellipsoid(ms, cen + V(dx, dy, dz) * k, tuple(x * k for x in r), 'hair', n=9, rings=5)
    # teal scrunchie
    nrm = (anchor - T.HEAD_C).normalized()
    tie_c = anchor + nrm * 0.012 * k + V(0, 0.022, 0) * k
    ax = (cen - anchor).normalized()
    pts, ns = [], []
    for i in range(14):
        a = TAU * i / 14
        x = ax.cross(V(1, 0, 0)).normalized()
        y = ax.cross(x)
        d = x * math.cos(a) + y * math.sin(a)
        pts.append(tie_c + d * 0.040 * k)
        ns.append(d)
    loop_tube(ms, pts, ns, 0.016 * k, 'shirt', n=5)
    # little dino-bone hair clip over her left temple
    u, v = 0.80, 0.55
    c = hp(u, v, 0.034 * k)
    n = hn(u, v)
    tg = (hp(u + 0.2, v + 0.12) - hp(u - 0.2, v - 0.12)).normalized()
    tg = (tg - n * tg.dot(n)).normalized()
    L = 0.042 * k
    T.tube(ms, [c - tg * L, c + tg * L], [0.0095 * k, 0.0095 * k], 'emblem', n=8, cap0=False, cap1=False)
    side = tg.cross(n).normalized()
    for e in (-1, 1):
        for q in (-1, 1):
            T.ellipsoid(ms, c + tg * e * L + side * q * 0.010 * k, (0.0125 * k,) * 3, 'emblem', n=8, rings=5)


def nat_glasses(mb):
    glasses(mb, 'glasses', ra=1.20, rb=1.13, off=0.022, r=0.0075)


NAT_COAT = [  # Tommy-space z, hw, front, back (then x kW, y kD)
    (0.222, 0.176, 0.146, 0.140), (0.250, 0.165, 0.132, 0.129), (0.290, 0.152, 0.117, 0.117),
    (0.330, 0.139, 0.106, 0.103), (0.370, 0.139, 0.112, 0.103), (0.420, 0.146, 0.123, 0.103),
    (0.465, 0.144, 0.117, 0.098), (0.500, 0.133, 0.101, 0.089), (0.528, 0.110, 0.082, 0.073),
    (0.552, 0.074, 0.060, 0.056)]


def nat_build(arm):
    b = NAT
    parts = []
    head_parts(arm, parts, nat_hair, extras_fn=nat_glasses, face_kw=dict(nose=1.15, blush=1.0),
               brow_kw=dict(w=0.022, lift=0.17, length=0.28, arch=0.04), girl=True)
    neck(b, parts, arm, r=0.92)
    # lab coat with a V neck showing the teal top
    mb = MB()
    prof = prof_tz(b, NAT_COAT)
    tzs = [0.246, 0.255, 0.270, 0.29, 0.33, 0.37, 0.40, 0.43, 0.46, 0.49, 0.505, 0.52, 0.535, 0.547]
    zv0, zv1 = b.tz(0.405), b.tz(0.552)

    zs0, zs1 = b.tz(0.232), b.tz(0.282)

    def vkey(i, k, c):
        return 'coat'
    torso_loft(mb, prof, [b.tz(z) for z in tzs], vkey, n=28, cap0=V(0, 0, b.tz(0.240)),
               cap1=V(0, 0, b.tz(0.562)), cap_keys=('coat', 'coat'))
    bvh = bvh_of(mb)
    coat = T.to_object('n_coat', mb)
    skin_skirt(coat, arm, b.root, b.tz(0.246), kmax=0.75)
    parts.append(coat)
    mb = MB()
    vpatch(mb, bvh, b.tz(0.546), zv0 - 0.01, 0.074 * b.kW, 0.003, 'shirt')
    lapels(mb, bvh, b, b.tz(0.552), zv0 - 0.012, 0.052 * b.kW, 0.030 * b.kW, 0.006, 'coat', nb=8)
    for z in (0.375, 0.335, 0.295):
        button(mb, bvh, 0.0, b.tz(z), 0.011, 'emblem', off=0.004)
    for s in (-1, 1):   # hip pockets
        def pk(a, c, s=s):
            return (s * lerp(0.050, 0.125, a) * b.kW, lerp(b.tz(0.325), b.tz(0.270), c))
        patch(mb, bvh, pk, 4, 3, 0.005, 'coat')
    # breast pocket (her left) + a pen
    def bp(a, c):
        return (lerp(0.055, 0.115, a) * b.kW, lerp(b.tz(0.455), b.tz(0.415), c))
    patch(mb, bvh, bp, 3, 2, 0.005, 'coat')
    hit = bvh.ray_cast(V(0.075 * b.kW, -0.9, b.tz(0.455)), V(0, 1, 0))[0]
    if hit:
        T.tube(mb, [hit + V(0, -0.006, -0.03), hit + V(0, -0.006, 0.035)], [0.0075, 0.0075], 'shirt', n=6)
    o = T.to_object('n_coat_bits', mb, recalc=False, out_from=V(0, 0, b.tz(0.38)))
    skin_skirt(o, arm, b.root, b.tz(0.246), kmax=0.75)
    parts.append(o)
    pelvis(b, parts, 'pants', wk=0.95, fk=0.95, bk=1.0)
    legs(b, parts, arm, 'pants', r=0.86, shorts=0.90, skin_r=0.88, cuff_key='pants')
    # cargo pockets on the outside of the shorts
    for s, sd in ((1, 'L'), (-1, 'R')):
        hip, kn = side_pt(T.HIP, s), side_pt(T.KNEE, s)
        c = hip + (kn - hip) * 0.74 + V(s * 0.062 * b.kR, 0, 0)
        mb = MB()
        T.ellipsoid(mb, c, (0.018, 0.045, 0.050), 'pants', n=7, rings=4)
        T.ellipsoid(mb, c + V(s * 0.006, 0, 0.040), (0.016, 0.048, 0.016), 'pants', n=7, rings=3)
        o = T.to_object('n_pocket' + sd, mb)
        C.skin_rigid(o, 'thigh.' + sd)
        parts.append(o)
    arm_pieces(b, parts, arm, 'coat', sleeve='long', cuff_key='coat', skin_r=0.88, sleeve_r=0.95)
    shoe(b, parts, arm, upper='shoes', sole='shoe_sole', toe_key='shoe_sole', lace_key='emblem', boot=0.06,
         collar=0.028, collar_key='emblem')
    return parts


# ---------------------------------------------------------------- Abuelo Juan

JUAN_COL = dict(skin='#f3c4a2', hair='#f2f0ea', eye_white='#ffffff', pupil='#2b1d1a', mouth='#8c2f2b',
                blush='#ff8a80', hat='#8b6a4b', coat='#e1a42c', shirt='#e8f0f7', pants='#7a5638',
                shoes='#8d3a40', shoe_sole='#f0e6d6', emblem='#6a4227')
JUAN_GAITS = {   # a shuffly grandpa walk; same lengths/speeds as Tommy
    'walk': ((0.5, 1.6, 0.46, 0.065, 9, 15), dict(bob=0.010, base=-0.045, lean=4, arm_amp=18, elbow=26)),
    'run': ((0.4, 3.5, 0.28, 0.10, 4, 22), dict(bob=0.015, base=-0.060, lean=9, arm_amp=26, elbow=60)),
    'carry_walk': ((0.5, 1.6, 0.46, 0.06, 8, 14), dict(bob=0.010, base=-0.045, lean=1)),
}
JUAN = Body(kH=1.12, kL=1.98, kT=1.74, kW=1.55, kHip=1.62, kD=1.70, kA=1.66, kHand=1.35, kR=1.42,
            foot=(1.36, 1.40, 1.15), low=1.2, gaits=JUAN_GAITS,
            posture={'spine': (6, 0, 0), 'chest': (9, 0, 0), 'neck': (-7, 0, 0), 'head': (-10, 0, 0)})


def flat_cap(mb, ms, k, infl, key='hat'):
    """Tweed flat cap (head space): a dome hugging the head, flattened on
    top, pulled forward into an overhang over a short brim."""
    Rc = RX(-4.0)
    edge = 57.0
    n, R = 30, 7
    zf = 0.62 * T.HZU

    def shape(p):
        x, y, z = p.x, p.y, p.z
        if z > zf:
            z = zf + (z - zf) * 0.45
        h = smoothstep(0.15 * T.HZU, 0.75 * T.HZU, p.z)
        if y < 0:
            y -= 0.050 * k * h * (-y / T.HY) ** 0.7
            z -= 0.018 * k * h * (-y / T.HY)
        x *= 1 + 0.07 * h
        y *= 1 + 0.04 * h
        return V(x, y, z)
    rows = []
    for i in range(1, R + 1):
        bb = math.radians(edge) * (i / R) ** 0.85
        rows.append([mb.vert(shape(T.cap_pt(T.cap_dir(Rc, TAU * j / n, bb), infl))) for j in range(n)])
    bb = math.radians(edge - 1.0)
    inner = []
    for j in range(n):
        d = T.cap_dir(Rc, TAU * j / n, bb)
        inner.append(mb.vert(T.cap_pt(d, infl) - d * 0.012))
    rows.append(inner)
    T.grid_faces(mb, rows, lambda i, kk, c: key)
    T.fan(mb, mb.vert(shape(T.cap_pt((Rc @ V(0, 0, 1)).normalized(), infl))), rows[0], key)
    T.bill(ms, Rc, edge, 52.0, 0.060 * k, 30.0, 0.008, 0.011, key, key, infl=infl)


def juan_hair(mb, ms):
    b = JUAN
    k = b.kH

    def wrap(u):
        a = abs(((u + PI) % TAU) - PI)
        return a

    def vlo(u):
        return T.interp([(0.9, 0.22), (1.25, 0.10), (1.5, 0.06), (1.8, -0.10), (2.4, -0.30), (PI, -0.34)], wrap(u))

    def vhi(u):
        return T.interp([(0.9, 0.36), (1.5, 0.42), (2.2, 0.48), (PI, 0.52)], wrap(u))

    head_band(mb, 0.92, TAU - 0.92, vlo, vhi,
              lambda u, s: (0.010 + 0.020 * math.sin(PI * min(1.0, s * 1.2)) ** 0.7)
              * (0.7 + 0.6 * curl_bump(u, s, 13.0)) * (0.6 + 0.4 * smoothstep(0.9, 1.4, wrap(u))) * k,
              'hair', NU=34, NV=4)
    # puffs over the ears
    for s in (-1, 1):
        for du, dv, r in ((1.35, 0.22, 0.040), (1.62, 0.12, 0.044), (1.9, 0.05, 0.038)):
            u, v = s * du, dv
            T.ellipsoid(ms, hp(u, v, 0.010 * k), (r * k, r * k * 0.85, r * k * 0.8), 'hair',
                        rot=T.frame_z(hn(u, v), V(0, 0, 1)), n=8, rings=5)
    # bushy moustache
    mv = T.MOUTH_V
    for s in (-1, 1):
        for du, dv, r, tw in ((0.085, 0.065, (0.072, 0.034, 0.032), 0.22), (0.20, 0.025, (0.058, 0.028, 0.026), 0.62)):
            u, v = s * du, mv + dv
            n = hn(u, v)
            rot = T.frame_z(n, V(math.cos(tw) * s, 0, -math.sin(tw)))
            T.ellipsoid(ms, hp(u, v, 0.008 * k), tuple(x * k for x in r), 'hair', rot=rot, n=12, rings=6)
    i0, i1 = len(ms.v), len(mb.v)
    flat_cap(mb, ms, k, 0.020 * k)
    head_space(ms, i0)
    head_space(mb, i1)


JUAN_CARD = [  # Tommy-space z, hw, front, back
    (0.262, 0.146, 0.104, 0.110), (0.285, 0.149, 0.112, 0.110), (0.320, 0.150, 0.124, 0.108),
    (0.365, 0.152, 0.134, 0.107), (0.410, 0.150, 0.130, 0.104), (0.450, 0.146, 0.118, 0.100),
    (0.485, 0.138, 0.104, 0.093), (0.515, 0.124, 0.092, 0.084), (0.540, 0.102, 0.076, 0.069),
    (0.560, 0.070, 0.056, 0.052)]


def juan_build(arm):
    b = JUAN
    parts = []
    head_parts(arm, parts, juan_hair, face_kw=dict(nose=1.5, blush=1.25, blush_v=-0.10),
               brow_kw=dict(w=0.040, lift=0.13, length=0.34, arch=0.03, tilt=0.0))
    neck(b, parts, arm, r=1.0)
    mb = MB()
    prof = prof_tz(b, JUAN_CARD)
    tzs = [0.262, 0.270, 0.280, 0.292, 0.31, 0.33, 0.355, 0.38, 0.405, 0.43, 0.455, 0.48, 0.50, 0.518, 0.535,
           0.550]
    zv0, zv1 = b.tz(0.415), b.tz(0.562)
    zr = b.tz(0.292)

    def key(i, kk, c):
        return 'coat'

    def mod(z, th):   # knitted ribbing on the hem band
        return 1.0 + (0.022 if z < zr else 0.0) * (0.5 + 0.5 * math.cos(18 * th))
    torso_loft(mb, prof, [b.tz(z) for z in tzs], key, n=36, mod=mod, cap0=V(0, 0, b.tz(0.255)),
               cap1=V(0, 0, b.tz(0.568)), cap_keys=('coat', 'coat'))
    bvh = bvh_of(mb)
    o = T.to_object('n_cardigan', mb)
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    mb = MB()
    vpatch(mb, bvh, b.tz(0.546), zv0 - 0.01, 0.066 * b.kW, 0.003, 'shirt')
    lapels(mb, bvh, b, b.tz(0.556), zv0 - 0.012, 0.044 * b.kW, 0.026 * b.kW, 0.006, 'coat', nb=8)
    neck_collar(mb, b.tz(0.553), 0.050 * b.kR * 1.0 + 0.004, 0.013, 'shirt')
    for z in (0.392, 0.352, 0.312, 0.274):
        button(mb, bvh, 0.0, b.tz(z), 0.014, 'emblem', off=0.006)
    for s in (-1, 1):
        def pk(a, c, s=s):
            return (s * lerp(0.055, 0.125, a) * b.kW, lerp(b.tz(0.345), b.tz(0.290), c))
        patch(mb, bvh, pk, 4, 3, 0.006, 'coat')
    o = T.to_object('n_card_bits', mb, recalc=False, out_from=V(0, 0, b.tz(0.40)))
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    pelvis(b, parts, 'pants', wk=1.0, fk=1.0, bk=1.0)
    legs(b, parts, arm, 'pants', r=0.95, cuff=True)
    arm_pieces(b, parts, arm, 'coat', sleeve='long', cuff_key='coat', skin_r=0.95, sleeve_r=1.0)
    shoe(b, parts, arm, upper='shoes', sole='shoe_sole', toe_key='shoes', lace_key='shoes', wide=1.06)
    return parts


# ---------------------------------------------------------------- the visiting kids (Tommy's body)

KID = Body()


def neck_collar(mb, z, r, rr, key, n=12):
    pts = [V(r * math.cos(TAU * i / n), 0.004 + r * math.sin(TAU * i / n), z) for i in range(n)]
    nrms = [V(math.cos(TAU * i / n), math.sin(TAU * i / n), 0) for i in range(n)]
    loop_tube(mb, pts, nrms, rr, key, n=5)


# kid A: pigtails, yellow raincoat, rain boots

KID_A_COL = dict(skin='#ffd9bf', hair='#c4602a', eye_white='#ffffff', pupil='#2b1d1a', mouth='#8c2f2b',
                 blush='#ff8f8f', coat='#ffd02e', pants='#36427e', shoes='#2f9be0', shoe_sole='#f4f6f8',
                 emblem='#ff5d8f')


def kid_a_hair(mb, ms):
    def hl(u):
        a = abs(u)
        v = T.interp([(0.0, 0.40), (0.55, 0.38), (0.85, 0.30), (1.10, 0.12), (1.30, 0.06), (1.62, 0.10),
                      (2.2, -0.18), (PI, -0.34)], a)
        if a < 0.95:
            v -= 0.05 * (0.5 + 0.5 * math.cos(16 * u)) ** 2 * smoothstep(0.95, 0.6, a)
        return v
    hair_cap(mb, hl, lambda u, t: 0.008 + 0.012 * (1 - t) ** 0.8, NU=46, TS=(0.18, 0.45, 0.7, 0.88, 1.0))
    # centre parting line? (a soft dip) - pigtails high on each side
    for s in (-1, 1):
        u, v = s * 1.62, 0.42
        base = hp(u, v, 0.010)
        out = (hn(u, v) + V(0, 0.25, 0.15)).normalized()
        T.ellipsoid(ms, base + out * 0.008, (0.024, 0.024, 0.024), 'emblem', n=8, rings=5)
        ctrl = [base + out * 0.015, base + out * 0.05 + V(0, 0.01, 0.005), base + out * 0.09 + V(0, 0.03, -0.04),
                base + out * 0.105 + V(0, 0.04, -0.10), base + out * 0.095 + V(0, 0.03, -0.15)]
        T.limb(ms, ctrl, [0.022, 0.040, 0.046, 0.036, 0.012], 'hair', per=2, n=10)
    # freckles
    for s in (-1, 1):
        for du, dv in ((0.52, -0.02), (0.62, 0.02), (0.70, -0.05), (0.58, -0.08)):
            T.blob(mb, s * du, dv - 0.05, 0.018, 0.018, 'hair', 0.0035, nr=1, na=6)


KID_A_COAT = [  # Tommy space: A-line raincoat to mid thigh
    (0.205, 0.172, 0.140, 0.140), (0.232, 0.166, 0.132, 0.132), (0.270, 0.158, 0.124, 0.122),
    (0.320, 0.152, 0.120, 0.112), (0.365, 0.155, 0.126, 0.110), (0.405, 0.154, 0.124, 0.108),
    (0.445, 0.149, 0.117, 0.102), (0.485, 0.141, 0.107, 0.095), (0.515, 0.129, 0.096, 0.087),
    (0.540, 0.107, 0.080, 0.072), (0.560, 0.074, 0.058, 0.054)]


def kid_a_build(arm):
    b = KID
    parts = []
    head_parts(arm, parts, kid_a_hair, girl=True, brow_kw=dict(w=0.022, lift=0.13))
    neck(b, parts, arm)
    mb = MB()
    tzs = [0.205, 0.215, 0.235, 0.26, 0.29, 0.32, 0.35, 0.38, 0.41, 0.44, 0.47, 0.50, 0.52, 0.538, 0.552]
    torso_loft(mb, KID_A_COAT, tzs, lambda i, k, c: 'coat', n=30, cap0=V(0, 0, 0.198), cap1=V(0, 0, 0.566))
    bvh = bvh_of(mb)
    o = T.to_object('n_coat', mb)
    skin_skirt(o, arm, 0.31, 0.205)
    parts.append(o)
    mb = MB()
    # front placket + toggles, pocket flaps, collar, hood down at the back
    patch(mb, bvh, lambda a, c: ((a - 0.5) * 0.030, lerp(0.545, 0.215, c)), 2, 10, 0.004, 'coat')
    for z in (0.49, 0.43, 0.37, 0.31, 0.25):
        button(mb, bvh, 0.0, z, 0.0105, 'emblem', off=0.006)
    for s in (-1, 1):
        patch(mb, bvh, lambda a, c, s=s: (s * lerp(0.045, 0.115, a), lerp(0.300, 0.282, c)), 4, 1, 0.006, 'coat')
        patch(mb, bvh, lambda a, c, s=s: (s * lerp(0.05, 0.110, a), lerp(0.283, 0.232, c)), 4, 2, 0.003, 'coat')
    neck_collar(mb, 0.553, 0.058, 0.016, 'coat')
    T.ellipsoid(mb, V(0, 0.095, 0.515), (0.105, 0.045, 0.060), 'coat', rot=RX(-20), n=10, rings=5)
    o = T.to_object('n_coat_bits', mb)
    skin_skirt(o, arm, 0.31, 0.205)
    parts.append(o)
    pelvis(b, parts, 'pants')
    legs(b, parts, arm, 'pants', r=0.9, cuff=False)
    arm_pieces(b, parts, arm, 'coat', sleeve='long', cuff_key='coat', sleeve_r=1.0)
    shoe(b, parts, arm, upper='shoes', sole='shoe_sole', toe_key='shoes', lace_key='shoes', boot=0.085,
         collar=0.022, collar_key='shoes', wide=1.04)
    return parts


# kid B: glasses, dino hoodie with the hood up

KID_B_COL = dict(skin='#8a573a', hair='#2a1d18', eye_white='#ffffff', pupil='#241614', mouth='#6e2224',
                 blush='#d9746a', coat='#5bbf5c', shirt='#d6f2a4', emblem='#ff9a3c', glasses='#d8433b',
                 pants='#8d99b3', shoes='#f3f3f3', shoe_sole='#ff9a3c')
HOOD = 0.034


def kid_b_hood_line(u):
    a = abs(u)
    return T.interp([(0.0, 0.74), (0.55, 0.68), (1.0, 0.42), (1.28, 0.0), (1.40, -0.45), (1.7, -0.70),
                     (PI, -0.62)], a)


def kid_b_hair(mb, ms):
    # fringe peeking out under the hood
    head_band(mb, -0.85, 0.85, lambda u: 0.44 - 0.06 * (0.5 + 0.5 * math.cos(14 * u)) ** 2,
              lambda u: kid_b_hood_line(u) + 0.08,
              lambda u, s: 0.010 + 0.006 * s, 'hair', NU=12, NV=2)
    # the hood: a thick shell over the head round the face
    hair_cap(mb, kid_b_hood_line, lambda u, t: HOOD * (1 - 0.25 * smoothstep(0.85, 1.0, t)), key='coat', NU=36,
             TS=(0.2, 0.45, 0.7, 0.88, 1.0), tuck=0.03)
    # rolled rim round the face
    pts, ns = [], []
    m = 30
    for i in range(m):
        u = -PI + TAU * i / m
        v = kid_b_hood_line(u)
        pts.append(hp(u, v + 0.01, HOOD * 0.62))
        ns.append(hn(u, v))
    loop_tube(ms, pts, ns, 0.013, 'coat', n=5)
    # spikes along the top and down the back
    for i, (u, v, h) in enumerate([(0, 0.95, 0.040), (0, 1.25, 0.055), (PI, 1.30, 0.062), (PI, 0.95, 0.058),
                                    (PI, 0.60, 0.050), (PI, 0.25, 0.040)]):
        p = hp(u, v, HOOD - 0.006)
        n = hn(u, v)
        T.tube(ms, [p - n * 0.006, p + n * h * 0.45, p + n * h], [0.024 + h * 0.15, 0.014 + h * 0.08, 0.002],
               'emblem', n=6, cap0=False, cap1=False)
    # dino eyes on the hood
    for s in (-1, 1):
        u, v = s * 0.36, 0.98
        p = hp(u, v, HOOD)
        n = hn(u, v)
        T.ellipsoid(ms, p, (0.034, 0.034, 0.022), 'eye_white', rot=T.frame_z(n, V(1, 0, 0)), n=9, rings=4)
        T.ellipsoid(ms, p + n * 0.016 + V(0, -0.004, 0), (0.016, 0.016, 0.010), 'pupil',
                    rot=T.frame_z(n, V(1, 0, 0)), n=7, rings=3)
    # little blunt teeth along the front rim
    for u in (-0.42, -0.21, 0.0, 0.21, 0.42):
        v = kid_b_hood_line(u)
        p = hp(u, v + 0.012, HOOD * 0.62)
        n = hn(u, v)
        T.tube(ms, [p, p - V(0, 0, 0.022) + n * 0.004], [0.010, 0.002], 'eye_white', n=6, cap0=True, cap1=False)


def kid_b_glasses(mb):
    glasses(mb, 'glasses', ra=1.17, rb=1.10, off=0.020, r=0.0080)


def kid_b_build(arm):
    b = KID
    parts = []
    head_parts(arm, parts, kid_b_hair, extras_fn=kid_b_glasses, face_kw=dict(ears=False),
               brow_kw=dict(w=0.024, lift=0.09))
    neck(b, parts, arm)
    mb = MB()
    prof = [(z, hw * 1.04, fr * 1.04, bk * 1.04) for z, hw, fr, bk in T.SHIRT]
    prof = [(0.285, 0.146, 0.116, 0.104), (0.300, 0.150, 0.120, 0.106)] + prof
    zs = [0.285, 0.292, 0.305, 0.325, 0.35, 0.38, 0.41, 0.44, 0.47, 0.50, 0.52, 0.538, 0.552]

    def mod(z, th):
        return 1.0 + (0.025 if z < 0.30 else 0.0) * (0.5 + 0.5 * math.cos(15 * th))
    torso_loft(mb, prof, zs, lambda i, k, c: 'coat', n=26, mod=mod, cap0=V(0, 0, 0.280), cap1=V(0, 0, 0.568))
    bvh = bvh_of(mb)
    o = T.to_object('n_hoodie', mb)
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    mb = MB()

    def belly(a, c):
        th = PI * (a - 0.5) * 0.92
        z = lerp(0.505, 0.312, c)
        w = 0.085 * math.sqrt(max(0.0, 1 - ((z - 0.40) / 0.11) ** 2)) + 0.02
        return (math.sin(th) * w * 1.1, z)
    patch(mb, bvh, belly, 5, 6, 0.003, 'shirt')
    # kangaroo pocket
    patch(mb, bvh, lambda a, c: ((a - 0.5) * 2 * lerp(0.070, 0.095, c), lerp(0.372, 0.312, c)), 4, 3, 0.007, 'coat')
    neck_collar(mb, 0.556, 0.056, 0.012, 'coat')
    # dino tail with spikes
    tail = [V(0, 0.085, 0.330), V(0, 0.150, 0.310), V(0, 0.210, 0.280), V(0, 0.250, 0.250)]
    T.limb(mb, tail, [0.050, 0.040, 0.026, 0.008], 'coat', per=3, n=8, cap0=False)
    for p, h in ((V(0, 0.13, 0.36), 0.034), (V(0, 0.185, 0.330), 0.028), (V(0, 0.228, 0.296), 0.020)):
        n = (p - V(0, 0.13, 0.26)).normalized()
        T.tube(mb, [p - n * 0.004, p + n * h], [0.016, 0.002], 'emblem', n=6, cap0=True, cap1=False)
    o = T.to_object('n_hoodie_bits', mb)
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    pelvis(b, parts, 'pants')
    legs(b, parts, arm, 'pants', r=0.95, cuff=True)
    arm_pieces(b, parts, arm, 'coat', sleeve='long', cuff_key='coat', sleeve_r=0.98)
    shoe(b, parts, arm, upper='shoes', sole='shoe_sole', toe_key='shoe_sole', lace_key='emblem')
    return parts


# kid C: sun hat, overalls, bob

KID_C_COL = dict(skin='#d39a6e', hair='#4a2c1c', eye_white='#ffffff', pupil='#2b1d1a', mouth='#8c2f2b',
                 blush='#ff8a80', hat='#f2d38b', hat_band='#e05c7c', shirt='#9fe3c8', overalls='#e05c7c',
                 emblem='#ffd23a', shoes='#8a63d8', shoe_sole='#fbfbfb')


def sun_hat(mb, ms, infl, brim=0.085):
    Rc = RX(-16.0)
    edge = 62.0
    j0 = len(mb.fk)
    T.crown(mb, Rc, edge, 'hat', n=26, rings=5, infl=infl)
    remap(mb, j0, {'cap_brim': 'hat'})
    n = 26
    b = math.radians(edge - 1.0)
    band = [T.cap_pt(T.cap_dir(Rc, TAU * i / n, b), infl) for i in range(n)]
    ax = (Rc @ V(0, 0, 1)).normalized()
    rows_t, rows_b = [], []
    for f, drop in ((0.0, 0.0), (0.4, 0.008), (1.0, 0.030)):
        rt, rb = [], []
        for p in band:
            h = p - ax * p.dot(ax)
            h = h.normalized()
            q = p + h * brim * f - ax * drop
            rt.append(ms.vert(q + ax * 0.005))
            rb.append(ms.vert(q - ax * 0.005))
        rows_t.append(rt)
        rows_b.append(rb)
    T.grid_faces(ms, rows_t, lambda i, k, c: 'hat')
    T.grid_faces(ms, list(reversed(rows_b)), lambda i, k, c: 'hat')
    T.grid_faces(ms, [rows_t[-1], rows_b[-1]], lambda i, k, c: 'hat')
    T.grid_faces(ms, [rows_b[0], rows_t[0]], lambda i, k, c: 'hat')     # closed slab
    # ribbon round the crown + a flower
    pts, ns = [], []
    b2 = math.radians(edge - 7.0)
    for i in range(n):
        d = T.cap_dir(Rc, TAU * i / n, b2)
        pts.append(T.cap_pt(d, infl) + d * 0.004)
        ns.append(d)
    loop_tube(ms, pts, ns, 0.013, 'hat_band', n=5)
    d = T.cap_dir(Rc, math.radians(-25), b2)
    c = T.cap_pt(d, infl) + d * 0.020
    for i in range(5):
        a = TAU * i / 5
        t1 = d.cross(V(0, 0, 1)).normalized()
        t2 = d.cross(t1)
        T.ellipsoid(ms, c + (t1 * math.cos(a) + t2 * math.sin(a)) * 0.020, (0.014, 0.014, 0.008), 'emblem',
                    rot=T.frame_z(d, t1), n=8, rings=4)
    T.ellipsoid(ms, c + d * 0.004, (0.010, 0.010, 0.008), 'hat_band', rot=T.frame_z(d, V(1, 0, 0)), n=8, rings=4)


def kid_c_hair(mb, ms):
    def hl(u):
        a = abs(u)
        v = T.interp([(0.0, 0.40), (0.6, 0.38), (0.92, 0.22), (1.15, -0.25), (1.6, -0.48), (2.4, -0.50),
                      (PI, -0.48)], a)
        return v
    hair_cap(mb, hl, lambda u, t: 0.008 + 0.016 * t ** 1.5 * smoothstep(0.9, 1.4, abs(u)) + 0.008 * (1 - t),
             NU=52, TS=(0.3, 0.55, 0.75, 0.88, 0.96, 1.0))
    i0, i1 = len(ms.v), len(mb.v)
    sun_hat(mb, ms, 0.030)
    head_space(ms, i0)
    head_space(mb, i1)


def kid_c_build(arm):
    b = KID
    parts = []
    head_parts(arm, parts, kid_c_hair, girl=True, face_kw=dict(ears=False), brow_kw=dict(w=0.022, lift=0.12))
    neck(b, parts, arm)
    mb = MB()
    torso_loft(mb, T.SHIRT, T.SHIRT_Z, lambda i, k, c: 'shirt', n=30, cap0=V(0, 0, 0.327), cap1=V(0, 0, 0.568))
    bvh = bvh_of(mb)
    o = T.to_object('n_shirt', mb)
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    mb = MB()
    zb0, zb1 = 0.335, 0.470
    patch(mb, bvh, lambda a, c: ((a - 0.5) * 2 * lerp(0.075, 0.090, c), lerp(zb1, zb0, c)), 6, 5, 0.005,
          'overalls')

    def heart(a, c):
        th = TAU * a
        x = 16 * math.sin(th) ** 3
        y = 13 * math.cos(th) - 5 * math.cos(2 * th) - 2 * math.cos(3 * th) - math.cos(4 * th)
        return (x * 0.0016 * (1 - c * 0.999), 0.414 + y * 0.0016 * (1 - c * 0.999))
    patch(mb, bvh, heart, 16, 1, 0.009, 'emblem')
    for s in (-1, 1):
        x0 = s * 0.064
        path = [V(x0, -0.2, zb1 - 0.008), V(s * 0.072, -0.06, 0.545), V(s * 0.068, 0.03, 0.565),
                V(s * 0.055, 0.15, 0.50), V(s * 0.03, 0.2, 0.40), V(0.0, 0.2, 0.335)]
        snap_strip(mb, bvh, path, 0.014, 0.005, 'overalls', n=5)
        button(mb, bvh, x0, zb1 - 0.014, 0.010, 'emblem', off=0.008)
    o = T.to_object('n_bib', mb, recalc=False, out_from=V(0, 0, 0.42))
    C.skin_near(o, arm, ['root', 'spine', 'chest'], power=3)
    parts.append(o)
    pelvis(b, parts, 'overalls')
    legs(b, parts, arm, 'overalls', cuff=True, cuff_r=1.16)
    arm_pieces(b, parts, arm, 'shirt', sleeve='short', cuff_key='shirt')
    shoe(b, parts, arm, upper='shoes', sole='shoe_sole', toe_key='shoe_sole', lace_key='shoe_sole')
    return parts


# ===========================================================================
# Build
# ===========================================================================

NPCS = {
    'nat': (NAT, NAT_COL, nat_build),
    'juampi': (JUAMPI, JUAMPI_COL, juampi_build),
    'juan': (JUAN, JUAN_COL, juan_build),
    'kid_a': (KID, KID_A_COL, kid_a_build),
    'kid_b': (KID, KID_B_COL, kid_b_build),
    'kid_c': (KID, KID_C_COL, kid_c_build),
}


def min_z(arm, body, act, frames):
    tr = arm.animation_data.nla_tracks
    for t in tr:
        t.mute = True
    arm.animation_data.action = act
    deps = bpy.context.evaluated_depsgraph_get()
    lo = 1e9
    for f in range(0, frames + 1, max(1, frames // 6)):
        bpy.context.scene.frame_set(f)
        ev = body.evaluated_get(deps)
        me = ev.to_mesh()
        lo = min(lo, min(v.co.z for v in me.vertices))
        ev.to_mesh_clear()
    arm.animation_data.action = None
    for t in tr:
        t.mute = False
    bpy.context.scene.frame_set(0)
    return lo


def settle(arm, body, name, frames, fn, attr, rest=0.002):
    """Shift tommy.<attr> (SIT_ROOT / SLEEP_ROOT) so the lowest point of
    the deformed mesh in that loop rests on the ground."""
    for _ in range(2):
        T.bake(arm, '_tmp', frames, fn)
        act = bpy.data.actions['_tmp']
        lo = min_z(arm, body, act, frames)
        tr = arm.animation_data.nla_tracks
        tr.remove(tr[-1])
        bpy.data.actions.remove(act)
        v = getattr(T, attr)
        setattr(T, attr, v + V(0, 0, rest - lo))
        if abs(lo - rest) < 0.002:
            break
    print('[npc] %s settled: %s z %+.3f' % (name, attr, getattr(T, attr).z))


def build(nid):
    body_spec, cols, fn = NPCS[nid]
    C.reset()
    C._mats.clear()
    T.MATS.clear()
    for k, c in cols.items():
        T.MATS[k] = C.mat(k, c, rough=0.6)
    apply_body(body_spec)
    T.REST.clear()
    T.PARENT.clear()
    arm = C.armature('npc_%s_rig' % nid, [(n, tuple(h), tuple(t), par) for n, h, t, par in T.bone_list()])
    T.read_rest(arm)
    parts = fn(arm)
    if A.get('parts'):
        print('[parts]', ', '.join('%s %d' % (o.name, T.tri_count(o)) for o in parts))
    body = C.bind('npc_' + nid, arm, parts)
    T.BODY[:] = [body]
    zs = [(body.matrix_world @ v.co).z for v in body.data.vertices]
    print('[npc] %s triangles %d, materials %d (%s), height %.3f m' % (
        nid, T.tri_count(body), len(body.data.materials), ', '.join(m.name for m in body.data.materials),
        max(zs)))
    # sit / sleep resting on the ground (a coat hem may sink 1 cm)
    settle(arm, body, 'sit', 90, T.a_sit, 'SIT_ROOT', rest=-0.008)
    settle(arm, body, 'sleep', 120, T.a_sleep, 'SLEEP_ROOT')
    only = A.get('anims')
    for name, frames, f in T.ANIMS + EXTRA_ANIMS:
        if only and name not in only.split(','):
            continue
        T.bake(arm, name, frames, f)
    T.quaternion_actions(arm)    # keep constant held poses (sit, sleep) in the glb
    path = os.path.join(OUT, 'npc_%s.glb' % nid)
    T.export_small(path, [arm, body])
    print('[npc] %s %.0f KB' % (nid, os.path.getsize(path) / 1024))


for nid in A.get('only', ','.join(NPCS)).split(','):
    build(nid)
