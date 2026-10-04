"""tommy.py - Tommy, the player character of Tommy's Dino Zoo: built, rigged
and animated procedurally, plus his default cap as a separate model.

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P tommy.py -- \
        [--out ../../game/assets/models] [--only tommy,cap]

Writes `tommy.glb` (one skinned mesh + armature + actions) and
`cap_basic.glb` (static mesh, attached to the `head` bone at runtime).

Look
  Tommy from Monster Hop (`ESP32S3_AmoledOS/apps/monsterhop/tools/blender/
  chars.py`), a touch rounder and softer: 1.0 m tall with the cap, the head
  ~42 % of that, big eyes with two catchlights, a small smile and blush,
  blue/white striped tee with a yellow emblem, navy jeans with a rolled cuff,
  chunky red sneakers with white soles. The face and the hair are surface
  patches laid a few mm above an analytic head ellipsoid (no textures).
  Materials are palette roles (ART-SPEC s.3): skin, hair, eye_white, pupil,
  mouth, blush, shirt, shirt_stripe, emblem, pants, shoes, shoe_sole (12 in
  tommy.glb) and cap, cap_brim (in cap_basic.glb).

Rig (Blender: +Z up, faces -Y, +X = his left; metres)
  root (hips, head at z 0.31, points up) > spine > chest > neck > head
  (head bone head = top of the neck, (0, 0, 0.60), points straight up);
  chest > upper_arm.X > forearm.X > hand.X; root > thigh.X > shin.X > foot.X;
  head > eyelid.X (scale ~0 = open, 1 = closed; the lid mesh is the closed
  lid), head > mouth_open (extra: scale ~0 = hidden, ~1 = open mouth, used by
  yawn/happy). Limbs are smooth tubes skinned across elbow/knee (skin_near).
  Every action keys every bone every frame (rotation + scale, plus the root's
  location), so nothing leaks from one animation into the next. Eyelids and
  mouth_open sit at scale 0.01 when "off" (collapsed inside the head).

Animations (30 fps; root stays in place, the game moves the node)
  idle       loop 4.0 s   breathing, weight shift, look left/right, 2 blinks
  walk       loop 0.5 s   1.6 m/s  (0.8 m per cycle, stance 36 %: a bouncy
                          little trot, the planted foot moves back at exactly
                          1.6 m/s, heel-strike and toe-off pivots)
  run        loop 0.4 s   3.5 m/s  (1.4 m per cycle, stance 20 %)
  pickup     0.7 s        crouch, grab with both hands, stand into carry pose
  carry_idle loop 2.0 s   both hands at the chest holding a box
  carry_walk loop 0.5 s   1.6 m/s, same legs as walk, carrying
  pet        1.0 s        reach forward at chest height, two strokes
  give       0.8 s        offer with the right hand
  happy      0.8 s        crouch, jump with both arms up, squash on landing
  yawn       1.6 s        stretch arms up, mouth open, eyes closed, relax
  pet_low    1.0 s        crouch, stroke low in front (~0.3 m up, baby dinos)
  use        1.0 s        right-hand tool: lift, tip forward/down x3, return
  dig        0.9 s        shovel scoop: thrust, lever, lift/toss right (repeats)
  wave       1.0 s        right arm up, three waves
  sit        loop 3.0 s   on the ground, legs forward, kicking feet, look
  sleep      loop 4.0 s   curled on his right side, slow breath, eyes closed
                          (lies along X, ~0.82 x 0.5 m centred on the origin)
  talk       loop 3.0 s   two phrases of mouth flaps, hand gestures, nods
  The big-item hold (carry_*) puts the hands at about (+-0.115, -0.175, 0.455)
  in model space (Blender), i.e. ~0.06 m in front of the belly.

Hand attach convention (item_*.glb on hand.R)
  hand.L/.R have their HEAD AT THE GRIP POINT (centre of the fist) and point
  straight up, so their Godot rest basis is identity: an item whose origin
  is its grip and whose axes are the model's (handle along +Z Blender, as in
  props.py) attaches to hand.R with an identity offset. The hand pivots about
  the grip. Animations steer the hand's world orientation (Pose.hold) so a
  held item stays roughly upright in idle/walk/run/talk/give, tips forward in
  `use` and angles the shovel in `dig`.

Cap attach convention (cap_basic.glb, and any cap_<style>.glb)
  The cap's ORIGIN is the `head` bone's head in rest pose: model-space
  (0, 0, 0.60) Blender = (0, 0.60, 0) Godot, the top of the neck. Its axes
  are the model's axes (Godot +Y up, facing +Z). The head bone points
  straight up with roll 0, which the glTF exporter turns into an IDENTITY
  bone basis, so in Godot: BoneAttachment3D(bone_name="head") as a child of
  the Skeleton3D, cap instance as its child with an identity transform.
  (The viewer does this with `--attach=cap_basic@head`.)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdz_common as C  # noqa: E402
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

A = C.args()
OUT = A.get('out', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'game', 'assets', 'models'))
ONLY = A.get('only', 'tommy,cap').split(',')
FPS = 30


def V(*a):
    return Vector(a if len(a) != 1 else a[0])


def clamp(x, a, b):
    return a if x < a else b if x > b else x


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def interp(table, x):
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def interp_rows(table, x):
    if x <= table[0][0]:
        return table[0][1:]
    for r0, r1 in zip(table, table[1:]):
        if x <= r1[0]:
            t = (x - r0[0]) / (r1[0] - r0[0])
            return tuple(a + (b - a) * t for a, b in zip(r0[1:], r1[1:]))
    return table[-1][1:]


def RX(d):
    return Matrix.Rotation(math.radians(d), 3, 'X')


def RY(d):
    return Matrix.Rotation(math.radians(d), 3, 'Y')


def RZ(d):
    return Matrix.Rotation(math.radians(d), 3, 'Z')


def T4(v):
    return Matrix.Translation(Vector(v))


def frame_z(z, xhint):
    """3x3 with Z along z and X as close as possible to xhint."""
    z = z.normalized()
    x = xhint - z * xhint.dot(z)
    if x.length < 1e-6:
        x = V(1, 0, 0) - z * z.x
    x.normalize()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed()


# ===========================================================================
# Materials (sRGB; the viewer's toon shader does the shading)
# ===========================================================================

COL = dict(skin='#f7c39c', hair='#7b4626', eye_white='#ffffff',
           pupil='#2b1d1a', mouth='#8c2f2b', blush='#ff8f8f',
           cap='#e3262b', cap_brim='#c71e24', shirt='#2f6fe4',
           shirt_stripe='#f6f7fb', emblem='#ffc21f', pants='#28336b',
           shoes='#e2302e', shoe_sole='#f7f5f2')
MATS = {}


def mats():
    for k, c in COL.items():
        MATS[k] = C.mat(k, c, rough=0.6)


# ===========================================================================
# Mesh building (ported from Monster Hop's chars.py)
# ===========================================================================

class MB:
    def __init__(self):
        self.v, self.f, self.fk = [], [], []

    def vert(self, p):
        self.v.append(Vector(p))
        return len(self.v) - 1

    def face(self, idx, key):
        self.f.append(tuple(idx))
        self.fk.append(key)


def to_object(name, mb, recalc=True, out_from=None):
    """recalc: closed mesh, recompute normals. out_from: open patch; flip
    faces so they point away from this point."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in mb.v], [], mb.f)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    keys = []
    for k in mb.fk:
        if k not in keys:
            keys.append(k)
    for k in keys:
        me.materials.append(MATS[k])
    me.polygons.foreach_set('material_index', [keys.index(k) for k in mb.fk])
    me.polygons.foreach_set('use_smooth', [True] * len(mb.f))
    bm = bmesh.new()
    bm.from_mesh(me)
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    elif out_from is not None:
        o = Vector(out_from)
        for f in bm.faces:
            if f.normal.dot(f.calc_center_median() - o) < 0:
                f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.update()
    return ob


def grid_faces(mb, rows, key_fn, closed=True):
    n = len(rows[0])
    kk = range(n) if closed else range(n - 1)
    for i in range(len(rows) - 1):
        for k in kk:
            k1 = (k + 1) % n
            a, b, c, d = rows[i][k], rows[i][k1], rows[i + 1][k1], rows[i + 1][k]
            cen = (mb.v[a] + mb.v[b] + mb.v[c] + mb.v[d]) / 4
            mb.face((a, b, c, d), key_fn(i, k, cen))


def fan(mb, centre, row, key, flip=False):
    n = len(row)
    for k in range(n):
        k1 = (k + 1) % n
        mb.face((centre, row[k1], row[k]) if not flip else (centre, row[k], row[k1]), key)


def ring_pts(c, xa, ya, xp, xn, yp, yn, n, e=2.0, th0=0.0):
    pts = []
    for k in range(n):
        th = th0 + 2 * math.pi * k / n
        cs, sn = math.cos(th), math.sin(th)
        ex = 2.0 / e
        x = math.copysign(abs(cs) ** ex, cs) * (xp if cs > 0 else xn)
        y = math.copysign(abs(sn) ** ex, sn) * (yp if sn > 0 else yn)
        pts.append(c + xa * x + ya * y)
    return pts


def loft(mb, rings, key_fn, cap0=None, cap1=None, cap_keys=(None, None)):
    rows = [[mb.vert(p) for p in r] for r in rings]
    grid_faces(mb, rows, key_fn)
    for cap, row, ck in ((cap0, rows[0], cap_keys[0]), (cap1, rows[-1], cap_keys[1])):
        if cap is None:
            continue
        c = mb.vert(cap)
        fan(mb, c, row, ck or key_fn(0, 0, Vector(cap)))
    return rows


def ellipsoid(mb, c, r, key, rot=None, n=14, rings=8):
    rot = (rot or Matrix.Identity(3)).to_3x3()
    c = Vector(c)
    top = mb.vert(c + rot @ V(0, 0, r[2]))
    bot = mb.vert(c + rot @ V(0, 0, -r[2]))
    rows = []
    for i in range(1, rings):
        ph = math.pi * i / rings
        z, s = math.cos(ph), math.sin(ph)
        rows.append([mb.vert(c + rot @ V(s * math.cos(2 * math.pi * k / n) * r[0],
                                            s * math.sin(2 * math.pi * k / n) * r[1], z * r[2]))
                     for k in range(n)])
    grid_faces(mb, rows, lambda i, k, cen: key)
    fan(mb, top, rows[0], key)
    fan(mb, bot, rows[-1], key, flip=True)


def catmull(ctrl, per=6):
    ctrl = [Vector(p) for p in ctrl]
    P = [ctrl[0] * 2 - ctrl[1]] + ctrl + [ctrl[-1] * 2 - ctrl[-2]]
    out, ts = [], []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
            ts.append(i - 1 + t)
    out.append(ctrl[-1])
    ts.append(len(ctrl) - 1.0)
    return out, ts


def tube(mb, pts, radii, keys, n=14, cap0=True, cap1=True, capr=0.5):
    """Tube through pts (parallel-transported frames), radius per point;
    keys: one key or one per segment. Caps are domes (3 rings)."""
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
        rows.append([mb.vert(p + N * (r * math.cos(2 * math.pi * k / n)) + B * (r * math.sin(2 * math.pi * k / n)))
                     for k in range(n)])
    kf = (lambda i, k, c: keys[i]) if isinstance(keys, (list, tuple)) else (lambda i, k, c: keys)
    grid_faces(mb, rows, kf)
    k0 = keys[0] if isinstance(keys, (list, tuple)) else keys
    k1 = keys[-1] if isinstance(keys, (list, tuple)) else keys
    for use, idx, sgn, key in ((cap0, 0, -1, k0), (cap1, m - 1, 1, k1)):
        if not use:
            continue
        p, r, (N_, B_) = pts[idx], radii[idx], frames[idx]
        prev = rows[idx]
        for s in (1, 2):
            a = (math.pi / 2) * s / 3
            cur = [mb.vert(p + (N_ * math.cos(2 * math.pi * k / n) + B_ * math.sin(2 * math.pi * k / n))
                           * r * math.cos(a) + Ts[idx] * sgn * r * capr * math.sin(a)) for k in range(n)]
            grid_faces(mb, [prev, cur], lambda i, k, c: key)
            prev = cur
        fan(mb, mb.vert(p + Ts[idx] * sgn * r * capr), prev, key)


def limb(mb, ctrl, rad_ctrl, key, per=5, n=14, cap0=True, cap1=True):
    pts, ts = catmull(ctrl, per)
    radii = []
    for t in ts:
        i = min(int(t), len(rad_ctrl) - 2)
        radii.append(lerp(rad_ctrl[i], rad_ctrl[i + 1], t - i))
    tube(mb, pts, radii, key, n=n, cap0=cap0, cap1=cap1)
    return pts


# ===========================================================================
# Dimensions (rest pose; Blender model space)
# ===========================================================================

HEAD_C = V(0.0, -0.004, 0.768)      # head ellipsoid centre
HX, HY, HZU, HZD = 0.214, 0.198, 0.200, 0.184

ROOT_H = V(0, 0, 0.31)
HIP_X = 0.070
HIP = V(HIP_X, 0.0, 0.300)
KNEE = V(HIP_X, -0.012, 0.183)
ANKLE = V(HIP_X, 0.0, 0.068)
TOE = V(HIP_X, -0.120, 0.022)
SOLE_Z = -ANKLE.z                    # the ground in foot space
SHOULDER = V(0.128, 0.004, 0.505)
L_UP, L_FORE, L_HAND = 0.100, 0.092, 0.070
HEAD_BONE = V(0, 0, 0.60)


def arm_dir(out_deg, fwd_deg, s):
    o, f = math.radians(out_deg), math.radians(fwd_deg)
    return V(s * math.sin(o) * math.cos(f), -math.sin(f), -math.cos(o) * math.cos(f)).normalized()


def arm_rest(s):
    sh = V(s * SHOULDER.x, SHOULDER.y, SHOULDER.z)
    el = sh + arm_dir(17, 4, s) * L_UP
    df = arm_dir(13, 20, s)
    wr = el + df * L_FORE
    tip = wr + df * L_HAND
    return sh, el, wr, tip


GRIP = 0.036     # wrist -> grip point (fist centre) along the hand


def grip_rest(s):
    """Rest grip point: the hand bone's head (held items attach here)."""
    _, _, wr, tip = arm_rest(s)
    return wr + (tip - wr).normalized() * GRIP


def side_pt(p, s):
    return V(s * p.x, p.y, p.z)


# --- head surface -----------------------------------------------------------

def hdir(u, v):
    return V(math.sin(u) * math.cos(v), -math.cos(u) * math.cos(v), math.sin(v))


def ell_pt(d, rx, ry, rzu, rzd):
    rz = rzu if d.z >= 0 else rzd
    k = 1.0 / math.sqrt((d.x / rx) ** 2 + (d.y / ry) ** 2 + (d.z / rz) ** 2)
    return d * k


def ell_nrm(p, rx, ry, rzu, rzd):
    rz = rzu if p.z >= 0 else rzd
    return V(p.x / rx ** 2, p.y / ry ** 2, p.z / rz ** 2).normalized()


def head_pt(u, v, off=0.0):
    """Point on the head (model space)."""
    p = ell_pt(hdir(u, v), HX, HY, HZU, HZD)
    if off:
        p = p + ell_nrm(p, HX, HY, HZU, HZD) * off
    return p + HEAD_C


def head_nrm(u, v):
    p = ell_pt(hdir(u, v), HX, HY, HZU, HZD)
    return ell_nrm(p, HX, HY, HZU, HZD)


def head_skin(mb):
    # the crown above v = 0.72 is always under the hair: one flat fan there
    NU, NV = 36, 19
    top = mb.vert(head_pt(0, math.pi / 2, -0.03))
    bot = mb.vert(head_pt(0, -math.pi / 2))
    rows = []
    for j in range(5, NV):
        v = math.pi / 2 - math.pi * j / NV
        rows.append([mb.vert(head_pt(-math.pi + 2 * math.pi * i / NU, v)) for i in range(NU)])
    grid_faces(mb, rows, lambda i, k, c: 'skin')
    fan(mb, top, rows[0], 'skin')
    fan(mb, bot, rows[-1], 'skin', flip=True)


def blob(mb, cu, cv, au, av, key, off, rot=0.0, nr=3, na=20, shape=None):
    """Elliptic patch on the head at (cu, cv), half sizes (au, av) rad.
    `off` metres above the surface, or a function of rho (0 centre..1 edge)."""
    offf = off if callable(off) else (lambda rho, _o=off: _o)
    c = mb.vert(head_pt(cu, cv, offf(0.0)))
    rows = []
    cr, sr = math.cos(rot), math.sin(rot)
    for i in range(1, nr + 1):
        rho = i / nr
        row = []
        for k in range(na):
            th = 2 * math.pi * k / na
            x, y = au * rho * math.cos(th), av * rho * math.sin(th)
            if shape:
                x, y = shape(x, y, th, rho)
            x, y = x * cr - y * sr, x * sr + y * cr
            row.append(mb.vert(head_pt(cu + x / math.cos(cv), cv + y, offf(rho))))
        rows.append(row)
    fan(mb, c, rows[0], key)
    grid_faces(mb, rows, lambda i, k, cc: key)


def strip(mb, curve, half_w, key, off, n=12):
    rows_a, rows_b = [], []
    for i in range(n + 1):
        s = i / n
        u, v = curve(s)
        u1, v1 = curve(max(0.0, s - 1e-3))
        u2, v2 = curve(min(1.0, s + 1e-3))
        tu, tv = (u2 - u1) * math.cos(v), v2 - v1
        L = math.hypot(tu, tv) or 1.0
        nu, nv = -tv / L, tu / L
        w = half_w(s)
        rows_a.append(mb.vert(head_pt(u + nu * w / math.cos(v), v + nv * w, off)))
        rows_b.append(mb.vert(head_pt(u - nu * w / math.cos(v), v - nv * w, off)))
    for i in range(n):
        mb.face((rows_a[i], rows_a[i + 1], rows_b[i + 1], rows_b[i]), key)


# --- face -------------------------------------------------------------------

EYE_U, EYE_V = 0.330, 0.165
EYE_AU, EYE_AV = 0.180, 0.245
MOUTH_V = -0.165


def build_eyes(mb):
    for s in (-1, 1):
        cu = s * EYE_U
        blob(mb, cu, EYE_V, EYE_AU, EYE_AV, 'eye_white', 0.002, nr=2, na=20)
        pu, pv, pa, pb = cu - s * 0.022, EYE_V - 0.030, 0.128, 0.198
        blob(mb, pu, pv, pa, pb, 'pupil', 0.004, nr=2, na=18)
        # catchlights, both upper-left on screen (the sun's side) + a small one
        blob(mb, pu - 0.048, pv + 0.080, 0.050, 0.060, 'eye_white', 0.006, nr=2, na=12)
        blob(mb, pu + 0.050, pv - 0.090, 0.020, 0.024, 'eye_white', 0.006, nr=1, na=8)


def build_brows(mb):
    for s in (-1, 1):
        cu = s * EYE_U
        curve = (lambda t, cu=cu, s=s: (cu + s * (t - 0.5) * 0.30,
                                         EYE_V + EYE_AV + 0.12 + 0.035 * (1 - ((t - 0.5) * 2) ** 2)))
        strip(mb, curve, lambda t: 0.026 * (0.55 + 0.45 * math.sin(math.pi * t)), 'hair', 0.003, n=8)


def build_mouth(mb):
    # a small soft smile
    strip(mb, lambda t: ((t - 0.5) * 0.30, MOUTH_V - 0.060 * (1 - ((t - 0.5) * 2) ** 2)),
          lambda t: 0.030 * (0.45 + 0.55 * math.sin(math.pi * t)), 'mouth', 0.003, n=10)


def build_face_extras(mb):
    ellipsoid(mb, head_pt(0.0, -0.03, -0.004), (0.020, 0.017, 0.016), 'skin',
              rot=frame_z(head_nrm(0.0, -0.03), V(1, 0, 0)), n=8, rings=5)
    for s in (-1, 1):
        u, v = s * 1.50, -0.05
        p = head_pt(u, v, -0.008)
        rot = frame_z(head_nrm(u, v), V(0, 0, 1))
        ellipsoid(mb, p, (0.052, 0.036, 0.030), 'skin', rot=rot, n=10, rings=6)
    for s in (-1, 1):
        blob(mb, s * 0.60, -0.06, 0.11, 0.065, 'blush', 0.002, nr=2, na=14)


def build_eyelid(mb, s):
    """The CLOSED lid (rest shape): a skin patch over the eye with a dark
    lash line curving down (a content, sleepy closed eye)."""
    cu = s * EYE_U
    blob(mb, cu, EYE_V, EYE_AU * 1.10, EYE_AV * 1.08, 'skin',
         lambda rho: 0.0032 + 0.0068 * (1 - rho * rho), nr=3, na=22)
    strip(mb, lambda t: (cu + (t - 0.5) * 2 * EYE_AU * 0.95,
                         EYE_V - 0.05 - 0.07 * (1 - ((t - 0.5) * 2) ** 2)),
          lambda t: 0.028 * (0.5 + 0.5 * math.sin(math.pi * t)), 'pupil', 0.0105, n=10)


def eyelid_pivot(s):
    return head_pt(s * EYE_U, EYE_V + EYE_AV * 0.9, -0.016)


def build_mouth_open(mb):
    """Open mouth (rest shape, hidden by scale ~0): a D shape, flat top
    covering the smile, round bottom, with a tongue."""
    blob(mb, 0.0, MOUTH_V - 0.035, 0.175, 0.100, 'mouth', 0.006, nr=3, na=22,
         shape=lambda x, y, th, rho: (x * (1.0 if y < 0 else 1.05), y if y < 0 else y * 0.45))
    blob(mb, 0.0, MOUTH_V - 0.095, 0.085, 0.032, 'blush', 0.0075, nr=2, na=14)


def mouth_pivot():
    return head_pt(0.0, MOUTH_V - 0.01, -0.014)


# --- hair -------------------------------------------------------------------

HAIR_BASE = [(0.0, 0.62), (0.55, 0.60), (0.85, 0.50), (1.02, 0.32), (1.12, 0.10), (1.22, -0.04),
             (1.30, 0.06), (1.38, 0.28), (1.58, 0.34), (1.78, 0.18), (2.10, -0.07), (2.50, -0.32),
             (math.pi, -0.42)]
LOCKS = 16
LOCK_PHASE = 0.13
HAIR_TOP = 0.016


def lock_ridge(u):
    return 0.5 + 0.5 * math.cos(LOCKS * (u + LOCK_PHASE))


def hairline(u):
    a = abs(u)
    v = interp(HAIR_BASE, a)
    if a < 1.0:
        amp = 0.19 * smoothstep(1.0, 0.62, a)
        v -= amp * lock_ridge(u) ** 2.2
    if a > 2.05:
        v -= 0.11 * smoothstep(2.05, 2.4, a) * lock_ridge(u + 0.2) ** 2.2
    v -= 0.10 * max(0.0, 1 - abs(a - 1.20) / 0.08)
    return v


def hair_thick(u, t):
    base = 0.007 + (HAIR_TOP - 0.007) * (1 - t) ** 0.9
    rid = lock_ridge(u + 0.05 * math.sin(3 * t))
    k = smoothstep(0.05, 0.35, t)
    lumps = 1 + 0.30 * (rid - 0.5) * k
    flick = 0.006 * smoothstep(0.75, 1.0, t) * (0.4 + 0.6 * rid)
    return base * lumps + flick


def build_hair(mb):
    NU = 80
    TS = [0.15, 0.35, 0.55, 0.72, 0.85, 0.94, 1.0]
    vt = math.pi / 2
    rows = []
    for t in TS:
        row = []
        for i in range(NU):
            u = -math.pi + 2 * math.pi * i / NU
            v = vt - t * (vt - hairline(u))
            row.append(mb.vert(head_pt(u, v, hair_thick(u, t))))
        rows.append(row)
    inner = []
    for i in range(NU):
        u = -math.pi + 2 * math.pi * i / NU
        inner.append(mb.vert(head_pt(u, hairline(u) + 0.02, -0.004)))
    rows.append(inner)
    grid_faces(mb, rows, lambda i, k, c: 'hair')
    top = mb.vert(head_pt(0, vt, hair_thick(0, 0)))
    fan(mb, top, rows[0], 'hair')


# --- torso ------------------------------------------------------------------

# z, half width, front, back
SHIRT = [(0.325, 0.142, 0.114, 0.101), (0.337, 0.149, 0.120, 0.105), (0.365, 0.152, 0.123, 0.106),
         (0.405, 0.151, 0.121, 0.104), (0.445, 0.146, 0.114, 0.099), (0.485, 0.138, 0.104, 0.092),
         (0.515, 0.126, 0.093, 0.084), (0.540, 0.104, 0.077, 0.069), (0.560, 0.070, 0.056, 0.052)]
BANDS = [(0.372, 0.397), (0.425, 0.450), (0.478, 0.503)]
SHIRT_Z = sorted(set([0.325, 0.334, 0.350, 0.530, 0.552] +
                     [z for b in BANDS for z in b]))
PELVIS = [(0.245, 0.050, 0.040, 0.042), (0.258, 0.100, 0.076, 0.082), (0.274, 0.122, 0.092, 0.098),
          (0.300, 0.132, 0.100, 0.104), (0.330, 0.134, 0.103, 0.104), (0.352, 0.130, 0.101, 0.102)]


def shirt_key(z):
    for z0, z1 in BANDS:
        if z0 <= z <= z1:
            return 'shirt_stripe'
    return 'shirt'


def build_shirt(mb):
    rings = []
    for z in SHIRT_Z:
        hw, fr, bk = interp_rows(SHIRT, z)
        rings.append(ring_pts(V(0, 0, z), V(1, 0, 0), V(0, -1, 0), hw, hw, fr, bk, 30, 2.3))
    loft(mb, rings, lambda i, k, c: shirt_key(c.z), cap0=V(0, 0, 0.327), cap1=V(0, 0, 0.568),
         cap_keys=('shirt', 'shirt'))


def build_emblem(mb, shirt_mb):
    bvh = BVHTree.FromPolygons([tuple(v) for v in shirt_mb.v], shirt_mb.f)
    cz, r = 0.452, 0.046
    nr, na = 2, 20

    def proj(x, z):
        hit = bvh.ray_cast(V(x, -0.4, z), V(0, 1, 0))
        if hit[0] is None:
            return V(x, -0.12, z)
        n = hit[1] if hit[1].y < 0 else -hit[1]
        return hit[0] + n * 0.0035
    c = mb.vert(proj(0, cz))
    rows = []
    for i in range(1, nr + 1):
        rho = i / nr
        rows.append([mb.vert(proj(r * rho * math.cos(2 * math.pi * k / na),
                                  cz + r * rho * math.sin(2 * math.pi * k / na))) for k in range(na)])
    fan(mb, c, rows[0], 'emblem')
    grid_faces(mb, rows, lambda i, k, cc: 'emblem')


def build_pelvis(mb):
    rings = []
    for z in [0.245, 0.252, 0.260, 0.274, 0.295, 0.320, 0.345]:
        hw, fr, bk = interp_rows(PELVIS, z)
        rings.append(ring_pts(V(0, 0, z), V(1, 0, 0), V(0, -1, 0), hw, hw, fr, bk, 24, 2.3))
    loft(mb, rings, lambda i, k, c: 'pants', cap0=V(0, 0, 0.240), cap1=V(0, 0, 0.356))


# --- hands, shoes -------------------------------------------------------------

def build_hand(mb, s):
    """A soft mitten at the rest wrist, palm facing in."""
    _, el, wr, tip = arm_rest(s)
    d = (tip - wr).normalized()
    out = V(s, 0, 0)
    rot = frame_z(d, out)                 # Z along the hand, X outwards
    fwd = rot @ V(0, 1, 0)
    if fwd.y > 0:                          # make local +Y the hand's front (thumb side)
        fwd = -fwd
    c = wr + d * 0.036
    rr = Matrix((rot @ V(1, 0, 0), fwd, d)).transposed()
    ellipsoid(mb, c, (0.029, 0.038, 0.043), 'skin', rot=rr, n=12, rings=7)
    th = wr + d * 0.024 + fwd * 0.030 - (rot @ V(1, 0, 0)) * 0.006
    ellipsoid(mb, th, (0.014, 0.014, 0.022), 'skin', rot=rr @ RX(-25), n=8, rings=6)


SHOE = [  # y (forward is -), half width, top z, bottom z   (foot space, ankle at 0)
    (0.068, 0.034, -0.024, -0.056), (0.062, 0.046, 0.000, -0.058), (0.045, 0.052, 0.012, -0.058),
    (0.020, 0.055, 0.014, -0.058), (-0.010, 0.057, 0.003, -0.058), (-0.040, 0.058, -0.011, -0.058),
    (-0.070, 0.058, -0.021, -0.058), (-0.098, 0.056, -0.027, -0.058), (-0.120, 0.050, -0.032, -0.056),
    (-0.138, 0.038, -0.037, -0.053), (-0.150, 0.020, -0.042, -0.050)]
SOLE = [(0.076, 0.030), (0.070, 0.050), (0.050, 0.058), (0.0, 0.061), (-0.060, 0.063), (-0.110, 0.058),
        (-0.140, 0.046), (-0.156, 0.026)]
HEEL_PIV = V(0, 0.060, SOLE_Z)        # foot-space pivots for heel strike / toe off
TOE_PIV = V(0, -0.105, SOLE_Z)


def build_shoe(mb, s):
    org = side_pt(ANKLE, s)
    rings = []
    for y, hw, top, bot in SHOE:
        zc = (top + bot) / 2
        rings.append([org + p for p in ring_pts(V(0, y, zc), V(1, 0, 0), V(0, 0, 1),
                                                 hw, hw, top - zc, zc - bot, 16, 2.5)])

    def key(i, k, c):
        c = c - org
        if c.y < -0.128 and c.z < -0.030:
            return 'shoe_sole'                 # toe cap
        if abs(c.x) < 0.020 and -0.065 < c.y < -0.012 and c.z > -0.022:
            return 'shoe_sole'                 # laces
        return 'shoes'
    loft(mb, rings, key, cap0=org + V(0, 0.072, -0.040), cap1=org + V(0, -0.154, -0.046),
         cap_keys=('shoes', 'shoe_sole'))
    zs = [(SOLE_Z, 0.94), (SOLE_Z + 0.002, 1.0), (SOLE_Z + 0.016, 1.0), (SOLE_Z + 0.020, 0.95)]
    rings = []
    for z, sc in zs:
        pts = []
        n = 18
        cy = (SOLE[0][0] + SOLE[-1][0]) / 2
        ry = (SOLE[0][0] - SOLE[-1][0]) / 2
        for k in range(n):
            th = 2 * math.pi * k / n
            y = cy + ry * math.sin(th)
            hw = interp(sorted(SOLE), y)
            x = hw * math.cos(th) / max(1e-3, abs(math.cos(th)) ** 0.35) * 0.98
            x = clamp(x, -hw, hw)
            pts.append(org + V(x * sc, cy + (y - cy) * sc, z))
        rings.append(pts)
    loft(mb, rings, lambda i, k, c: 'shoe_sole', cap0=org + V(0, -0.04, SOLE_Z - 0.001),
         cap1=org + V(0, -0.04, SOLE_Z + 0.021))


# ===========================================================================
# The cap (built in model space at rest, exported relative to the head bone)
# ===========================================================================

CAP_INFL = 0.027


def cap_pt(d, infl=CAP_INFL):
    return ell_pt(d, HX + infl, HY + infl, HZU + infl, HZD + infl)


def cap_dir(Rc, a, b):
    return (Rc @ V(math.sin(b) * math.cos(a), math.sin(b) * math.sin(a), math.cos(b))).normalized()


def crown(mb, Rc, edge_deg, key, n=36, rings=8, infl=CAP_INFL, fold=0.012):
    rows = []
    for i in range(1, rings + 1):
        b = math.radians(edge_deg) * (i / rings) ** 0.9
        rows.append([mb.vert(cap_pt(cap_dir(Rc, 2 * math.pi * k / n, b), infl)) for k in range(n)])
    inner = []
    b = math.radians(edge_deg - 1.0)
    for k in range(n):
        d = cap_dir(Rc, 2 * math.pi * k / n, b)
        inner.append(mb.vert(cap_pt(d, infl) - d * fold))
    rows.append(inner)
    grid_faces(mb, rows, lambda i, k, c: key if i < len(rows) - 2 else 'cap_brim')
    top = mb.vert(cap_pt((Rc @ V(0, 0, 1)).normalized(), infl))
    fan(mb, top, rows[0], key)
    # seams: six thin raised gores would cost triangles; the button reads enough


def bill(mb, Rc, edge_deg, span_deg, length, droop_deg, camber, thick, key, under, fwd=-90.0,
         infl=CAP_INFL):
    ncol, nrow = 15, 4
    b = math.radians(edge_deg - 0.5)
    inner, outer = [], []
    fw = Rc @ V(math.cos(math.radians(fwd)), math.sin(math.radians(fwd)), 0)
    ax = Rc @ V(0, 0, 1)
    for c in range(ncol):
        t = (c / (ncol - 1)) * 2 - 1
        a = math.radians(fwd + span_deg * t)
        d = cap_dir(Rc, a, b)
        inner.append(cap_pt(d, infl) - ax * 0.004 - d * 0.010)
        outer.append(length * (1 - abs(t) ** 2.2) ** 0.55 + 0.004)
    top_rows, bot_rows = [], []
    tdn = math.tan(math.radians(droop_deg))
    for r in range(nrow + 1):
        s = r / nrow
        trow, brow = [], []
        for c in range(ncol):
            t = (c / (ncol - 1)) * 2 - 1
            pin, L = inner[c], outer[c]
            p = pin + fw * (L * s) - ax * (L * s * tdn) - ax * (camber * t * t * s)
            trow.append(mb.vert(p))
            brow.append(mb.vert(p - ax * thick))
        top_rows.append(trow)
        bot_rows.append(brow)
    for r in range(nrow):
        for c in range(ncol - 1):
            mb.face((top_rows[r][c], top_rows[r][c + 1], top_rows[r + 1][c + 1], top_rows[r + 1][c]), key)
            mb.face((bot_rows[r][c], bot_rows[r + 1][c], bot_rows[r + 1][c + 1], bot_rows[r][c + 1]), under)
    for c in range(ncol - 1):
        mb.face((top_rows[nrow][c], bot_rows[nrow][c], bot_rows[nrow][c + 1], top_rows[nrow][c + 1]), key)
    for c in (0, ncol - 1):
        for r in range(nrow):
            mb.face((top_rows[r][c], bot_rows[r][c], bot_rows[r + 1][c], top_rows[r + 1][c]), key)
    for c in range(ncol - 1):
        mb.face((top_rows[0][c], top_rows[0][c + 1], bot_rows[0][c + 1], bot_rows[0][c]), under)


def build_cap(mb):
    """Head-space cap (relative to the head centre), as in Monster Hop:
    pushed back so the bill rides above the eyes."""
    Rc = RX(-14.0)
    edge = 64.0
    crown(mb, Rc, edge, 'cap')
    ax = (Rc @ V(0, 0, 1)).normalized()
    ellipsoid(mb, cap_pt(ax), (0.019, 0.019, 0.010), 'cap', rot=frame_z(ax, V(1, 0, 0)), n=10, rings=5)
    bill(mb, Rc, edge, 58.0, 0.125, 4.0, 0.022, 0.012, 'cap_brim', 'cap_brim')


# ===========================================================================
# Rig
# ===========================================================================

def bone_list():
    B = [('root', ROOT_H, V(0, 0, 0.37), None),
         ('spine', V(0, 0, 0.37), V(0, 0, 0.45), 'root'),
         ('chest', V(0, 0, 0.45), V(0, 0, 0.555), 'spine'),
         ('neck', V(0, 0, 0.555), HEAD_BONE, 'chest'),
         ('head', HEAD_BONE, V(0, 0, 0.97), 'neck')]
    for s, sd in ((1, 'L'), (-1, 'R')):
        sh, el, wr, tip = arm_rest(s)
        B += [('upper_arm.' + sd, sh, el, 'chest'),
              ('forearm.' + sd, el, wr, 'upper_arm.' + sd),
              # head at the grip point, pointing straight up: identity rest
              # basis in Godot, so items (origin = grip, model axes) attach
              # to hand.X with no offset
              ('hand.' + sd, grip_rest(s), grip_rest(s) + V(0, 0, 0.05), 'forearm.' + sd),
              ('thigh.' + sd, side_pt(HIP, s), side_pt(KNEE, s), 'root'),
              ('shin.' + sd, side_pt(KNEE, s), side_pt(ANKLE, s), 'thigh.' + sd),
              ('foot.' + sd, side_pt(ANKLE, s), side_pt(TOE, s), 'shin.' + sd)]
        p = eyelid_pivot(s)
        B.append(('eyelid.' + sd, p, p + V(0, 0, -0.03), 'head'))
    p = mouth_pivot()
    B.append(('mouth_open', p, p + V(0, 0, -0.03), 'head'))
    return B


def build_body(arm):
    parts = []

    def obj(name, mb, **kw):
        o = to_object(name, mb, **kw)
        return o

    # head: skin, ears, nose, hair, face patches
    mb = MB()
    head_skin(mb)
    build_face_extras(mb)
    h = obj('t_head', mb)
    mb = MB()
    build_hair(mb)
    hair = obj('t_hair', mb)
    mb = MB()
    build_eyes(mb)
    build_brows(mb)
    build_mouth(mb)
    face = obj('t_face', mb, recalc=False, out_from=HEAD_C)
    for o in (h, hair, face):
        C.skin_rigid(o, 'head')
        parts.append(o)
    for s, sd in ((1, 'L'), (-1, 'R')):
        mb = MB()
        build_eyelid(mb, s)
        o = obj('t_lid' + sd, mb, recalc=False, out_from=HEAD_C)
        C.skin_rigid(o, 'eyelid.' + sd)
        parts.append(o)
    mb = MB()
    build_mouth_open(mb)
    o = obj('t_mouth_open', mb, recalc=False, out_from=HEAD_C)
    C.skin_rigid(o, 'mouth_open')
    parts.append(o)
    # neck
    mb = MB()
    tube(mb, [V(0, 0.004, 0.535), V(0, 0.004, 0.60), V(0, 0.0, 0.64)], [0.050, 0.049, 0.047], 'skin', n=10)
    o = obj('t_neck', mb)
    C.skin_near(o, arm, ['chest', 'neck', 'head'], power=4)
    parts.append(o)
    # shirt + emblem
    mb = MB()
    build_shirt(mb)
    em = MB()
    build_emblem(em, mb)
    o = obj('t_shirt', mb)
    o2 = obj('t_emblem', em, recalc=False, out_from=V(0, 0, 0.45))
    for x in (o, o2):
        C.skin_near(x, arm, ['root', 'spine', 'chest'], power=3)
        parts.append(x)
    # jeans
    mb = MB()
    build_pelvis(mb)
    o = obj('t_pelvis', mb)
    C.skin_rigid(o, 'root')
    parts.append(o)
    for s, sd in ((1, 'L'), (-1, 'R')):
        sh, el, wr, tip = arm_rest(s)
        du = (el - sh).normalized()
        # arm: one smooth tube shoulder -> wrist
        mb = MB()
        limb(mb, [sh - du * 0.012, el, wr + (wr - el).normalized() * 0.014], [0.034, 0.031, 0.029], 'skin',
             per=4, n=10, cap0=False, cap1=False)
        o = obj('t_arm' + sd, mb)
        C.skin_near(o, arm, ['upper_arm.' + sd, 'forearm.' + sd], power=4)
        parts.append(o)
        # sleeve + shoulder ball
        mb = MB()
        tube(mb, [sh, sh + du * 0.030, sh + du * 0.050], [0.054, 0.053, 0.051], 'shirt',
             n=12, cap0=False, cap1=False)
        tube(mb, [sh + du * 0.046, sh + du * 0.072], [0.0525, 0.0515], 'shirt_stripe',
             n=12, cap0=False, capr=0.25)
        ellipsoid(mb, sh, (0.054, 0.054, 0.054), 'shirt', n=12, rings=7)
        o = obj('t_sleeve' + sd, mb)
        C.skin_rigid(o, 'upper_arm.' + sd)
        parts.append(o)
        mb = MB()
        build_hand(mb, s)
        o = obj('t_hand' + sd, mb)
        C.skin_rigid(o, 'hand.' + sd)
        parts.append(o)
        # leg: jeans tube hip -> ankle, rolled cuff
        hip, kn, an = side_pt(HIP, s), side_pt(KNEE, s), side_pt(ANKLE, s)
        dshin = (an - kn).normalized()
        cuff = an - dshin * 0.040
        mb = MB()
        limb(mb, [hip + V(0, 0, 0.035), hip, kn, cuff + dshin * 0.012], [0.057, 0.061, 0.056, 0.057], 'pants',
             per=4, n=12, cap0=False, cap1=False)
        o = obj('t_leg' + sd, mb)
        C.skin_near(o, arm, ['thigh.' + sd, 'shin.' + sd], power=4)
        parts.append(o)
        mb = MB()
        tube(mb, [cuff - dshin * 0.022, cuff, cuff + dshin * 0.006],
             [0.064, 0.066, 0.061], 'pants', n=12)
        o = obj('t_cuff' + sd, mb)
        C.skin_rigid(o, 'shin.' + sd)
        parts.append(o)
        mb = MB()
        build_shoe(mb, s)
        o = obj('t_shoe' + sd, mb)
        C.skin_rigid(o, 'foot.' + sd)
        parts.append(o)
    return C.bind('tommy', arm, parts)


# ===========================================================================
# Posing: a pose is described in "character axes" (model space): each bone's
# rotation is an Euler XYZ (degrees) about the bone's head, relative to its
# parent:  +rx tilts an upward bone forward (a downward limb swings BACK),
#          +ry tilts an upward bone to his left (+X) (a downward limb to -X),
#          +rz turns the front towards his left.
# Legs are always solved by IK to foot targets; arms are FK, or IK to a
# target point. solve() converts everything into bone-local channels.
# ===========================================================================

REST = {}
PARENT = {}
LEN = {}


def read_rest(arm):
    for b in arm.data.bones:
        REST[b.name] = (b.head_local.copy(), b.matrix_local.to_3x3().copy(), b.tail_local.copy())
        PARENT[b.name] = b.parent.name if b.parent else None


def ik2(a, target, l1, l2, pole):
    d = target - a
    dist = d.length
    dn = d.normalized() if dist > 1e-9 else V(0, 0, -1)
    dist_c = clamp(dist, abs(l1 - l2) + 1e-4, (l1 + l2) * 0.9995)
    cos_a = (l1 * l1 + dist_c * dist_c - l2 * l2) / (2 * l1 * dist_c)
    sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
    pp = pole - dn * pole.dot(dn)
    if pp.length < 1e-6:
        pp = V(0, -1, 0) - dn * (-dn.y)
    pp.normalize()
    return a + dn * (cos_a * l1) + pp * (sin_a * l1), a + dn * dist_c


def frame3(axis, ref):
    y = axis.normalized()
    x = ref - y * ref.dot(y)
    if x.length < 1e-6:
        x = V(1, 0, 0) - y * y.x
    x.normalize()
    z = x.cross(y)
    return Matrix((x, y, z)).transposed()


def eul(r):
    return Euler([math.radians(a) for a in r], 'XYZ').to_matrix()


class Pose:
    def __init__(self):
        self.root = V(0, 0, 0)
        self.r = {}
        self.s = {}
        # foot: (footprint V = ankle position if the foot were flat,
        #        pitch deg (+ toe up), yaw deg (+ toe to his left), lift V)
        self.foot = {'L': None, 'R': None}
        self.hand = {'L': None, 'R': None}    # (target V, pole V) or None
        self.lid = [0.0, 0.0]                 # L, R: 0 open .. 1 closed
        self.mouth = (0.0, 0.0, 0.0)          # mouth_open scale (w, h, d)
        self.legfk = {'L': False, 'R': False}  # True: legs FK from self.r (sit, sleep)
        # hold: (euler deg in the chest frame, k): the hand's WORLD rotation is
        # blended (k) towards chest @ euler, so a held item (+Z up in rest)
        # stays upright / is tipped on purpose whatever the arm does
        self.hold = {'L': None, 'R': None}

    def add(self, b, r):
        a = self.r.get(b, (0, 0, 0))
        self.r[b] = tuple(x + y for x, y in zip(a, r))


def foot_default(sd):
    s = 1 if sd == 'L' else -1
    return (side_pt(ANKLE, s), 0.0, 0.0, V(0, 0, 0))


def foot_place(fp):
    """Ankle position and foot rotation for a foot spec, pivoting on the heel
    (toe up) or the toe ball (heel up) so the contact point stays put."""
    P, pitch, yaw, lift = fp
    Gf = RZ(yaw) @ RX(-pitch)
    Gy = RZ(yaw)
    piv = HEEL_PIV if pitch > 0 else TOE_PIV
    contact = P + Gy @ piv
    ank = contact - Gf @ piv + lift
    return ank, Gf


def hold_rot(p, sd, Gh, Gchest):
    e, k = p.hold[sd]
    q0 = Gh.to_quaternion()
    q1 = (Gchest @ eul(e)).to_quaternion()
    if q0.dot(q1) < 0:
        q1.negate()
    return q0.slerp(q1, clamp(k, 0.0, 1.0)).to_matrix()


def solve(p):
    """Pose -> {bone: (R_char 3x3, loc V or None, scale or None)} and the
    world joints (for checks)."""
    D, G, out, J = {}, {}, {}, {}
    order = ['root', 'spine', 'chest', 'neck', 'head', 'eyelid.L', 'eyelid.R', 'mouth_open']
    for b in order:
        h, M, _ = REST[b]
        R = eul(p.r.get(b, (0, 0, 0)))
        sc = p.s.get(b)
        if b == 'eyelid.L':
            v = max(0.01, p.lid[0])
            sc = (v, v, v)
        elif b == 'eyelid.R':
            v = max(0.01, p.lid[1])
            sc = (v, v, v)
        elif b == 'mouth_open':
            sc = tuple(max(0.01, x) for x in p.mouth)
        S = Matrix.Identity(3)
        if sc is not None:
            S = M @ Matrix.Diagonal(V(sc)) @ M.inverted()
        L4 = T4(h) @ (R @ S).to_4x4() @ T4(-h)
        if b == 'root':
            D[b] = T4(p.root) @ L4
            G[b] = R
            out[b] = (R, p.root.copy(), sc)
        else:
            par = PARENT[b]
            D[b] = D[par] @ L4
            G[b] = G[par] @ R
            out[b] = (R, None, sc)
    for sd, s in (('L', 1), ('R', -1)):
        ua, fa, hd = 'upper_arm.' + sd, 'forearm.' + sd, 'hand.' + sd
        if p.hand[sd] is None:
            for b in (ua, fa, hd):
                h, M, _ = REST[b]
                R = eul(p.r.get(b, (0, 0, 0)))
                if b == hd and p.hold[sd] is not None:
                    R = G[fa].transposed() @ hold_rot(p, sd, G[fa] @ R, G['chest'])
                D[b] = D[PARENT[b]] @ T4(h) @ R.to_4x4() @ T4(-h)
                G[b] = G[PARENT[b]] @ R
                out[b] = (R, None, None)
        else:
            tgt, pole = p.hand[sd]
            S0, _, E0 = REST[ua]
            W0 = REST[fa][2]
            Sw = D['chest'] @ S0
            E, W = ik2(Sw, tgt, (E0 - S0).length, (W0 - E0).length, pole)
            ref0 = E0 - (S0 + (W0 - S0) * ((E0 - S0).dot(W0 - S0) / (W0 - S0).length_squared))
            Gu = frame3(E - Sw, pole) @ frame3(E0 - S0, ref0).transposed()
            Gf = frame3(W - E, pole) @ frame3(W0 - E0, ref0).transposed()
            Rh = eul(p.r.get(hd, (0, 0, 0)))
            Gh = Gf @ Rh
            if p.hold[sd] is not None:
                Gh = hold_rot(p, sd, Gh, G['chest'])
            for b, Gb in ((ua, Gu), (fa, Gf), (hd, Gh)):
                R = G[PARENT[b]].transposed() @ Gb
                G[b] = Gb
                out[b] = (R, None, None)
            J['wrist' + sd] = W
    for sd, s in (('L', 1), ('R', -1)):
        th, sh, ft = 'thigh.' + sd, 'shin.' + sd, 'foot.' + sd
        H0, K0, A0 = REST[th][0], REST[sh][0], REST[ft][0]
        if p.legfk[sd]:
            for b in (th, sh, ft):
                h = REST[b][0]
                R = eul(p.r.get(b, (0, 0, 0)))
                D[b] = D[PARENT[b]] @ T4(h) @ R.to_4x4() @ T4(-h)
                G[b] = G[PARENT[b]] @ R
                out[b] = (R, None, None)
            J['ankle' + sd] = J['ankle_tgt' + sd] = D[sh] @ A0
            J['foot' + sd] = G[ft]
            continue
        Hw = D['root'] @ H0
        fp = p.foot[sd] or foot_default(sd)
        A, Gfoot = foot_place(fp)
        fwd = (G['root'] @ V(0, -1, 0)) + (Gfoot @ V(0, -1, 0))
        fwd.z = max(fwd.z, -0.2)
        pole = (fwd.normalized() + V(s * 0.12, 0, 0)).normalized()
        K, A2 = ik2(Hw, A, (K0 - H0).length, (A0 - K0).length, pole)
        Gt = frame3(K - Hw, pole) @ frame3(K0 - H0, V(0, -1, 0)).transposed()
        Gs = frame3(A2 - K, pole) @ frame3(A0 - K0, V(0, -1, 0)).transposed()
        for b, Gb in ((th, Gt), (sh, Gs), (ft, Gfoot)):
            out[b] = (G[PARENT[b]].transposed() @ Gb, None, None)
            G[b] = Gb
        J['ankle' + sd] = A2
        J['ankle_tgt' + sd] = A
        J['foot' + sd] = Gfoot
    J['D'] = D
    return out, J


def bake(arm, name, frames, pose_fn, check_feet=None):
    """Evaluate pose_fn(t) at every frame and key every bone."""
    keys = {}
    prev = {}
    err = 0.0
    for f in range(frames + 1):
        t = f / FPS
        out, J = solve(pose_fn(t))
        k = {}
        for b in REST:
            R, loc, sc = out[b]
            M = REST[b][1]
            Rl = M.inverted() @ R @ M
            e = Rl.to_euler('XYZ', prev[b]) if b in prev else Rl.to_euler('XYZ')
            prev[b] = e
            v = {'rot': tuple(math.degrees(a) for a in e), 'scale': tuple(sc) if sc else (1, 1, 1)}
            if b == 'root':
                v['loc'] = tuple(M.inverted() @ loc)
            k[b] = v
        keys[f] = k
        for sd in 'LR':
            err = max(err, (J['ankle' + sd] - J['ankle_tgt' + sd]).length)
        if check_feet:
            check_feet(t, J)
    act = C.action(arm, name, frames, keys, fps=FPS)
    if A.get('check') and BODY:
        ground_check(arm, BODY[0], act, frames)
    print('[tommy] %-11s %3d frames  %.2f s  max IK miss %.1f mm' % (name, frames, frames / FPS, err * 1000))


# ---------------------------------------------------------------- curves

def trk(t, keys):
    """Catmull-Rom (non-uniform) through [(t, value)], flat at both ends.
    Values may be floats or tuples."""
    if isinstance(keys[0][1], (tuple, list)):
        n = len(keys[0][1])
        return tuple(trk(t, [(k[0], k[1][i]) for k in keys]) for i in range(n))
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for i in range(len(keys) - 1):
        t0, p0 = keys[i]
        t1, p1 = keys[i + 1]
        if t <= t1:
            break
    if 0 < i:
        m0 = (p1 - keys[i - 1][1]) / (t1 - keys[i - 1][0])
    else:
        m0 = 0.0
    if i + 2 < len(keys):
        m1 = (keys[i + 2][1] - p0) / (keys[i + 2][0] - t0)
    else:
        m1 = 0.0
    h = t1 - t0
    u = (t - t0) / h
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * m0 +
            (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * m1)


def blink(t, t0, dur=0.20):
    """Lid closure for a blink starting at t0 (fast close, slower open)."""
    x = t - t0
    if x < 0 or x > dur:
        return 0.0
    c = 0.06
    if x < c:
        return smoothstep(0, c, x)
    if x < c + 0.03:
        return 1.0
    return 1.0 - smoothstep(c + 0.03, dur, x)


TAU = 2 * math.pi


def sinw(t, period, phase=0.0):
    return math.sin(TAU * (t / period - phase))


def cosw(t, period, phase=0.0):
    return math.cos(TAU * (t / period - phase))


# ---------------------------------------------------------------- base poses

ARM_RELAX = {'L': (0, 0, 0), 'R': (0, 0, 0)}


def idle_upper(p, t, period=4.0, look=True):
    """Breathing, a slow sway and a look around (all periodic in `period`)."""
    b = sinw(t, period / 2)
    w = sinw(t, period)
    p.root += V(0.006 * w, 0, 0.002 * b - 0.004)
    p.add('root', (0, -1.5 * w, 0))
    p.add('spine', (-1.0 * b, 1.0 * w, 0))
    p.add('chest', (-1.5 * b, 1.2 * w, 0))
    p.add('neck', (0.8 * b, 0, 0))
    lag = sinw(t, period / 2, 0.08)
    for sd, s in (('L', 1), ('R', -1)):
        p.add('upper_arm.' + sd, (2.0 * lag, -s * (1.5 + 1.5 * lag), 0))
        p.add('forearm.' + sd, (-6 - 2.0 * sinw(t, period / 2, 0.15), 0, 0))
        p.add('hand.' + sd, (-4 - 3 * sinw(t, period / 2, 0.2), 0, 0))
    if look:
        T = period
        yaw = trk(t, [(0, 0), (0.25 * T, 0), (0.32 * T, 30), (0.47 * T, 27), (0.56 * T, -24),
                      (0.70 * T, -22), (0.80 * T, 2), (0.9 * T, 0), (T, 0)])
        tilt = trk(t, [(0, 0), (0.25 * T, 0), (0.33 * T, 7), (0.47 * T, 6), (0.57 * T, -6),
                       (0.70 * T, -5), (0.80 * T, 0), (T, 0)])
        nod = trk(t, [(0, -3), (0.25 * T, -3), (0.30 * T, 2), (0.35 * T, -4), (0.47 * T, -4),
                      (0.52 * T, 1), (0.58 * T, -5), (0.70 * T, -5), (0.82 * T, -2), (T, -3)])
        p.add('chest', (0, 0, 0.12 * yaw))
        p.add('neck', (0, 0, 0.3 * yaw))
        p.add('head', (nod, -tilt, 0.58 * yaw))


# ---------------------------------------------------------------- gaits

class Gait:
    def __init__(self, period, speed, stance, lift, heel, toe, width=HIP_X):
        self.T, self.v, self.S = period, speed, stance
        self.Y0 = speed * stance * period / 2      # footprint +- from the hip
        self.lift, self.heel, self.toe, self.width = lift, heel, toe, width

    def foot(self, t, s, phase0):
        q = (t / self.T + phase0) % 1.0
        S = self.S
        x = s * self.width
        if q < S:
            u = q / S
            y = -self.Y0 + 2 * self.Y0 * u
            pitch = trk(u, [(0, self.heel), (0.28, 0), (0.55, 0), (1.0, -self.toe)])
            lift = V(0, 0, 0)
        else:
            u = (q - S) / (1 - S)
            e = u - math.sin(TAU * u) / TAU
            y = self.Y0 - 2 * self.Y0 * e
            pitch = trk(u, [(0, -self.toe), (0.3, -self.toe * 0.6), (0.7, self.heel * 0.6), (1.0, self.heel)])
            lift = V(0, 0, self.lift * math.sin(math.pi * u ** 0.85) ** 1.2)
        return (V(x, y, ANKLE.z), pitch, 0.0, lift), q


def gait_pose(p, t, g, bob, base, lean, arms=True, arm_amp=26, elbow=22, carry=False):
    q = (t / g.T) % 1.0
    S = g.S
    for sd, s, ph in (('L', 1, 0.0), ('R', -1, 0.5)):
        p.foot[sd], _ = g.foot(t, s, ph)
    # hips: low at mid-stance (compression), high in the flight between steps
    hz = base - bob * math.cos(TAU * (2 * q - S))
    p.root += V(0, 0, hz)
    # sway over the stance foot, pelvis yaw follows the forward leg
    p.root += V(0.010 * math.cos(TAU * (q - S / 2)), 0, 0)
    p.add('root', (lean, 2.5 * math.cos(TAU * (q - S / 2)), -7 * math.cos(TAU * q)))
    p.add('spine', (2 + 1.5 * math.cos(TAU * (2 * q - S - 0.1)), 0, 3 * math.cos(TAU * q)))
    p.add('chest', (1.0 * math.cos(TAU * (2 * q - S - 0.15)), -1.5 * math.cos(TAU * (q - S / 2)),
                    6 * math.cos(TAU * q)))
    # head stays level-ish, a soft lagging bob
    p.add('neck', (-0.4 * lean, 0, -1 * math.cos(TAU * q)))
    p.add('head', (-0.5 * lean + 3.0 * math.cos(TAU * (2 * q - S - 0.22)), 1.5 * math.cos(TAU * (q - 0.3)),
                   -2 * math.cos(TAU * q)))
    sq = 0.025 * max(0.0, math.cos(TAU * (2 * q - S * 0.5)))
    p.s['spine'] = (1 + sq * 0.5, 1 - sq, 1 + sq * 0.5)
    if arms and not carry:
        for sd, s, ph in (('L', 1, 0.0), ('R', -1, 0.5)):
            c = math.cos(TAU * (q + ph - 0.06))
            c2 = math.cos(TAU * (q + ph - 0.13))
            p.add('upper_arm.' + sd, (arm_amp * c, -s * 4, s * 4))
            p.add('forearm.' + sd, (-elbow - 0.5 * elbow * max(0.0, -c2), 0, 0))
            p.add('hand.' + sd, (-8 + 6 * c2, 0, 0))
            p.hold[sd] = ((4 * c2, 0, 0), 0.7)
    return q


# ---------------------------------------------------------------- actions

def a_idle(t):
    p = Pose()
    idle_upper(p, t, 4.0)
    l = max(blink(t, 0.55), blink(t, 2.95), blink(t, 3.20))
    p.lid = [l, l]
    p.hold = {'L': ((0, 0, 0), 0.7), 'R': ((0, 0, 0), 0.7)}
    return p


def a_walk(t):
    p = Pose()
    g = Gait(0.5, 1.6, 0.36, 0.075, 16, 26)
    gait_pose(p, t, g, bob=0.012, base=-0.036, lean=5)
    return p


def a_run(t):
    p = Pose()
    g = Gait(0.4, 3.5, 0.20, 0.11, 6, 34)
    q = gait_pose(p, t, g, bob=0.016, base=-0.040, lean=13, arm_amp=38, elbow=70)
    p.add('neck', (-3, 0, 0))
    for sd, s in (('L', 1), ('R', -1)):
        p.add('upper_arm.' + sd, (0, -s * 6, 0))
    return p


CARRY = {'L': V(0.115, -0.175, 0.455), 'R': V(-0.115, -0.175, 0.455)}


def carry_arms(p, t, lag_bob=0.0):
    p.add('chest', (-3, 0, 0))
    for sd, s in (('L', 1), ('R', -1)):
        p.hand[sd] = None  # computed after the chest is known (see carry_targets)
        p.r['hand.' + sd] = (8, s * 0, -s * 8)


def with_carry(pose_fn, bob_fn=None):
    """Wrap a pose so both hands go to the carry points, which follow the
    chest (solved in two passes: the chest first, then the arm IK)."""
    def fn(t):
        p = pose_fn(t)
        carry_arms(p, t)
        out, J = solve(p)
        Dc = J['D']['chest']
        bob = bob_fn(t) if bob_fn else 0.0
        for sd, s in (('L', 1), ('R', -1)):
            tgt = Dc @ (CARRY[sd] + V(0, 0, bob))
            pole = (Dc.to_3x3() @ V(s * 0.9, 0.5, -0.6)).normalized()
            p.hand[sd] = (tgt, pole)
        return p
    return fn


def a_carry_idle(t):
    p = Pose()
    idle_upper(p, t, 2.0, look=False)
    p.add('root', (-3, 0, 0))
    p.add('head', (-2, 0, 0))
    p.lid = [blink(t, 1.2)] * 2
    return p


def a_carry_walk(t):
    p = Pose()
    g = Gait(0.5, 1.6, 0.36, 0.07, 14, 24)
    gait_pose(p, t, g, bob=0.012, base=-0.036, lean=1, carry=True)
    return p


def carry_walk_bob(t):
    q = (t / 0.5) % 1.0
    return -0.006 * math.cos(TAU * (2 * q - 0.36 - 0.12))


def a_pickup(t):
    """0.7 s: dip, both hands to the ground in front, grab, stand into the
    carry pose."""
    p = Pose()
    crouch = trk(t, [(0, 0), (0.06, -0.004), (0.24, -0.135), (0.34, -0.14), (0.52, -0.012), (0.60, 0.0),
                     (0.7, 0.0)])
    lean = trk(t, [(0, 0), (0.06, -2), (0.24, 22), (0.34, 24), (0.54, 0), (0.62, -4), (0.7, -3)])
    p.root += V(0, 0.015 * lean / 28, crouch)
    p.add('root', (lean * 0.55, 0, 0))
    p.add('spine', (lean * 0.30, 0, 0))
    p.add('chest', (lean * 0.15 - 3 * smoothstep(0.45, 0.7, t), 0, 0))
    p.add('neck', (lean * 0.1, 0, 0))
    p.add('head', (trk(t, [(0, 0), (0.24, 6), (0.34, 2), (0.5, -4), (0.62, -6), (0.7, -2)]), 0, 0))
    p.lid = [blink(t, 0.38)] * 2
    return p


def pickup_targets(t, Dc, sd, s):
    ground = V(s * trk(t, [(0, 0.15), (0.22, 0.13), (0.30, 0.118)]), -0.235, 0.10)
    carry = Dc @ CARRY[sd]
    k = smoothstep(0.32, 0.56, t)
    reach = smoothstep(0.02, 0.24, t)
    rest = Dc @ (arm_rest(s)[2] + V(0, -0.02, 0.0))
    a = rest.lerp(ground, reach)
    return a.lerp(carry, k)


def a_pickup_full(t):
    p = a_pickup(t)
    for sd, s in (('L', 1), ('R', -1)):
        p.r['hand.' + sd] = (8 * smoothstep(0.3, 0.6, t), 0, -s * 8 * smoothstep(0.1, 0.4, t))
    out, J = solve(p)
    Dc = J['D']['chest']
    for sd, s in (('L', 1), ('R', -1)):
        pole = (Dc.to_3x3() @ V(s * 0.9, 0.5, -0.6)).normalized()
        p.hand[sd] = (pickup_targets(t, Dc, sd, s), pole)
    return p


def a_pet(t):
    """1.0 s: right hand forward at chest height, two strokes, eyes smiling."""
    p = Pose()
    lean = trk(t, [(0, 0), (0.2, 12), (0.8, 12), (1.0, 0)])
    p.add('root', (lean * 0.5, 0, 0))
    p.add('spine', (lean * 0.3, 0, 3 * smoothstep(0, 0.2, t) * (1 - smoothstep(0.8, 1, t))))
    p.add('chest', (lean * 0.2, 0, 6 * smoothstep(0, 0.2, t) * (1 - smoothstep(0.8, 1, t))))
    tilt = trk(t, [(0, 0), (0.22, 12), (0.5, 9), (0.78, 12), (1.0, 0)])
    p.add('head', (trk(t, [(0, 0), (0.2, -10), (0.8, -10), (1.0, 0)]), -tilt, 0))
    p.lid = [trk(t, [(0, 0), (0.18, 0), (0.26, 1), (0.74, 1), (0.84, 0), (1.0, 0)])] * 2
    out, J = solve(p)
    Dc = J['D']['chest']
    stroke = trk(t, [(0, 0), (0.2, 0), (0.35, 1), (0.5, 0), (0.65, 1), (0.8, 0), (1.0, 0)])
    reach = trk(t, [(0, 0), (0.18, 1), (0.82, 1), (1.0, 0)])
    rest = Dc @ (arm_rest(-1)[2] + V(0, -0.03, 0))
    pet = V(-0.10, -0.215 - 0.05 * stroke, 0.45 - 0.015 * stroke)
    p.hand['R'] = (rest.lerp(pet, reach), (Dc.to_3x3() @ V(-0.9, 0.3, -0.5)).normalized())
    p.r['hand.R'] = (lerp(0, 35 - 15 * stroke, reach), 0, lerp(0, 50, reach))
    p.add('upper_arm.L', (trk(t, [(0, 0), (0.2, 10), (0.8, 10), (1, 0)]), 0, 0))
    p.add('forearm.L', (-10, 0, 0))
    return p


def a_give(t):
    """0.8 s: offer something with the right hand, palm up."""
    p = Pose()
    reach = trk(t, [(0, 0), (0.25, 1.05), (0.33, 1.0), (0.55, 1.0), (0.8, 0)])
    lean = 10 * reach
    p.add('root', (lean * 0.5, 0, 0))
    p.add('spine', (lean * 0.3, 0, 4 * reach))
    p.add('chest', (lean * 0.2, 0, 6 * reach))
    p.add('head', (trk(t, [(0, 0), (0.25, -8), (0.36, 0), (0.5, -6), (0.8, 0)]), -6 * reach, -4 * reach))
    p.lid = [blink(t, 0.6)] * 2
    out, J = solve(p)
    Dc = J['D']['chest']
    rest = Dc @ (arm_rest(-1)[2] + V(0, -0.03, 0))
    give = V(-0.07, -0.225, 0.45)
    p.hand['R'] = (rest.lerp(give, min(reach, 1.0)), (Dc.to_3x3() @ V(-0.9, 0.4, -0.6)).normalized())
    p.r['hand.R'] = (lerp(0, -30, min(reach, 1)), lerp(0, 70, min(reach, 1)), lerp(0, -20, min(reach, 1)))
    p.hold['R'] = ((-8, 0, 0), 0.6 + 0.4 * min(reach, 1.0))
    p.add('upper_arm.L', (6 * reach, 0, 0))
    return p


def a_happy(t):
    """0.8 s: anticipation, jump with both arms up, squash on landing."""
    p = Pose()
    z = trk(t, [(0, 0), (0.12, -0.075), (0.20, 0.01), (0.25, 0.085), (0.36, 0.145), (0.47, 0.085),
                (0.52, 0.0), (0.58, -0.07), (0.68, 0.012), (0.8, 0.0)])
    air = z > 0.0 and 0.18 < t < 0.53
    p.root += V(0, 0, z)
    tuck = trk(t, [(0, 0), (0.2, 0), (0.30, 0.05), (0.42, 0.05), (0.52, 0.0)])
    for sd, s in (('L', 1), ('R', -1)):
        fz = max(0.0, z - tuck) if air else 0.0
        toe = trk(t, [(0, 0), (0.18, 0), (0.24, -30), (0.36, -15), (0.5, 5), (0.54, 0)])
        p.foot[sd] = (side_pt(ANKLE, s), 0.0 if not air else toe, 0.0, V(0, 0, fz))
    sq = trk(t, [(0, 0), (0.12, 0.08), (0.20, -0.07), (0.36, -0.04), (0.5, 0), (0.58, 0.11),
                 (0.68, -0.03), (0.8, 0)])
    p.s['spine'] = (1 + sq * 0.6, 1 - sq, 1 + sq * 0.6)
    lean = trk(t, [(0, 0), (0.12, 10), (0.24, -8), (0.40, -4), (0.52, 6), (0.6, 10), (0.8, 0)])
    p.add('root', (lean * 0.6, 0, 0))
    p.add('spine', (lean * 0.4, 0, 0))
    up = trk(t, [(0, 0), (0.12, -0.25), (0.24, 1.0), (0.42, 1.05), (0.56, 0.75), (0.68, 0.25), (0.8, 0)])
    wav = math.sin(TAU * t * 4.0) * smoothstep(0.24, 0.3, t) * (1 - smoothstep(0.5, 0.62, t))
    for sd, s in (('L', 1), ('R', -1)):
        p.add('upper_arm.' + sd, (-6 * up, -s * 98 * up, 0))
        p.add('forearm.' + sd, (-10 - 12 * (1 - up), -s * (28 * up + 12 * wav), 0))
        p.add('hand.' + sd, (-10, -s * 15 * up, 0))
    p.add('head', (trk(t, [(0, 0), (0.12, 2), (0.26, -14), (0.42, -10), (0.56, 8), (0.66, -3), (0.8, 0)]), 0, 0))
    eyes = trk(t, [(0, 0), (0.2, 0), (0.26, 1), (0.52, 1), (0.6, 0), (0.8, 0)])
    p.lid = [eyes, eyes]
    m = trk(t, [(0, 0), (0.18, 0), (0.26, 0.9), (0.5, 0.9), (0.62, 0), (0.8, 0)])
    p.mouth = (m * 0.9, m * 0.85, m)
    return p


def a_yawn(t):
    """1.6 s: stretch up, big yawn with the eyes closed, relax."""
    p = Pose()
    st = trk(t, [(0, 0), (0.15, -0.1), (0.45, 1.0), (0.95, 1.05), (1.25, 0.3), (1.45, -0.05), (1.6, 0)])
    rise = max(0.0, st)
    p.root += V(0, 0, 0.012 * rise)
    for sd, s in (('L', 1), ('R', -1)):
        p.foot[sd] = (side_pt(ANKLE, s), -8 * rise, 0.0, V(0, 0, 0))
    p.add('root', (-4 * rise, 0, 0))
    p.add('spine', (-5 * rise, 0, 0))
    p.add('chest', (-6 * rise, 0, 0))
    p.add('neck', (-6 * rise, 0, 0))
    hb = trk(t, [(0, 0), (0.2, 4), (0.5, -18), (1.0, -20), (1.3, 2), (1.45, 4), (1.6, 0)])
    roll = trk(t, [(0, 0), (0.5, 6), (1.0, 4), (1.3, -2), (1.6, 0)])
    p.add('head', (hb, roll, 0))
    for sd, s in (('L', 1), ('R', -1)):
        p.add('upper_arm.' + sd, (-8 * st, -s * 104 * rise, 0))
        p.add('forearm.' + sd, (-8 * rise, -s * 45 * rise * (1 - 0.3 * smoothstep(0.35, 0.6, t)), 0))
        p.add('hand.' + sd, (-15 * rise, -s * 20 * rise, 0))
    m = trk(t, [(0, 0), (0.3, 0), (0.55, 1.0), (0.95, 1.1), (1.2, 0.0), (1.6, 0)])
    p.mouth = (0.75 * m, 1.35 * m, m)
    lid = trk(t, [(0, 0), (0.3, 0), (0.45, 1), (1.15, 1), (1.3, 0.35), (1.42, 0.5), (1.55, 0), (1.6, 0)])
    p.lid = [lid, lid]
    return p


def a_pet_low(t):
    """1.0 s: crouch and stroke a baby dino low in front (~0.3 m up)."""
    p = Pose()
    k = trk(t, [(0, 0), (0.22, 1.0), (0.8, 1.0), (1.0, 0)])
    p.root += V(0, 0.02 * k, -0.125 * k)
    p.add('root', (16 * k, 0, 0))
    p.add('spine', (6 * k, 0, 3 * k))
    p.add('chest', (2 * k, 0, 5 * k))
    tilt = trk(t, [(0, 0), (0.24, 12), (0.5, 9), (0.78, 12), (1.0, 0)])
    p.add('neck', (-6 * k, 0, 0))
    p.add('head', (-8 * k, -tilt, 0))
    p.lid = [trk(t, [(0, 0), (0.2, 0), (0.28, 1), (0.74, 1), (0.84, 0), (1.0, 0)])] * 2
    for sd, s in (('L', 1), ('R', -1)):
        p.foot[sd] = (side_pt(ANKLE, s) + V(s * 0.012 * k, 0, 0), 0.0, -s * 8 * k, V(0, 0, 0))
    out, J = solve(p)
    Dc = J['D']['chest']
    stroke = trk(t, [(0, 0), (0.22, 0), (0.37, 1), (0.52, 0), (0.67, 1), (0.82, 0), (1.0, 0)])
    rest = Dc @ (arm_rest(-1)[2] + V(0, -0.03, 0))
    pet = V(-0.09, -0.25 - 0.045 * stroke, 0.30 - 0.012 * stroke)
    p.hand['R'] = (rest.lerp(pet, k), (Dc.to_3x3() @ V(-0.9, 0.3, -0.5)).normalized())
    p.r['hand.R'] = (lerp(0, 30 - 15 * stroke, k), 0, lerp(0, 45, k))
    p.add('upper_arm.L', (-25 * k, -12 * k, 0))
    p.add('forearm.L', (-35 * k, 0, 0))
    return p


def a_use(t):
    """1.0 s: generic tool with the right hand: lift forward, tip it
    forward/down with a little to-and-fro (watering can, brush), return."""
    p = Pose()
    k = trk(t, [(0, 0), (0.2, 1.0), (0.82, 1.0), (1.0, 0)])
    tip = trk(t, [(0, 0), (0.22, 0), (0.35, 1.0), (0.45, 0.7), (0.55, 1.0), (0.65, 0.7), (0.75, 1.0),
                  (0.85, 0), (1.0, 0)])
    p.add('root', (6 * k, 0, 0))
    p.add('spine', (3 * k, 0, 4 * k))
    p.add('chest', (2 * k + 3 * tip, 0, 5 * k))
    p.add('head', (8 * k, -4 * k, -3 * k))
    p.lid = [blink(t, 0.86)] * 2
    out, J = solve(p)
    Dc = J['D']['chest']
    rest = Dc @ (arm_rest(-1)[2] + V(0, -0.03, 0))
    hold = Dc @ V(-0.12, -0.165, 0.40 - 0.02 * tip)
    p.hand['R'] = (rest.lerp(hold, k), (Dc.to_3x3() @ V(-0.9, 0.5, -0.4)).normalized())
    p.r['hand.R'] = (lerp(0, -25, k) + 45 * tip, 0, 0)
    p.hold['R'] = ((60 * tip, 0, -10 * k), 0.6 + 0.4 * k)
    p.add('upper_arm.L', (6 * k, -6 * k, 0))
    p.add('forearm.L', (-20 * k, 0, 0))
    return p


DIG_KEYS = [  # t, root dz, lean, twist, R hand (chest rest space), L hand
    (0.00, 0.000, 4, 0, V(-0.10, -0.150, 0.36), V(0.005, -0.150, 0.47)),
    (0.22, -0.055, 20, 6, V(-0.07, -0.170, 0.33), V(0.010, -0.170, 0.42)),
    (0.30, -0.065, 22, 6, V(-0.07, -0.170, 0.32), V(0.010, -0.172, 0.41)),
    (0.45, -0.050, 14, 0, V(-0.10, -0.120, 0.37), V(0.015, -0.165, 0.38)),
    (0.65, 0.000, 0, -18, V(-0.13, -0.140, 0.43), V(-0.02, -0.160, 0.49)),
    (0.78, 0.000, 2, -8, V(-0.11, -0.150, 0.39), V(0.000, -0.150, 0.47)),
    (0.90, 0.000, 4, 0, V(-0.10, -0.150, 0.36), V(0.005, -0.150, 0.47)),
]


def a_dig(t):
    """0.9 s: shovel scoop with both hands: thrust down, lever, lift and
    toss to his right, back to ready (loops cleanly if repeated)."""
    p = Pose()
    col = lambda i: [(r[0], r[i]) for r in DIG_KEYS]  # noqa: E731
    dz, lean, tw = trk(t, col(1)), trk(t, col(2)), trk(t, col(3))
    p.root += V(0, 0.01 * lean / 22, dz)
    p.add('root', (lean * 0.55, 0, tw * 0.3))
    p.add('spine', (lean * 0.3, 0, tw * 0.3))
    p.add('chest', (lean * 0.15, 0, tw * 0.4))
    p.add('head', (6 - 0.3 * lean, 0, -0.5 * tw))
    for sd, s in (('L', 1), ('R', -1)):
        p.foot[sd] = (side_pt(ANKLE, s) + V(0, -s * 0.03, 0), 0.0, 0.0, V(0, 0, 0))
    out, J = solve(p)
    Dc = J['D']['chest']
    R = V(*trk(t, [(r[0], tuple(r[4])) for r in DIG_KEYS]))
    L = V(*trk(t, [(r[0], tuple(r[5])) for r in DIG_KEYS]))
    p.hand['R'] = (Dc @ R, (Dc.to_3x3() @ V(-0.9, 0.5, -0.5)).normalized())
    p.hand['L'] = (Dc @ L, (Dc.to_3x3() @ V(0.9, 0.4, -0.5)).normalized())
    p.r['hand.R'] = (-10, 0, 20)
    p.r['hand.L'] = (0, 0, -40)
    # shovel (held by hand.R, blade down): angle in the chest frame
    sh = trk(t, [(0.0, (-28, 0, 0)), (0.22, (-48, 0, 0)), (0.30, (-46, 0, 0)), (0.45, (-72, 0, 0)),
                 (0.65, (-88, 22, 0)), (0.78, (-45, 6, 0)), (0.9, (-28, 0, 0))])
    p.hold['R'] = (sh, 1.0)
    p.lid = [blink(t, 0.70)] * 2
    return p


def a_wave(t):
    """1.0 s: right arm up, three waves, head tilt, little smile-open mouth."""
    p = Pose()
    up = trk(t, [(0, 0), (0.18, 1.05), (0.25, 1.0), (0.8, 1.0), (1.0, 0)])
    env = smoothstep(0.15, 0.25, t) * (1 - smoothstep(0.75, 0.85, t))
    wav = math.sin(TAU * 3.0 * (t - 0.2)) * env
    p.add('upper_arm.R', (-14 * up, 118 * up, 0))
    p.add('forearm.R', (-8 * up, (40 + 28 * wav) * up, 0))
    p.add('hand.R', (-10 * up, 15 * up + 10 * wav, 0))
    p.add('upper_arm.L', (0, -3 * up, 0))
    p.add('forearm.L', (-8, 0, 0))
    p.add('chest', (-2 * up, 3 * up, 0))
    p.add('head', (-4 * up, trk(t, [(0, 0), (0.25, -9), (0.8, -9), (1.0, 0)]) , 0))
    p.root += V(0, 0, -0.004 + 0.004 * math.cos(TAU * 3.0 * (t - 0.2)) * env)
    m = trk(t, [(0, 0), (0.2, 0), (0.3, 0.45), (0.7, 0.45), (0.85, 0), (1.0, 0)])
    p.mouth = (0.8 * m, 0.7 * m, m)
    p.lid = [blink(t, 0.08)] * 2
    return p


SIT_ROOT = V(0, 0.07, -0.22)


def a_sit(t):
    """3.0 s loop: sitting on the ground, legs forward, hands on the ground
    beside him, a small sway, kicking feet, a look and a blink."""
    p = Pose()
    T = 3.0
    w = sinw(t, T)
    b = sinw(t, T / 2)
    p.root += SIT_ROOT + V(0, 0, 0.002 * b)
    p.add('root', (-6, 2.0 * w, 0))
    p.add('spine', (4 - 1.0 * b, 1.5 * w, 0))
    p.add('chest', (2 - 1.5 * b, 1.5 * w, 0))
    yaw = trk(t, [(0, 0), (0.9, 0), (1.15, 20), (1.6, 18), (1.85, -6), (2.4, -6), (2.7, 0), (T, 0)])
    p.add('neck', (0, 0, 0.3 * yaw))
    p.add('head', (-6 + 2 * b, -3 * w - 0.15 * yaw, 0.6 * yaw))
    for sd, s, ph in (('L', 1, 0.0), ('R', -1, 0.5)):
        p.legfk[sd] = True
        kick = sinw(t, T / 3, ph)
        p.r['thigh.' + sd] = (-98, -s * 9, s * 4)
        p.r['shin.' + sd] = (16 + 7 * kick, 0, 0)
        p.r['foot.' + sd] = (22, 0, -s * 6)
        p.r['upper_arm.' + sd] = (16 - 2 * b, -s * 16, 0)
        p.r['forearm.' + sd] = (-14, 0, 0)
        p.r['hand.' + sd] = (30, 0, 0)
    p.lid = [max(blink(t, 0.5), blink(t, 2.2))] * 2
    return p


SLEEP_ROOT = V(0.20, 0.14, -0.121)


def a_sleep(t):
    """4.0 s loop: curled on his right side, slow breathing, eyes closed."""
    p = Pose()
    T = 4.0
    b = sinw(t, T / 1)          # one slow breath per loop: inhale, sigh
    b2 = sinw(t, T / 2)
    p.root += SLEEP_ROOT + V(0, 0, 0.002 * b)
    p.add('root', (0, -90, 0))
    p.add('spine', (12 - 1.5 * b, 4, 0))
    p.add('chest', (10 - 2.0 * b, 4, 0))
    p.s['chest'] = (1 + 0.02 * b, 1, 1 + 0.02 * b)
    p.add('neck', (8, 8, 0))
    p.add('head', (6 + 1.2 * b2, 12, 0))
    for sd, s in (('L', 1), ('R', -1)):
        p.legfk[sd] = True
        p.r['thigh.' + sd] = (-72 - (6 if s > 0 else 0), -s * 4, 0)
        p.r['shin.' + sd] = (100 + (8 if s > 0 else 0), 0, 0)
        p.r['foot.' + sd] = (-20, 0, 0)
    # arms tucked under the cheek / in front of the chest
    p.r['upper_arm.R'] = (-70, 10, 0)
    p.r['forearm.R'] = (-95, 0, 0)
    p.r['hand.R'] = (-10, 0, 0)
    p.r['upper_arm.L'] = (-55 - 2 * b, 8, 0)
    p.r['forearm.L'] = (-70, 0, 0)
    p.r['hand.L'] = (-20, 0, 0)
    p.lid = [1.0, 1.0]
    m = 0.22 + 0.10 * b
    p.mouth = (0.45 * m / 0.32, 0.55 * m / 0.32, m / 0.32 * 0.6)
    return p


def a_talk(t):
    """3.0 s loop: chatting: mouth flaps in phrases, hands gesture, head nods."""
    p = Pose()
    T = 3.0
    idle_upper(p, t, T, look=False)
    env = trk(t, [(0, 0.2), (0.15, 1), (0.9, 1), (1.05, 0.1), (1.3, 0.1), (1.45, 1), (2.45, 1), (2.65, 0.1),
                  (2.85, 0.2), (T, 0.2)])
    flap = 0.5 + 0.5 * math.sin(TAU * 5.0 * t) * (0.7 + 0.3 * math.sin(TAU * (2.0 / T) * t))
    m = env * (0.15 + 0.55 * flap)
    p.mouth = (0.7 * m, 0.6 * m, m)
    nod = 4 * math.sin(TAU * (6.0 / T) * t) * env
    tilt = trk(t, [(0, 0), (0.5, 6), (1.2, -4), (1.9, 7), (2.5, -3), (T, 0)])
    p.add('head', (nod, -tilt, trk(t, [(0, 0), (0.6, 8), (1.6, -6), (2.4, 4), (T, 0)])))
    tw = trk(t, [(0, 0), (0.6, 5), (1.6, -5), (2.4, 3), (T, 0)])
    p.add('chest', (0, 0, tw))
    gR = trk(t, [(0, 0), (0.2, 0), (0.45, 1), (0.95, 0.8), (1.2, 0.1), (2.0, 0.1), (2.25, 1), (2.6, 0.9),
                 (2.85, 0), (T, 0)])
    gL = trk(t, [(0, 0), (1.1, 0), (1.35, 1), (1.85, 0.8), (2.1, 0.0), (2.25, 0.6), (2.6, 0.7), (2.85, 0),
                 (T, 0)])
    bob = math.sin(TAU * (6.0 / T) * t)
    for sd, s, g in (('L', 1, gL), ('R', -1, gR)):
        p.add('upper_arm.' + sd, (-22 * g, -s * 18 * g, 0))
        p.add('forearm.' + sd, (-62 * g - 6 * g * bob, -s * 10 * g, 0))
        p.add('hand.' + sd, (-15 * g, 0, -s * 50 * g))
    p.lid = [blink(t, 1.15)] * 2
    p.hold['R'] = ((0, 0, 0), 0.4)
    return p


ANIMS = [
    ('idle', 120, a_idle),
    ('walk', 15, a_walk),
    ('run', 12, a_run),
    ('pickup', 21, a_pickup_full),
    ('carry_idle', 60, with_carry(a_carry_idle)),
    ('carry_walk', 15, with_carry(a_carry_walk, carry_walk_bob)),
    ('pet', 30, a_pet),
    ('give', 24, a_give),
    ('happy', 24, a_happy),
    ('yawn', 48, a_yawn),
    ('pet_low', 30, a_pet_low),
    ('use', 30, a_use),
    ('dig', 27, a_dig),
    ('wave', 30, a_wave),
    ('sit', 90, a_sit),
    ('sleep', 120, a_sleep),
    ('talk', 90, a_talk),
]


# ===========================================================================
# Build
# ===========================================================================

BODY = []


def ground_check(arm, body, act, frames):
    """Print the lowest point of the deformed mesh at a few frames."""
    tr = arm.animation_data.nla_tracks
    for t in tr:
        t.mute = True
    arm.animation_data.action = act
    deps = bpy.context.evaluated_depsgraph_get()
    res = []
    for f in sorted(set([0, frames // 4, frames // 2, 3 * frames // 4])):
        bpy.context.scene.frame_set(f)
        ev = body.evaluated_get(deps)
        me = ev.to_mesh()
        zs = [v.co.z for v in me.vertices]
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        res.append('f%d z%.3f x[%.2f,%.2f] y[%.2f,%.2f]' % (f, min(zs), min(xs), max(xs), min(ys), max(ys)))
        ev.to_mesh_clear()
    arm.animation_data.action = None
    for t in tr:
        t.mute = False
    bpy.context.scene.frame_set(0)
    print('[check] %s: %s' % (act.name, '  '.join(res)))


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def build_tommy():
    C.reset()
    C._mats.clear()
    mats()
    arm = C.armature('tommy_rig', [(n, tuple(h), tuple(t), par) for n, h, t, par in bone_list()])
    read_rest(arm)
    body = build_body(arm)
    BODY[:] = [body]
    print('[tommy] triangles %d, materials %d (%s)' % (
        tri_count(body), len(body.data.materials), ', '.join(m.name for m in body.data.materials)))
    only = A.get('anims')
    for name, frames, fn in ANIMS:
        if only and name not in only.split(','):
            continue
        bake(arm, name, frames, fn)
    export_small(os.path.join(OUT, 'tommy.glb'), [arm, body])


def export_small(path, objects):
    """C.export_glb plus the exporter's animation-size optimisation (drops
    samples that repeat; every channel is kept), to stay under 1 MB."""
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    try:
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_apply=False,
                                  export_animations=True, export_yup=True, use_selection=True,
                                  export_materials='EXPORT', export_nla_strips=True,
                                  export_optimize_animation_size=True)
        print('[tdz] wrote', path)
    except TypeError:
        C.export_glb(path, objects)


def build_cap_model():
    C.reset()
    C._mats.clear()
    mats()
    mb = MB()
    build_cap(mb)
    ob = to_object('cap_basic', mb)
    # build_cap() works around the head centre; the origin must be the head
    # bone's head (top of the neck) in rest pose
    ob.data.transform(Matrix.Translation(HEAD_C - HEAD_BONE))
    # drop unused material slots
    print('[tommy] cap triangles %d' % tri_count(ob))
    C.export_glb(os.path.join(OUT, 'cap_basic.glb'), [ob])


if 'tommy' in ONLY:
    build_tommy()
if 'cap' in ONLY:
    build_cap_model()
