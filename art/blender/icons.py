"""icons.py - tiny 3D icon models for the HUD, prompts and thought bubbles.
The game renders each one in an off-screen viewport (scripts/core/icons.gd),
so icons share the toon look of everything else.

    Blender -b -P icons.py -- [--only heart,coin]

Each icon fits roughly a 0.5 m box, faces the camera (-Y in Blender =
+Z in Godot), origin at its centre-bottom. Names: icon_<name>.glb.
Item icons are not here: the game renders the item's own model.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdz_common as C  # noqa: E402
from mathutils import Vector  # noqa: E402

A = C.args()
OUT = A.get('out', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'game', 'assets', 'models'))
ONLY = A.get('only', '').split(',') if A.get('only') else None

ICONS = {}


def icon(fn):
    ICONS[fn.__name__] = fn
    return fn


def heart_shape(name, m, loc, s, depth=0.35):
    """A puffy heart: two spheres + a cone-ish bottom, joined."""
    x, y, z = loc
    a = C.ellipsoid(name + 'a', m, (x - 0.1 * s, y, z + 0.06 * s), (0.15 * s, 0.11 * s, 0.15 * s))
    b = C.ellipsoid(name + 'b', m, (x + 0.1 * s, y, z + 0.06 * s), (0.15 * s, 0.11 * s, 0.15 * s))
    c = C.tube(name + 'c', m, [(x, y, z - 0.24 * s), (x, y, z - 0.08 * s), (x, y, z + 0.04 * s)],
               [0.02 * s, 0.16 * s, 0.2 * s], seg=24,
               flatten=[(1.2, 0.55), (1.25, 0.55), (1.2, 0.5)])
    return [a, b, c]


@icon
def heart():
    m = C.mat('heart', '#ff5d8f')
    return heart_shape('h', m, (0, 0, 0.25), 1.2)


@icon
def need_love():
    m = C.mat('heart', '#ff8fb5')
    return heart_shape('h', m, (0, 0, 0.25), 1.2)


@icon
def coin():
    g = C.mat('gold', '#ffc93a', rough=0.35, metal=0.3)
    d = C.mat('gold_dark', '#e09a1c', rough=0.35, metal=0.3)
    a = C.cylinder('coin', d, (0, 0.04, 0.25), 0.22, 0.08, rot=(90, 0, 0), seg=40)
    b = C.cylinder('face', g, (0, 0.0, 0.25), 0.18, 0.1, rot=(90, 0, 0), seg=40)
    parts = [a, b]
    for i in range(5):
        an = math.radians(90 + i * 72)
        parts.append(C.cone('p%d' % i, d, (0, -0.06, 0.25),
                            (math.cos(an) * 0.11, -0.06, 0.25 + math.sin(an) * 0.11), 0.04, seg=8))
    return parts


@icon
def star():
    m = C.mat('star', '#ffd84a', rough=0.4)
    parts = [C.ellipsoid('core', m, (0, 0, 0.25), (0.11, 0.07, 0.11))]
    for i in range(5):
        a = math.radians(90 + i * 72)
        tip = (math.cos(a) * 0.26, 0, 0.25 + math.sin(a) * 0.26)
        parts.append(C.cone('p%d' % i, m, (0, 0, 0.25), tip, 0.09, seg=10))
    return parts


@icon
def sun():
    m = C.mat('sun', '#ffcc33', emit=0.3)
    r = C.mat('ray', '#ffa733')
    parts = [C.ellipsoid('sun', m, (0, 0, 0.25), (0.15, 0.08, 0.15))]
    for i in range(8):
        a = math.radians(i * 45)
        base = (math.cos(a) * 0.17, 0.02, 0.25 + math.sin(a) * 0.17)
        tip = (math.cos(a) * 0.27, 0.02, 0.25 + math.sin(a) * 0.27)
        parts.append(C.cone('r%d' % i, r, base, tip, 0.045, seg=8))
    return parts


@icon
def moon():
    m = C.mat('moon', '#ffe9a8', emit=0.2)
    parts = []
    # crescent as a chain of shrinking spheres along an arc
    for i in range(11):
        t = i / 10
        a = math.radians(-120 + 240 * t)
        r = 0.08 * math.sin(math.pi * (0.1 + 0.8 * t)) + 0.02
        parts.append(C.ellipsoid('m%d' % i, m, (math.cos(a) * 0.17 - 0.03, 0, 0.25 + math.sin(a) * 0.17), (r, r * 0.7, r)))
    return parts


@icon
def egg():
    m = C.mat('egg', '#fff3dc')
    s = C.mat('spots', '#b9a6e8')
    e = C.ellipsoid('egg', m, (0, 0, 0.26), (0.16, 0.16, 0.22))
    parts = [e]
    for i, (x, z, r) in enumerate([(-0.06, 0.34, 0.04), (0.07, 0.24, 0.05), (-0.04, 0.16, 0.03), (0.05, 0.4, 0.025)]):
        parts.append(C.decal_on('s%d' % i, s, e, (x, -0.16, z), (0, -1, 0), r))
    return parts


@icon
def sparkle():
    m = C.mat('sparkle', '#fff2a6', emit=0.4)
    parts = []
    for cx, cz, s in [(0, 0.27, 1.0), (0.17, 0.42, 0.45), (-0.16, 0.12, 0.4)]:
        for a in (0, 90, 180, 270):
            r = math.radians(a)
            parts.append(C.cone('s', m, (cx, 0, cz), (cx + math.cos(r) * 0.2 * s, 0, cz + math.sin(r) * 0.2 * s), 0.05 * s, seg=8))
    return parts


@icon
def need_food():
    """an apple: the universal 'hungry' sign"""
    r = C.mat('apple', '#ff5a4e')
    l = C.mat('leaf', '#5cc45a')
    st = C.mat('wood_dark', '#7a5236')
    return [C.ellipsoid('apple', r, (0, 0, 0.22), (0.19, 0.17, 0.18)),
            C.cylinder('stem', st, (0, 0, 0.36), 0.015, 0.09),
            C.ellipsoid('leaf', l, (0.07, 0, 0.43), (0.07, 0.025, 0.035), rot=(0, -30, 0))]


@icon
def need_clean():
    """soap bubbles"""
    b = C.mat('bubble', '#9fe4ff', rough=0.1)
    w = C.mat('white', '#ffffff', emit=0.3)
    parts = []
    for x, z, r in [(-0.08, 0.2, 0.14), (0.12, 0.33, 0.1), (0.08, 0.12, 0.07)]:
        parts.append(C.ellipsoid('b', b, (x, 0, z), (r, r * 0.6, r)))
        parts.append(C.ellipsoid('g', w, (x - r * 0.35, -r * 0.55, z + r * 0.35), (r * 0.22, r * 0.1, r * 0.22)))
    return parts


@icon
def need_fun():
    """a striped ball"""
    parts = [C.ellipsoid('core', C.mat('ball_core', '#ffffff'), (0, 0, 0.24), (0.195, 0.195, 0.195))]
    cols = ['#ff5d5d', '#ffffff', '#4ab3ff', '#ffffff', '#ffd84a', '#ffffff']
    for i, c in enumerate(cols):
        m = C.mat('ball%d' % i, c)
        e = C.ellipsoid('s%d' % i, m, (0, 0, 0.24), (0.2, 0.2, 0.2))
        # keep a wedge of the sphere only: scale-free trick, slice by verts
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(e.data)
        a0 = 2 * math.pi * i / 6
        a1 = 2 * math.pi * (i + 1) / 6
        kill = []
        for v in bm.verts:
            a = math.atan2(v.co.y, v.co.x) % (2 * math.pi)
            if not (a0 - 0.02 <= a <= a1 + 0.02):
                kill.append(v)
        bmesh.ops.delete(bm, geom=kill, context='VERTS')
        bm.to_mesh(e.data)
        bm.free()
        e.rotation_euler = (math.radians(70), 0, math.radians(20))
        parts.append(e)
    return parts


@icon
def pet():
    """an open hand with a little heart"""
    sk = C.mat('skin', '#ffd1b0')
    parts = [C.ellipsoid('palm', sk, (0, 0, 0.2), (0.13, 0.06, 0.14))]
    for i, (x, l) in enumerate([(-0.09, 0.13), (-0.03, 0.15), (0.03, 0.15), (0.09, 0.13)]):
        parts.append(C.tube('f%d' % i, sk, [(x, 0, 0.3), (x * 1.15, 0, 0.3 + l)], [0.033, 0.03], seg=10))
    parts.append(C.tube('th', sk, [(0.12, 0, 0.18), (0.22, 0, 0.27)], [0.035, 0.03], seg=10))
    parts += heart_shape('h', C.mat('heart', '#ff5d8f'), (-0.17, -0.05, 0.42), 0.45)
    return parts


@icon
def pickup():
    sk = C.mat('skin', '#ffd1b0')
    parts = [C.ellipsoid('palm', sk, (0, 0, 0.22), (0.14, 0.12, 0.11))]
    for i, x in enumerate([-0.09, -0.03, 0.03, 0.09]):
        parts.append(C.tube('f%d' % i, sk, [(x, -0.05, 0.3), (x, -0.13, 0.36), (x, -0.17, 0.3)], [0.033, 0.03, 0.028], seg=10))
    return parts


@icon
def hands():
    """two hands raised: hands full"""
    parts = pickup()
    for p in parts:
        p.location.x -= 0.14
    sk = C.mat('skin', '#ffd1b0')
    parts.append(C.ellipsoid('palm2', sk, (0.16, 0, 0.22), (0.12, 0.1, 0.1)))
    return parts


@icon
def feed():
    """a bowl with food"""
    b = C.mat('paint_blue', '#5aa8ff')
    f = C.mat('leaf', '#6cc957')
    a = C.mat('apple', '#ff5a4e')
    return [C.cylinder('bowl', b, (0, 0, 0.1), 0.16, 0.14, r2=0.24, seg=28),
            C.ellipsoid('food', f, (0, 0, 0.25), (0.2, 0.2, 0.06)),
            C.ellipsoid('ap', a, (0.06, -0.06, 0.3), (0.07, 0.07, 0.07))]


@icon
def fill():
    w = C.mat('wood', '#c98b52')
    f = C.mat('leaf', '#6cc957')
    return [C.box('tr', w, (0, 0, 0.18), (0.5, 0.26, 0.18), bevel=0.04),
            C.ellipsoid('food', f, (0, 0, 0.28), (0.22, 0.1, 0.05))]


@icon
def water():
    m = C.mat('water', '#4ab8ff', rough=0.15)
    w = C.mat('white', '#ffffff', emit=0.3)
    d = C.ellipsoid('drop', m, (0, 0, 0.18), (0.15, 0.11, 0.15))
    t = C.cone('tip', m, (0, 0, 0.24), (0, 0, 0.48), 0.13, seg=20)
    return [d, t, C.ellipsoid('g', w, (-0.06, -0.1, 0.24), (0.03, 0.015, 0.05))]


@icon
def plant():
    s = C.mat('soil', '#8a5a3a')
    l = C.mat('leaf', '#5cc45a')
    st = C.mat('leaf_dark', '#3f9a45')
    return [C.ellipsoid('soil', s, (0, 0, 0.04), (0.2, 0.14, 0.06)),
            C.tube('stem', st, [(0, 0, 0.05), (0, 0, 0.3)], [0.025, 0.02], seg=10),
            C.ellipsoid('l1', l, (-0.09, 0, 0.33), (0.1, 0.04, 0.05), rot=(0, 25, 0)),
            C.ellipsoid('l2', l, (0.09, 0, 0.36), (0.1, 0.04, 0.05), rot=(0, -25, 0))]


@icon
def harvest():
    w = C.mat('straw', '#e9c46a')
    f = C.mat('apple', '#ff5a4e')
    l = C.mat('leaf', '#5cc45a')
    return [C.cylinder('basket', w, (0, 0, 0.06), 0.17, 0.16, r2=0.22, seg=24),
            C.ellipsoid('a1', f, (-0.08, 0, 0.26), (0.08, 0.08, 0.08)),
            C.ellipsoid('a2', l, (0.08, 0, 0.26), (0.08, 0.08, 0.07)),
            C.ellipsoid('a3', f, (0, -0.06, 0.3), (0.07, 0.07, 0.07)),
            C.tube('handle', w, [(-0.2, 0, 0.2), (0, 0, 0.46), (0.2, 0, 0.2)], [0.02, 0.02, 0.02], seg=8)]


@icon
def shake():
    b = C.mat('bark', '#8a5a3a')
    l = C.mat('leaf', '#5cc45a')
    a = C.mat('apple', '#ff5a4e')
    return [C.cylinder('trunk', b, (0, 0, 0), 0.05, 0.25),
            C.ellipsoid('can', l, (0, 0, 0.36), (0.22, 0.16, 0.16)),
            C.ellipsoid('a1', a, (-0.1, -0.13, 0.32), (0.045, 0.045, 0.045)),
            C.ellipsoid('a2', a, (0.12, -0.12, 0.4), (0.045, 0.045, 0.045))]


@icon
def missions():
    w = C.mat('wood', '#c98b52')
    p = C.mat('white', '#fffaf0')
    c = C.mat('paint_red', '#ff6b5a')
    return [C.box('board', w, (0, 0, 0.27), (0.36, 0.05, 0.44), bevel=0.03),
            C.box('paper', p, (0, -0.03, 0.25), (0.26, 0.02, 0.32), bevel=0.01),
            C.box('l1', c, (0, -0.045, 0.33), (0.18, 0.01, 0.03)),
            C.box('l2', c, (0, -0.045, 0.25), (0.18, 0.01, 0.03)),
            C.box('l3', c, (0, -0.045, 0.17), (0.12, 0.01, 0.03))]


@icon
def sleep():
    m = C.mat('zzz', '#8fa8ff')
    parts = []
    for i, (x, z, s) in enumerate([(-0.1, 0.12, 1.0), (0.05, 0.3, 0.75), (0.16, 0.44, 0.55)]):
        w = 0.16 * s
        t = 0.035 * s
        parts += [C.box('a%d' % i, m, (x, 0, z + w / 2), (w, t, t), bevel=t * 0.4),
                  C.box('b%d' % i, m, (x, 0, z - w / 2), (w, t, t), bevel=t * 0.4)]
        d = C.box('c%d' % i, m, (x, 0, z), (w * 1.35, t, t), bevel=t * 0.4)
        d.rotation_euler = (0, math.radians(45), 0)
        parts.append(d)
    return parts


@icon
def shop():
    b = C.mat('paint_yellow', '#ffcf4a')
    h = C.mat('wood_dark', '#7a5236')
    return [C.box('bag', b, (0, 0, 0.2), (0.34, 0.16, 0.34), bevel=0.04),
            C.tube('handle', h, [(-0.09, 0, 0.36), (0, 0, 0.46), (0.09, 0, 0.36)], [0.018, 0.018, 0.018], seg=8)]


@icon
def place():
    b = C.mat('cardboard', '#d9a46a')
    t = C.mat('tape', '#f2e3b3')
    return [C.box('box', b, (0, 0, 0.2), (0.38, 0.32, 0.36), bevel=0.02),
            C.box('tape', t, (0, 0, 0.385), (0.1, 0.34, 0.012))]


@icon
def scoop():
    br = C.mat('poop', '#9b6a45')
    parts = []
    for i, (z, r) in enumerate([(0.08, 0.17), (0.2, 0.13), (0.3, 0.08)]):
        parts.append(C.ellipsoid('p%d' % i, br, (0, 0, z), (r, r * 0.9, r * 0.6)))
    parts.append(C.cone('tip', br, (0, 0, 0.33), (0.03, 0, 0.42), 0.04, seg=10))
    return parts


@icon
def nope():
    m = C.mat('paint_red', '#ff6b5a')
    a = C.box('a', m, (0, 0, 0.25), (0.42, 0.08, 0.09), bevel=0.04)
    a.rotation_euler = (0, math.radians(45), 0)
    b = C.box('b', m, (0, 0, 0.25), (0.42, 0.08, 0.09), bevel=0.04)
    b.rotation_euler = (0, math.radians(-45), 0)
    return [a, b]


@icon
def throw():
    parts = need_fun()
    return parts


@icon
def photo():
    body = C.mat('paint_blue', '#5aa8ff')
    dark = C.mat('pupil', '#2b2b38')
    w = C.mat('white', '#ffffff')
    return [C.box('cam', body, (0, 0, 0.22), (0.42, 0.18, 0.28), bevel=0.05),
            C.cylinder('lens', dark, (0, -0.08, 0.22), 0.09, 0.08, rot=(90, 0, 0), seg=24),
            C.cylinder('glint', w, (0, -0.16, 0.22), 0.05, 0.01, rot=(90, 0, 0), seg=16),
            C.box('btn', C.mat('paint_red', '#ff6b5a'), (0.13, 0, 0.38), (0.07, 0.07, 0.04), bevel=0.015)]


@icon
def brush():
    w = C.mat('wood', '#c98b52')
    b = C.mat('bristle', '#ffe08a')
    return [C.box('back', w, (0, 0, 0.27), (0.36, 0.14, 0.09), bevel=0.04),
            C.box('bristles', b, (0, 0, 0.19), (0.32, 0.12, 0.08), bevel=0.02),
            C.tube('handle', w, [(0.18, 0, 0.29), (0.32, 0, 0.36)], [0.03, 0.025], seg=10)]


@icon
def talk():
    w = C.mat('white', '#ffffff')
    d = C.mat('pupil', '#7a5236')
    b = C.ellipsoid('bubble', w, (0, 0, 0.3), (0.24, 0.08, 0.17))
    t = C.cone('tail', w, (-0.06, 0, 0.18), (-0.16, 0, 0.06), 0.06, seg=10)
    dots = [C.ellipsoid('d%d' % i, d, (x, -0.08, 0.3), (0.03, 0.02, 0.03)) for i, x in enumerate((-0.09, 0, 0.09))]
    return [b, t] + dots


@icon
def backpack():
    """the shop's backpack: one more pocket"""
    body = C.mat('paint_red', '#ef5a4c')
    flap = C.mat('paint_yellow', '#ffcf4a')
    strap = C.mat('wood_dark', '#7a5236')
    return [C.box('bag', body, (0, 0, 0.24), (0.36, 0.2, 0.42), bevel=0.09),
            C.box('pocket', flap, (0, -0.11, 0.16), (0.24, 0.06, 0.16), bevel=0.04),
            C.box('flap', flap, (0, -0.02, 0.42), (0.37, 0.22, 0.12), bevel=0.05),
            C.tube('handle', strap, [(-0.07, 0, 0.45), (0, 0, 0.52), (0.07, 0, 0.45)], [0.018, 0.018, 0.018], seg=8),
            C.ellipsoid('star', C.mat('white', '#ffffff'), (0, -0.145, 0.17), (0.04, 0.01, 0.04))]


def build(name):
    C.reset()
    C._mats.clear()
    parts = ICONS[name]()
    ob = C.join_static('icon_' + name, parts)
    C.export_glb(os.path.join(OUT, 'icon_%s.glb' % name), [ob])


for n in ICONS:
    if ONLY and n not in ONLY:
        continue
    build(n)
