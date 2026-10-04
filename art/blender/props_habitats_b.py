"""props_habitats_b.py - habitat props for Tommy's Dino Zoo, set B:
the canyon (ankylo, pachy, proto), the cliff / aviary (ptera, archaeo) and
toys & care props that go anywhere.

    cd art/blender
    Blender -b -P props_habitats_b.py -- [--only prop_mesa,prop_cliff] [--out DIR]
    Blender -b -P props_habitats_b.py -- --list

Writes game/assets/models/<name>.glb. Same conventions as props.py (see
docs/ART-SPEC.md): origin = footprint centre on the ground, footprint in
whole metres, front faces -Y in Blender (+Z in Godot), shared material
roles from props_lib.PAL plus a few habitat roles added below (`rock_*`,
`sand*`, `cliff*`, `mud*`, `leaf_sage*`, `egg_blue`, `rope`).

Named sub-objects (separate nodes in the .glb, like prop_trough's `food`):
  prop_waterfall  `fall`   the falling water sheet + the stream on top,
                           material `water`, UV v runs along the flow
                           (0 at the back of the stream -> 1 at the pool),
                           u across; scroll v to animate.
  prop_shower     `spray`  falling water drops (show while showering).
  prop_tall_feeder `food`  the hay + leaves in the basket (hide when empty).
  prop_perch      `top`    empty at the landing spot on top (z = PERCH_TOP).

Rock formations are stacks of soft "slabs": a plan outline (rounded
superellipse with low-frequency noise) lofted into a puffy layer with
rounded top/bottom edges; each slab is a colour band.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector, noise  # noqa: E402

import props_lib as L  # noqa: E402
import tdz_common as C  # noqa: E402
from props_lib import M  # noqa: E402

# habitat palette roles (added at run time; props_lib itself is unchanged)
for _k, _v in {
    'rock_peach': '#f2b186', 'rock_terra': '#d97858', 'rock_cream': '#fbe2bb',
    'rock_red': '#dd6e55', 'sand': '#f7d9a6', 'sand_dark': '#e8b57c',
    'cliff': '#cbc3d2', 'cliff_dark': '#aaa1b9', 'egg_blue': '#bfe6f7',
    'leaf_sage': '#a8cc6a', 'leaf_sage_dark': '#7fae55',
    'mud': ('#74482f', {'rough': 0.25}), 'mud_light': '#a27258',
    'rope': '#ecc98c', 'foam': '#f4fbff', 'dune': '#f2c690',
}.items():
    L.PAL.setdefault(_k, _v)

DEFS = {}
PERCH_TOP = 3.0      # landing height on prop_perch (z of the `top` empty)


def define(name, footprint=None, budget=3000):
    def deco(fn):
        DEFS[name] = dict(fn=fn, footprint=footprint, budget=budget)
        return fn
    return deco


# =================================================================== helpers


def _resample(pts, n):
    """Closed polyline -> n points evenly spaced by arc length."""
    P = [Vector((p[0], p[1])) for p in pts]
    P.append(P[0])
    seg = [(P[i + 1] - P[i]).length for i in range(len(P) - 1)]
    total = sum(seg)
    out, i, acc = [], 0, 0.0
    for k in range(n):
        d = total * k / n
        while i < len(seg) - 1 and acc + seg[i] < d:
            acc += seg[i]
            i += 1
        t = (d - acc) / seg[i] if seg[i] > 0 else 0.0
        out.append(P[i].lerp(P[i + 1], t))
    return out


def _normals2(pts):
    n = len(pts)
    out = []
    for i in range(n):
        t = pts[(i + 1) % n] - pts[i - 1]
        out.append(Vector((t.y, -t.x)).normalized())
    return out


def plan(hx, hy, p=3.0, n=48, amp=0.0, freq=1.1, seed=0, off=(0, 0),
         rot=0.0, lobes=None):
    """Closed CCW outline: superellipse of half sizes hx, hy (p=2 ellipse,
    larger = squarer) pushed in/out by smooth noise of `amp` metres.
    `lobes` = [(angle_deg, amount_m, width_deg)] adds bulges."""
    dense = []
    for k in range(360):
        a = 2 * math.pi * k / 360
        c, s = math.cos(a), math.sin(a)
        dense.append((hx * math.copysign(abs(c) ** (2 / p), c),
                      hy * math.copysign(abs(s) ** (2 / p), s)))
    pts = _resample(dense, n)
    nr = _normals2(pts)
    o = Vector((seed * 3.17 + 0.5, seed * 1.93 + 0.2, seed * 0.71))
    out = []
    for q, nn in zip(pts, nr):
        d = 0.0
        if amp:
            d += amp * noise.noise(Vector((q.x * freq, q.y * freq, 0)) + o)
        if lobes:
            ang = math.degrees(math.atan2(q.y, q.x))
            for (la, lm, lw) in lobes:
                da = (ang - la + 180) % 360 - 180
                d += lm * math.exp(-(da / lw) ** 2)
        q = q + nn * d
        cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        out.append(Vector((q.x * cr - q.y * sr + off[0],
                           q.x * sr + q.y * cr + off[1])))
    return out


def slab(name, material, outline, z0, z1, bt=0.16, bb=0.07, bulge=0.04,
         top=True, tseg=3, dome=0.04, wob=0.0, wfreq=1.6, seed=0):
    """Loft a plan outline into a soft layer from z0 to z1: rounded top
    edge (radius bt), small rounded bottom edge (bb), puffy middle (bulge),
    a gently domed top (`dome` m) and optional noise wobble (`wob` m).
    Open bottom (it always sits on the ground or another slab)."""
    P = [Vector((q[0], q[1])) for q in outline]
    N = _normals2(P)
    cen = sum(P, Vector((0, 0))) / len(P)
    prof = []
    prof.append((-bb, z0))
    prof.append((0.0, z0 + bb))
    if bulge:
        prof.append((bulge, z0 + bb + (z1 - bt - z0 - bb) * 0.5))
    for k in range(tseg + 1):
        a = math.radians(90 * k / tseg)
        prof.append((-bt + bt * math.cos(a), z1 - bt + bt * math.sin(a)))
    o = Vector((seed * 2.3, seed * 1.1, seed * 0.7))

    def wv(v):
        if not wob:
            return v
        d = noise.noise(v * wfreq + o)
        nv = Vector((v.x - cen.x, v.y - cen.y, 0))
        if nv.length > 1e-6:
            nv.normalize()
        return v + nv * wob * d
    bm = bmesh.new()
    rings = []
    for off, z in prof:
        rings.append([bm.verts.new(wv(Vector((p.x + nn.x * off,
                                               p.y + nn.y * off, z))))
                      for p, nn in zip(P, N)])
    n = len(P)
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    if top:
        last = rings[-1]
        inner = [bm.verts.new((v.co.x + (cen.x - v.co.x) * 0.45,
                               v.co.y + (cen.y - v.co.y) * 0.45,
                               z1 + dome * 0.75)) for v in last]
        for k in range(n):
            bm.faces.new((last[k], last[(k + 1) % n], inner[(k + 1) % n],
                          inner[k]))
        c = bm.verts.new((cen.x, cen.y, z1 + dome))
        for k in range(n):
            bm.faces.new((inner[k], inner[(k + 1) % n], c))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # make sure the sides face out (open meshes can confuse recalc)
    f0 = bm.faces[0]
    f0c = f0.calc_center_median()
    if f0.normal.dot(Vector((f0c.x - cen.x, f0c.y - cen.y, 0))) < 0:
        for f in bm.faces:
            f.normal_flip()
    return L._bm_obj(bm, name, material)


def wobble(ob, amp, freq=1.5, seed=0):
    """Push vertices along their normals by smooth noise (lumpy rock)."""
    bpy.context.view_layer.update()
    C.apply_xf(ob)
    o = Vector((seed * 1.7, seed * 2.9, seed * 0.3))
    for v in ob.data.vertices:
        v.co = v.co + v.normal * amp * noise.noise(v.co * freq + o)
    ob.data.update()
    return ob


def band_paint(ob, mats, cuts, pick=None):
    """Slice `ob` with horizontal planes at `cuts` (world z) and give each
    band its own material: band i (below cuts[0] is 0) -> mats[pick(i)]
    (default: cycle through mats). Clean, straight band edges."""
    bpy.context.view_layer.update()
    C.apply_xf(ob)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for z in cuts:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-4,
                               plane_co=(0, 0, z), plane_no=(0, 0, 1))
    for f in bm.faces:
        cz = f.calc_center_median().z
        i = sum(1 for z in cuts if cz > z)
        f.material_index = pick(i) if pick else i % len(mats)
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    bm.to_mesh(me)
    bm.free()
    return ob


def mound(name, material, hx, hy, h, rings=7, seg=32, p=2.0, shape=None,
          loc=(0, 0, 0), amp=0.0, seed=0, freq=2.0, rot=0.0):
    """Smooth low mound over a superellipse outline: height h*shape(t)
    (t = 0 centre .. 1 rim; default soft dome that meets the ground)."""
    if shape is None:
        def shape(t):
            return (1 - t * t) ** 1.6
    out = plan(hx, hy, p=p, n=seg, amp=amp, freq=freq, seed=seed)
    bm = bmesh.new()
    c = bm.verts.new((0, 0, h * shape(0.0)))
    prev = None
    rr = []
    for i in range(1, rings + 1):
        t = i / rings
        tt = t ** 0.8
        ring = [bm.verts.new((q.x * tt, q.y * tt, h * shape(tt)))
                for q in out]
        rr.append(ring)
    first = rr[0]
    for k in range(seg):
        bm.faces.new((c, first[k], first[(k + 1) % seg]))
    for a, b in zip(rr, rr[1:]):
        for k in range(seg):
            bm.faces.new((a[k], b[k], b[(k + 1) % seg], a[(k + 1) % seg]))
    del prev
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = L._bm_obj(bm, name, material)
    if ob.data.polygons[0].normal.z < 0:
        L.flip(ob)
    return L.place(ob, loc, (0, 0, rot))


def drop_z(objs, x, y, z0=30.0):
    """Height of the top surface of `objs` at (x, y) (ray cast down)."""
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    names = {o.name for o in objs}
    org = Vector((x, y, z0))
    for _ in range(8):
        hit, loc, nrm, _i, ob, _m = bpy.context.scene.ray_cast(
            deps, org, Vector((0, 0, -1)))
        if not hit:
            return 0.0
        if ob.name in names:
            return loc.z
        org = loc - Vector((0, 0, 1e-3))
    return 0.0


def pebble(name, mat, loc, r, seed=0, squash=0.7):
    return L.lumpy(name, M(mat), (loc[0], loc[1], loc[2] + r * squash * 0.8),
                   (r, r * 0.9, r * squash), subdiv=2, amp=0.12, seed=seed,
                   flat_bottom=-r * squash * 0.75)


def flower_head(name, petal, loc, r, petals=5, tilt=(0, 0), center='flower_center',
                lite=False):
    """Little 5-petal flower head (same shape as props.py flowers);
    `lite` = cheaper profile for tiny flowers (~60 tris)."""
    k = petals / 2.0
    f = r / 0.12
    prof = [(0, -0.018 * f), (r, 0.0), (0, 0.027 * f)] if lite else \
        [(0, -0.018 * f), (r * 0.95, -0.004 * f), (r * 0.8, 0.022 * f),
         (0, 0.027 * f)]
    head = L.lathe(name, M(petal), prof,
                   seg=20, rfun=lambda th, zz: 0.55 + 0.45 * abs(math.cos(k * th)))
    ctr = L.sphere(name + '_c', M(center), (0, 0, 0.026 * f), r * 0.32,
                   seg=6, rings=3, squash=(1, 1, 0.6))
    L.transform_objs([head, ctr], loc=loc, rot=(tilt[0], tilt[1], 0))
    return [head, ctr]


def shrub(name, center, radii, seed, n=6, flowers=8, petal='petal_pink',
          petal2='petal_yellow', zmin=None):
    """Round sage-green shrub dotted with tiny flowers."""
    objs = L.canopy(name, M('leaf_sage'), center, radii, n=n, blob=(0.48, 0.62),
                    seed=seed, lower_mat=M('leaf_sage_dark'), lump=0.07,
                    lower_z=-0.1, spread=0.75, subdiv=2, core_subdiv=2)
    bpy.context.view_layer.update()
    rm = (radii[0] + radii[1] + radii[2]) / 3

    def fl(i, loc, nrm):
        tilt = (math.degrees(math.atan2(-nrm.y, nrm.z)) * 0.8,
                math.degrees(math.atan2(nrm.x, nrm.z)) * 0.8)
        return flower_head('%s_f%d' % (name, i), petal if i % 3 else petal2,
                           loc + nrm * 0.01, 0.055 * rm / 0.4 + 0.02,
                           tilt=tilt, lite=True)
    rng = random.Random(seed)
    dirs = []
    while len(dirs) < 300:
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 0.5),
                    rng.uniform(-0.1, 1)))
        if 0.2 < d.length <= 1:
            dirs.append(d)
    z0 = center[2] - radii[2] * 0.1 if zmin is None else zmin
    objs += L.scatter_on(objs[:], flowers, seed, fl, zmin=z0,
                         min_gap=rm * 0.42, center=center, dirs=dirs)
    return objs


def uv_grid(ob, uvs):
    """Assign per-loop UVs from a per-vertex list."""
    me = ob.data
    lay = me.uv_layers.new(name='UVMap')
    for loop in me.loops:
        lay.data[loop.index].uv = uvs[loop.vertex_index]
    return ob


# =================================================================== canyon

SAND_BANDS = ['rock_terra', 'rock_peach', 'rock_cream', 'rock_peach',
              'rock_terra', 'rock_cream']


@define('prop_mesa', footprint=(4, 4), budget=5000)
def mesa():
    """Tall layered sandstone mesa (~5 m): puffy strata of different
    thickness in terracotta, cream and peach, stepping in as they rise;
    a flowering shrub and pebbles on top, rubble at the foot."""
    layers = [  # z0, z1, hx, hy, offset, mat, lobe angle
        (0.0, 1.3, 1.88, 1.84, (0.0, 0.0), 'rock_terra', -120),
        (1.24, 1.78, 1.7, 1.68, (0.05, 0.04), 'rock_cream', 10),
        (1.72, 3.0, 1.6, 1.55, (-0.04, 0.08), 'rock_peach', 150),
        (2.94, 3.42, 1.5, 1.44, (0.06, 0.06), 'rock_terra', -40),
        (3.36, 4.85, 1.38, 1.33, (-0.02, 0.1), 'rock_peach', 80),
    ]
    objs = []
    for i, (z0, z1, hx, hy, off, m, la) in enumerate(layers):
        out = plan(hx, hy, p=2.5, n=44, amp=0.16, freq=0.9, seed=i + 1,
                   off=off, lobes=[(la, 0.14, 35), (la + 150, -0.08, 30)])
        thin = z1 - z0 < 0.7
        objs.append(slab('l%d' % i, M(m), out, z0, z1, bt=0.13 if thin else 0.24,
                         bb=0.07, bulge=0.03 if thin else 0.06, tseg=2,
                         dome=0.06, wob=0.07, wfreq=1.3, seed=i))
    # thin stripes inside the thick layers
    band_paint(objs[0], [M('rock_terra'), M('rock_peach')], [0.52, 0.66],
               pick=lambda i: 1 if i == 1 else 0)
    band_paint(objs[2], [M('rock_peach'), M('rock_cream')], [2.3, 2.42],
               pick=lambda i: 1 if i == 1 else 0)
    band_paint(objs[4], [M('rock_peach'), M('rock_terra')], [3.98, 4.1],
               pick=lambda i: 1 if i == 1 else 0)
    zt = drop_z(objs, 0.3, 0.35)
    objs += shrub('sh', (0.3, 0.35, zt + 0.26), (0.42, 0.4, 0.32), 4, n=5,
                  flowers=7)
    for i, (x, y, r, m) in enumerate(((-0.55, -0.4, 0.2, 'rock_cream'),
                                      (-0.25, -0.68, 0.12, 'rock_terra'))):
        objs.append(pebble('pt%d' % i, m, (x, y, drop_z(objs, x, y) - 0.03),
                           r, seed=2 + i))
    for i, (x, y, r, m) in enumerate(((-1.6, -1.6, 0.26, 'rock_peach'),
                                      (-1.2, -1.86, 0.15, 'rock_cream'),
                                      (1.72, -1.45, 0.2, 'rock_terra'),
                                      (1.45, -1.78, 0.11, 'rock_peach'))):
        objs.append(pebble('pb%d' % i, m, (x, y, 0), r, seed=7 + i))
    return objs


@define('prop_rock_arch', footprint=(3, 1))
def rock_arch():
    """Natural sandstone arch (~2.5 m): two banded pillars at x = +-1.02
    under a chunky lumpy striped span; the opening is ~1.2 m wide and
    ~1.75 m tall in the middle."""
    objs = []
    X = 1.02
    for s in (-1, 1):
        specs = [(0.0, 0.62, 0.45, 0.42, 'rock_terra'),
                 (0.56, 1.1, 0.38, 0.36, 'rock_cream'),
                 (1.04, 1.6, 0.42, 0.38, 'rock_peach')]
        for i, (z0, z1, hx, hy, m) in enumerate(specs):
            out = plan(hx, hy, p=2.4, n=20, amp=0.05, freq=2.0,
                       seed=i + (5 if s > 0 else 0),
                       off=(s * X + s * 0.03 * (i % 2), 0.0))
            objs.append(slab('p%d_%d' % (s, i), M(m), out, z0, z1, bt=0.13,
                             bb=0.05, bulge=0.035, tseg=2, wob=0.04,
                             seed=i + 3 * s))
    pts = [(-X - 0.02, 0, 1.3), (-0.84, 0, 1.92), (-0.34, 0, 2.15),
           (0.34, 0, 2.15), (0.84, 0, 1.92), (X + 0.02, 0, 1.3)]
    span = C.tube('span', M('rock_peach'), pts,
                  [0.42, 0.39, 0.36, 0.36, 0.39, 0.42], seg=12,
                  flatten=[(1.25, 1.0)] * 6)
    wobble(span, 0.06, freq=2.2, seed=3)
    band_paint(span, [M('rock_terra'), M('rock_peach'), M('rock_cream')],
               [1.72, 1.95, 2.3], pick=lambda i: (0, 2, 1, 0)[i])
    objs.append(span)
    for i, (x, y, r, m) in enumerate(((-1.36, -0.34, 0.14, 'rock_peach'),
                                      (1.3, -0.36, 0.11, 'rock_cream'))):
        objs.append(pebble('pb%d' % i, m, (x, y, 0), r, seed=11 + i))
    objs += shrub('sh', (-0.5, -0.2, 0.18), (0.22, 0.2, 0.18), 6, n=3,
                  flowers=2)
    return objs


@define('prop_canyon_wall', footprint=(4, 1))
def canyon_wall():
    """Straight banded cliff (4 m wide, ~3.5 m): strata of different
    thickness stepping back a little; ends reach x = +-2.05 so neighbours
    overlap and tile side by side."""
    layers = [(0.0, 1.05, 0.5, 0.0, 'rock_terra'),
              (1.0, 1.42, 0.46, 0.04, 'rock_cream'),
              (1.37, 2.55, 0.45, 0.06, 'rock_peach'),
              (2.5, 3.45, 0.4, 0.1, 'rock_terra')]
    objs = []
    for i, (z0, z1, hy, oy, m) in enumerate(layers):
        out = plan(2.0 + (0.0 if i % 2 else 0.04), hy, p=7.0, n=38,
                   amp=0.06, freq=1.3, seed=20 + i, off=(0, oy))
        thin = z1 - z0 < 0.6
        objs.append(slab('l%d' % i, M(m), out, z0, z1,
                         bt=0.12 if thin else 0.2, bb=0.06,
                         bulge=0.03 if thin else 0.05, tseg=2, dome=0.03,
                         wob=0.06, wfreq=1.4, seed=i + 9))
    band_paint(objs[2], [M('rock_peach'), M('rock_cream')], [1.92, 2.04],
               pick=lambda i: 1 if i == 1 else 0)
    for i, (x, y, r, m) in enumerate(((-1.1, 0.12, 0.2, 'rock_cream'),
                                      (-0.85, -0.05, 0.11, 'rock_peach'),
                                      (1.0, 0.18, 0.15, 'rock_peach'))):
        objs.append(pebble('t%d' % i, m, (x, y, drop_z(objs, x, y) - 0.03),
                           r, seed=3 + i))
    objs += shrub('sh', (0.35, 0.15, 3.66), (0.24, 0.22, 0.2), 8, n=3,
                  flowers=3)
    objs.append(pebble('b0', 'rock_peach', (-0.5, -0.5, 0), 0.15, seed=5))
    objs.append(pebble('b1', 'rock_cream', (1.3, -0.5, 0), 0.11, seed=6))
    return objs


@define('prop_boulder_red', footprint=(1, 1))
def boulder_red():
    """Round red-sand boulder with a cream stripe and a pebble."""
    r = L.lumpy('rock', M('rock_red'), (0, 0.02, 0.33), (0.44, 0.4, 0.36),
                subdiv=4, amp=0.1, freq=1.3, seed=4, flat_bottom=-0.3)
    band_paint(r, [M('rock_red'), M('rock_cream')], [0.24, 0.33],
               pick=lambda i: 1 if i == 1 else 0)
    peb = pebble('peb', 'rock_peach', (0.36, -0.26, 0), 0.11, seed=5)
    peb2 = pebble('peb2', 'rock_red', (-0.38, -0.2, 0), 0.07, seed=8)
    return [r, peb, peb2]


@define('prop_dig_spot', footprint=(1, 1))
def dig_spot():
    """Soft sand mound marked with an X of two sticks."""
    objs = [mound('mound', M('sand_dark'), 0.42, 0.38, 0.17, rings=6, seg=28,
                  amp=0.03, seed=2)]
    for i, a in enumerate((35, -35)):
        d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
        objs.append(L.plank('stick%d' % i, M('wood_dark'),
                            Vector((0, 0, 0.19 + 0.025 * i)) - d * 0.24,
                            Vector((0, 0, 0.19 + 0.025 * i)) + d * 0.24,
                            0.055, 0.04, bevel=0.018))
    rng = random.Random(3)
    for i in range(5):
        a = 2 * math.pi * i / 5 + 0.4
        rr = rng.uniform(0.3, 0.42)
        objs.append(L.lumpy('clump%d' % i, M('sand'),
                            (rr * math.cos(a), rr * math.sin(a), 0.03),
                            (0.07, 0.06, 0.045), subdiv=2, amp=0.15, seed=i))
    objs.append(pebble('peb', 'rock_peach', (0.3, -0.3, 0), 0.06, seed=4))
    return objs


@define('prop_desert_shrub', footprint=(1, 1))
def desert_shrub():
    """Round prehistoric shrub, sage green with tiny pink/yellow flowers."""
    return shrub('sh', (0, 0, 0.36), (0.44, 0.42, 0.36), 12, n=6, flowers=10)


@define('prop_sand_dune', footprint=(3, 2))
def sand_dune():
    """Very low smooth dune (0.35 m), walkable, with wind ripples."""
    def shape(t):
        return (1 - t * t) ** 1.8
    d = mound('dune', M('dune'), 1.42, 0.92, 0.35, rings=8, seg=40, p=2.2,
              shape=shape, amp=0.08, seed=6, freq=1.2)
    objs = [d]
    bpy.context.view_layer.update()
    for i, y0 in enumerate((-0.5, -0.12, 0.28)):
        pts, wid = [], []
        n = 9
        xr = 1.05 - abs(y0) * 0.7
        for k in range(n):
            x = -xr + 2 * xr * k / (n - 1)
            y = y0 + 0.08 * math.sin(x * 2.4 + i)
            pts.append((x, y, drop_z([d], x, y) + 0.006))
            wid.append(0.05 * math.sin(math.pi * k / (n - 1)) + 0.004)
        rib = L.ribbon('rip%d' % i, M('rock_peach'), pts, wid,
                       side=(0, 1, 0))
        objs.append(rib)
    objs.append(pebble('peb', 'rock_peach', (1.05, -0.62, 0.0), 0.08, seed=2))
    return objs


# =================================================================== cliff


def nest_ring(name, loc, R, r, n_sticks=14, seed=0, eggs=0, egg_r=0.11):
    """Round straw nest (ring + bed + poking sticks), optional eggs."""
    x0, y0, z0 = loc
    objs = [L.torus(name + '_ring', M('straw'), (x0, y0, z0 + r * 0.7), R, r,
                    seg=20, rseg=8, squash=0.75,
                    rfun=lambda th: 1 + 0.1 * math.sin(5 * th + seed) +
                    0.06 * math.sin(11 * th + 1))]
    objs.append(L.lathe(name + '_bed', M('straw_dark'),
                        [(0, z0 + 0.01), (R * 0.9, z0 + 0.02),
                         (R * 1.02, z0 + r * 0.5), (0, z0 + r * 0.55)],
                        seg=16, loc=(x0, y0, 0)))
    rng = random.Random(seed)
    for i in range(n_sticks):
        th = 2 * math.pi * i / n_sticks + rng.uniform(-0.1, 0.1)
        ph = rng.uniform(-0.2, 1.6)
        rr = R + r * 0.95 * math.cos(ph)
        c = Vector((x0 + rr * math.cos(th), y0 + rr * math.sin(th),
                    z0 + r * 0.7 + r * 0.7 * math.sin(ph)))
        t = Vector((-math.sin(th), math.cos(th), rng.uniform(-0.6, 0.6)))
        ln = rng.uniform(1.0, 1.4) * R * 0.6
        objs.append(L.plank('%s_st%d' % (name, i),
                            M('straw_dark' if i % 3 else 'wood'),
                            c - t * ln / 2, c + t * ln / 2, r * 0.13, r * 0.1,
                            bevel=0.0))
    for k in range(eggs):
        a = 2 * math.pi * k / max(eggs, 1) + 0.6
        d = R * 0.42 if eggs > 1 else 0.0
        e = C.ellipsoid('%s_egg%d' % (name, k),
                        M('egg_blue' if k % 2 == 0 else 'eggshell'),
                        (x0 + d * math.cos(a), y0 + d * math.sin(a),
                         z0 + r * 0.55 + egg_r * 1.1),
                        (egg_r, egg_r, egg_r * 1.3), seg=12, rings=8,
                        rot=(rng.uniform(-15, 15), rng.uniform(-15, 15), 0))
        objs.append(e)
        # three little spots on each egg (front/top, where the camera sees)
        bpy.context.view_layer.update()
        ec = Vector(e.location)
        for j, dd in enumerate(((0.2, -0.8, 0.6), (-0.5, -0.5, 0.75),
                                (0.55, -0.2, 0.85))):
            objs.append(C.decal_on('%s_eg%d_%d' % (name, k, j),
                                   M('paint_lilac' if k % 2 == 0 else
                                     'rock_peach'), e,
                                   ec + Vector(dd).normalized() * egg_r,
                                   dd, egg_r * 0.26, lift=0.003, seg=8))
    return objs


def grass_tuft(name, base, n=7, h=0.22, seed=0, mat='grass'):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        a = 2 * math.pi * i * 0.382 + rng.uniform(-0.2, 0.2)
        d = Vector((math.cos(a), math.sin(a), 0))
        hh = rng.uniform(0.6, 1.0) * h
        o = rng.uniform(0.04, 0.09)
        b = Vector(base)
        pts = [b + d * 0.01 - Vector((0, 0, 0.02)),
               b + d * o * 0.3 + Vector((0, 0, hh * 0.45)),
               b + d * o + Vector((0, 0, hh))]
        out.append(L.ribbon('%s_%d' % (name, i), M(mat), pts,
                            [0.075, 0.05, 0.0], side=(-d.y, d.x, 0)))
    return out


def cliff_stack(prefix, layers, n=48, wob=0.07, mats=('cliff_dark', 'cliff')):
    """Grey-lilac stone strata: [(z0, z1, hx, hy, (ox, oy), seed), ...]."""
    out = []
    for i, (z0, z1, hx, hy, off, sd) in enumerate(layers):
        pl = plan(hx, hy, p=2.6, n=n, amp=0.14 * min(1.0, hx), freq=1.0,
                  seed=sd, off=off)
        out.append(slab('%s%d' % (prefix, i), M(mats[i % 2]), pl, z0, z1,
                        bt=min(0.24, (z1 - z0) * 0.3), bb=0.07, bulge=0.05,
                        tseg=2, dome=0.05, wob=wob, wfreq=1.4, seed=sd))
    return out


def grass_cap(name, layer, z1, hx, hy, off, sd, n=48, grow=0.06, tseg=2):
    """Mossy grass icing on top of a stone stack: a thin soft slab a bit
    wider than the top layer, with the same outline."""
    pl = plan(hx + grow, hy + grow, p=2.6, n=n, amp=0.14 * min(1.0, hx),
              freq=1.0, seed=sd, off=off)
    return slab(name, M('grass'), pl, z1 - 0.12, z1 + 0.14, bt=0.12, bb=0.05,
                bulge=0.0, tseg=tseg, dome=0.08, wob=0.07, wfreq=1.4, seed=sd)


@define('prop_cliff', footprint=(4, 4), budget=6000)
def cliff():
    """Big grey-lilac cliff block (~6 m) with a grassy top, ledges that
    step back toward the front and two straw nests with eggs on them."""
    layers = [(0.0, 1.6, 1.9, 1.88, (0.0, 0.0), 31),
              (1.52, 2.95, 1.7, 1.5, (0.2, 0.42), 32),
              (2.86, 4.25, 1.5, 1.45, (-0.3, 0.45), 33),
              (4.16, 5.6, 1.3, 1.2, (-0.2, 0.72), 34)]
    objs = cliff_stack('c', layers, n=46)
    objs.append(grass_cap('cap', None, 5.6, 1.3, 1.2, (-0.2, 0.72), 34,
                          n=46))
    bpy.context.view_layer.update()
    rock = objs[:]
    # nests on the ledges (front-left low, front-right high)
    for i, (x, y, eg) in enumerate(((-0.75, -1.42, 2), (1.5, -0.35, 1))):
        z = drop_z(rock, x, y)
        objs.append(mound('moss%d' % i, M('moss'), 0.5, 0.36, 0.06, rings=3,
                          seg=16, loc=(x, y, z - 0.035)))
        objs += nest_ring('n%d' % i, (x, y, z), 0.27, 0.12, n_sticks=12,
                          seed=i + 3, eggs=eg, egg_r=0.11)
    # grass and a bush on top, tufts on the ledges
    zt = drop_z(rock, -0.4, 0.6)
    objs += L.canopy('bush', M('leaf'), (-0.5, 0.75, zt + 0.25),
                     (0.45, 0.4, 0.33), n=5, blob=(0.48, 0.62), seed=3,
                     lower_mat=M('leaf_dark'), lump=0.07, lower_z=-0.1,
                     spread=0.75, subdiv=2, core_subdiv=2)
    for i, (x, y) in enumerate(((0.5, 0.5), (-1.0, 0.1), (0.2, 1.2),
                                (1.55, -1.25), (0.3, -1.55), (-0.6, -0.65))):
        objs += grass_tuft('gt%d' % i, (x, y, drop_z(rock, x, y)), n=9,
                           h=0.36, seed=i)
    for i, (x, y, r) in enumerate(((1.65, -1.62, 0.22), (-1.7, -1.7, 0.15),
                                   (0.2, -1.95, 0.12))):
        objs.append(pebble('pb%d' % i, 'cliff', (x, y, 0), r, seed=40 + i))
    return objs


@define('prop_perch', footprint=(1, 1))
def perch():
    """Tall wooden perch pole (~3 m): a round landing pad with a straw rim
    on top (z = PERCH_TOP), three branch arms with leafy tips and a little
    birdhouse with a red roof hanging from one arm. Stone base."""
    objs = [mound('base', M('stone'), 0.42, 0.42, 0.2, rings=4, seg=20,
                  amp=0.03, seed=1)]
    H = PERCH_TOP - 0.08
    objs.append(L.lathe('pole', M('wood'), [(0, 0.0), (0.12, 0.0), (0.1, 0.4),
                                            (0.085, H * 0.6), (0.08, H),
                                            (0, H)], seg=12))
    for i, z in enumerate((0.9, 1.8)):
        objs.append(L.torus('band%d' % i, M('wood_dark'), (0, 0, z), 0.088,
                            0.025, seg=14, rseg=5))
    # landing pad: a flat round board on a short bracket, straw cushion
    objs.append(L.lathe('bracket', M('wood_dark'), [(0, H - 0.22),
                                                    (0.09, H - 0.22),
                                                    (0.2, H - 0.06),
                                                    (0, H - 0.06)], seg=12))
    objs.append(L.lathe('pad', M('wood'), L.round_corners(
        [(0, H - 0.08), (0.46, H - 0.08), (0.46, H + 0.02), (0, H + 0.02)],
        [0, 0.035, 0.035, 0], n=2), seg=22))
    objs.append(L.torus('rim', M('straw'), (0, 0, H + 0.04), 0.4, 0.065,
                        seg=22, rseg=6, squash=0.8,
                        rfun=lambda th: 1 + 0.12 * math.sin(6 * th)))
    objs.append(L.lathe('cushion', M('straw_dark'), [(0, H + 0.02),
                                                     (0.36, H + 0.02),
                                                     (0.3, H + 0.08),
                                                     (0, H + 0.08)], seg=18))
    # three branch arms with leafy tips
    arms = [(1.15, 200, 0.5), (1.75, -15, 0.55), (2.35, 105, 0.42)]
    for i, (z, a, ln) in enumerate(arms):
        d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
        p0 = Vector((0, 0, z))
        p1 = p0 + d * ln * 0.5 + Vector((0, 0, 0.12))
        p2 = p0 + d * ln + Vector((0, 0, 0.18))
        objs.append(C.tube('arm%d' % i, M('wood'), [p0, p1, p2],
                           [0.05, 0.04, 0.032], seg=8))
        objs += L.canopy('lf%d' % i, M('leaf'), tuple(p2 + Vector((0, 0, 0.06))),
                         (0.15, 0.14, 0.11), n=2, blob=(0.6, 0.7), seed=i,
                         lower_mat=M('leaf_dark'), spread=0.8, subdiv=2,
                         core_subdiv=1)
    # birdhouse hanging from the second arm
    d = Vector((math.cos(math.radians(-15)), math.sin(math.radians(-15)), 0))
    hp = Vector((0, 0, 1.75)) + d * 0.4 + Vector((0, 0, 0.12))
    objs.append(C.tube('string', M('rope'), [hp, hp - Vector((0, 0, 0.12))],
                       [0.01, 0.01], seg=4, cap=False))
    bh = []
    bh.append(L.rbox('bh_body', M('paint_mint'), (0, 0, -0.17),
                     (0.26, 0.24, 0.26), bevel=0.035))
    for s in (-1, 1):
        bh.append(L.rbox('bh_roof%d' % s, M('roof'), (s * 0.095, 0, -0.01),
                         (0.22, 0.32, 0.05), rot=(0, -s * 38, 0),
                         bevel=0.018))
    bh.append(C.cylinder('bh_hole', M('pupil'), (0, -0.118, -0.15), 0.05,
                         0.01, rot=(90, 0, 0), seg=12))
    bh.append(C.cylinder('bh_peg', M('wood_dark'), (0, -0.12, -0.25), 0.014,
                         0.07, rot=(90, 0, 0), seg=6))
    L.transform_objs(bh, loc=tuple(hp - Vector((0, 0, 0.1))), rot=(0, 0, -15))
    objs += bh
    return {'static': objs, 'empties': {'top': (0, 0, PERCH_TOP)}}


@define('prop_nest_pillar', footprint=(1, 1))
def nest_pillar():
    """Stone pillar (~2 m) of three lilac strata with a big straw nest on
    top (inner bed at z ~1.95)."""
    layers = [(0.0, 0.72, 0.4, 0.38, (0, 0), 51),
              (0.66, 1.32, 0.33, 0.32, (0.02, 0.01), 52),
              (1.26, 1.86, 0.37, 0.35, (-0.01, 0.0), 53)]
    objs = cliff_stack('s', layers, n=24, wob=0.035)
    objs.append(grass_cap('cap', None, 1.86, 0.37, 0.35, (-0.01, 0.0), 53,
                          n=24, grow=0.03))
    zt = drop_z(objs, 0, 0)
    objs += nest_ring('nest', (0, 0, zt - 0.03), 0.3, 0.13, n_sticks=16,
                      seed=5)
    objs += grass_tuft('gt', (0.3, -0.33, 0), n=5, h=0.2, seed=2)
    objs.append(pebble('pb', 'cliff', (-0.36, -0.3, 0), 0.1, seed=3))
    return objs


def heart_pts(s, n=24):
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - \
            math.cos(4 * t)
        out.append((x * s / 32, z * s / 32))
    return list(reversed(out))


@define('prop_aviary_arch', footprint=(3, 1))
def aviary_arch():
    """Garden arch for the aviary entrance: chunky white lattice posts and
    a double arched top (2.2 m clear inside, ~2.8 m tall), flowering vines
    climbing it, a pink heart on top."""
    objs = []
    X, Y = 1.22, 0.17
    Hp = 1.9
    for sx in (-1, 1):
        for sy in (-1, 1):
            objs.append(L.rbox('post%d%d' % (sx, sy), M('white'),
                               (sx * X, sy * Y, Hp / 2), (0.15, 0.15, Hp),
                               bevel=0.04, seg=1))
        objs.append(L.rbox('foot%d' % sx, M('white'), (sx * X, 0, 0.06),
                           (0.28, 0.56, 0.12), bevel=0.045, seg=1))
        for k in range(2):
            z = 0.62 + k * 0.7
            objs.append(L.plank('rung%d_%d' % (sx, k), M('white'),
                                (sx * X, -Y, z), (sx * X, Y, z), 0.06, 0.06,
                                bevel=0.02, seg=1))
    # arched top: two rails (front/back) + rungs
    R, rise = X, 0.78
    for sy in (-1, 1):
        pts = [(R * math.cos(math.radians(a)), sy * Y,
                Hp + rise * math.sin(math.radians(a)))
               for a in range(180, -1, -45)]
        objs.append(C.tube('rail%d' % sy, M('white'), pts, [0.08] * len(pts),
                           seg=7))
    for k, a in enumerate((135, 45)):
        x = R * math.cos(math.radians(a))
        z = Hp + rise * math.sin(math.radians(a))
        objs.append(L.plank('arung%d' % k, M('white'), (x, -Y, z), (x, Y, z),
                            0.055, 0.055, bevel=0.018, seg=1))
    h = L.extrude('heart', M('paint_pink'), heart_pts(0.38, n=14), 0.07,
                  bevel=0.025, seg=1)
    h.location = (0, -Y - 0.03, Hp + rise + 0.1)
    objs.append(h)
    # vines: wind up the front posts and along the front rail
    rng = random.Random(5)
    petals = ['petal_pink', 'petal_yellow', 'petal_lilac', 'petal_white']
    fi = 0
    for sx in (-1, 1):
        pts = []
        for k in range(5):
            t = k / 4
            z = 0.1 + t * (Hp - 0.1)
            a = t * 1.25 * 2 * math.pi + (0 if sx < 0 else math.pi)
            pts.append((sx * X + 0.11 * math.cos(a), -Y + 0.11 * math.sin(a), z))
        for a in ((150, 105) if sx < 0 else (30, 75)):
            pts.append((R * math.cos(math.radians(a)), -Y - 0.07,
                        Hp + (rise + 0.04) * math.sin(math.radians(a))))
        objs.append(C.tube('vine%d' % sx, M('plant_stem'), pts,
                           [0.032] * len(pts), seg=4))
        for j in range(1, len(pts)):
            p = Vector(pts[j])
            out = (p - Vector((sx * X, 0, p.z))) if j < 5 else \
                (p - Vector((0, 0, Hp)))
            out.y = -0.7
            out.normalize()
            lp = p + out * 0.08 + Vector((rng.uniform(-0.03, 0.03), 0,
                                          rng.uniform(-0.04, 0.04)))
            objs.append(L.sphere('leaf%d_%d' % (sx, j),
                                 M('leaf' if j % 3 else 'leaf_dark'), lp,
                                 0.16, seg=6, rings=4, squash=(1.0, 0.5, 0.72)))
            if j % 2 == 0:
                fp = p + out * 0.14 + Vector((0, -0.05, 0.0))
                tilt = (40, sx * rng.uniform(-25, 25))
                objs += flower_head('fl%d_%d' % (sx, j), petals[fi % 4], fp,
                                    0.13, tilt=tilt)
                fi += 1
    # leafy clumps at the feet
    for sx in (-1, 1):
        objs += L.canopy('clump%d' % sx, M('leaf'), (sx * (X + 0.05), -0.3, 0.14),
                         (0.3, 0.22, 0.18), n=3, blob=(0.55, 0.66), seed=sx + 4,
                         lower_mat=M('leaf_dark'), spread=0.8, subdiv=1,
                         core_subdiv=1)
    return objs


@define('prop_waterfall', footprint=(3, 2))
def waterfall():
    """Small lilac cliff (~3 m) at the back with a grassy top; a stream on
    top falls over the lip (`fall`, material `water`) into a round pool
    lined with stones at the front."""
    layers = [(0.0, 1.45, 1.45, 0.48, (0, 0.42), 61),
              (1.38, 2.8, 1.33, 0.44, (0.0, 0.47), 63)]
    objs = cliff_stack('w', layers, n=30, wob=0.05)
    band_paint(objs[0], [M('cliff_dark'), M('cliff')], [0.62, 0.78],
               pick=lambda i: 1 if i == 1 else 0)
    band_paint(objs[1], [M('cliff'), M('cliff_dark')], [2.0, 2.14],
               pick=lambda i: 1 if i == 1 else 0)
    objs.append(grass_cap('cap', None, 2.8, 1.33, 0.44, (0.0, 0.47), 63,
                          n=30, tseg=1))
    rock = objs[:]
    bpy.context.view_layer.update()
    ztop = drop_z(rock, 0, 0.5)
    # pool: stone basin, water surface, stones around
    PX, PY, PC = 0.86, 0.4, -0.47
    objs.append(L.lathe('basin', M('stone_dark'), [(0, 0.02), (1.0, 0.02),
                                                   (1.0, 0.1), (0, 0.1)],
                        seg=24, loc=(0, PC, 0), scale=(PX, PY, 1)))
    objs.append(L.lathe('pool', M('water'), [(0, 0.17), (1.0, 0.17),
                                             (1.0, 0.2), (0, 0.2)],
                        seg=24, loc=(0, PC, 0), scale=(PX + 0.02, PY + 0.02, 1)))
    rng = random.Random(4)
    nst = 10
    for i in range(nst):
        a = 2 * math.pi * i / nst + 0.3
        if math.sin(a) > 0.5 and abs(math.cos(a)) < 0.6:
            continue   # leave the back open where the fall lands
        r = rng.uniform(0.15, 0.2)
        x = (PX + 0.05) * math.cos(a)
        y = PC + (PY + 0.03) * math.sin(a)
        objs.append(L.lumpy('st%d' % i, M('stone' if i % 3 else 'cliff'),
                            (x, y, r * 0.55), (r, r * 0.85, r * 0.7),
                            subdiv=2, amp=0.12, seed=i, flat_bottom=-r * 0.6))
    # foam where the water lands
    for i in range(3):
        a = math.pi * (0.2 + 0.6 * i / 2)
        objs.append(L.sphere('foam%d' % i, M('foam'),
                             (0.3 * math.cos(a), -0.3 - 0.06 * math.sin(a),
                              0.22), 0.16 - 0.04 * (i % 2), seg=8, rings=5,
                             squash=(1, 0.8, 0.5)))
    # the water: stream on top (from the back) over the lip and down
    W = 0.56
    path = []
    yb = 0.7
    yl = -0.06           # front lip of the top layer
    for k in range(5):   # stream across the top
        y = yb + (yl - yb) * k / 4
        path.append(Vector((0, y, ztop + 0.03)))
    for k in range(1, 4):  # roll over the lip
        a = math.radians(90 * k / 3)
        path.append(Vector((0, yl - 0.12 * math.sin(a),
                            ztop + 0.03 - 0.12 * (1 - math.cos(a)))))
    nfall = 9
    ys, zs = path[-1].y, path[-1].z
    for k in range(1, nfall + 1):
        t = k / nfall
        path.append(Vector((0, ys - 0.12 * t - 0.06 * t * t, zs + (0.19 - zs) * t)))
    cols = 6
    verts, uvs = [], []
    lens = [0.0]
    for a, b in zip(path, path[1:]):
        lens.append(lens[-1] + (b - a).length)
    for i, p in enumerate(path):
        t = lens[i] / lens[-1]
        w = W * (1.0 + 0.25 * max(0.0, t - 0.4))
        tan = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        nrm = Vector((1, 0, 0)).cross(tan).normalized()
        for c in range(cols + 1):
            u = c / cols
            x = (u - 0.5) * w
            ripple = 0.018 * math.sin(u * math.pi * 5)
            verts.append(Vector((x, p.y, p.z)) + nrm * ripple)
            uvs.append((u, t))
    faces = []
    for i in range(len(path) - 1):
        for c in range(cols):
            a = i * (cols + 1) + c
            faces.append((a, a + 1, a + cols + 2, a + cols + 1))
    fall = L.mesh_obj('fall_sheet', verts, faces, M('water'))
    # face up on the stream / toward the camera (-Y) on the drop
    if fall.data.polygons[0].normal.z < 0:
        L.flip(fall)
    uv_grid(fall, uvs)
    # banks of the stream on top: two soft stone rolls
    for s in (-1, 1):
        objs.append(C.tube('bank%d' % s, M('cliff'),
                           [(s * W * 0.62, yb + 0.05, ztop - 0.02),
                            (s * W * 0.6, 0.3, ztop),
                            (s * W * 0.62, yl + 0.04, ztop - 0.03)],
                           [0.09, 0.1, 0.08], seg=5))
    for i, (x, y) in enumerate(((-0.95, 0.4), (0.9, 0.55),
                                (1.2, -0.75))):
        objs += grass_tuft('gt%d' % i, (x, y, drop_z(rock, x, y)), n=6,
                           h=0.28, seed=i + 2)
    objs += flower_head('fl0', 'petal_pink', (0.55, 0.6, ztop + 0.1), 0.1,
                        tilt=(30, 0), lite=True)
    objs += flower_head('fl1', 'petal_yellow', (-1.3, -0.5, 0.2), 0.1,
                        tilt=(30, 0), lite=True)
    return {'static': objs, 'named': {'fall': [fall]}}


# =================================================================== toys


def sweep_xz(name, mat, path, section, cap=True):
    """Sweep a closed 2D section [(s, h)] along a path in the XZ plane
    [(x, z)]: s runs along Y, h along the path's upward normal."""
    P = [Vector((x, 0, z)) for x, z in path]
    n = len(section)
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        nn = Vector((-t.z, 0, t.x))
        if nn.z < 0:
            nn = -nn
        rings.append([bm.verts.new(p + Vector((0, sy, 0)) + nn * sh)
                      for sy, sh in section])
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    if cap:
        bm.faces.new(rings[0])
        bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return L._bm_obj(bm, name, mat)


@define('prop_dino_slide', footprint=(3, 2))
def dino_slide():
    """Pastel playground slide sized for dinos: chunky toy-block stairs at
    the back climb to a tower platform (z 1.15) under a striped tent roof;
    the blue chute runs down the front half toward -X."""
    objs = []
    PZ = 1.15
    X0, X1 = 0.55, 1.42           # tower platform x range
    # platform + posts + roof
    objs.append(L.rbox('plat', M('white'), ((X0 + X1) / 2, 0, PZ - 0.06),
                       (X1 - X0, 1.9, 0.12), bevel=0.04))
    for x in (X0 + 0.07, X1 - 0.07):
        for y in (-0.88, 0.88):
            objs.append(L.rbox('post', M('paint_yellow'), (x, y, 1.05),
                               (0.12, 0.12, 2.1), bevel=0.035, seg=1))
    # side rails on the platform (front and right), leaving the chute and
    # stairs open
    objs.append(L.plank('railr', M('paint_yellow'), (X1 - 0.07, -0.88, PZ + 0.42),
                        (X1 - 0.07, 0.88, PZ + 0.42), 0.07, 0.07, bevel=0.025, seg=1))
    objs.append(L.plank('railf', M('paint_yellow'), (X0 + 0.07, -0.88, PZ + 0.42),
                        (X1 - 0.07, -0.88, PZ + 0.42), 0.07, 0.07, bevel=0.025, seg=1))
    roof = L.lathe('roof', M('paint_pink'), L.round_corners(
        [(0, 2.02), (0.82, 2.02), (0.86, 2.08), (0.08, 2.4), (0, 2.42)],
        [0, 0.03, 0.05, 0.05, 0], n=2), seg=16, loc=((X0 + X1) / 2, 0, 0),
        scale=(0.6, 1.2, 1))
    bpy.context.view_layer.update()
    C.apply_xf(roof)
    cx = (X0 + X1) / 2

    def stripe(c, nrm):
        a = math.atan2(c.y, c.x - cx) % (2 * math.pi)
        return int(a / (2 * math.pi / 8)) % 2
    L.paint_faces(roof, [M('paint_pink'), M('white')], stripe)
    objs.append(roof)
    objs.append(L.sphere('fin', M('paint_yellow'), (cx, 0, 2.48), 0.09,
                         seg=10, rings=6))
    # stairs: toy blocks along the back half, climbing toward +X
    cols = ['paint_mint', 'paint_lilac', 'paint_yellow', 'paint_blue',
            'paint_pink']
    nst = 5
    for i in range(nst):
        h = PZ * (i + 1) / (nst + 0.0) - 0.02
        x = -0.92 + i * 0.3
        objs.append(L.rbox('step%d' % i, M(cols[i]), (x + 0.15, 0.5, h / 2),
                           (0.3, 0.76, h), bevel=0.04, seg=1))
    # chute: a U channel down the front half from the platform to the
    # ground at x = -1.45
    path = []
    n = 14
    for k in range(n + 1):
        t = k / n
        x = X0 + 0.05 - t * (X0 + 0.05 + 1.47)
        u = min(1.0, t / 0.86)
        z = 0.14 + (PZ - 0.02 - 0.14) * (0.5 + 0.5 * math.cos(math.pi * u))
        path.append((x, z))
    W, Hw, T = 0.36, 0.2, 0.06
    sec = L.round_corners([(-W, Hw), (-W, -T), (W, -T), (W, Hw), (W - T, Hw),
                           (W - T, 0.0), (-W + T, 0.0), (-W + T, Hw)],
                          [0.03, 0.08, 0.08, 0.03, 0.03, 0.04, 0.04, 0.03],
                          n=2, closed=True)
    ch = sweep_xz('chute', M('paint_blue'), path, sec)
    L.transform_objs([ch], loc=(0, -0.52, 0))
    objs.append(ch)
    # rolled lip along the top of both walls
    for sy in (-1, 1):
        pts = [(x, -0.52 + sy * (W - T / 2), z + Hw + 0.01)
               for (x, z) in path[::3]]
        objs.append(C.tube('lip%d' % sy, M('white'), pts, [0.045] * len(pts),
                           seg=6))
    # legs under the chute
    for x in (-0.55,):
        z = 0.14 + (PZ - 0.16) * 0.5 * (1 + math.cos(math.pi * min(
            1.0, (X0 + 0.05 - x) / (X0 + 0.05 + 1.47) / 0.86)))
        objs.append(L.rbox('leg', M('paint_yellow'), (x, -0.52, z / 2),
                           (0.12, 0.12, z), bevel=0.035, seg=1))
    for sy in (-1, 1):
        objs.append(L.rbox('foot%d' % sy, M('paint_yellow'),
                           (-1.3, -0.52 + sy * 0.3, 0.05), (0.14, 0.14, 0.1),
                           bevel=0.04, seg=1))
    # star badge on the tower front
    star = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        r = 0.16 if k % 2 == 0 else 0.07
        star.append((r * math.cos(a), r * math.sin(a)))
    st = L.extrude('star', M('paint_yellow'), L.round_corners(
        star, [0.02, 0.0] * 5, n=1, closed=True), 0.04, bevel=0.012, seg=1)
    st.location = (cx, -0.97, PZ + 0.42)
    objs.append(st)
    return objs


@define('prop_mud_pool', footprint=(2, 2))
def mud_pool():
    """Round mud bath: lumpy earth rim, glossy brown mud with bubbles and
    a little rubber duck. Dinos walk in (no collider)."""
    objs = [L.torus('rim', M('soil'), (0, 0, 0.07), 0.8, 0.17, seg=32,
                    rseg=8, squash=0.55,
                    rfun=lambda th: 1 + 0.12 * math.sin(5 * th) +
                    0.07 * math.sin(9 * th + 1))]
    objs.append(L.lathe('mud', M('mud'), [(0, 0.1), (0.82, 0.1),
                                          (0.84, 0.05), (0, 0.03)], seg=32,
                        rfun=lambda th, z: 1 + 0.04 * math.sin(5 * th)))
    rng = random.Random(3)
    for i, (x, y, r) in enumerate(((-0.3, 0.2, 0.09), (0.15, 0.38, 0.06),
                                   (0.38, -0.05, 0.075), (-0.1, -0.35, 0.05),
                                   (-0.45, -0.15, 0.04))):
        objs.append(L.sphere('bub%d' % i, M('mud_light'), (x, y, 0.1), r,
                             seg=10, rings=6, squash=(1, 1, 0.75)))
        objs.append(L.sphere('bhl%d' % i, M('white'), (x - r * 0.35,
                                                       y - r * 0.3,
                                                       0.1 + r * 0.6),
                             r * 0.25, seg=6, rings=4, squash=(1, 1, 0.5)))
    for i, (x, y) in enumerate(((0.1, 0.1), (-0.25, -0.05))):
        objs.append(L.torus('ring%d' % i, M('mud_light'), (x, y, 0.105),
                            0.14 + 0.05 * i, 0.012, seg=18, rseg=4,
                            squash=0.4))
    for i, a in enumerate((2.3, 0.4, 4.2)):
        rr = 0.86 + rng.uniform(-0.02, 0.04)
        objs += grass_tuft('gt%d' % i, (rr * math.cos(a), rr * math.sin(a),
                                        0.12), n=6, h=0.24, seed=i)
    for i, (a, r) in enumerate(((1.2, 0.11), (3.6, 0.08), (5.3, 0.09))):
        objs.append(pebble('pb%d' % i, 'stone', (0.86 * math.cos(a),
                                                0.86 * math.sin(a), 0.08), r,
                           seed=i + 3))
    # rubber duck
    duck = [L.sphere('dbody', M('paint_yellow'), (0, 0, 0.07), 0.1, seg=12,
                     rings=8, squash=(1.25, 1, 0.75)),
            L.sphere('dhead', M('paint_yellow'), (0.06, 0, 0.16), 0.065,
                     seg=12, rings=8),
            L.sphere('dbeak', M('carrot'), (0.125, 0, 0.15), 0.035, seg=8,
                     rings=5, squash=(1.2, 1, 0.5)),
            L.sphere('dtail', M('paint_yellow'), (-0.12, 0, 0.11), 0.035,
                     seg=8, rings=5)]
    for s in (-1, 1):
        duck.append(L.sphere('deye%d' % s, M('pupil'), (0.095, s * 0.035, 0.18),
                             0.012, seg=6, rings=4))
    L.transform_objs(duck, loc=(0.32, -0.36, 0.05), rot=(0, 0, -60),
                     scale=1.6)
    objs += duck
    return objs


@define('prop_shower', footprint=(1, 1))
def shower():
    """Dino shower: mint pole that curves over into a big yellow shower
    head, two tap knobs, a round drain mat. Named `spray` = water drops
    (show while a dino showers)."""
    objs = [L.lathe('mat', M('paint_blue'), L.round_corners(
        [(0, 0), (0.46, 0), (0.46, 0.05), (0, 0.05)], [0, 0.02, 0.025, 0],
        n=2), seg=24)]
    for i, r in enumerate((0.36, 0.24)):
        objs.append(L.torus('mring%d' % i, M('white'), (0, 0, 0.05), r, 0.022,
                            seg=20, rseg=4, squash=0.6))
    objs.append(L.lathe('drain', M('metal'), [(0, 0.04), (0.1, 0.04),
                                              (0.1, 0.062), (0, 0.062)],
                        seg=14))
    for k in range(3):
        objs.append(L.rbox('slot%d' % k, M('metal_dark'),
                           ((k - 1) * 0.045, 0, 0.064), (0.022, 0.12, 0.006),
                           bevel=0.0))
    # pole
    py = 0.36
    pts = [(0, py, 0.0), (0, py, 1.2), (0, py, 2.0), (0, py - 0.04, 2.22),
           (0, py - 0.2, 2.34), (0, 0.04, 2.33), (0, -0.04, 2.24)]
    objs.append(C.tube('pole', M('paint_mint'), pts, [0.055] * len(pts),
                       seg=8))
    objs.append(L.lathe('pfoot', M('paint_mint'), L.round_corners(
        [(0, 0.0), (0.15, 0.0), (0.13, 0.08), (0.06, 0.16), (0, 0.16)],
        [0, 0.02, 0.03, 0.02, 0], n=2), seg=12, loc=(0, py, 0)))
    # shower head: wide cone opening downward, white face with nozzles
    hz = 2.2
    objs.append(L.lathe('head', M('paint_yellow'), L.round_corners(
        [(0, hz + 0.1), (0.07, hz + 0.1), (0.3, hz - 0.04), (0.3, hz - 0.08),
         (0, hz - 0.08)], [0, 0.04, 0.04, 0.02, 0], n=2), seg=20,
        loc=(0, -0.04, 0)))
    objs.append(L.lathe('face', M('white'), [(0, hz - 0.095), (0.27, hz - 0.095),
                                             (0.27, hz - 0.08), (0, hz - 0.08)],
                        seg=20, loc=(0, -0.04, 0)))
    for k in range(6):
        a = 2 * math.pi * k / 5
        rr = 0 if k == 5 else 0.16
        objs.append(L.sphere('noz%d' % k, M('paint_blue'),
                             (rr * math.cos(a), -0.04 + rr * math.sin(a),
                              hz - 0.1), 0.028, seg=6, rings=4,
                             squash=(1, 1, 0.5)))
    # taps
    for s, m in ((-1, 'paint_red'), (1, 'paint_blue')):
        objs.append(C.cylinder('tap%d' % s, M('metal'), (s * 0.06, py - 0.05,
                                                         1.05), 0.025, 0.07,
                               rot=(90, 0, 0), seg=8))
        objs.append(L.sphere('knob%d' % s, M(m), (s * 0.1, py - 0.12, 1.05),
                             0.06, seg=10, rings=7, squash=(1, 0.7, 1)))
    # spray: drops falling in a cone under the head
    rng = random.Random(7)
    spray = []
    for i in range(15):
        a = rng.uniform(0, 2 * math.pi)
        f = rng.uniform(0.15, 1.0)
        z = hz - 0.15 - f * (hz - 0.35)
        rr = 0.06 + 0.3 * f * rng.uniform(0.5, 1.0)
        spray.append(C.ellipsoid('drop%d' % i, M('water'),
                                 (rr * math.cos(a), -0.04 + rr * math.sin(a), z),
                                 (0.028, 0.028, 0.065), seg=6, rings=4))
    return {'static': objs, 'named': {'spray': spray}}


@define('prop_ball_pile', footprint=(1, 1))
def ball_pile():
    """Pile of colourful play balls, some with a white stripe."""
    cols = ['paint_red', 'paint_blue', 'paint_yellow', 'paint_mint',
            'paint_pink', 'paint_lilac']
    spec = []
    R = 0.15
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.3
        spec.append((0.29 * math.cos(a), 0.29 * math.sin(a), R, R))
    spec.append((0.0, 0.0, R + 0.02, R + 0.02))
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.8
        spec.append((0.15 * math.cos(a), 0.15 * math.sin(a), R * 2.3, R * 0.95))
    spec.append((0.02, -0.02, R * 3.55, R * 0.9))
    objs = []
    for i, (x, y, z, r) in enumerate(spec):
        b = L.sphere('ball%d' % i, M(cols[i % 6]), (x, y, z), r, seg=12,
                     rings=8)
        if i in (2, 7, 10):   # beach balls: white segments
            L.paint_faces(b, [M(cols[i % 6]), M('white')],
                          lambda c, nn: int(((math.atan2(nn.y, nn.x) + 7) %
                                             (2 * math.pi)) /
                                            (math.pi / 3)) % 2)
        objs.append(b)
    # two strays rolled away
    for i, (x, y, r, m) in enumerate(((0.38, -0.36, 0.1, 'paint_yellow'),
                                      (-0.4, -0.3, 0.08, 'paint_red'))):
        objs.append(L.sphere('stray%d' % i, M(m), (x, y, r), r, seg=12,
                             rings=8))
    return objs


@define('prop_tall_feeder', footprint=(1, 1))
def tall_feeder():
    """Tall hay rack for the brachio: tripod of legs and a pole up to a
    slatted basket at 2.45-2.95 m. Named `food` = the hay and leaves in
    the basket (hide when empty)."""
    objs = []
    top = 2.45
    objs.append(L.lathe('pole', M('wood'), [(0, 0), (0.1, 0), (0.08, 0.3),
                                            (0.075, top), (0, top)], seg=12))
    for k in range(3):
        a = 2 * math.pi * k / 3 + math.pi / 2
        d = Vector((math.cos(a), math.sin(a), 0))
        objs.append(L.plank('leg%d' % k, M('wood_dark'), d * 0.44 + Vector((0, 0, 0.02)),
                            Vector((0, 0, 1.0)), 0.08, 0.07, bevel=0.025,
                            up=(0, 0, 1), seg=1))
    for i, z in enumerate((0.7, 1.6)):
        objs.append(L.torus('band%d' % i, M('wood_dark'), (0, 0, z), 0.082,
                            0.025, seg=12, rseg=4))
    # basket: bottom dish + slats + two rings
    objs.append(L.lathe('dish', M('wood_dark'), L.round_corners(
        [(0, top - 0.1), (0.14, top - 0.1), (0.36, top + 0.04),
         (0.34, top + 0.08), (0, top + 0.05)], [0, 0.03, 0.03, 0.02, 0], n=2),
        seg=14))
    n = 10
    for k in range(n):
        a = 2 * math.pi * k / n
        d = Vector((math.cos(a), math.sin(a), 0))
        objs.append(L.plank('slat%d' % k, M('wood'),
                            d * 0.33 + Vector((0, 0, top + 0.02)),
                            d * 0.46 + Vector((0, 0, top + 0.56)),
                            0.07, 0.03, bevel=0.012, seg=1,
                            up=(d.x, d.y, 0)))
    for i, (z, r) in enumerate(((top + 0.2, 0.385), (top + 0.52, 0.455))):
        objs.append(L.torus('ring%d' % i, M('wood_dark'), (0, 0, z), r, 0.032,
                            seg=20, rseg=4))
    # food: hay mound with leaves and fern fronds poking out
    food = [L.lumpy('hay', M('straw'), (0, 0, top + 0.5), (0.42, 0.42, 0.24),
                    subdiv=3, amp=0.12, freq=2.5, seed=4, flat_bottom=-0.2)]
    rng = random.Random(9)
    for k in range(5):
        a = 2 * math.pi * k / 5 + rng.uniform(-0.2, 0.2)
        food.append(L.frond('fr%d' % k, M('fern' if k % 2 else 'leaf'),
                            (0.12 * math.cos(a), 0.12 * math.sin(a), top + 0.62),
                            a, rng.uniform(0.42, 0.5), 1.1, 1.35, 0.1,
                            teeth=4, comb=0.45, fold=0.3, thick=0.01))
    for k in range(4):
        a = 2 * math.pi * k / 4 + 0.9
        food.append(L.sphere('lf%d' % k, M('leaf_dark' if k % 2 else 'leaf'),
                             (0.26 * math.cos(a), 0.26 * math.sin(a),
                              top + 0.64), 0.11, seg=8, rings=5,
                             squash=(1, 1, 0.7)))
    return {'static': objs, 'named': {'food': food}}


@define('prop_scratch_post', footprint=(1, 1))
def scratch_post():
    """Thick padded scratching post (~1.6 m): two ridged rope sections
    between puffy pastel cushions with buttons, on a round wooden base,
    a pom-pom on a spring on top."""
    objs = [L.lathe('base', M('wood'), L.round_corners(
        [(0, 0), (0.44, 0), (0.44, 0.13), (0, 0.13)], [0, 0.04, 0.05, 0],
        n=2), seg=24)]
    objs.append(L.torus('trim', M('wood_dark'), (0, 0, 0.065), 0.445, 0.03,
                        seg=24, rseg=4))
    # rope column: ridged profile (one ridge per wrap)
    prof = [(0, 0.12)]
    z, k = 0.12, 0
    while z < 1.42:
        prof.append((0.205 if k % 2 == 0 else 0.235, z))
        z += 0.045
        k += 1
    prof.append((0, 1.42))
    objs.append(L.lathe('rope', M('rope'), prof, seg=12))
    # cushions (puffy pillows) at three heights
    for i, (z, h, m) in enumerate(((0.12, 0.26, 'paint_pink'),
                                   (0.76, 0.2, 'paint_lilac'),
                                   (1.36, 0.24, 'paint_mint'))):
        prof = L.round_corners([(0, z), (0.32, z), (0.345, z + h / 2),
                                (0.32, z + h), (0, z + h)],
                               [0, 0.08, 0.06, 0.08, 0], n=2)
        objs.append(L.lathe('cush%d' % i, M(m), prof, seg=16,
                            rfun=lambda th, zz: 1 + 0.05 * math.cos(6 * th)))
        for k in range(4):
            a = -math.pi / 2 + (k - 1.5) * math.pi / 3
            objs.append(L.sphere('btn%d_%d' % (i, k), M('white'),
                                 (0.345 * math.cos(a), 0.345 * math.sin(a),
                                  z + h / 2), 0.026, seg=6, rings=4))
    objs.append(L.sphere('dome', M('paint_mint'), (0, 0, 1.6), 0.27,
                         seg=16, rings=6, squash=(1, 1, 0.28)))
    objs.append(C.tube('spring', M('metal'), [(0, 0, 1.64), (0.025, 0, 1.7),
                                              (-0.025, 0, 1.76), (0, 0, 1.8)],
                       [0.016] * 4, seg=5))
    objs.append(L.sphere('pom', M('paint_yellow'), (0.0, 0, 1.86), 0.085,
                         seg=12, rings=8))
    return objs

# =================================================================== main


def build(name, out):
    d = DEFS[name]
    L.begin()
    res = d['fn']()
    if os.environ.get('HAB_TRIS'):
        parts = res['static'] if isinstance(res, dict) else res
        grp = {}
        for o in parts:
            k = ''.join(ch for ch in o.name.split('_')[0] if not ch.isdigit())
            grp[k] = grp.get(k, 0) + L.tris(o)
        print('[hab_b] breakdown', sorted(grp.items(), key=lambda kv: -kv[1]))
    empties = []
    if isinstance(res, dict):
        mesh = L.finish(name, res['static'])
        objs = [mesh] + [L.finish(k, v) for k, v in res.get('named', {}).items()]
        for k, loc in res.get('empties', {}).items():
            e = bpy.data.objects.new(k, None)
            bpy.context.scene.collection.objects.link(e)
            e.location = loc
            empties.append(e)
    else:
        mesh = L.finish(name, res)
        objs = [mesh]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts),
                 min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts),
                 max(p.z for p in pts)))
    nt = sum(L.tris(o) for o in objs if o.type == 'MESH')
    mats = sorted({m.name for o in objs for m in o.data.materials})
    flag = '' if nt <= d['budget'] else '  OVER BUDGET %d' % d['budget']
    print('[hab_b] %-20s tris %5d  mats %2d  x %.2f..%.2f  y %.2f..%.2f  '
          'z %.2f..%.2f%s' % (name, nt, len(mats), lo.x, hi.x, lo.y, hi.y,
                              lo.z, hi.z, flag))
    print('[hab_b]    nodes: %s   mats: %s' % (
        ', '.join(o.name for o in objs + empties), ', '.join(mats)))
    C.export_glb(os.path.join(out, name + '.glb'), objs + empties)
    return dict(name=name, tris=nt, mats=mats, footprint=d['footprint'],
                lo=tuple(round(v, 3) for v in lo),
                hi=tuple(round(v, 3) for v in hi))


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
            print('[hab_b] unknown', n)
            continue
        rows.append(build(n, out))
    if isinstance(A.get('summary'), str):
        import json
        with open(A['summary'], 'w') as f:
            json.dump(rows, f, indent=1)


main()
