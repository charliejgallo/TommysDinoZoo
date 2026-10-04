"""props_habitats_a.py - habitat props for Tommy's Dino Zoo (set A):
the tall forest ("Bosque alto"), the lagoon ("Laguna") and the rex valley
("Valle Rex").

    cd art/blender
    Blender -b -P props_habitats_a.py -- [--only prop_log,prop_dock] [--out DIR]
    Blender -b -P props_habitats_a.py -- --list

Writes game/assets/models/<name>.glb and prints triangles and bounds. Same
conventions as props.py (docs/ART-SPEC.md): metres, origin = centre of the
footprint on the ground, front = -Y in Blender (+Z in Godot), 1 m grid
footprints (listed next to each definition; tree crowns may overhang),
shared material roles from props_lib.PAL plus a few specifics (HPAL).

Named sub-objects (separate nodes the game can animate; their origin is
the centre of their own bounds):
  prop_volcano    `smoke`  white puffs over the crater (bob / scale it)
  prop_hot_spring `steam`  steam puffs over the water
Water surfaces: prop_lilypads has its origin at the water surface (the pads
float on z = 0); prop_dock's deck top is 0.25 m above its origin and its
posts reach 0.8 m below it, for water sunk under the ground level.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import props_lib as L  # noqa: E402
import tdz_common as C  # noqa: E402

# specific materials of this set (sRGB hex); everything else is props_lib.PAL
HPAL = {
    'lava': ('#ff8a2e', {'emit': 1.6}),
    'bone': '#f8ecd0',
    'driftwood': '#dfcfb6',
    'starfish': '#ff8f6b',
    'cattail': '#9a5f3e',
}


def M(role):
    """Material of a role: this set's specifics first, then the shared PAL."""
    if role in HPAL:
        v = HPAL[role]
        if isinstance(v, tuple):
            return C.mat(role, v[0], **v[1])
        return C.mat(role, v)
    return L.M(role)


DEFS = {}


def define(name, footprint=None, budget=3000):
    def deco(fn):
        DEFS[name] = dict(fn=fn, footprint=footprint, budget=budget)
        return fn
    return deco


# =================================================================== helpers


def ring_lathe(name, material, prof, seg=24, rfun=None, loc=(0, 0, 0),
               rot=(0, 0, 0)):
    """Revolve a CLOSED (r, z) profile (all r > 0) around Z: a thick-walled
    tube / ring (hollow logs, rims). `rfun(theta, z)` scales the radius."""
    bm = bmesh.new()
    rings = []
    for (r, z) in prof:
        ring = []
        for k in range(seg):
            th = 2 * math.pi * k / seg
            rr = r * (rfun(th, z) if rfun else 1.0)
            ring.append(bm.verts.new((rr * math.cos(th), rr * math.sin(th), z)))
        rings.append(ring)
    n = len(rings)
    for i in range(n):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(seg):
            bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = L._bm_obj(bm, name, material)
    return L.place(ob, loc, rot)


def tube(name, material, pts, radii, seg=16, cap=True, flatten=None, sub=2,
         cap_steps=3):
    """tdz_common.tube with fewer Catmull-Rom sub-steps per span (`sub`) and
    cap rings (`cap_steps`): same look on short props, far fewer triangles."""
    P = [Vector(p) for p in pts]
    R = list(radii)
    F = list(flatten) if flatten else [(1.0, 1.0)] * len(P)
    dp, dr, df = [], [], []
    for i in range(len(P) - 1):
        p0 = P[max(i - 1, 0)]
        p1, p2 = P[i], P[i + 1]
        p3 = P[min(i + 2, len(P) - 1)]
        for s in range(sub):
            t = s / sub
            t2, t3 = t * t, t * t * t
            dp.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                             (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                             (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
            dr.append(R[i] + (R[i + 1] - R[i]) * t)
            df.append(tuple(F[i][k] + (F[i + 1][k] - F[i][k]) * t
                            for k in range(2)))
    dp.append(P[-1])
    dr.append(R[-1])
    df.append(F[-1])
    bm = bmesh.new()
    rings = []
    up_ref = Vector((0, 0, 1))
    for i, p in enumerate(dp):
        if i == 0:
            t = (dp[1] - dp[0]).normalized()
        elif i == len(dp) - 1:
            t = (dp[-1] - dp[-2]).normalized()
        else:
            t = (dp[i + 1] - dp[i - 1]).normalized()
        ref = up_ref if abs(t.dot(up_ref)) < 0.95 else Vector((1, 0, 0))
        side = t.cross(ref).normalized()
        up = side.cross(t).normalized()
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            ring.append(bm.verts.new(p + side * math.cos(a) * dr[i] * df[i][0] +
                                     up * math.sin(a) * dr[i] * df[i][1]))
        rings.append((ring, p, t, side, up, dr[i], df[i]))
    for i in range(len(rings) - 1):
        a, b = rings[i][0], rings[i + 1][0]
        for k in range(seg):
            bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
    if cap:
        for end, sign in ((rings[0], -1), (rings[-1], 1)):
            ring, p, t, side, up, r, f = end
            prev = ring
            for s in range(1, cap_steps):
                ang = (math.pi / 2) * s / cap_steps
                cr, ca = math.cos(ang), math.sin(ang)
                cur = []
                for k in range(seg):
                    a = 2 * math.pi * k / seg
                    off = (side * math.cos(a) * r * f[0] +
                           up * math.sin(a) * r * f[1]) * cr + t * sign * r * ca
                    cur.append(bm.verts.new(p + off))
                for k in range(seg):
                    q = (prev[k], prev[(k + 1) % seg], cur[(k + 1) % seg],
                         cur[k])
                    bm.faces.new(q if sign > 0 else q[::-1])
                prev = cur
            tipv = bm.verts.new(p + t * sign * r)
            for k in range(seg):
                tri = (prev[k], prev[(k + 1) % seg], tipv)
                bm.faces.new(tri if sign > 0 else tri[::-1])
    else:
        for end in (rings[0][0], rings[-1][0]):
            bm.faces.new(end)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return L._bm_obj(bm, name, material)


def decals(target, material, dirs, r, center, aspect=(1.0, 1.0), lift=0.004):
    """Flat discs on `target` in directions `dirs` from `center` (spots)."""
    bpy.context.view_layer.update()
    out = []
    c = Vector(center)
    for i, d in enumerate(dirs):
        d = Vector(d).normalized()
        rr = r[i] if isinstance(r, (list, tuple)) else r
        out.append(C.decal_on('%s_sp%d' % (target.name, i), material, target,
                              c + d * 0.3, d, rr, aspect=aspect, lift=lift,
                              seg=12))
    return out


def mushroom(name, x, y, h, R, rot=(0, 0), z=0.0):
    """Cute spotted mushroom (same as props.py's) standing at (x, y, z)."""
    rs = R * 0.38
    stem = L.lathe(name + '_stem', M('white'),
                   L.round_corners([(0, 0), (rs * 1.2, 0), (rs, h * 0.5),
                                    (rs * 0.85, h), (0, h)], 0.02), seg=10)
    prof = [(0, h - 0.015), (R * 0.7, h - 0.01), (R, h + 0.015)]
    for k in range(1, 7):
        a = math.pi / 2 * k / 6
        prof.append((R * math.cos(a), h + 0.015 + R * 0.75 * math.sin(a)))
    cap = L.lathe(name + '_cap', M('shroom'), prof, seg=16)
    for o in (stem, cap):
        o.location = (x, y, z)
        o.rotation_euler = (math.radians(rot[0]), math.radians(rot[1]), 0)
    bpy.context.view_layer.update()
    ctr = Vector((x, y, z + h + 0.015))
    dirs = [(0, 0, 1), (0.7, -0.4, 0.6), (-0.7, -0.35, 0.6), (0.1, -0.85, 0.5),
            (-0.4, 0.7, 0.6)]
    return [stem, cap] + decals(cap, M('white'), dirs, R * 0.2, ctr)


def trunk(h, r0, r1, lean=(0.0, 0.0), roots=3, seed=1, mat='bark', seg=12,
          root_len=1.7):
    """Tree trunk with flared roots (props.py's _trunk, more knobs)."""
    rng = random.Random(seed)
    lx, ly = lean
    pts = [(0, 0, -0.05), (lx * 0.2, ly * 0.2, h * 0.3),
           (lx * 0.7, ly * 0.7, h * 0.7), (lx, ly, h)]
    objs = [tube('trunk', M(mat), pts, [r0, r0 * 0.85, r1 * 1.05, r1],
                   seg=seg, cap=False)]
    for i in range(roots):
        a = 2 * math.pi * i / roots + rng.uniform(-0.3, 0.3)
        objs.append(tube('root%d' % i, M(mat),
                           [(0, 0, r0 * 1.25), (math.cos(a) * r0 * 1.2,
                                                math.sin(a) * r0 * 1.2, 0.06),
                            (math.cos(a) * r0 * root_len,
                             math.sin(a) * r0 * root_len, 0.0)],
                           [r0 * 0.55, r0 * 0.38, r0 * 0.2], seg=7,
                           cap=False))
    return objs


def tuft(name, base, n, h, seed, mat='grass', spread=0.09, w=0.05):
    """Little grass tuft of ribbons (like prop_grass_tuft) at `base`."""
    rng = random.Random(seed)
    b = Vector(base)
    out = []
    for i in range(n):
        a = 2 * math.pi * i * 0.382 + rng.uniform(-0.2, 0.2)
        d = Vector((math.cos(a), math.sin(a), 0))
        hh = rng.uniform(0.55, 1.0) * h
        o = rng.uniform(0.5, 1.0) * spread
        pts = [b + d * 0.01 - Vector((0, 0, 0.01)),
               b + d * o * 0.25 + Vector((0, 0, hh * 0.4)),
               b + d * o * 0.6 + Vector((0, 0, hh * 0.75)),
               b + d * o + Vector((0, 0, hh))]
        side = Vector((-d.y, d.x, 0))
        out.append(L.ribbon('%s%d' % (name, i), M(mat), pts,
                            [w, w * 0.9, w * 0.6, 0.0], side=side))
    return out


def puff(name, mat, center, size, seed, n=4, subdiv=2):
    """Soft cartoon cloud puff: a few overlapping round blobs."""
    rng = random.Random(seed)
    c = Vector(center)
    out = [L.ico(name + '_c', mat, c, (size, size, size * 0.85),
                 subdiv=subdiv)]
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.4, 0.4)
        d = Vector((math.cos(a), math.sin(a) * 0.7, rng.uniform(-0.25, 0.35)))
        r = size * rng.uniform(0.55, 0.75)
        out.append(L.ico('%s_%d' % (name, i), mat, c + d * size * 0.8,
                         (r, r, r * 0.9), subdiv=subdiv))
    return out


def star_pts(r_out, r_in, n=5, k=6, rot=90.0):
    """Rounded star outline in (x, z) (starfish, sparkles)."""
    pts = []
    m = n * k * 2
    for i in range(m):
        th = 2 * math.pi * i / m + math.radians(rot)
        s = abs(math.cos(n * (th - math.radians(rot)) / 2)) ** 1.6
        r = r_in + (r_out - r_in) * s
        pts.append((r * math.cos(th), r * math.sin(th)))
    return pts


# =================================================================== FOREST


@define('prop_tree_tall', footprint=(1, 1), budget=4000)
def tree_tall():
    """Tall prehistoric conifer (~6 m): straight trunk and five layered
    umbrella tiers whose rims are round-tipped branch lobes, shrinking up to
    a pom-pom top (alternating teal greens so the layers read)."""
    objs = trunk(5.3, 0.27, 0.09, roots=4, seed=2, root_len=1.75)
    tiers = [(1.9, 1.5, 9), (2.65, 1.28, 8), (3.35, 1.05, 7), (4.0, 0.82, 6),
             (4.6, 0.58, 5)]
    for t, (z, R, n) in enumerate(tiers):
        th = 0.2 + 0.07 * R
        prof = [(0, z + 0.3 * R ** 0.5), (R * 0.5, z + 0.19 * R),
                (R * 0.86, z + 0.01), (R, z - th * 0.55), (R * 0.9, z - th * 1.1),
                (R * 0.45, z - th * 0.8), (0, z - th * 0.6)]
        k = n
        ph = t * 0.6
        objs.append(L.lathe('tier%d' % t, M('fern_dark' if t % 2 else 'fern'),
                            prof, seg=n * 6,
                            rfun=lambda a, zz, k=k, ph=ph:
                            0.78 + 0.22 * abs(math.cos(k * (a + ph) / 2)) ** 0.6))
        if t < 3:   # a few branch arms under the lower tiers
            for i in range(3):
                a = 2 * math.pi * i / 3 + t
                objs.append(tube('br%d_%d' % (t, i), M('bark'),
                                 [(0, 0, z - 0.35),
                                  (R * 0.35 * math.cos(a), R * 0.35 * math.sin(a),
                                   z - 0.2),
                                  (R * 0.6 * math.cos(a), R * 0.6 * math.sin(a),
                                   z - 0.12)],
                                 [0.07, 0.05, 0.035], seg=6, cap=False))
    objs.append(L.lumpy('top', M('fern'), (0, 0, 5.12), (0.34, 0.34, 0.42),
                        subdiv=3, amp=0.04, seed=9))
    return objs


@define('prop_tree_giant', footprint=(1, 1), budget=5000)
def tree_giant():
    """Huge broad leafy tree (~7 m): thick flared trunk forking into big
    limbs, a wide round crown whose underside sits ~3.9 m up (brachio
    height) and a few leaf clusters hanging from it."""
    objs = trunk(2.6, 0.42, 0.3, lean=(0.04, 0.0), roots=5, seed=6,
                 root_len=1.15, seg=14)
    for i, (a, l, z1) in enumerate(((0.3, 1.25, 4.4), (2.4, 1.1, 4.6),
                                    (4.3, 1.0, 4.3))):
        d = Vector((math.cos(a), math.sin(a), 0))
        objs.append(tube('limb%d' % i, M('bark'),
                           [tuple(Vector((0.04, 0, 2.3))),
                            tuple(Vector((0.04, 0, 2.9)) + d * l * 0.4),
                            tuple(Vector((0, 0, z1)) + d * l)],
                           [0.27, 0.2, 0.12], seg=9, cap=False))
    crown = L.canopy('crown', M('leaf'), (0.0, 0.0, 5.25), (2.4, 2.2, 1.5),
                     n=9, blob=(0.48, 0.6), seed=5, lower_mat=M('leaf_dark'),
                     lower_z=-0.05, lump=0.07, spread=0.8, subdiv=3,
                     core_subdiv=2)
    objs += crown
    # hanging leaf clusters (vine + two drops), on the sides the camera sees
    for i, (a, rr) in enumerate(((-1.95, 2.05), (-1.05, 2.15), (-0.2, 2.0),
                                 (-2.75, 1.9))):
        d = Vector((math.cos(a), math.sin(a), 0))
        top = Vector((0, 0, 4.1)) + d * rr
        bot = top + Vector((0, 0, -0.95 - 0.2 * (i % 2))) + d * 0.1
        objs.append(tube('vine%d' % i, M('plant_stem'),
                           [tuple(top), tuple((top + bot) / 2 + d * 0.05),
                            tuple(bot)], [0.035, 0.03, 0.025], seg=5,
                           cap=False))
        side = Vector((-d.y, d.x, 0))
        for j, (f, r) in enumerate(((0.45, 0.2), (0.75, 0.17), (1.0, 0.15))):
            p = top.lerp(bot, f) + side * (0.07 if j % 2 else -0.07)
            objs.append(L.lumpy('drop%d_%d' % (i, j),
                                M('leaf' if j % 2 == 0 else 'leaf_dark'), p,
                                (r, r, r * 1.15), subdiv=2, amp=0.12,
                                freq=2.0, seed=i * 3 + j))
    return objs


@define('prop_giant_fern', footprint=(1, 1))
def giant_fern():
    """Giant fern clump (~2 m): a stubby fibrous stump, tall arching fronds,
    a ring of small fronds at the foot and two fiddleheads."""
    rng = random.Random(23)
    objs = [L.lathe('stump', M('bark'), L.round_corners(
        [(0, -0.02), (0.26, -0.02), (0.2, 0.12), (0.17, 0.34), (0.2, 0.42),
         (0, 0.44)], [0, 0.06, 0.05, 0.04, 0.05, 0], n=2), seg=12,
        rfun=lambda th, z: 1 + 0.08 * math.sin(7 * th + z * 14))]
    n = 8
    for i in range(n):
        phi = 2 * math.pi * i / n + rng.uniform(-0.15, 0.15)
        inner = i % 2 == 0
        objs.append(L.frond(
            'fr%d' % i, M('fern' if inner else 'fern_dark'), (0, 0, 0.4), phi,
            rng.uniform(1.25, 1.4) if inner else rng.uniform(1.15, 1.25),
            rng.uniform(3.2, 3.5) if inner else rng.uniform(2.3, 2.6),
            rng.uniform(2.3, 2.5) if inner else rng.uniform(2.0, 2.2),
            0.27, teeth=7, comb=0.5, fold=0.3, thick=0.016))
    for i in range(4):
        phi = 2 * math.pi * (i + 0.5) / 4 + rng.uniform(-0.2, 0.2)
        objs.append(L.frond('sm%d' % i, M('fern_dark'), (0, 0, 0.05), phi,
                            rng.uniform(0.55, 0.65), 1.3, 1.25, 0.12, teeth=4,
                            comb=0.5, fold=0.3, thick=0.01))
    for k, phi in enumerate((0.9, 3.6)):
        d = Vector((math.cos(phi), math.sin(phi), 0))
        pts, rad = [], []
        H = 0.85 - 0.2 * k
        for j in range(8):
            s = j / 7
            if s < 0.5:
                p = d * 0.06 + Vector((0, 0, 0.4 + H * s / 0.5))
            else:
                u = (s - 0.5) / 0.5
                ang = u * 1.6 * math.pi
                R = 0.13 * (1 - 0.6 * u)
                p = d * 0.06 + Vector((0, 0, 0.4 + H)) + \
                    d * (R * math.sin(ang)) + Vector((0, 0, R * (1 - math.cos(ang))))
            pts.append(tuple(p))
            rad.append(0.035 * (1 - 0.45 * s))
        objs.append(tube('fid%d' % k, M('fern'), pts, rad, seg=5))
    return objs


@define('prop_log', footprint=(2, 1))
def log():
    """Fallen hollow log (2x1) lying along X: bark outside, pale cut ends
    with a growth ring, dark hollow, moss on top, a mushroom and a sprout."""
    Ro, Ri, H = 0.33, 0.21, 0.8
    prof = L.round_corners([(Ri, -H), (Ro, -H), (Ro, H), (Ri, H)], 0.06, n=3,
                           closed=True)
    lg = ring_lathe('log', M('bark'), prof, seg=22,
                    rfun=lambda th, z: 1 + 0.035 * math.sin(6 * th + z * 2.0) +
                    0.025 * math.sin(3 * z + th))
    mid = (Ri + Ro) / 2

    def rule(c, n):
        if abs(c.z) > H - 0.015 and abs(n.z) > 0.5:
            return 1                                   # cut end
        if math.hypot(c.x, c.y) < mid:
            return 2                                   # hollow inside
        return 0
    L.paint_faces(lg, [M('bark'), M('wood'), M('wood_dark')], rule)
    lg.rotation_euler = (0, math.radians(90), 0)
    lg.location = (0, 0, Ro - 0.03)
    objs = [lg]
    for s in (-1, 1):
        objs.append(L.torus('ring%d' % s, M('wood_dark'), (s * (H + 0.004), 0,
                                                           Ro - 0.03),
                            mid + 0.005, 0.012, seg=22, rseg=4, rot=(0, 90, 0),
                            squash=0.5))
    bpy.context.view_layer.update()
    moss = L.shell_cap(lg, 'moss', M('moss'),
                       lambda co, n: n.z > 0.35 and co.z + 0.05 * math.sin(co.x * 7)
                       + 0.03 * math.cos(co.x * 13) > Ro + 0.13, offset=0.014)
    objs.append(moss)
    # a stubby broken branch
    objs.append(tube('stub', M('bark'), [(0.25, -0.1, 0.45), (0.38, -0.2, 0.62),
                                           (0.42, -0.22, 0.72)],
                       [0.08, 0.06, 0.055], seg=8))
    objs.append(L.lathe('stubend', M('wood'), [(0, 0), (0.05, 0), (0, 0.012)],
                        seg=8, loc=(0.42, -0.22, 0.765), rot=(-20, 20, 0)))
    objs += mushroom('m0', -0.42, -0.1, 0.17, 0.12, rot=(-8, -6),
                     z=Ro * 2 - 0.1)
    objs += mushroom('m1', -0.3, -0.2, 0.1, 0.075, rot=(-14, 10),
                     z=Ro * 2 - 0.16)
    # a sprout with two round leaves
    objs.append(tube('sprout', M('plant_stem'), [(0.08, 0.02, 0.6),
                                                   (0.08, 0.0, 0.72),
                                                   (0.1, -0.02, 0.8)],
                       [0.014, 0.012, 0.01], seg=5))
    for s in (-1, 1):
        lf = L.lathe('spl%d' % s, M('leaf'), [(0, -0.006), (0.055, 0.0),
                                              (0.03, 0.01), (0, 0.012)], seg=10,
                     scale=(1.6, 1, 1))
        L.place(lf, (0.1 + s * 0.07, -0.02, 0.8), (0, -s * 25, 0), (1.6, 1, 1))
        objs.append(lf)
    objs += tuft('gr', (0.7, -0.33, 0), 6, 0.2, 3)
    return objs


@define('prop_stump', footprint=(1, 1))
def stump():
    """Tree stump: flared bark sides with roots, pale top with growth
    rings, a tiny sprout."""
    Ht = 0.5
    prof = L.round_corners([(0, -0.02), (0.46, -0.02), (0.4, 0.08),
                            (0.35, 0.22), (0.34, Ht - 0.04), (0.32, Ht),
                            (0, Ht)], [0, 0.04, 0.06, 0.06, 0.03, 0.02, 0],
                           n=2)
    st = L.lathe('stump', M('bark'), prof, seg=26,
                 rfun=lambda th, z: 1 + 0.045 * abs(math.sin(5 * th)) -
                 0.02 * math.sin(11 * th + 1))
    L.paint_faces(st, [M('bark'), M('wood')],
                  lambda c, n: 1 if n.z > 0.8 and c.z > Ht - 0.03 else 0)
    objs = [st]
    for i, r in enumerate((0.09, 0.17, 0.24)):
        objs.append(L.torus('gring%d' % i, M('wood_dark'), (0.0, 0, Ht + 0.002),
                            r, 0.011, seg=24, rseg=4, squash=0.4,
                            rfun=lambda th: 1.0))
    objs.append(L.sphere('pith', M('wood_dark'), (0.0, 0, Ht + 0.003), 0.025,
                         seg=8, rings=4, squash=(1, 1, 0.3)))
    rng = random.Random(4)
    for i in range(4):
        a = 2 * math.pi * i / 4 + 0.5 + rng.uniform(-0.2, 0.2)
        d = Vector((math.cos(a), math.sin(a), 0))
        objs.append(tube('root%d' % i, M('bark'),
                           [tuple(d * 0.25 + Vector((0, 0, 0.18))),
                            tuple(d * 0.42 + Vector((0, 0, 0.06))),
                            tuple(d * 0.52 + Vector((0, 0, 0.0)))],
                           [0.1, 0.07, 0.04], seg=7))
    # a cheeky sprout on the side
    objs.append(tube('sprout', M('plant_stem'), [(0.3, -0.16, 0.36),
                                                   (0.36, -0.2, 0.44),
                                                   (0.36, -0.22, 0.52)],
                       [0.014, 0.012, 0.01], seg=5))
    for s in (-1, 1):
        lf = L.lathe('spl%d' % s, M('leaf'), [(0, -0.006), (0.05, 0.0),
                                              (0.03, 0.01), (0, 0.012)], seg=10)
        L.place(lf, (0.36 + s * 0.065, -0.22, 0.52), (0, -s * 25, 0),
                (1.6, 1, 1))
        objs.append(lf)
    objs += tuft('gr', (-0.38, -0.3, 0), 6, 0.18, 5)
    return objs


@define('prop_cycad', footprint=(1, 1))
def cycad():
    """Stubby prehistoric cycad (~1.6 m): a fat scaly pineapple trunk, a
    crown of stiff arching fronds and an orange seed cone in the middle."""
    Ht = 0.72
    prof = L.round_corners([(0, -0.02), (0.3, -0.02), (0.33, 0.15),
                            (0.3, 0.45), (0.23, Ht), (0, Ht + 0.03)],
                           [0, 0.05, 0.1, 0.1, 0.06, 0], n=2)

    objs = [L.lathe('trunk', M('bark'), prof, seg=14)]
    # overlapping scale rings: lobed tori, each turned half a lobe
    for i in range(4):
        z = 0.11 + i * 0.165
        r = 0.27 - 0.05 * max(0, i - 1) - 0.02 * (i == 0)
        ph = (i % 2) * math.pi / 7
        objs.append(L.torus('scale%d' % i, M('wood_dark' if i % 2 else 'bark'),
                            (0, 0, z), r, 0.085, seg=28, rseg=4, squash=0.95,
                            rfun=lambda th, ph=ph: 0.75 + 0.35 * abs(
                                math.cos(3.5 * (th + ph))) ** 0.7))
    rng = random.Random(12)
    n = 8
    for i in range(n):
        phi = 2 * math.pi * i / n + rng.uniform(-0.1, 0.1)
        up = i % 2 == 0
        objs.append(L.frond('fr%d' % i, M('leaf_dark' if up else 'leaf'),
                            (0, 0, Ht - 0.02), phi,
                            rng.uniform(0.95, 1.05) if up else rng.uniform(0.85, 0.95),
                            rng.uniform(2.0, 2.2) if up else 1.25,
                            rng.uniform(1.4, 1.5) if up else 1.25,
                            0.17, teeth=6, comb=0.7, fold=0.35,
                            thick=0.012))
    objs.append(L.lathe('cone', M('pumpkin'), L.round_corners(
        [(0, Ht - 0.04), (0.11, Ht), (0.12, Ht + 0.12), (0.07, Ht + 0.24),
         (0, Ht + 0.27)], [0, 0.03, 0.05, 0.04, 0], n=2), seg=12,
        rfun=lambda th, z: 1 + 0.08 * abs(math.sin(3 * th + z * 30))))
    return objs


@define('prop_moss_rock', footprint=(2, 2))
def moss_rock():
    """Big mossy boulder (2x2) with a mossy pebble, a fern sprout and a
    tiny mushroom."""
    r = L.lumpy('rock', M('stone'), (0, 0.04, 0.5), (0.95, 0.84, 0.6),
                subdiv=4, amp=0.16, freq=1.5, seed=7, flat_bottom=-0.48)
    moss = L.shell_cap(r, 'moss', M('moss'),
                       lambda co, n: co.z + 0.1 * math.sin(co.x * 5) +
                       0.08 * math.cos(co.y * 6 + 1) > 0.8 and n.z > 0.35,
                       offset=0.016)
    p = L.lumpy('peb', M('stone'), (0.72, -0.55, 0.16), (0.27, 0.23, 0.2),
                subdiv=3, amp=0.1, seed=3, flat_bottom=-0.15)
    pm = L.shell_cap(p, 'pmoss', M('moss'),
                     lambda co, n: co.z > 0.24 and n.z > 0.3, offset=0.01)
    p2 = L.lumpy('peb2', M('stone_dark'), (-0.78, -0.48, 0.07), (0.13, 0.11, 0.1),
                 subdiv=2, amp=0.1, seed=4, flat_bottom=-0.06)
    objs = [r, moss, p, pm, p2]
    rng = random.Random(3)
    for i in range(3):
        phi = 2 * math.pi * i / 3 + rng.uniform(-0.2, 0.2) + 0.4
        objs.append(L.frond('fr%d' % i, M('fern'), (-0.72, -0.2, 0.02), phi,
                            0.36, 1.7, 1.6, 0.08, teeth=4, comb=0.5, fold=0.3,
                            thick=0.008))
    objs += mushroom('mu', 0.4, -0.72, 0.14, 0.09, rot=(-6, 8))
    return objs


# =================================================================== LAGOON


@define('prop_reeds', footprint=(1, 1))
def reeds():
    """Cattail / reed clump: tall bent blades and five brown cattails
    (where players harvest water plants)."""
    rng = random.Random(9)
    objs = []
    n = 16
    for i in range(n):
        a = 2 * math.pi * i * 0.382 + rng.uniform(-0.2, 0.2)
        d = Vector((math.cos(a), math.sin(a), 0))
        b = d * rng.uniform(0.03, 0.2)
        h = rng.uniform(0.7, 1.25)
        lean = rng.uniform(0.12, 0.35) * (1.4 if i % 4 == 0 else 1.0)
        pts = [b - Vector((0, 0, 0.02)), b + d * lean * 0.08 + Vector((0, 0, h * 0.35)),
               b + d * lean * 0.3 + Vector((0, 0, h * 0.7)),
               b + d * lean * 0.65 + Vector((0, 0, h * 0.92)),
               b + d * lean + Vector((0, 0, h * (0.95 if i % 4 else 0.8)))]
        side = Vector((-d.y, d.x, 0))
        w = rng.uniform(0.065, 0.085)
        objs.append(L.ribbon('bl%d' % i, M(('leaf', 'grass', 'leaf_dark')[i % 3]),
                             pts, [w, w, w * 0.85, w * 0.55, 0.0], side=side))
    for i, (x, y, h) in enumerate(((0.02, 0.05, 1.45), (-0.14, -0.02, 1.2),
                                   (0.15, -0.08, 1.3), (-0.04, -0.16, 1.05),
                                   (0.1, 0.16, 1.15))):
        lx, ly = x * 0.6, y * 0.6
        top = Vector((x + lx, y + ly, h))
        objs.append(tube('st%d' % i, M('plant_stem'),
                           [(x, y, -0.02), (x + lx * 0.3, y + ly * 0.3, h * 0.5),
                            tuple(top)], [0.018, 0.016, 0.013], seg=5,
                           cap=False))
        d = (top - Vector((x + lx * 0.3, y + ly * 0.3, h * 0.5))).normalized()
        head = tube('ct%d' % i, M('cattail'),
                      [tuple(top - d * 0.2), tuple(top - d * 0.1), tuple(top)],
                      [0.048, 0.052, 0.048], seg=10)
        objs.append(head)
        objs.append(tube('sp%d' % i, M('plant_stem'),
                           [tuple(top), tuple(top + d * 0.13)], [0.01, 0.006],
                           seg=4))
    return objs


@define('prop_lilypads', footprint=(1, 1), budget=1000)
def lilypads():
    """Four lily pads and a pink lotus, floating; origin at the water
    surface (the pads' undersides sit just below z = 0)."""
    def pad(name, mat, r, loc, ang):
        notch = 28
        pts = [(0.0, 0.0)]
        a0, a1 = notch / 2, 360 - notch / 2
        for k in range(12):
            a = math.radians(a0 + (a1 - a0) * k / 11)
            pts.append((r * math.cos(a), r * math.sin(a)))
        ob = L.extrude(name, M(mat), pts, 0.03, bevel=0.012, seg=1)
        ob.rotation_euler = (math.radians(90), 0, 0)
        L.transform_objs([ob], loc=loc, rot=(0, 0, ang))
        return ob
    objs = [pad('p0', 'leaf', 0.3, (-0.12, 0.1, 0.008), 200),
            pad('p1', 'leaf_dark', 0.22, (0.27, 0.2, 0.006), -30),
            pad('p2', 'leaf', 0.2, (0.22, -0.26, 0.007), 70),
            pad('p3', 'leaf_dark', 0.16, (-0.3, -0.27, 0.005), 140)]
    # vein lines on the biggest pad
    for i, a in enumerate((150, 200, 250)):
        d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
        c = Vector((-0.12, 0.1, 0.024))
        objs.append(L.plank('vein%d' % i, M('leaf_dark'), c + d * 0.05,
                            c + d * 0.23, 0.012, 0.004, bevel=0.0, seg=1))
    # lotus on the big pad: two rings of pointed petals tilted up
    c = Vector((-0.1, 0.08, 0.03))
    for j, (n, ln, tilt, m, ofs) in enumerate(((6, 0.135, 28, 'petal_pink', 0.0),
                                               (5, 0.1, 55, 'paint_pink', 0.5))):
        for i in range(n):
            a = 360.0 * (i + ofs) / n
            pt = C.ellipsoid('pet%d_%d' % (j, i), M(m), (0, ln * 0.5, 0),
                             (ln * 0.36, ln * 0.55, 0.016), seg=6, rings=4)
            L.transform_objs([pt], rot=(tilt, 0, 0))
            L.transform_objs([pt], loc=tuple(c), rot=(0, 0, a))
            objs.append(pt)
    objs.append(L.sphere('ctr', M('flower_center'), c + Vector((0, 0, 0.035)),
                         0.035, seg=8, rings=5, squash=(1, 1, 0.6)))
    # closed bud on the second pad
    objs.append(L.lathe('bud', M('petal_pink'), L.round_corners(
        [(0, 0.0), (0.045, 0.02), (0.05, 0.07), (0, 0.14)], [0, 0.02, 0.02, 0],
        n=1), seg=10, loc=(0.27, 0.2, 0.02), rot=(-10, 8, 0),
        rfun=lambda th, z: 0.85 + 0.15 * abs(math.cos(2.5 * th))))
    return objs


@define('prop_dock', footprint=(2, 4))
def dock():
    """Small wooden pier (2x4) running along Y: from the shore (+Y) out over
    the water toward the front (-Y). Deck top at z = 0.25; posts reach
    z = -0.8. A lantern post and a life ring at the water end."""
    W, Ytop, Ybot = 1.5, 1.95, -1.95
    T = 0.06
    zt = 0.25
    objs = []
    rng = random.Random(3)
    n = 16
    step = (Ytop - Ybot) / n
    for i in range(n):
        y = Ybot + step * (i + 0.5)
        ww = W + rng.uniform(-0.06, 0.06)
        dx = rng.uniform(-0.03, 0.03)
        objs.append(L.rbox('pl%d' % i, M('wood' if i % 5 else 'wood_dark'),
                           (dx, y, zt - T / 2), (ww, step - 0.035, T),
                           rot=(0, 0, rng.uniform(-1.2, 1.2)), bevel=0.018,
                           seg=1))
    for x in (-0.55, 0.55):
        objs.append(L.rbox('beam', M('wood_dark'), (x, 0, zt - T - 0.06),
                           (0.12, Ytop - Ybot + 0.05, 0.12), bevel=0.03, seg=1))
    for i, y in enumerate((-1.85, -0.6, 0.65, 1.85)):
        hh = 0.24 if i == 0 else 0.12
        for x in (-0.8, 0.8):
            objs.append(L.post('post', M('wood_dark'), (x, y, -0.8),
                               0.8 + zt + hh, 0.09, seg=8, top=0.6))
        objs.append(L.rbox('cross', M('wood_dark'), (0, y, zt - T - 0.14),
                           (1.7, 0.08, 0.09), bevel=0.025, seg=1))
    # rope between the front posts (sagging) on both sides
    for x in (-0.8, 0.8):
        objs.append(tube('rope', M('straw_dark'),
                           L.arc((x, -1.85, zt + 0.3), (x, -0.6, zt + 0.25),
                                 -0.1, n=5), [0.018] * 5, seg=4))
    # life ring hanging on the right front post
    ring = L.torus('lifering', M('white'), (0, 0, 0), 0.17, 0.055, seg=20,
                   rseg=8)
    L.paint_faces(ring, [M('white'), M('paint_red')],
                  lambda c, nrm: int(((math.atan2(c.y, c.x) + math.pi) /
                                      (math.pi / 2)) % 2))
    ring.rotation_euler = (math.radians(90), 0, math.radians(90))
    ring.location = (0.9, -1.2, zt + 0.12)
    objs.append(ring)
    # little lantern post at the water end (left)
    lx, ly = -0.8, -1.85
    objs.append(tube('lpole', M('paint_green'), [(lx, ly, zt + 0.3),
                                                   (lx, ly, zt + 1.35)],
                       [0.035, 0.03], seg=8, cap=False))
    objs.append(tube('arm', M('paint_green'),
                       L.arc((lx, ly, zt + 1.3), (lx + 0.28, ly, zt + 1.3),
                             0.08, n=5), [0.022] * 5, seg=6))
    hx = lx + 0.28
    objs.append(L.lathe('lcap', M('paint_green'), L.round_corners(
        [(0, 1.1), (0.1, 1.1), (0.09, 1.14), (0.03, 1.2), (0, 1.21)],
        [0, 0.02, 0.03, 0.02, 0], n=2), seg=12, loc=(hx, ly, zt)))
    objs.append(L.sphere('bulb', M('bulb'), (hx, ly, zt + 1.02), 0.085, seg=12,
                         rings=8, squash=(1, 1, 1.1)))
    objs.append(L.lathe('lbase', M('paint_green'), [(0, 0.92), (0.06, 0.92),
                                                    (0.075, 0.95), (0, 0.95)],
                        seg=12, loc=(hx, ly, zt)))
    objs.append(L.sphere('fin', M('paint_yellow'), (lx, ly, zt + 1.4), 0.045,
                         seg=10, rings=6))
    return objs


@define('prop_driftwood', footprint=(2, 1))
def driftwood():
    """Bleached driftwood branch (2x1) with a fork, a knot, pale cut ends,
    a draped bit of seaweed and a little pink shell."""
    main = [(-0.87, 0.08, 0.1), (-0.5, 0.0, 0.14), (-0.05, 0.05, 0.15),
            (0.4, -0.03, 0.13), (0.88, 0.06, 0.09)]
    objs = [tube('main', M('driftwood'), main,
                   [0.11, 0.125, 0.11, 0.09, 0.07], seg=11)]
    objs.append(tube('fork', M('driftwood'),
                       [(-0.08, 0.05, 0.18), (0.12, 0.16, 0.3),
                        (0.28, 0.28, 0.44), (0.36, 0.33, 0.54)],
                       [0.07, 0.06, 0.045, 0.035], seg=8))
    objs.append(tube('twig', M('driftwood'),
                       [(-0.45, 0.02, 0.2), (-0.56, 0.22, 0.3),
                        (-0.62, 0.33, 0.33)], [0.045, 0.035, 0.03], seg=7))
    objs.append(tube('root', M('driftwood'),
                       [(-0.82, 0.08, 0.12), (-0.92, -0.12, 0.08),
                        (-0.94, -0.26, 0.05)], [0.06, 0.045, 0.035], seg=7))
    objs.append(L.torus('knot', M('wood'), (0.15, -0.065, 0.2), 0.035, 0.016,
                        seg=10, rseg=5, rot=(80, 0, 0)))
    objs.append(L.lathe('end', M('wood'), [(0, 0), (0.055, 0), (0, 0.01)],
                        seg=10, loc=(0.938, 0.07, 0.085), rot=(0, 85, 0)))
    # a little red crab peeking at the camera
    cr = [C.ellipsoid('crab', M('paint_red'), (0, 0, 0.07), (0.1, 0.075, 0.055),
                      seg=12, rings=7)]
    for sx in (-1, 1):
        cr.append(tube('stalk', M('paint_red'), [(sx * 0.035, -0.04, 0.1),
                                                 (sx * 0.04, -0.05, 0.15)],
                       [0.012, 0.012], seg=5, cap=False))
        cr.append(L.sphere('ceye', M('eye_white'), (sx * 0.04, -0.05, 0.16),
                           0.022, seg=8, rings=5))
        cr.append(L.sphere('cpup', M('pupil'), (sx * 0.04, -0.068, 0.162),
                           0.011, seg=6, rings=4))
        cr.append(tube('arm', M('paint_red'), [(sx * 0.08, -0.03, 0.06),
                                               (sx * 0.13, -0.08, 0.06)],
                       [0.018, 0.016], seg=5, cap=False))
        cr.append(C.ellipsoid('claw', M('paint_red'), (sx * 0.14, -0.11, 0.065),
                              (0.04, 0.032, 0.03), seg=8, rings=5))
        for k in range(3):
            cr.append(tube('leg', M('paint_red'),
                           [(sx * 0.07, 0.01 + k * 0.03, 0.05),
                            (sx * 0.12, 0.02 + k * 0.035, 0.04),
                            (sx * 0.14, 0.02 + k * 0.04, 0.0)],
                           [0.01, 0.009, 0.008], seg=4, cap=False))
    cr.append(tube('smile', M('pupil'), L.arc((-0.025, -0.075, 0.07),
                                              (0.025, -0.075, 0.07), -0.01, n=4),
                   [0.005] * 4, seg=4))
    L.transform_objs(cr, loc=(-0.25, -0.28, 0.0), rot=(0, 0, -15))
    objs += cr
    # pink scallop shell on the sand
    sh = L.lathe('shell', M('petal_pink'), [(0, 0.0), (0.09, 0.0), (0.07, 0.03),
                                            (0, 0.04)], seg=18,
                 rfun=lambda th, z: (0.85 + 0.15 * abs(math.cos(5 * th))) *
                 (1.0 if math.sin(th) > -0.6 else 0.6))
    L.place(sh, (0.62, -0.33, 0.0), (0, 0, 30))
    objs.append(sh)
    return objs


@define('prop_beach_rock', footprint=(1, 1))
def beach_rock():
    """Smooth sea-rocks cluster (1x1) with an orange starfish."""
    objs = [L.lumpy('r0', M('stone'), (-0.06, 0.06, 0.2), (0.36, 0.3, 0.25),
                    subdiv=3, amp=0.05, freq=1.1, seed=4, flat_bottom=-0.19),
            L.lumpy('r1', M('stone_dark'), (0.28, -0.16, 0.12), (0.2, 0.18, 0.15),
                    subdiv=3, amp=0.05, freq=1.1, seed=8, flat_bottom=-0.11),
            L.lumpy('r2', M('stone'), (-0.34, -0.26, 0.06), (0.12, 0.1, 0.08),
                    subdiv=2, amp=0.05, seed=2, flat_bottom=-0.05),
            L.lumpy('r3', M('stone_dark'), (0.3, 0.28, 0.06), (0.1, 0.09, 0.07),
                    subdiv=2, amp=0.05, seed=6, flat_bottom=-0.05)]
    st = L.extrude('star', M('starfish'), star_pts(0.2, 0.075), 0.05,
                   bevel=0.016, seg=2)
    st.rotation_euler = (math.radians(90), 0, 0)
    L.transform_objs([st], loc=(-0.1, -0.03, 0.43), rot=(-24, 8, 15))
    objs.append(st)
    bpy.context.view_layer.update()
    for k in range(5):
        a = math.radians(90 + 72 * k + 15)
        p = Vector((math.cos(a) * 0.1, math.sin(a) * 0.1, 0.032))
        q = L.sphere('dot%d' % k, M('white'), (0, 0, 0), 0.018, seg=6, rings=4)
        q.location = p
        L.transform_objs([q], loc=(-0.1, -0.03, 0.43), rot=(-24, 8, 15))
        objs.append(q)
    objs.append(L.sphere('dotc', M('white'), (0, 0, 0.034), 0.022, seg=6, rings=4))
    L.transform_objs([objs[-1]], loc=(-0.1, -0.03, 0.43), rot=(-24, 8, 15))
    return objs


@define('prop_fishing_sign', footprint=(1, 1))
def fishing_sign():
    """Fishing-spot sign: a rounded board on a post with a cute blue fish,
    two waves and bubbles, and a little hook hanging under it."""
    objs = [L.rbox('post', M('wood_dark'), (0, 0.03, 0.5), (0.09, 0.09, 1.0),
                   bevel=0.03)]
    b = L.extrude('board', M('wood'), L.round_corners(
        [(-0.38, 0), (0.38, 0), (0.38, 0.42), (-0.38, 0.42)], 0.1, n=3,
        closed=True), 0.06, bevel=0.018)
    b.location = (0, -0.035, 0.0)
    brd = [b]
    fy = -0.068
    # fish body (ellipse) + tail + fin
    body = [(0.13 * math.cos(2 * math.pi * k / 24),
             0.075 * math.sin(2 * math.pi * k / 24)) for k in range(24)]
    fb = L.extrude('fish', M('fish'), body, 0.012, bevel=0.004, seg=1)
    fb.location = (0.03, fy, 0.25)
    brd.append(fb)
    belly = [(0.085 * math.cos(math.pi + math.pi * k / 12) + 0.0,
              0.035 * math.sin(math.pi + math.pi * k / 12) - 0.012)
             for k in range(13)]
    fbl = L.extrude('belly', M('fish_belly'), belly, 0.006, bevel=0.0)
    fbl.location = (0.04, fy - 0.007, 0.25)
    brd.append(fbl)
    tail = L.extrude('tail', M('paint_blue'), L.round_corners(
        [(0.0, 0.0), (-0.11, 0.07), (-0.09, 0.0), (-0.11, -0.07)],
        [0.0, 0.02, 0.02, 0.02], n=2, closed=True), 0.012, bevel=0.004, seg=1)
    tail.location = (-0.08, fy, 0.25)
    brd.append(tail)
    fin = L.extrude('fin', M('paint_blue'), L.round_corners(
        [(-0.05, 0.0), (0.03, 0.0), (-0.03, 0.05)], 0.015, n=2, closed=True),
        0.01, bevel=0.003, seg=1)
    fin.location = (0.02, fy + 0.002, 0.315)
    brd.append(fin)
    brd.append(C.ellipsoid('eye', M('eye_white'), (0.11, fy - 0.01, 0.265),
                           (0.024, 0.008, 0.024), seg=12, rings=6))
    brd.append(C.ellipsoid('pup', M('pupil'), (0.114, fy - 0.017, 0.262),
                           (0.013, 0.005, 0.013), seg=10, rings=5))
    brd.append(C.ellipsoid('blush', M('blush'), (0.08, fy - 0.009, 0.22),
                           (0.018, 0.004, 0.011), seg=10, rings=4))
    # smile
    brd.append(tube('smile', M('pupil'),
                      L.arc((0.125, fy - 0.009, 0.232), (0.15, fy - 0.009, 0.238),
                            -0.006, n=4), [0.004] * 4, seg=4))
    # bubbles
    for i, (x, z, r) in enumerate(((0.21, 0.31, 0.022), (0.25, 0.36, 0.016),
                                   (0.23, 0.39, 0.011))):
        brd.append(L.torus('bub%d' % i, M('paint_blue'), (x, fy - 0.005, z), r,
                           0.006, seg=12, rseg=4, rot=(90, 0, 0)))
    # waves
    for i, z in enumerate((0.1, 0.06)):
        pts = [(-0.27 + 0.54 * k / 12, fy - 0.003,
                z + 0.018 * math.sin(k * math.pi / 3 + i)) for k in range(13)]
        brd.append(tube('wave%d' % i, M('paint_blue'), pts, [0.011] * 13,
                          seg=5))
    for x in (-0.3, 0.3):
        brd.append(L.sphere('nail', M('wood_dark'), (x, -0.07, 0.36), 0.018,
                            seg=8, rings=5, squash=(1, 0.5, 1)))
    L.transform_objs(brd, rot=(-8, 0, 0))
    L.transform_objs(brd, loc=(0, 0, 0.56))
    # hook on a string under the board's right corner
    hx, hy = 0.26, -0.06
    objs.append(tube('line', M('white'), [(hx, hy, 0.56), (hx, hy, 0.4)],
                       [0.005, 0.005], seg=4))
    objs.append(tube('hook', M('metal'),
                       [(hx, hy, 0.4), (hx, hy, 0.34), (hx - 0.015, hy, 0.315),
                        (hx - 0.04, hy, 0.325), (hx - 0.045, hy, 0.345)],
                       [0.008] * 5, seg=5))
    objs += tuft('gr', (-0.12, -0.05, 0), 7, 0.22, 2)
    return objs + brd


# =================================================================== REX VALLEY


def _insert_levels(prof, levels):
    """Insert profile points exactly at heights `levels` so material bands
    painted by height end on a clean ring."""
    out = [prof[0]]
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        for zl in sorted(levels, reverse=z1 < z0):
            if min(z0, z1) + 1e-3 < zl < max(z0, z1) - 1e-3:
                f = (zl - z0) / (z1 - z0)
                out.append((r0 + (r1 - r0) * f, zl))
        out.append((r1, z1))
    return out


@define('prop_volcano', footprint=(14, 14), budget=6000)
def volcano():
    """Cute backdrop volcano (14 m wide, 9 m tall): soft rounded chocolate
    slopes over a terracotta foot and a grassy hem, darker near the top, a
    glowing lava rim, crater pool and three lava trickles down the front;
    `smoke` is a separate object (a stack of white puffs) the game can bob."""
    Z_GRASS, Z_TERRA, Z_TOP = 0.42, 2.0, 7.55
    base = L.round_corners([(0, -0.05), (7.0, -0.05), (6.6, 0.55), (5.5, 1.7),
                            (4.3, 3.5), (3.25, 5.5), (2.5, 7.3), (2.15, 8.55),
                            (1.75, 8.95), (1.4, 8.8), (1.2, 8.4), (0, 8.3)],
                           [0, 0.3, 0.6, 0.8, 0.8, 0.7, 0.6, 0.35, 0.25, 0.2,
                            0.2, 0], n=2)
    prof = _insert_levels(base, [Z_GRASS, Z_TERRA, Z_TOP])

    def lobes(th, z):
        f = min(1.0, max(0.0, z) / 1.5)
        return 1 + f * (0.055 * math.sin(5 * th + 0.4) +
                        0.03 * math.sin(9 * th + 1.3 + z * 0.2))
    vol = L.lathe('volcano', M('soil'), prof, seg=36, rfun=lobes)

    def rule(c, n):
        if c.z > 8.0 and math.hypot(c.x, c.y) < 1.5:
            return 4                                   # lava pool / inner wall
        if c.z < Z_GRASS:
            return 3
        if c.z < Z_TERRA:
            return 1
        if c.z > Z_TOP:
            return 2
        return 0
    L.paint_faces(vol, [M('soil'), M('brick'), M('soil_dark'), M('grass'),
                        M('lava')], rule)
    objs = [vol]
    # glowing rim
    objs.append(L.torus('rim', M('lava'), (0, 0, 8.86), 1.66, 0.2, seg=36,
                        rseg=7, squash=0.75,
                        rfun=lambda th: 1 + 0.18 * math.sin(6 * th)))

    # lava trickles down the front (-Y) slopes, ray-cast onto the surface
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    for i, (a, zend, w) in enumerate(((-90, 5.3, 0.42), (-118, 6.6, 0.34),
                                      (-64, 6.9, 0.32))):
        pts, rad = [], []
        m = 9
        for k in range(m):
            z = 8.55 - (8.55 - zend) * k / (m - 1)
            th = math.radians(a) + 0.03 * math.sin(k * 1.3 + i * 2)
            d = Vector((math.cos(th), math.sin(th), 0))
            hit, loc, nrm, _, _, _ = bpy.context.scene.ray_cast(
                deps, d * 12 + Vector((0, 0, z)), -d)
            if not hit:
                continue
            pts.append(tuple(loc + nrm * w * 0.12))
            rad.append(w * (1.0 - 0.25 * k / (m - 1)))
        # start over the rim, from the crater
        r0 = Vector(pts[0])
        pts.insert(0, (r0.x * 0.8, r0.y * 0.8, 8.95))
        rad.insert(0, rad[0])
        objs.append(tube('flow%d' % i, M('lava'), pts, rad, seg=9, sub=1,
                         flatten=[(1.0, 0.4)] * len(pts)))
        e = Vector(pts[-1])
        objs.append(L.sphere('drip%d' % i, M('lava'), e, rad[-1] * 1.25,
                             seg=12, rings=7, squash=(1, 1, 0.9)))
    # a few boulders at the foot
    for i, (a, s) in enumerate(((-100, 0.7), (-55, 0.5), (-140, 0.45),
                                (30, 0.6))):
        th = math.radians(a)
        objs.append(L.lumpy('bo%d' % i, M('stone'),
                            (6.4 * math.cos(th), 6.4 * math.sin(th), s * 0.55),
                            (s, s * 0.9, s * 0.8), subdiv=2, amp=0.1, seed=i,
                            flat_bottom=-s * 0.6))
    smoke = []
    for i, (x, y, z, s) in enumerate(((0.1, 0.0, 9.6, 0.62),
                                      (-0.35, 0.1, 10.55, 0.82),
                                      (0.35, 0.2, 11.65, 1.0))):
        smoke += puff('smoke%d' % i, M('white'), (x, y, z), s, seed=i + 3,
                      n=4 if i < 2 else 5, subdiv=2)
    return {'static': objs, 'named': {'smoke': smoke}}


@define('prop_hot_spring', footprint=(3, 3))
def hot_spring():
    """Warm pool (3x3): a ring of rounded stones (alternating greys so each
    stone reads), turquoise water with glints, a bathing ducky; `steam`
    is a separate object (white puffs) the game can bob."""
    R = 1.12
    k = 11

    def bumps(th):
        return 0.78 + 0.32 * abs(math.cos(k * th / 2)) ** 0.5
    rim = L.torus('rim', M('stone'), (0, 0, 0.17), R, 0.27, seg=55, rseg=8,
                  squash=0.82, rfun=bumps)
    L.paint_faces(rim, [M('stone'), M('stone_dark')],
                  lambda c, n: int(((math.atan2(c.y, c.x) + 2 * math.pi) %
                                    (2 * math.pi)) / (2 * math.pi / k)) % 2)
    objs = [rim]
    objs.append(L.lathe('basin', M('stone_dark'), [(0, 0.02), (R, 0.02),
                                                   (R, 0.05), (0, 0.05)],
                        seg=32))
    objs.append(L.lathe('water', M('water'), [(0, 0.2), (R - 0.05, 0.2),
                                              (R - 0.05, 0.22), (0, 0.22)],
                        seg=36))
    for i, (x, y, s, a) in enumerate(((-0.45, -0.25, 0.13, 20),
                                      (0.35, 0.3, 0.1, -10),
                                      (0.5, -0.35, 0.07, 30))):
        objs.append(C.ellipsoid('glint%d' % i, M('white'), (x, y, 0.224),
                                (s * 1.6, s * 0.6, 0.004), rot=(0, 0, a),
                                seg=8, rings=3))
    # one big accent stone at the back
    objs.append(L.lumpy('acc', M('stone'), (-0.85, 0.95, 0.27),
                        (0.45, 0.4, 0.36), subdiv=3, amp=0.07, seed=2,
                        flat_bottom=-0.27))
    # bathing ducky
    duck = [C.ellipsoid('duck', M('paint_yellow'), (0, 0, 0.05),
                        (0.12, 0.09, 0.075), seg=14, rings=8),
            L.sphere('dhead', M('paint_yellow'), (-0.07, 0, 0.15), 0.065,
                     seg=12, rings=8),
            C.ellipsoid('beak', M('carrot'), (-0.13, 0, 0.135),
                        (0.04, 0.03, 0.016), seg=10, rings=5),
            C.cone('tailp', M('paint_yellow'), (0.09, 0, 0.08),
                   (0.15, 0, 0.14), 0.04, seg=8)]
    for s in (-1, 1):
        duck.append(L.sphere('deye%d' % s, M('pupil'),
                             (-0.105, s * 0.04, 0.175), 0.013, seg=6, rings=4))
    L.transform_objs(duck, loc=(0.2, -0.15, 0.2), rot=(0, 0, 60), scale=1.5)
    objs += duck
    steam = []
    for i, (x, y, z, s) in enumerate(((-0.4, 0.15, 0.62, 0.17),
                                      (0.3, 0.35, 0.78, 0.2),
                                      (-0.15, -0.4, 0.85, 0.15))):
        steam += puff('st%d' % i, M('white'), (x, y, z), s, seed=i, n=2,
                      subdiv=2)
    return {'static': objs, 'named': {'steam': steam}}


@define('prop_fossil', footprint=(2, 1))
def fossil():
    """Cute dino-skeleton arch (2x1): a chunky backbone with round
    vertebrae arching ~1.5 m from a grinning skull resting on the ground
    (left) to the tail tip (right), a short rib cage hanging from its top."""
    objs = []
    ax0, ax1, H = -0.55, 0.92, 1.45
    pts = []
    m = 11
    for k in range(m):
        t = k / (m - 1)
        x = ax0 + (ax1 - ax0) * t
        u = (t - 0.4) / 0.6 if t > 0.4 else (t - 0.4) / 0.4
        z = H * (1 - abs(u) ** 2.2)
        pts.append(Vector((x, 0, max(z, 0.0) + 0.06)))
    objs.append(tube('spine', M('bone'), [tuple(p) for p in pts],
                     [0.11] * 6 + [0.095, 0.08, 0.065, 0.05, 0.042], seg=8,
                     sub=1))
    for k in range(1, m - 1):
        p = pts[k]
        tng = (pts[k + 1] - pts[k - 1]).normalized()
        s = 0.18 * (1 - 0.45 * max(0, k - 4) / 5)
        v = C.ellipsoid('vert%d' % k, M('bone'), (0, 0, 0), (s * 0.55, s, s),
                        seg=8, rings=5)
        L.orient(v, p, tng)
        objs.append(v)
        nrm = Vector((-tng.z, 0, tng.x))
        if nrm.z < 0:
            nrm = -nrm
        if k % 2:
            objs.append(L.sphere('knob%d' % k, M('bone'), p + nrm * s * 1.0,
                                 s * 0.45, seg=7, rings=5))
    # ribs: short curved bones out to both sides from the top of the arch
    for j, k in enumerate((3, 4, 5)):
        p = pts[k]
        ln = 0.72 - 0.12 * abs(k - 4)
        for s in (-1, 1):
            rib = [tuple(p), (p.x, s * 0.26, p.z - 0.06 * ln),
                   (p.x, s * 0.4, p.z - 0.45 * ln), (p.x, s * 0.34, p.z - 0.85 * ln),
                   (p.x, s * 0.22, p.z - ln)]
            objs.append(tube('rib%d%d' % (j, s), M('bone'), rib,
                             [0.07, 0.066, 0.062, 0.058, 0.064], seg=7,
                             sub=1, cap_steps=2))
    # front leg bones holding the arch up near the skull, a back leg at the
    # tail end
    for (x, z0), s in (((pts[2].x, pts[2].z), 1), ((pts[7].x, pts[7].z), 1)):
        for sy in (-1, 1):
            objs.append(tube('leg', M('bone'),
                             [(x, sy * 0.1, z0 - 0.05), (x + 0.05, sy * 0.2, z0 * 0.5),
                              (x, sy * 0.24, 0.07)], [0.075, 0.065, 0.085], seg=7,
                             cap_steps=2))
    # skull on the ground at the left, nose to the front-left
    sk = [C.ellipsoid('cran', M('bone'), (0, 0, 0.3), (0.3, 0.27, 0.27),
                      seg=16, rings=9),
          C.ellipsoid('snout', M('bone'), (0, -0.2, 0.2), (0.22, 0.24, 0.16),
                      seg=14, rings=8),
          C.ellipsoid('jaw', M('bone'), (0, -0.14, 0.07), (0.2, 0.24, 0.08),
                      seg=12, rings=6)]
    bpy.context.view_layer.update()
    for s in (-1, 1):
        sk.append(C.decal_on('sock%d' % s, M('soil_dark'), sk[0],
                             (s * 0.13, -0.18, 0.4), (s * 0.45, -1, 0.35), 0.075,
                             lift=0.004, seg=14))
        sk.append(C.decal_on('nos%d' % s, M('soil_dark'), sk[1],
                             (s * 0.06, -0.42, 0.28), (s * 0.2, -0.6, 1), 0.022,
                             lift=0.004, seg=8))
    for t in range(3):
        x = -0.09 + t * 0.09
        sk.append(C.ellipsoid('tooth%d' % t, M('white'), (x, -0.4, 0.12),
                              (0.022, 0.018, 0.03), seg=6, rings=4))
    sk.append(tube('grin', M('soil_dark'),
                   L.arc((-0.17, -0.37, 0.15), (0.17, -0.37, 0.15), -0.02,
                         n=4), [0.012] * 4, seg=4))
    L.transform_objs(sk, rot=(0, 0, -30))
    L.transform_objs(sk, loc=(-0.66, -0.08, 0.0))
    objs += sk
    # grass tufts at the feet
    objs += tuft('ga', (0.15, -0.38, 0), 6, 0.2, 7)
    return objs


@define('prop_big_boulder', footprint=(3, 3))
def big_boulder():
    """Big rounded boulder (3x3, ~2 m): a lumpy two-lobed rock with a dark
    crack, a smaller rock leaning on it, pebbles and grass at the foot."""
    r = L.lumpy('rock', M('stone'), (-0.12, 0.08, 0.95), (1.22, 1.1, 1.0),
                subdiv=4, amp=0.15, freq=1.5, seed=11, flat_bottom=-0.92)
    r2 = L.lumpy('lobe', M('stone'), (0.62, 0.15, 0.62), (0.75, 0.8, 0.68),
                 subdiv=3, amp=0.12, freq=1.6, seed=5, flat_bottom=-0.6)
    objs = [r, r2]
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    crack = []
    for k, (x, z) in enumerate(((-0.55, 1.75), (-0.42, 1.5), (-0.5, 1.28),
                                (-0.36, 1.05))):
        hit, loc, nrm, _, _, _ = bpy.context.scene.ray_cast(
            deps, Vector((x, -5, z)), Vector((0, 1, 0)))
        if hit:
            crack.append(tuple(loc + nrm * 0.005))
    if len(crack) >= 3:
        objs.append(tube('crack', M('stone_dark'), crack,
                         [0.022, 0.03, 0.026, 0.018], seg=5))
    objs.append(L.lumpy('r3', M('stone_dark'), (0.95, -0.92, 0.3),
                        (0.42, 0.37, 0.33), subdiv=3, amp=0.1, seed=4,
                        flat_bottom=-0.3))
    for i, (x, y, s) in enumerate(((-1.1, -0.95, 0.15), (0.3, -1.22, 0.1),
                                   (1.28, 0.55, 0.13))):
        objs.append(L.lumpy('peb%d' % i, M('stone_dark' if i % 2 else 'stone'),
                            (x, y, s * 0.6), (s * 1.2, s, s * 0.85), subdiv=2,
                            amp=0.1, seed=i, flat_bottom=-s * 0.5))
    objs += tuft('ga', (-0.85, -1.05, 0), 7, 0.28, 3, spread=0.12)
    objs += tuft('gb', (0.45, -1.15, 0), 6, 0.22, 4)
    objs += tuft('gc', (1.3, 0.2, 0), 5, 0.24, 5)
    return objs


@define('prop_bone_toy', footprint=(1, 1))
def bone_toy():
    """Giant cartoon chew bone (rex toy): chunky waisted shaft with double
    knobs, red rubber bands near the ends."""
    Lh, rk, zc = 0.3, 0.13, 0.14
    objs = [tube('shaft', M('bone'), [(-Lh - 0.05, 0, zc), (-0.1, 0, zc),
                                        (0.1, 0, zc), (Lh + 0.05, 0, zc)],
                   [0.1, 0.085, 0.085, 0.1], seg=16, cap=False)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            objs.append(L.sphere('knob', M('bone'), (sx * (Lh + 0.04),
                                                     sy * 0.085, zc), rk,
                                 seg=18, rings=12))
        objs.append(L.torus('band%d' % sx, M('paint_red'), (sx * (Lh - 0.1), 0, zc),
                            0.093, 0.022, seg=18, rseg=6, rot=(0, 90, 0)))
    # bite marks: little dents faked as darker dots
    bpy.context.view_layer.update()
    for i, x in enumerate((-0.05, 0.03, 0.1)):
        objs.append(C.decal_on('bite%d' % i, M('stone'), objs[0],
                               (x, -0.06, zc + 0.05), (0, -0.6, 1), 0.016,
                               lift=0.003, seg=8))
    L.transform_objs(objs, rot=(0, 0, 18))
    return objs


@define('prop_palm_big', footprint=(1, 1), budget=4000)
def palm_big():
    """Big cartoon palm (~5 m): curved ringed trunk, ten drooping leaves,
    four coconuts (the prop_palm family, scaled up and chunkier)."""
    N = 12
    Hh = 4.3
    pts, radii = [], []
    for i in range(N):
        for f, s in ((0.0, 0.85), (0.75, 1.0)):
            t = (i + f) / N
            pts.append((0.75 * t * t, 0.18 * t * t, Hh * t))
            radii.append((0.27 - 0.1 * t) * s)
    top = Vector(pts[-1])
    objs = [tube('trunk', M('bark'), pts, radii, seg=11)]
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.7
        objs.append(tube('root%d' % i, M('bark'),
                           [(0, 0, 0.3), (0.3 * math.cos(a), 0.3 * math.sin(a),
                                          0.05),
                            (0.42 * math.cos(a), 0.42 * math.sin(a), 0.0)],
                           [0.15, 0.1, 0.05], seg=6, cap=False))
    objs.append(L.sphere('crown', M('leaf_dark'), top + Vector((0, 0, 0.06)),
                         0.23, seg=12, rings=8))
    rng = random.Random(8)
    n = 9
    for i in range(n):
        phi = 2 * math.pi * i / n + rng.uniform(-0.12, 0.12)
        objs.append(L.frond('leaf%d' % i, M('leaf' if i % 3 else 'leaf_dark'),
                            top + Vector((0, 0, 0.12)), phi,
                            rng.uniform(1.8, 2.1), 0.62, 1.15, 0.38,
                            teeth=7, comb=0.35, fold=0.25, thick=0.016))
    for i in range(4):
        a = 2 * math.pi * i / 4 + 0.3
        objs.append(L.sphere('coco%d' % i, M('coconut'),
                             top + Vector((0.18 * math.cos(a),
                                           0.18 * math.sin(a), -0.17)),
                             0.15, seg=10, rings=7))
    return objs


# =================================================================== main


def _origin_to_center(ob):
    """Move a named sub-object's origin to the centre of its bounds."""
    bpy.context.view_layer.update()
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    c = (lo + hi) / 2
    ob.data.transform(Matrix.Translation(-c))
    ob.location = c
    return ob


def build(name, out):
    d = DEFS[name]
    L.begin()
    res = d['fn']()
    if C.args().get('parts'):     # --parts: triangles per part (budgeting)
        parts = res['static'] + sum(res['named'].values(), []) \
            if isinstance(res, dict) else res
        bpy.context.view_layer.update()
        agg = {}
        for o in parts:
            k = o.name.rstrip('0123456789_-').split('_')[0]
            agg[k] = agg.get(k, 0) + L.tris(o)
        print('[parts]', name, sorted(agg.items(), key=lambda kv: -kv[1]))
    if isinstance(res, dict):
        mesh = L.finish(name, res['static'])
        named = []
        for k, v in res['named'].items():
            o = L.finish(k, v)
            _origin_to_center(o)
            named.append(o)
        objs = [mesh] + named
    else:
        mesh = L.finish(name, res)
        objs = [mesh]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts),
                 min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts),
                 max(p.z for p in pts)))
    nt = sum(L.tris(o) for o in objs)
    mats = {m.name for o in objs for m in o.data.materials}
    flag = '' if nt <= d['budget'] else '  OVER BUDGET %d' % d['budget']
    print('[habA] %-20s tris %5d  mats %2d  x %.2f..%.2f  y %.2f..%.2f  '
          'z %.2f..%.2f  %s%s' % (name, nt, len(mats), lo.x, hi.x, lo.y, hi.y,
                                  lo.z, hi.z, ','.join(o.name for o in objs[1:]),
                                  flag))
    C.export_glb(os.path.join(out, name + '.glb'), objs)
    return dict(name=name, tris=nt, mats=sorted(mats), footprint=d['footprint'],
                lo=tuple(round(v, 3) for v in lo),
                hi=tuple(round(v, 3) for v in hi),
                named=[o.name for o in objs[1:]])


def main():
    A = C.args()
    out = A.get('out', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    '..', '..', 'game', 'assets', 'models'))
    if A.get('list'):
        for k, d in DEFS.items():
            print(k, d['footprint'])
        return
    only = A.get('only')
    names = only.split(',') if isinstance(only, str) else list(DEFS)
    rows = []
    for n in names:
        if n not in DEFS:
            print('[habA] unknown', n)
            continue
        rows.append(build(n, out))
    if isinstance(A.get('summary'), str):
        import json
        with open(A['summary'], 'w') as f:
            json.dump(rows, f, indent=1)


main()
