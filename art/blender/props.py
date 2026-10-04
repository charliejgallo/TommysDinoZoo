"""props.py - Tommy's Dino Zoo environment props and held items.

    cd art/blender
    Blender -b -P props.py -- [--only prop_fence,item_ball] [--out DIR]
    Blender -b -P props.py -- --list

Writes game/assets/models/<name>.glb, one per definition below, built from
the blocks in props_lib.py. Prints triangles and bounds of each model.

Conventions (see docs/ART-SPEC.md):
  * Props: origin = centre of the footprint on the ground; footprint in
    whole metres (listed next to each definition); front faces -Y in
    Blender (+Z in Godot). Fences span x = -0.5..+0.5 between post centres,
    so sections and posts line up on the 1 m grid (both ends of a section
    carry a post; a neighbour's post lands exactly on it).
  * Held items (`item_*`): origin = grip point (where the palm closes).
    Handle axis along +Z (Godot +Y); the item's face looks -Y like
    everything else. Long tools stick up/down along Z from the grip, bags
    and baskets hang below it. `item_pumpkin` is carried with both hands:
    its origin is its centre (between the palms).
  * Animated props: `prop_gate` has an armature `gate_rig` (bones `root`,
    `door`; the door hinges on the left post, x = -0.43) and actions
    `open` (0.5 s, closed -> open 105 deg, swings toward +Y = away from the
    camera / into the pen) and `close` (0.5 s, back). Rest pose = closed.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import props_lib as L  # noqa: E402
import tdz_common as C  # noqa: E402
from props_lib import M  # noqa: E402

DEFS = {}


def define(name, footprint=None, budget=3000):
    """Register a builder: it returns a list of objects (static prop) or a
    dict {'static': [...], 'rig': fn(static_obj) -> [objects to export]}."""
    def deco(fn):
        DEFS[name] = dict(fn=fn, footprint=footprint, budget=budget)
        return fn
    return deco


def spots(target, material, dirs, r, center, aspect=(1.0, 1.0)):
    """Flat decal discs on `target` in directions `dirs` from `center`."""
    bpy.context.view_layer.update()
    out = []
    c = Vector(center)
    for i, d in enumerate(dirs):
        d = Vector(d).normalized()
        rr = r[i] if isinstance(r, (list, tuple)) else r
        out.append(C.decal_on('%s_sp%d' % (target.name, i), material, target,
                              c + d * 0.3, d, rr, aspect=aspect, lift=0.004,
                              seg=12))
    return out


def heart_pts(s, n=28):
    """Heart outline in the (x, z) plane, about `s` metres wide."""
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - \
            math.cos(4 * t)
        out.append((x * s / 32, z * s / 32))
    return list(reversed(out))


# =================================================================== fences

FENCE_POST_H = 0.78


def _post_white(name, x, h=FENCE_POST_H, y=0.0):
    """Square soft post with a ball finial (white picket family)."""
    w = 0.15
    body = L.rbox(name, M('white'), (x, y, h / 2 - 0.02), (w, w, h + 0.04),
                  bevel=0.04, seg=2)
    collar = L.rbox(name + '_col', M('white'), (x, y, h - 0.01),
                    (w + 0.05, w + 0.05, 0.06), bevel=0.025, seg=2)
    ball = L.sphere(name + '_ball', M('paint_mint'), (x, y, h + 0.08), 0.08,
                    seg=14, rings=9)
    return [body, collar, ball]


def _picket(name, x, h, y=-0.04, w=0.13, z0=0.05, mat='white'):
    r = w / 2
    pts = [(-r, 0.0), (r, 0.0)] + L.arc_pts(0, h - r, r, 0, 180, 8)[:]
    pts = L.round_corners(pts, [0.0, 0.0] + [0.0] * 9, n=2, closed=True)
    ob = L.extrude(name, M(mat), pts, 0.045, bevel=0.015, seg=2)
    ob.location = (x, y, z0)
    return ob


@define('prop_fence', footprint=(1, 1))
def fence():
    """White picket fence: 1 m section, posts at x = +-0.5."""
    objs = _post_white('pl', -0.5) + _post_white('pr', 0.5)
    for i, z in enumerate((0.2, 0.5)):
        objs.append(L.plank('rail%d' % i, M('white'), (-0.5, 0.02, z),
                            (0.5, 0.02, z), 0.05, 0.09, bevel=0.018))
    for i, x in enumerate((-0.25, 0.0, 0.25)):
        objs.append(_picket('pk%d' % i, x, 0.62 + (0.03 if x == 0 else 0)))
    return objs


@define('prop_fence_post', footprint=(1, 1))
def fence_post():
    """Single post for ends and corners (same as a section's posts)."""
    return _post_white('p', 0.0)


@define('prop_gate', footprint=(1, 1))
def gate():
    """Picket gate between two taller posts; the door is rigged."""
    H = 0.95
    static = _post_white('pl', -0.5, h=H) + _post_white('pr', 0.5, h=H)
    door = []
    x0, x1 = -0.425, 0.425
    for i, z in enumerate((0.2, 0.5)):
        door.append(L.plank('drail%d' % i, M('white'), (x0, 0.02, z),
                            (x1, 0.02, z), 0.05, 0.09, bevel=0.018))
    # brace
    door.append(L.plank('brace', M('white'), (x0 + 0.06, 0.02, 0.22),
                        (x1 - 0.06, 0.02, 0.49), 0.035, 0.06, bevel=0.012))
    xs = (-0.33, -0.165, 0.0, 0.165, 0.33)
    for i, x in enumerate(xs):
        hh = 0.6 + 0.12 * math.cos(x / 0.33 * math.pi / 2)
        door.append(_picket('dpk%d' % i, x, hh, w=0.115))
    heart = L.extrude('heart', M('paint_pink'), heart_pts(0.17), 0.03,
                      bevel=0.01, seg=2)
    heart.location = (0, -0.08, 0.36)
    door.append(heart)

    def rig(body_static, body_door):
        hx = -0.44
        arm = C.armature('gate_rig', [
            ('root', (0, 0, 0), (0, 0, 0.3), None),
            ('door', (hx, 0, 0.1), (hx, 0, 0.6), 'root'),
        ])
        C.skin_rigid(body_static, 'root')
        C.skin_rigid(body_door, 'door')
        body = C.bind('prop_gate', arm, [body_static, body_door])
        C.action(arm, 'open', 15, {0: {'door': (0, 0, 0)},
                                   15: {'door': (0, 105, 0)}})
        C.action(arm, 'close', 15, {0: {'door': (0, 105, 0)},
                                    15: {'door': (0, 0, 0)}})
        return [arm, body]
    return {'static': static, 'door': door, 'rig': rig}


def _post_log(name, x, h=0.8, y=0.0, r=0.075):
    return L.post(name, M('wood'), (x, y, 0), h, r, seg=12, top=0.7)


@define('prop_fence_wood', footprint=(1, 1))
def fence_wood():
    """Natural wood ranch fence (log posts, two chunky rails)."""
    objs = [_post_log('pl', -0.5), _post_log('pr', 0.5)]
    for i, z in enumerate((0.3, 0.6)):
        objs.append(L.plank('rail%d' % i, M('wood_dark'), (-0.56, -0.08, z),
                            (0.56, -0.08, z + (0.015 if i else -0.01)),
                            0.05, 0.11, bevel=0.025))
    return objs


@define('prop_fence_wood_post', footprint=(1, 1))
def fence_wood_post():
    return [_post_log('p', 0.0)]


# =================================================================== trees


def _trunk(h, r0, r1, lean=(0.0, 0.0), roots=3, seed=1, mat='bark'):
    rng = random.Random(seed)
    lx, ly = lean
    pts = [(0, 0, -0.05), (lx * 0.2, ly * 0.2, h * 0.3),
           (lx * 0.7, ly * 0.7, h * 0.7), (lx, ly, h)]
    objs = [C.tube('trunk', M(mat), pts, [r0, r0 * 0.85, r1 * 1.05, r1],
                   seg=12, cap=False)]
    for i in range(roots):
        a = 2 * math.pi * i / roots + rng.uniform(-0.3, 0.3)
        objs.append(C.tube('root%d' % i, M(mat),
                           [(0, 0, 0.3), (math.cos(a) * r0 * 1.2,
                                          math.sin(a) * r0 * 1.2, 0.06),
                            (math.cos(a) * r0 * 1.7, math.sin(a) * r0 * 1.7,
                             0.0)],
                           [r0 * 0.55, r0 * 0.38, r0 * 0.2], seg=6,
                           cap=False))
    return objs


@define('prop_tree_round', footprint=(1, 1), budget=4000)
def tree_round():
    """Big round leafy tree (~3.5 m); trunk `bark`, crown `leaf`."""
    objs = _trunk(2.0, 0.24, 0.15, lean=(0.05, 0.0), seed=3)
    objs.append(C.tube('branch', M('bark'), [(0.03, 0, 1.4), (0.35, -0.05, 1.8),
                                            (0.55, -0.05, 2.1)],
                       [0.08, 0.06, 0.04], seg=7, cap=False))
    objs += L.canopy('crown', M('leaf'), (0.05, 0.0, 2.38), (1.15, 1.08, 0.98),
                     n=10, blob=(0.42, 0.55), seed=7, lower_mat=M('leaf_dark'),
                     lower_z=-0.05)
    return objs


@define('prop_tree_fruit', footprint=(1, 1), budget=4000)
def tree_fruit():
    """Apple tree: same family, rounder crown, red apples."""
    objs = _trunk(1.9, 0.22, 0.14, lean=(-0.04, 0.02), seed=5)
    crown = L.canopy('crown', M('leaf'), (0.0, 0.0, 2.25), (1.05, 1.0, 0.92),
                     n=7, blob=(0.46, 0.6), seed=11, lower_mat=M('leaf_dark'),
                     lower_z=-0.05)
    objs += crown
    bpy.context.view_layer.update()

    def apple(i, loc, nrm):
        p = loc + nrm * 0.05
        a = L.sphere('apple%d' % i, M('apple'), p, 0.125, seg=8, rings=6,
                     squash=(1, 1, 0.9))
        st = C.cylinder('stem%d' % i, M('wood_dark'),
                        (p.x, p.y, p.z + 0.09), 0.014, 0.05, seg=4)
        return [a, st]
    # favour the sides the game camera sees (front -Y and top)
    rng = random.Random(4)
    dirs = []
    while len(dirs) < 400:
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 0.45),
                    rng.uniform(-0.25, 0.8)))
        if 0.2 < d.length <= 1:
            dirs.append(d)
    objs += L.scatter_on(crown, 13, 4, apple, zmin=1.6, min_gap=0.36,
                         center=(0, 0, 2.15), dirs=dirs)
    return objs


@define('prop_palm', footprint=(1, 1), budget=4000)
def palm():
    """Cartoon palm: ringed curved trunk, drooping leaves, coconuts."""
    N = 9
    H = 2.7
    pts, radii = [], []
    for i in range(N):
        for f, s in ((0.0, 0.84), (0.78, 1.0)):
            t = (i + f) / N
            pts.append((0.5 * t * t, 0.12 * t * t, H * t))
            radii.append((0.17 - 0.06 * t) * s)
    top = Vector(pts[-1])
    objs = [C.tube('trunk', M('bark'), pts, radii, seg=10)]
    objs.append(L.sphere('crown', M('leaf_dark'), top + Vector((0, 0, 0.05)),
                         0.15, seg=12, rings=8))
    rng = random.Random(5)
    n = 8
    for i in range(n):
        phi = 2 * math.pi * i / n + rng.uniform(-0.15, 0.15)
        objs.append(L.frond('leaf%d' % i, M('leaf'), top + Vector((0, 0, 0.08)),
                            phi, rng.uniform(1.15, 1.35), 0.55, 1.25, 0.24,
                            teeth=7, comb=0.35, fold=0.25, thick=0.012))
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.4
        objs.append(L.sphere('coco%d' % i, M('coconut'),
                             top + Vector((0.12 * math.cos(a),
                                           0.12 * math.sin(a), -0.12)),
                             0.1, seg=10, rings=7))
    return objs


@define('prop_fern', footprint=(1, 1))
def fern():
    """Prehistoric fern clump (herbivore food)."""
    rng = random.Random(21)
    objs = []
    n = 10
    for i in range(n):
        phi = 2 * math.pi * i / n + rng.uniform(-0.15, 0.15)
        inner = i % 2 == 0
        objs.append(L.frond(
            'fr%d' % i, M('fern' if inner else 'fern_dark'), (0, 0, 0.03), phi,
            rng.uniform(0.62, 0.72) if inner else rng.uniform(0.5, 0.58),
            rng.uniform(1.6, 1.9) if inner else rng.uniform(1.05, 1.2),
            rng.uniform(1.5, 1.65) if inner else rng.uniform(1.05, 1.15),
            0.13, teeth=6, comb=0.5, fold=0.3,
            thick=0.01))
    for k in range(2):
        phi = math.pi * k + 0.5
        d = Vector((math.cos(phi), math.sin(phi), 0))
        pts, rad = [], []
        for j in range(7):
            s = j / 6
            if s < 0.5:
                u = s / 0.5
                p = d * 0.03 + Vector((0, 0, 0.3 * u))
            else:
                u = (s - 0.5) / 0.5
                ang = u * 1.6 * math.pi
                R = 0.06 * (1 - 0.6 * u)
                p = d * 0.03 + Vector((0, 0, 0.3)) + d * (R * math.sin(ang)) + \
                    Vector((0, 0, R * (1 - math.cos(ang))))
            pts.append(tuple(p))
            rad.append(0.018 * (1 - 0.5 * s))
        objs.append(C.tube('fid%d' % k, M('fern'), pts, rad, seg=5))
    return objs


def _bush(name, center, radii, seed, n=6):
    return L.canopy(name, M('leaf'), center, radii, n=n, blob=(0.48, 0.62),
                    seed=seed, seg=12, rings=8, lower_mat=M('leaf_dark'),
                    lower_z=-0.1, spread=0.75)


@define('prop_bush', footprint=(1, 1))
def bush():
    return _bush('bush', (0, 0, 0.36), (0.48, 0.44, 0.36), 3)


@define('prop_berry_bush', footprint=(1, 1))
def berry_bush():
    objs = _bush('bush', (0, 0, 0.36), (0.48, 0.44, 0.36), 9)
    bpy.context.view_layer.update()

    def cluster(i, loc, nrm):
        t = nrm.cross(Vector((0, 0, 1)))
        if t.length < 1e-3:
            t = Vector((1, 0, 0))
        t.normalize()
        b = nrm.cross(t)
        out = []
        for k in range(3):
            a = 2 * math.pi * k / 3 + i
            p = loc + nrm * 0.035 + (t * math.cos(a) + b * math.sin(a)) * 0.045
            out.append(L.sphere('ber%d_%d' % (i, k), M('berry'), p, 0.05,
                                seg=8, rings=6))
        return out
    objs += L.scatter_on(objs[:], 9, 2, cluster, zmin=0.3, min_gap=0.24,
                         center=(0, 0, 0.3))
    return objs


def _flower(name, base, h, r, petal, lean=(0, 0), petals=5, tilt=(0, 0)):
    x, y, z = base
    top = (x + lean[0], y + lean[1], z + h)
    objs = [C.tube(name + '_stem', M('plant_stem'),
                   [(x, y, z - 0.02), (x + lean[0] * 0.3, y + lean[1] * 0.3,
                                       z + h * 0.5), top],
                   [0.016, 0.014, 0.012], seg=5, cap=False)]
    k = petals / 2.0
    head = L.lathe(name + '_head', M(petal),
                   [(0, -0.02), (r * 0.55, -0.018), (r * 0.95, 0.0),
                    (r, 0.012), (r * 0.8, 0.025), (0, 0.03)],
                   seg=20, rfun=lambda th, zz: 0.55 + 0.45 * abs(math.cos(k * th)))
    ctr = L.sphere(name + '_c', M('flower_center'), (0, 0, 0.028), r * 0.32,
                   seg=8, rings=5, squash=(1, 1, 0.6))
    L.transform_objs([head, ctr], loc=top, rot=(tilt[0], tilt[1], 0))
    objs += [head, ctr]
    return objs


@define('prop_flowers', footprint=(1, 1))
def flowers():
    """A cluster of pastel flowers with leaves."""
    rng = random.Random(8)
    objs = []
    spec = [((-0.18, -0.12), 0.34, 'petal_pink'), ((0.14, -0.16), 0.28,
                                                   'petal_yellow'),
            ((0.02, 0.1), 0.42, 'petal_lilac'), ((-0.22, 0.18), 0.3,
                                                 'petal_white'),
            ((0.26, 0.14), 0.36, 'petal_pink'), ((0.0, -0.3), 0.22,
                                                 'petal_lilac')]
    for i, ((x, y), h, pm) in enumerate(spec):
        lean = (x * 0.25, y * 0.25)
        objs += _flower('fl%d' % i, (x, y, 0), h, rng.uniform(0.085, 0.1), pm,
                        lean=lean, tilt=(rng.uniform(-18, 6),
                                         rng.uniform(-10, 10)))
    for i in range(6):
        a = 2 * math.pi * i / 6 + 0.3
        d = Vector((math.cos(a), math.sin(a), 0))
        L_ = rng.uniform(0.22, 0.3)
        pts = [tuple(d * 0.02), tuple(d * L_ * 0.5 + Vector((0, 0, 0.1))),
               tuple(d * L_ + Vector((0, 0, 0.06)))]
        objs.append(L.blade('lf%d' % i, M('leaf'), pts, 0.045, thick=0.25,
                            seg=6))
    return objs


@define('prop_rock', footprint=(1, 1))
def rock():
    """Round mossy rock with a pebble."""
    r = L.lumpy('rock', M('stone'), (0, 0, 0.27), (0.43, 0.37, 0.32),
                subdiv=4, amp=0.12, freq=1.4, seed=2, flat_bottom=-0.25)
    moss = L.shell_cap(r, 'moss', M('moss'),
                       lambda co, n: co.z + 0.05 * math.sin(co.x * 9) +
                       0.04 * math.cos(co.y * 11) > 0.43 and n.z > 0.2,
                       offset=0.012)
    peb = L.lumpy('peb', M('stone'), (0.36, -0.22, 0.07), (0.12, 0.1, 0.09),
                  subdiv=3, amp=0.1, seed=5, flat_bottom=-0.06)
    return [r, moss, peb]


@define('prop_grass_tuft', footprint=(1, 1))
def grass_tuft():
    """Tiny grass tuft for scattering (~0.25 m)."""
    rng = random.Random(4)
    objs = []
    n = 8
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.2, 0.2)
        d = Vector((math.cos(a), math.sin(a), 0))
        h = rng.uniform(0.15, 0.27)
        o = rng.uniform(0.05, 0.11)
        pts = [d * 0.01 - Vector((0, 0, 0.01)),
               d * o * 0.25 + Vector((0, 0, h * 0.4)),
               d * o * 0.6 + Vector((0, 0, h * 0.75)), d * o + Vector((0, 0, h))]
        side = Vector((-d.y, d.x, 0))
        objs.append(L.ribbon('bl%d' % i, M('grass'), pts,
                             [0.05, 0.045, 0.03, 0.0], side=side))
    return objs


def _mushroom(name, x, y, h, R, rot=(0, 0)):
    rs = R * 0.38
    stem = L.lathe(name + '_stem', M('white'),
                   L.round_corners([(0, 0), (rs * 1.2, 0), (rs, h * 0.5),
                                    (rs * 0.85, h), (0, h)], 0.02),
                   seg=12)
    prof = [(0, h - 0.015), (R * 0.7, h - 0.01), (R, h + 0.015)]
    for k in range(1, 7):
        a = math.pi / 2 * k / 6
        prof.append((R * math.cos(a), h + 0.015 + R * 0.75 * math.sin(a)))
    cap = L.lathe(name + '_cap', M('shroom'), prof, seg=18)
    for o in (stem, cap):
        o.location = (x, y, 0)
        o.rotation_euler = (math.radians(rot[0]), math.radians(rot[1]), 0)
    bpy.context.view_layer.update()
    ctr = Vector((x, y, h + 0.015))
    dirs = [(0, 0, 1), (0.7, -0.4, 0.6), (-0.7, -0.35, 0.6), (0.1, -0.85, 0.5),
            (-0.4, 0.7, 0.6), (0.7, 0.6, 0.5)]
    sp = spots(cap, M('white'), dirs, R * 0.2, ctr)
    return [stem, cap] + sp


@define('prop_mushroom', footprint=(1, 1))
def mushroom():
    """Three cute spotted mushrooms."""
    return (_mushroom('m0', 0.0, 0.02, 0.3, 0.17, rot=(-4, 3)) +
            _mushroom('m1', 0.2, -0.12, 0.18, 0.11, rot=(-6, 12)) +
            _mushroom('m2', -0.17, -0.12, 0.12, 0.08, rot=(-8, -14)))


# =================================================================== farm


@define('prop_trough', footprint=(2, 1))
def trough():
    """Wooden feeding trough on crossed legs."""
    body = L.hollow_box('body', M('wood'), M('wood_dark'), (0, 0, 0.16),
                        (1.6, 0.62, 0.34), 0.07, 0.24, corner=0.1, bevel=0.025)
    objs = [body]
    for x in (-0.6, 0.6):
        for s in (-1, 1):
            objs.append(L.plank('leg', M('wood_dark'), (x, s * 0.36, -0.02),
                                (x, -s * 0.18, 0.32), 0.08, 0.07,
                                bevel=0.02, up=(1, 0, 0)))
    # rim bands
    for x in (-0.45, 0.45):
        objs.append(L.rbox('band', M('wood_dark'), (x, 0, 0.33),
                           (0.07, 0.66, 0.36), bevel=0.02))
    return objs


@define('prop_water_trough', footprint=(2, 1))
def water_trough():
    """Rounded stone water trough with a `water` surface."""
    objs = [L.hollow_box('body', M('stone'), M('stone_dark'), (0, 0, 0),
                         (1.62, 0.7, 0.44), 0.09, 0.3, corner=0.16,
                         bevel=0.03)]
    w = L.rbox('water', M('water'), (0, 0, 0.355), (1.46, 0.54, 0.03),
               bevel=0.0)
    objs.append(w)
    for i, (x, y, s) in enumerate(((-0.4, -0.08, 0.09), (0.3, 0.1, 0.07),
                                   (0.5, -0.12, 0.05))):
        objs.append(C.ellipsoid('glint%d' % i, M('white'), (x, y, 0.372),
                                (s * 1.6, s * 0.7, 0.004), seg=12, rings=4))
    # front plaque: a little paw/heart
    h = L.extrude('heart', M('paint_blue'), heart_pts(0.14), 0.03,
                  bevel=0.008, seg=1)
    h.location = (0, -0.36, 0.2)
    objs.append(h)
    return objs


@define('prop_hay', footprint=(1, 1))
def hay():
    """Round hay bale lying on its side, with twine and end spirals."""
    R, Lh = 0.42, 0.4
    prof = L.round_corners([(0, -Lh), (R, -Lh), (R, Lh), (0, Lh)], 0.1, n=3)
    bale = L.lathe('bale', M('straw'), prof, seg=26,
                   rfun=lambda th, z: 1 + 0.025 * math.sin(7 * th + z * 5))
    bale.rotation_euler = (0, math.radians(90), 0)
    bale.location = (0, 0, R)
    objs = [bale]
    for x in (-0.2, 0.2):
        objs.append(L.torus('twine', M('paint_red'), (x, 0, R), R + 0.008,
                            0.016, seg=26, rseg=5, rot=(0, 90, 0)))
    for s in (-1, 1):
        pts = []
        for k in range(12):
            t = k / 11
            a = t * 2.4 * 2 * math.pi
            rr = 0.04 + 0.27 * t
            pts.append((s * (Lh + 0.004), rr * math.cos(a), R + rr * math.sin(a)))
        objs.append(C.tube('spiral', M('straw_dark'), pts,
                           [0.015] * len(pts), seg=4))
    rng = random.Random(3)
    for i in range(5):
        a = rng.uniform(0.3, 2.8)
        x = rng.uniform(-0.3, 0.3)
        d = Vector((0, math.cos(a), math.sin(a)))
        b = Vector((x, 0, R)) + d * (R - 0.01)
        objs.append(L.blade('tuft%d' % i, M('straw'), [tuple(b), tuple(
            b + d * 0.06 + Vector((rng.uniform(-0.04, 0.04), 0, 0.02))),
            tuple(b + d * 0.1 + Vector((rng.uniform(-0.06, 0.06), 0, 0.03)))],
            0.016, thick=0.4, seg=4, tip=0.2))
    return objs


@define('prop_nest', footprint=(2, 2))
def nest():
    """Dino sleeping nest: lumpy straw ring, soft bed, poking sticks."""
    objs = [L.torus('ring', M('straw'), (0, 0, 0.16), 0.62, 0.24, seg=32,
                    rseg=10, squash=0.72,
                    rfun=lambda th: 1 + 0.1 * math.sin(5 * th) +
                    0.06 * math.sin(11 * th + 1))]
    objs.append(L.lathe('bed', M('straw_dark'),
                        [(0, 0.02), (0.55, 0.03), (0.64, 0.08), (0, 0.1)],
                        seg=28))
    rng = random.Random(7)
    for i in range(26):
        th = 2 * math.pi * i / 26 + rng.uniform(-0.1, 0.1)
        ph = rng.uniform(-0.2, 1.6)
        rr = 0.62 + 0.23 * math.cos(ph)
        c = Vector((rr * math.cos(th), rr * math.sin(th),
                    0.16 + 0.17 * math.sin(ph)))
        tdir = Vector((-math.sin(th), math.cos(th), rng.uniform(-0.6, 0.6)))
        ln = rng.uniform(0.22, 0.34)
        objs.append(L.plank('stick%d' % i, M('straw_dark' if i % 3 else 'wood'),
                            c - tdir * ln / 2, c + tdir * ln / 2, 0.025, 0.02,
                            bevel=0.0))
    return objs


@define('prop_incubator', footprint=(1, 1))
def incubator():
    """Cute egg incubator: pastel base, glass dome, egg cup, knobs, light."""
    base = L.lathe('base', M('paint_mint'), L.round_corners(
        [(0, 0.04), (0.34, 0.04), (0.38, 0.12), (0.36, 0.42), (0.3, 0.46),
         (0, 0.46)], [0, 0.04, 0.05, 0.05, 0.03, 0], n=2), seg=24)
    objs = [base]
    for i in range(4):
        a = math.pi / 4 + i * math.pi / 2
        objs.append(L.sphere('foot%d' % i, M('paint_pink'),
                             (0.27 * math.cos(a), 0.27 * math.sin(a), 0.05),
                             0.06, seg=10, rings=6, squash=(1, 1, 0.8)))
    objs.append(L.torus('trim', M('paint_pink'), (0, 0, 0.2), 0.372, 0.03,
                        seg=28, rseg=6))
    objs.append(L.torus('ring', M('metal'), (0, 0, 0.47), 0.3, 0.035,
                        seg=28, rseg=8))
    # front panel with knobs and a light
    panel = L.extrude('panel', M('white'), L.round_corners(
        [(-0.17, 0.0), (0.17, 0.0), (0.17, 0.13), (-0.17, 0.13)], 0.04, n=2,
        closed=True), 0.05, bevel=0.012)
    panel.location = (0, -0.355, 0.255)
    panel.rotation_euler = (math.radians(-4), 0, 0)
    objs.append(panel)
    for i, (x, m) in enumerate(((-0.1, 'paint_yellow'), (0.0, 'paint_blue'))):
        objs.append(C.cylinder('knob%d' % i, M(m), (x, -0.38, 0.32), 0.032,
                               0.04, rot=(90, 0, 0), seg=12))
    objs.append(L.sphere('led', M('led'), (0.1, -0.385, 0.32), 0.03, seg=10,
                         rings=6))
    # egg cup with a straw cushion
    objs.append(L.lathe('cup', M('white'), [(0, 0.45), (0.13, 0.46),
                                            (0.15, 0.53), (0.12, 0.54),
                                            (0, 0.5)], seg=20))
    objs.append(L.torus('cushion', M('straw'), (0, 0, 0.53), 0.12, 0.035,
                        seg=20, rseg=6))
    # glass dome + handle
    prof = [(0.3, 0.47)]
    for k in range(1, 9):
        a = math.pi / 2 * k / 8
        prof.append((0.3 * math.cos(a), 0.47 + 0.36 * math.sin(a)))
    objs.append(L.lathe('dome', M('glass'), prof, seg=24))
    objs.append(L.sphere('handle', M('paint_pink'), (0, 0, 0.86), 0.05,
                         seg=12, rings=8))
    return objs


@define('prop_board', footprint=(1, 1))
def board():
    """Missions board: framed cork board on posts, little roof, papers."""
    objs = []
    for x in (-0.42, 0.42):
        objs.append(L.rbox('post', M('wood'), (x, 0, 0.9), (0.1, 0.1, 1.8),
                           bevel=0.03))
    objs.append(L.rbox('panel', M('cork'), (0, 0, 1.14), (0.76, 0.05, 0.62),
                       bevel=0.012))
    fr = [((-0.4, 0.84), (0.4, 0.84)), ((-0.4, 1.44), (0.4, 1.44))]
    for i, (a, b) in enumerate(fr):
        objs.append(L.plank('fr%d' % i, M('wood_dark'), (a[0], -0.005, a[1]),
                            (b[0], -0.005, b[1]), 0.08, 0.07, bevel=0.02,
                            up=(0, 0, 1)))
    # roof: two slabs meeting at a rounded ridge
    for s in (-1, 1):
        objs.append(L.plank('roof%d' % s, M('roof'), (0, s * 0.02, 2.02),
                            (0, s * 0.36, 1.66), 1.2, 0.07, bevel=0.03,
                            up=(0, s * 0.36, 0.34)))
    objs.append(C.tube('ridge', M('roof_dark'), [(-0.6, 0, 2.04),
                                                (0.6, 0, 2.04)],
                       [0.05, 0.05], seg=10))
    for i, (x, z, w, h, r, m) in enumerate((
            (-0.2, 1.2, 0.2, 0.26, -6, 'paper'),
            (0.06, 1.25, 0.18, 0.2, 5, 'paper_yellow'),
            (0.22, 1.02, 0.2, 0.22, -3, 'paper_blue'),
            (-0.12, 0.96, 0.16, 0.14, 8, 'paper_yellow'))):
        objs.append(L.rbox('paper%d' % i, M(m), (x, -0.032, z), (w, 0.012, h),
                           rot=(0, r, 0), bevel=0.004, seg=1))
        objs.append(L.sphere('pin%d' % i, M('paint_red'),
                             (x, -0.045, z + h / 2 - 0.035), 0.018, seg=8,
                             rings=5))
    return objs


@define('prop_mailbox', footprint=(1, 1))
def mailbox():
    """Round-topped mailbox on a post with a little flag."""
    objs = [L.rbox('post', M('wood'), (0, 0.04, 0.45), (0.1, 0.1, 0.92),
                   bevel=0.03)]
    w, h = 0.28, 0.16
    prof = [(-w / 2, 0), (w / 2, 0)] + L.arc_pts(0, h, w / 2, 0, 180, 10)
    body = L.extrude('box', M('paint_blue'), L.round_corners(
        prof, [0.03, 0.03] + [0] * 11, n=2, closed=True), 0.46, bevel=0.025,
        seg=2)
    body.location = (0, 0.0, 0.88)
    objs.append(body)
    door = L.extrude('door', M('white'), L.round_corners(
        [(-w / 2 - 0.012, -0.012), (w / 2 + 0.012, -0.012)] +
        L.arc_pts(0, h, w / 2 + 0.012, 0, 180, 10), [0.03, 0.03] + [0] * 11,
        n=2, closed=True), 0.03, bevel=0.01, seg=1)
    door.location = (0, -0.235, 0.88)
    objs.append(door)
    objs.append(L.sphere('knob', M('paint_yellow'), (0, -0.26, 1.02), 0.025,
                         seg=10, rings=6))
    # flag on the right side
    objs.append(L.rbox('mast', M('paint_red'), (w / 2 + 0.025, 0.08, 1.06),
                       (0.022, 0.03, 0.3), bevel=0.008, seg=1))
    objs.append(L.rbox('flag', M('paint_red'), (w / 2 + 0.03, 0.0, 1.17),
                       (0.02, 0.15, 0.09), bevel=0.01, seg=1))
    hrt = L.extrude('heart', M('paint_pink'), heart_pts(0.1), 0.02,
                    bevel=0.006, seg=1)
    hrt.location = (-w / 2 - 0.006, 0.02, 1.0)
    hrt.rotation_euler = (0, 0, math.radians(90))
    objs.append(hrt)
    return objs


@define('prop_lamp', footprint=(1, 1))
def lamp():
    """Garden street lamp; `bulb` is emissive (glows at night)."""
    objs = [L.lathe('foot', M('paint_green'), L.round_corners(
        [(0, 0), (0.2, 0), (0.2, 0.08), (0.1, 0.16), (0.06, 0.3), (0, 0.3)],
        [0, 0.03, 0.03, 0.04, 0.03, 0], n=2), seg=18)]
    objs.append(L.lathe('pole', M('paint_green'),
                        [(0, 0.28), (0.045, 0.28), (0.04, 1.8), (0, 1.8)],
                        seg=12))
    objs.append(L.torus('ring', M('paint_yellow'), (0, 0, 1.0), 0.05, 0.022,
                        seg=14, rseg=6))
    objs.append(L.lathe('cup', M('paint_green'), L.round_corners(
        [(0, 1.76), (0.07, 1.76), (0.14, 1.86), (0.12, 1.89), (0, 1.86)],
        [0, 0.02, 0.02, 0.01, 0], n=2), seg=16))
    objs.append(L.sphere('bulb', M('bulb'), (0, 0, 2.0), 0.15, seg=16,
                         rings=10, squash=(1, 1, 1.05)))
    objs.append(L.lathe('hat', M('paint_green'), L.round_corners(
        [(0, 2.1), (0.21, 2.1), (0.2, 2.14), (0.08, 2.26), (0, 2.28)],
        [0, 0.02, 0.03, 0.04, 0], n=2), seg=18))
    objs.append(L.sphere('fin', M('paint_yellow'), (0, 0, 2.31), 0.04, seg=10,
                         rings=6))
    return objs


@define('prop_bench', footprint=(2, 1))
def bench():
    """Garden bench: wooden slats, painted legs and arms."""
    objs = []
    Lx = 1.36
    for i, y in enumerate((-0.15, -0.03, 0.09)):
        objs.append(L.rbox('seat%d' % i, M('wood'), (0, y, 0.42),
                           (Lx, 0.1, 0.05), bevel=0.02))
    for i, z in enumerate((0.62, 0.78)):
        objs.append(L.rbox('back%d' % i, M('wood'), (0, 0.19 + 0.03 * i, z),
                           (Lx, 0.05, 0.11), rot=(-12, 0, 0), bevel=0.02))
    for x in (-0.58, 0.58):
        objs.append(L.plank('fleg', M('paint_green'), (x, -0.16, 0.0),
                            (x, -0.15, 0.6), 0.07, 0.06, bevel=0.02,
                            up=(0, -1, 0)))
        objs.append(L.plank('bleg', M('paint_green'), (x, 0.16, 0.0),
                            (x, 0.24, 0.86), 0.07, 0.06, bevel=0.02,
                            up=(0, -1, 0)))
        objs.append(L.plank('arm', M('paint_green'), (x, -0.22, 0.6),
                            (x, 0.2, 0.62), 0.08, 0.05, bevel=0.02))
        objs.append(L.plank('rail', M('paint_green'), (x, -0.16, 0.38),
                            (x, 0.18, 0.38), 0.05, 0.05, bevel=0.015))
    return objs


@define('prop_garden_plot', footprint=(2, 2))
def garden_plot():
    """2x2 tilled soil bed with a wooden edge and furrows."""
    S = 1.88
    objs = [L.rbox('fill', M('soil_dark'), (0, 0, 0.06), (S - 0.1, S - 0.1, 0.12),
                   bevel=0.02)]
    for s in (-1, 1):
        objs.append(L.plank('ex', M('wood'), (-S / 2, s * (S / 2 - 0.05), 0.09),
                            (S / 2, s * (S / 2 - 0.05), 0.09), 0.1, 0.18,
                            bevel=0.03))
        objs.append(L.plank('ey', M('wood'), (s * (S / 2 - 0.05), -S / 2 + 0.1,
                                               0.09),
                            (s * (S / 2 - 0.05), S / 2 - 0.1, 0.09), 0.1, 0.18,
                            bevel=0.03))
    for x in (-1, 1):
        for y in (-1, 1):
            objs.append(L.post('cp', M('wood_dark'),
                               (x * (S / 2 - 0.05), y * (S / 2 - 0.05), 0),
                               0.25, 0.075, seg=10, top=0.6))
    for i, y in enumerate((-0.55, -0.18, 0.19, 0.56)):
        objs.append(C.tube('furrow%d' % i, M('soil'), [(-0.7, y, 0.12),
                                                      (0.7, y, 0.12)],
                           [0.13, 0.13], seg=10, flatten=[(1, 0.45)] * 2))
    return objs


@define('prop_sign', footprint=(1, 1))
def sign():
    """Blank wooden sign on a post."""
    objs = [L.rbox('post', M('wood_dark'), (0, 0.03, 0.5), (0.09, 0.09, 1.0),
                   bevel=0.03)]
    b = L.extrude('board', M('wood'), L.round_corners(
        [(-0.34, 0), (0.34, 0), (0.34, 0.36), (-0.34, 0.36)], 0.07, n=3,
        closed=True), 0.06, bevel=0.018)
    b.location = (0, -0.035, 0.62)
    objs.append(b)
    for x in (-0.25, 0.25):
        objs.append(L.sphere('nail', M('wood_dark'), (x, -0.07, 0.92), 0.018,
                             seg=8, rings=5, squash=(1, 0.5, 1)))
    return objs


@define('prop_house', footprint=(4, 4), budget=8000)
def house():
    """Tommy's storybook cottage (4x4): cream walls, red roof, round
    windows, arched door facing -Y, chimney."""
    W, D, He, Hr, z0 = 3.0, 2.8, 1.85, 3.0, 0.14
    objs = [L.rbox('found', M('stone'), (0, 0, 0.08), (W + 0.24, D + 0.24,
                                                       0.18), bevel=0.06)]
    wall = L.extrude('walls', M('wall'), L.round_corners(
        [(-W / 2, 0), (W / 2, 0), (W / 2, He), (0, Hr), (-W / 2, He)],
        [0.06, 0.06, 0.1, 0.3, 0.1], n=3, closed=True), D, bevel=0.06, seg=2)
    wall.rotation_euler = (0, 0, 0)
    wall.location = (0, 0, z0)
    objs.append(wall)
    # roof: thick inverted V with a rounded ridge, overhanging
    slope = (Hr - He) / (W / 2)
    ex = W / 2 + 0.38
    th = 0.2
    ez = He - (ex - W / 2) * slope + z0
    rz = Hr + z0 + 0.02
    n_up = th * math.sqrt(1 + slope * slope)
    roof_pts = [(-ex, ez - 0.02), (0, rz), (ex, ez - 0.02),
                (ex + 0.03, ez + n_up * 0.9), (0, rz + n_up),
                (-ex - 0.03, ez + n_up * 0.9)]
    roof = L.extrude('roof', M('roof'), L.round_corners(
        roof_pts, [0.03, 0.15, 0.03, 0.09, 0.3, 0.09], n=3, closed=True),
        D + 0.55, bevel=0.07, seg=3)
    objs.append(roof)
    # fish-scale shingle rows on both slopes
    sl = math.hypot(1.0, slope)
    Lr = D + 0.5
    eave_top = Vector((ex + 0.03, 0, ez + n_up * 0.9))
    up_s = (Vector((0, 0, rz + n_up)) - eave_top)
    slen = up_s.length
    up_s.normalize()
    for s in (-1, 1):
        nrm = Vector((s * slope, 0, 1)) / sl
        ups = Vector((-s * up_s.x, 0, up_s.z))
        e = Vector((s * eave_top.x, 0, eave_top.z))
        for k in range(5):
            d = 0.42 * (k + 1) + 0.04
            if d > slen - 0.05:
                break
            c = e + ups * d
            objs.append(L.scallop_row('sh%d_%d' % (s, k), M('roof'),
                                      c - Vector((0, Lr / 2, 0)),
                                      c + Vector((0, Lr / 2, 0)), -ups, nrm,
                                      8, 0.2, 0.2, lift=0.05, thick=0.05,
                                      res=6))
    # ridge roll
    objs.append(C.tube('ridge', M('roof_dark'), [(0, -(D + 0.6) / 2, rz + n_up
                                                   - 0.02),
                                                  (0, (D + 0.6) / 2, rz + n_up
                                                   - 0.02)],
                       [0.1, 0.1], seg=12))
    # chimney
    objs.append(L.rbox('chim', M('brick'), (0.78, 0.55, 2.95),
                       (0.42, 0.42, 1.3), bevel=0.05))
    objs.append(L.rbox('chimcap', M('stone'), (0.78, 0.55, 3.62),
                       (0.54, 0.54, 0.14), bevel=0.04))
    fy = -D / 2
    # arched door
    dw, dh = 0.78, 1.2
    dprof = [(-dw / 2, 0), (dw / 2, 0)] + L.arc_pts(0, dh - dw / 2, dw / 2, 0,
                                                    180, 10)
    frame = L.extrude('dframe', M('wood_dark'), [(x * 1.2, z * 1.08)
                                                 for x, z in dprof],
                      0.1, bevel=0.03)
    frame.location = (-0.55, fy - 0.0, z0)
    door = L.extrude('door', M('wood'), dprof, 0.1, bevel=0.025)
    door.location = (-0.55, fy - 0.04, z0 + 0.0)
    objs += [frame, door]
    for i, x in enumerate((-0.15, 0.15)):
        objs.append(L.rbox('plk%d' % i, M('wood_dark'),
                           (-0.55 + x, fy - 0.095, z0 + 0.5),
                           (0.03, 0.02, 0.9), bevel=0.008, seg=1))
    objs.append(L.sphere('knobd', M('paint_yellow'), (-0.55 + 0.26, fy - 0.11,
                                                     z0 + 0.58), 0.045, seg=10,
                         rings=7))
    objs.append(L.rbox('step', M('stone'), (-0.55, fy - 0.3, 0.06),
                       (1.0, 0.45, 0.12), bevel=0.04))

    def round_window(name, loc, r, rot, box=False):
        out = [L.torus(name + '_fr', M('wood'), (0, 0, 0), r, 0.06, seg=24,
                       rseg=8),
               L.lathe(name + '_gl', M('window'), [(0, -0.01), (r, -0.01),
                                                   (r, 0.02), (0, 0.03)],
                       seg=24)]
        out.append(L.rbox(name + '_m1', M('wood'), (0, 0, 0.025),
                          (r * 2, 0.04, 0.03), bevel=0.01, seg=1))
        out.append(L.rbox(name + '_m2', M('wood'), (0, 0, 0.025),
                          (0.04, r * 2, 0.03), bevel=0.01, seg=1))
        out.append(C.ellipsoid(name + '_hl', M('white'),
                               (-r * 0.35, r * 0.38, 0.036),
                               (r * 0.18, r * 0.09, 0.004), rot=(0, 0, 40),
                               seg=10, rings=4))
        L.transform_objs(out, loc=loc, rot=rot)
        if box:
            bx, by, bz = loc
            out.append(L.rbox(name + '_box', M('wood_dark'),
                              (bx, by - 0.08, bz - r - 0.12),
                              (r * 2.4, 0.22, 0.18), bevel=0.04))
            for k in range(5):
                xx = bx - r * 1.0 + k * r * 0.5
                out.append(L.sphere(name + '_lf%d' % k, M('leaf'),
                                    (xx, by - 0.1, bz - r - 0.02), 0.08,
                                    seg=10, rings=6))
                if k % 2 == 0:
                    out.append(L.sphere(name + '_fl%d' % k,
                                        M('petal_pink' if k != 2 else
                                          'petal_yellow'),
                                        (xx, by - 0.16, bz - r + 0.04), 0.06,
                                        seg=10, rings=6))
        return out
    # front: round window right of the door (with flower box), gable window
    objs += round_window('wf', (0.68, fy - 0.03, z0 + 1.05), 0.36,
                         (90, 0, 0), box=True)
    objs += round_window('wg', (0.0, fy - 0.03, z0 + 2.3), 0.22, (90, 0, 0))
    # sides
    for s in (-1, 1):
        objs += round_window('ws%d' % s, (s * (W / 2 + 0.03), 0.0, z0 + 1.1),
                             0.3, (90, 0, s * 90))
    return objs


# =================================================================== items


def _shift(objs, dz):
    L.transform_objs(objs, loc=(0, 0, dz))
    return objs


@define('item_fern', budget=800)
def item_fern():
    """Bundle of fern leaves tied with a ribbon; grip at the tie."""
    objs = []
    for i, (ang, H) in enumerate(((5, 0.3), (-28, 0.25), (30, 0.26))):
        lh = H * math.tan(math.radians(abs(ang)))
        rise = H / lh / 0.8
        objs.append(L.frond('f%d' % i, M('fern'), (0, 0, 0.0),
                            0.0 if ang > 0 else math.pi, lh, rise, rise * 0.2,
                            0.055, teeth=5, comb=0.5, fold=0.15, thick=0.005,
                            side=(1, 0, 0), up=(0, -1, 0)))
    objs.append(C.tube('stalks', M('fern_dark'), [(0, 0, -0.07), (0, 0, 0.02)],
                       [0.018, 0.016], seg=6))
    objs.append(L.torus('tie', M('paint_red'), (0, 0, 0.0), 0.022, 0.011,
                        seg=12, rseg=5))
    return objs


@define('item_berries', budget=800)
def item_berries():
    """Small wicker basket of blue berries; hangs from the handle top."""
    prof = L.round_corners([(0, 0), (0.07, 0), (0.095, 0.075), (0.083, 0.075),
                            (0.062, 0.012), (0, 0.012)],
                           [0, 0.015, 0.008, 0.006, 0.006, 0], n=2)
    objs = [L.lathe('basket', M('straw'), prof, seg=10)]
    objs.append(L.torus('rim', M('straw_dark'), (0, 0, 0.075), 0.09, 0.009,
                        seg=10, rseg=4))
    objs.append(C.tube('handle', M('straw_dark'),
                       L.arc((-0.088, 0, 0.07), (0.088, 0, 0.07), 0.12, n=5),
                       [0.009] * 5, seg=4))
    rng = random.Random(2)
    for i in range(6):
        a = 2 * math.pi * i / 5
        rr = 0 if i == 5 else 0.045
        objs.append(L.sphere('b%d' % i, M('berry'),
                             (rr * math.cos(a), rr * math.sin(a),
                              0.072 + (0.03 if i == 5 else rng.uniform(0, 0.01))),
                             0.028, seg=7, rings=4))
    return _shift(objs, -0.19)


@define('item_pumpkin', budget=800)
def item_pumpkin():
    """Pumpkin carried with both hands; origin at its centre."""
    R = 0.16
    prof = [(0, -R * 0.72)]
    for k in range(1, 8):
        a = -math.pi / 2 + math.pi * k / 8
        prof.append((R * math.cos(a), R * 0.78 * math.sin(a)))
    prof.append((0.02, R * 0.62))
    body = L.lathe('pump', M('pumpkin'), prof, seg=24,
                   rfun=lambda th, z: 0.9 + 0.1 * abs(math.cos(4 * th)))
    stem = C.tube('stem', M('plant_stem'), [(0, 0, R * 0.55), (0.01, 0, R * 0.8),
                                            (0.04, 0, R * 0.92)],
                  [0.018, 0.015, 0.012], seg=6)
    leaf = L.blade('leaf', M('leaf'), [(0.0, 0, R * 0.62), (-0.05, -0.02,
                                                            R * 0.7),
                                       (-0.09, -0.02, R * 0.66)], 0.028,
                   thick=0.25, seg=6)
    return [body, stem, leaf]


@define('item_kibble', budget=800)
def item_kibble():
    """Dino kibble bag with a meat icon; hangs from the crimped top."""
    bag = L.rbox('bag', M('bag'), (0, 0, -0.14), (0.18, 0.09, 0.22),
                 bevel=0.04, seg=2)
    top = L.rbox('top', M('paper'), (0, 0, -0.025), (0.19, 0.05, 0.05),
                 bevel=0.015, seg=1)
    objs = [bag, top]
    # meat-on-the-bone icon on the front
    fy = -0.048
    objs.append(C.ellipsoid('meat', M('roof_dark'), (-0.012, fy, -0.13),
                            (0.045, 0.006, 0.034), rot=(0, 30, 0), seg=14,
                            rings=5))
    objs.append(L.plank('bone', M('white'), (0.02, fy - 0.002, -0.15),
                        (0.055, fy - 0.002, -0.17), 0.006, 0.014, bevel=0.003,
                        seg=1, up=(0, -1, 0)))
    for dz in (-0.01, 0.01):
        objs.append(C.ellipsoid('knob', M('white'),
                                (0.062 + dz * 0.5, fy - 0.002, -0.172 + dz),
                                (0.011, 0.005, 0.011), seg=8, rings=4))
    return objs


@define('item_fish', budget=800)
def item_fish():
    """Fish held by the tail (origin), head down."""
    pts = [(0, 0, -0.04), (0, 0, -0.1), (0, 0, -0.19), (0, 0, -0.25)]
    body = C.tube('body', M('fish'), pts, [0.022, 0.05, 0.048, 0.02], seg=10,
                  flatten=[(0.5, 1.0)] * 4)
    L.paint_faces(body, [M('fish'), M('fish_belly')],
                  lambda c, n: 1 if c.y < -0.012 else 0)
    tail = L.extrude('tail', M('fish'), L.round_corners(
        [(0, -0.05), (0.05, 0.01), (0.0, -0.005), (-0.05, 0.01)],
        [0.01, 0.015, 0.01, 0.015], n=2, closed=True), 0.012, bevel=0.004,
        seg=1)
    tail.rotation_euler = (0, 0, math.radians(90))
    fin = L.extrude('fin', M('paint_blue'), [(0.0, 0.0), (0.035, -0.03),
                                             (0.0, -0.06)], 0.008)
    fin.rotation_euler = (0, 0, math.radians(90))
    fin.location = (0, 0.02, -0.1)
    objs = [body, tail, fin]
    for s in (-1, 1):
        objs.append(C.ellipsoid('eye', M('eye_white'), (s * 0.019, -0.012, -0.205),
                                (0.008, 0.013, 0.013), seg=8, rings=5))
        objs.append(C.ellipsoid('pup', M('pupil'), (s * 0.025, -0.014, -0.207),
                                (0.004, 0.007, 0.007), seg=6, rings=4))
    return objs


@define('item_watering_can', budget=800)
def item_watering_can():
    """Watering can; origin at the top of the handle (can hangs below)."""
    body = L.lathe('can', M('paint_mint'), L.round_corners(
        [(0, 0), (0.075, 0), (0.08, 0.14), (0.05, 0.16), (0, 0.165)],
        [0, 0.02, 0.03, 0.02, 0], n=2), seg=14)
    objs = [body]
    objs.append(L.torus('band', M('paint_yellow'), (0, 0, 0.05), 0.078, 0.01,
                        seg=16, rseg=4))
    objs.append(C.tube('spout', M('paint_mint'), [(0.05, 0, 0.04),
                                                  (0.13, 0, 0.1),
                                                  (0.19, 0, 0.17)],
                       [0.018, 0.014, 0.012], seg=6, cap=False))
    rose = L.lathe('rose', M('paint_yellow'), [(0, -0.005), (0.016, 0.0),
                                                (0.03, 0.03), (0, 0.032)],
                   seg=12)
    rose.location = (0.19, 0, 0.17)
    rose.rotation_euler = (0, math.radians(50), 0)
    objs.append(rose)
    objs.append(C.tube('handle', M('paint_mint'),
                       L.arc((-0.07, 0, 0.13), (0.02, 0, 0.16), 0.09, n=5),
                       [0.012] * 5, seg=5))
    return _shift(objs, -0.235)


@define('item_brush', budget=800)
def item_brush():
    """Grooming brush: handle in the fist (origin), head up, bristles
    facing -Y."""
    objs = [C.tube('handle', M('wood'), [(0, 0, -0.06), (0, 0, 0.08)],
                   [0.016, 0.019], seg=8)]
    objs.append(L.rbox('head', M('paint_pink'), (0, 0, 0.14), (0.1, 0.05, 0.14),
                       bevel=0.022, seg=2))
    objs.append(L.rbox('bristle', M('bristle'), (0, -0.035, 0.14),
                       (0.08, 0.04, 0.12), bevel=0.012, seg=1))
    hrt = L.extrude('heart', M('white'), heart_pts(0.04), 0.01, bevel=0.003,
                    seg=1)
    hrt.location = (0, 0.026, 0.14)
    objs.append(hrt)
    return objs


@define('item_shovel', budget=800)
def item_shovel():
    """Kid's shovel: grip on the upper handle (origin), blade down."""
    objs = [C.tube('handle', M('wood'), [(0, 0, -0.32), (0, 0, 0.14)],
                   [0.014, 0.014], seg=8)]
    objs.append(L.torus('grip', M('paint_red'), (0, 0, 0.19), 0.045, 0.014,
                        seg=14, rseg=5, rot=(90, 0, 0), squash=1.0))
    objs.append(L.lathe('collar', M('metal_dark'), [(0, -0.33), (0.022, -0.33),
                                                    (0.02, -0.28), (0, -0.28)],
                        seg=10))
    blade = L.extrude('blade', M('metal'), L.round_corners(
        [(-0.065, 0.0), (0.065, 0.0), (0.06, -0.11), (0.0, -0.17),
         (-0.06, -0.11)], [0.015, 0.015, 0.03, 0.03, 0.03], n=2, closed=True),
        0.014, bevel=0.005, seg=1)
    blade.location = (0, 0, -0.32)
    objs.append(blade)
    return objs


@define('item_ball', budget=800)
def item_ball():
    """Striped beach ball; held from below (origin at its bottom)."""
    r = 0.14
    b = C.ellipsoid('ball', M('white'), (0, 0, 0), (r, r, r), seg=24, rings=12)
    cols = [M('paint_red'), M('white'), M('paint_blue'), M('paint_yellow')]
    order = [0, 1, 2, 1, 3, 1]

    def rule(c, n):
        if abs(c.z) > r * 0.9:
            return 3 if c.z > 0 else 1
        a = (math.atan2(c.y, c.x) + 2 * math.pi) % (2 * math.pi)
        return order[int(a / (math.pi / 3)) % 6]
    L.paint_faces(b, cols, rule)
    b.location = (0, 0, r)
    return [b]


# =================================================================== main


def build(name, out):
    d = DEFS[name]
    L.begin()
    res = d['fn']()
    if isinstance(res, dict):
        st = L.finish(name + '_static', res['static'])
        dr = L.finish(name + '_door', res['door'])
        objs = res['rig'](st, dr)
        mesh = [o for o in objs if o.type == 'MESH'][0]
        mesh.data.use_auto_smooth = True
    else:
        mesh = L.finish(name, res)
        objs = [mesh]
    bpy.context.view_layer.update()
    pts = [mesh.matrix_world @ Vector(c) for c in mesh.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts),
                 min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts),
                 max(p.z for p in pts)))
    nt = L.tris(mesh)
    flag = '' if nt <= d['budget'] else '  OVER BUDGET %d' % d['budget']
    print('[props] %-22s tris %5d  mats %d  x %.2f..%.2f  y %.2f..%.2f  '
          'z %.2f..%.2f%s' % (name, nt, len(mesh.data.materials), lo.x, hi.x,
                              lo.y, hi.y, lo.z, hi.z, flag))
    C.export_glb(os.path.join(out, name + '.glb'), objs)


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
    for n in names:
        if n not in DEFS:
            print('[props] unknown', n)
            continue
        build(n, out)


main()
