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
    'cliff': '#bdb2d2', 'cliff_dark': '#9a8fb2', 'egg_blue': '#bfe6f7',
    'leaf_sage': '#a8cc6a', 'leaf_sage_dark': '#7fae55',
    'mud': ('#80543a', {'rough': 0.25}), 'mud_light': '#a8775a',
    'rope': '#ecc98c', 'foam': '#f4fbff',
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
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
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


def flower_head(name, petal, loc, r, petals=5, tilt=(0, 0), center='flower_center'):
    """Little 5-petal flower head (same shape as props.py flowers)."""
    k = petals / 2.0
    head = L.lathe(name, M(petal),
                   [(0, -0.018 * r / 0.12), (r * 0.9, -0.006 * r / 0.12),
                    (r, 0.01 * r / 0.12), (r * 0.75, 0.024 * r / 0.12),
                    (0, 0.027 * r / 0.12)],
                   seg=15, rfun=lambda th, zz: 0.55 + 0.45 * abs(math.cos(k * th)))
    ctr = L.sphere(name + '_c', M(center), (0, 0, 0.026 * r / 0.12), r * 0.32,
                   seg=6, rings=4, squash=(1, 1, 0.6))
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
                           tilt=tilt)
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
            out = plan(hx, hy, p=2.4, n=24, amp=0.05, freq=2.0,
                       seed=i + (5 if s > 0 else 0),
                       off=(s * X + s * 0.03 * (i % 2), 0.0))
            objs.append(slab('p%d_%d' % (s, i), M(m), out, z0, z1, bt=0.13,
                             bb=0.05, bulge=0.035, tseg=2, wob=0.04,
                             seed=i + 3 * s))
    pts = [(-X - 0.02, 0, 1.3), (-0.84, 0, 1.92), (-0.34, 0, 2.15),
           (0.34, 0, 2.15), (0.84, 0, 1.92), (X + 0.02, 0, 1.3)]
    span = C.tube('span', M('rock_peach'), pts,
                  [0.42, 0.39, 0.36, 0.36, 0.39, 0.42], seg=14,
                  flatten=[(1.25, 1.0)] * 6)
    wobble(span, 0.06, freq=2.2, seed=3)
    band_paint(span, [M('rock_terra'), M('rock_peach'), M('rock_cream')],
               [1.72, 1.95, 2.3], pick=lambda i: (0, 2, 1, 0)[i])
    objs.append(span)
    for i, (x, y, r, m) in enumerate(((-1.36, -0.34, 0.14, 'rock_peach'),
                                      (1.3, -0.36, 0.11, 'rock_cream'),
                                      (0.6, 0.32, 0.12, 'rock_terra'))):
        objs.append(pebble('pb%d' % i, m, (x, y, 0), r, seed=11 + i))
    objs += shrub('sh', (-0.5, -0.2, 0.18), (0.22, 0.2, 0.18), 6, n=4,
                  flowers=4)
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
        out = plan(2.0 + (0.0 if i % 2 else 0.04), hy, p=7.0, n=44,
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
    objs += shrub('sh', (0.35, 0.15, 3.66), (0.24, 0.22, 0.2), 8, n=4,
                  flowers=3)
    objs.append(pebble('b0', 'rock_peach', (-0.5, -0.62, 0), 0.17, seed=5))
    objs.append(pebble('b1', 'rock_cream', (1.3, -0.6, 0), 0.12, seed=6))
    return objs


@define('prop_boulder_red', footprint=(1, 1))
def boulder_red():
    """Round red-sand boulder with a cream stripe and a pebble."""
    r = L.lumpy('rock', M('rock_red'), (0, 0.02, 0.33), (0.44, 0.4, 0.36),
                subdiv=4, amp=0.1, freq=1.3, seed=4, flat_bottom=-0.3)
    band_paint(r, [M('rock_red'), M('rock_cream'), M('rock_peach')],
               [0.3, 0.38, 0.56], pick=lambda i: (0, 1, 0, 2)[i])
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
    d = mound('dune', M('sand'), 1.42, 0.92, 0.35, rings=8, seg=40, p=2.2,
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
        rib = L.ribbon('rip%d' % i, M('sand_dark'), pts, wid,
                       side=(0, 1, 0))
        objs.append(rib)
    objs.append(pebble('peb', 'rock_peach', (1.05, -0.62, 0.0), 0.08, seed=2))
    return objs


# =================================================================== main


def build(name, out):
    d = DEFS[name]
    L.begin()
    res = d['fn']()
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
