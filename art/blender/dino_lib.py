"""dino_lib.py - the parameterised dinosaur framework of Tommy's Dino Zoo.

One species = one dict of numbers (body plan, proportions, palette, parts);
this module turns it into a skinned, rigged, animated .glb for any age:

    D = Dino(spec, 'baby')      # 'baby' | 'juv' | 'adult'
    D.build()                   # layout -> armature -> meshes -> skin
    D.animate()                 # the 12 actions of ART-SPEC section 4
    D.export(out_dir)           # <id>_<age>.glb

Body plans (spec['plan']):
  quad      four column legs, short neck (trike, stego, ankylo, proto)
  sauropod  quad with a long neck of 4-6 bones and taller front legs (brachio)
  biped     two legs, short arms, long tail counterweight (trex, raptor, ...)
  flier     small biped body with wing.L/.R + wing2.L/.R (ptera, archaeo)
  swimmer   round body, four flippers on the leg bones, long neck (plesio)

Ages re-proportion the same species before it is scaled to its height:
babies have much bigger heads and eyes, shorter legs/snouts/tails, rounder
bodies and nubs instead of horns; juveniles sit in between (AGES below).
Heights: baby 45 %, juv 70 % of the adult (ART-SPEC section 2).

Conventions (see docs/ART-SPEC.md):
  * metres, Blender +Z up, the model faces -Y; origin on the ground under the
    body centre.
  * bones: root (hips), spine, neck_1..n, head, jaw, tail_1..n,
    thigh/shin/foot.L/.R, fthigh/fshin/ffoot.L/.R (quads) or arm/forearm.L/.R
    (bipeds), wing/wing2.L/.R (fliers), eyelid.L/.R.
  * eyelid.L/.R close by SCALE: (1,1,1) = closed (the rest pose), open is
    keyed as scale (0.4, 0.03, 0.06) in the bone's local axes (the lid folds up
    into the top rim of the eye; Y runs down across the eye, Z out of it).
  * every action keys every bone (rotation, location, scale) on every frame,
    so switching animations in Godot never leaves a bone behind.

Adding a species: copy the closest dict in dinos.py (TRIKE quad, BRACHIO
sauropod, RAPTOR/TREX biped, PTERA flier, PLESIO swimmer drafts), change the
numbers, palette and `parts` (features: horns, frill, beak, spots, stripes,
feathers, ridge, plates, sail, bump), set `speeds` per age, register it in
SPECIES and run `--only <id>_baby,<id>_juv,<id>_adult --stats`. Per-species
animation tweaks go in spec['moves'] (stance, clap, hop, *_speed/_duty/_reach,
sleep_fwd, sleep_lift); new generic behaviour belongs in Moves.

Posing works in "semantic" angles: pitch (+ = nose down, about world X),
yaw (+ = turn to its left, about world Z), roll (+ = top to its left, about
world Y), applied as if the parent were at rest. Legs are posed by IK
(feet planted on the ground or on given targets), so walks do not slide and
the root can bob, squash and lean while the feet stay put. Head reaching
(eat, drink, pet) is solved by CCD over the spine/neck chain.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdz_common as C  # noqa: E402

V = Vector
UP = V((0, 0, 1))
FWD = V((0, -1, 0))
FPS = 30
TAU = 2 * math.pi
ROLES = ('body', 'belly', 'accent', 'spots', 'horn', 'eye_white', 'pupil',
         'iris', 'mouth', 'tongue', 'blush', 'nose')

# ---------------------------------------------------------------- maths


def clamp(x, a, b):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease(t):
    """smoother step"""
    t = clamp(t, 0.0, 1.0)
    return t * t * t * (t * (6 * t - 15) + 10)


def env(t, a, b, c, d):
    """0 before a, eases up to 1 at b, stays to c, eases down to 0 at d."""
    if t <= a or t >= d:
        return 0.0
    if t < b:
        return smooth((t - a) / max(b - a, 1e-6))
    if t <= c:
        return 1.0
    return 1.0 - smooth((t - c) / max(d - c, 1e-6))


def tl(t, keys):
    """Timeline: keys [(time, value), ...] sorted; smooth easing between."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = smooth((t - t0) / max(t1 - t0, 1e-6))
            return v0 + (v1 - v0) * u
    return keys[-1][1]


def wave(t, period, phase=0.0):
    return math.sin(TAU * (t / period) + phase)


def on_ell(c, r, az, el):
    """Point and normal on an axis-aligned ellipsoid (centre c, radii r) at
    azimuth `az` (deg, 0 = forward -Y, + towards +X) and elevation `el`."""
    a, e = math.radians(az), math.radians(el)
    d = V((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    p = V(c) + V((d.x * r[0], d.y * r[1], d.z * r[2]))
    n = V((d.x / r[0], d.y / r[1], d.z / r[2])).normalized()
    return p, n


def frame(n, up=UP):
    """3x3 matrix whose columns are X (across), Y (up along the surface),
    Z = n (out of the surface)."""
    z = V(n).normalized()
    y = V(up) - z * z.dot(V(up))
    if y.length < 1e-5:
        y = V((0, 1, 0)) - z * z.dot(V((0, 1, 0)))
    y.normalize()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed()


def _rotm(rot):
    if rot is None:
        return Matrix.Identity(3)
    if isinstance(rot, Matrix):
        return rot.to_3x3()
    if isinstance(rot, Quaternion):
        return rot.to_matrix()
    from mathutils import Euler
    return Euler([math.radians(a) for a in rot], 'XYZ').to_matrix()


def qsem(p=0.0, y=0.0, r=0.0):
    """Semantic rotation (degrees) as a quaternion in armature axes."""
    return (Quaternion(UP, math.radians(y)) @
            Quaternion(V((1, 0, 0)), math.radians(p)) @
            Quaternion(V((0, 1, 0)), math.radians(r)))


# ---------------------------------------------------------------- primitives


def _mk(name, m, bm):
    return C._obj_from_bm(bm, name, m)


def ell(name, m, c, r, rot=None, seg=20, rings=12, deform=None, keep=None):
    """Ellipsoid (centre c, radii r) turned by `rot` (euler deg / Matrix).
    `deform(u)` reshapes unit-sphere coordinates before scaling; `keep(u)`
    drops vertices (e.g. back halves hidden inside the head)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    R = _rotm(rot)
    dead = []
    for v in bm.verts:
        u = v.co.copy()
        if keep is not None and not keep(u):
            dead.append(v)
        if deform is not None:
            u = deform(u)
        v.co = V(c) + R @ V((u.x * r[0], u.y * r[1], u.z * r[2]))
    if dead:
        bmesh.ops.delete(bm, geom=dead, context='VERTS')
    return _mk(name, m, bm)


def tube(name, m, pts, radii, seg=14, flat=None, nrm=None, cap=True, sub=4):
    """Swept tube with rounded caps. `flat` = per-point thickness ratio of
    the section along `nrm` (a world direction; the section is wide across
    it, default up). `cap`: True/'both', 'start', 'end' or False (ends
    hidden inside other parts need no cap). `sub` = rings per span."""
    P = [V(p) for p in pts]
    R = list(radii)
    Fl = list(flat) if flat else [1.0] * len(P)
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
            df.append(Fl[i] + (Fl[i + 1] - Fl[i]) * t)
    dp.append(P[-1])
    dr.append(R[-1])
    df.append(Fl[-1])
    n0 = V(nrm) if nrm is not None else UP
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(dp):
        if i == 0:
            t = (dp[1] - dp[0]).normalized()
        elif i == len(dp) - 1:
            t = (dp[-1] - dp[-2]).normalized()
        else:
            t = (dp[i + 1] - dp[i - 1]).normalized()
        a = n0 - t * t.dot(n0)
        if a.length < 1e-5:
            a = V((1, 0, 0)) - t * t.dot(V((1, 0, 0)))
        a.normalize()
        b = t.cross(a).normalized()
        ring = []
        for k in range(seg):
            ang = TAU * k / seg
            off = b * math.cos(ang) * dr[i] + a * math.sin(ang) * dr[i] * df[i]
            ring.append(bm.verts.new(p + off))
        rings.append((ring, p, t, b, a, dr[i], df[i]))
    for i in range(len(rings) - 1):
        ra, rb = rings[i][0], rings[i + 1][0]
        for k in range(seg):
            bm.faces.new((ra[k], ra[(k + 1) % seg], rb[(k + 1) % seg], rb[k]))
    ends = []
    if cap in (True, 'both', 'start'):
        ends.append((rings[0], -1))
    if cap in (True, 'both', 'end'):
        ends.append((rings[-1], 1))
    if ends:
        for end, sign in ends:
            ring, p, t, b, a, r, f = end
            if r < 1e-5:
                continue
            prev = ring
            steps = 3
            for s in range(1, steps):
                ang = (math.pi / 2) * s / steps
                cr, ca = math.cos(ang), math.sin(ang)
                cur = []
                for k in range(seg):
                    an = TAU * k / seg
                    off = (b * math.cos(an) * r + a * math.sin(an) * r * f) * cr + \
                        t * sign * r * ca * max(f, 0.35)
                    cur.append(bm.verts.new(p + off))
                for k in range(seg):
                    q = (prev[k], prev[(k + 1) % seg], cur[(k + 1) % seg], cur[k])
                    bm.faces.new(q if sign > 0 else q[::-1])
                prev = cur
            tipv = bm.verts.new(p + t * sign * r * max(f, 0.35))
            for k in range(seg):
                tri = (prev[k], prev[(k + 1) % seg], tipv)
                bm.faces.new(tri if sign > 0 else tri[::-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _mk(name, m, bm)


def slab(name, m, fn, nu, nv, thick, ref=None):
    """A thick rounded sheet (frills, sails, wings, plates): `fn(u, v)` gives
    the mid-surface point for u, v in [0, 1]; thickness tapers to 0 on all
    four borders so the edge is a soft rounded rim. `ref` is a direction the
    front face should point to (to orient normals)."""
    bm = bmesh.new()
    grid = [[V(fn(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]

    def normal(i, j):
        i0, i1 = max(i - 1, 0), min(i + 1, nu)
        j0, j1 = max(j - 1, 0), min(j + 1, nv)
        du = grid[i1][j] - grid[i0][j]
        dv = grid[i][j1] - grid[i][j0]
        n = du.cross(dv)
        if n.length < 1e-9:
            return V(ref) if ref else UP
        n.normalize()
        if ref is not None and n.dot(V(ref)) < 0:
            n = -n
        return n

    def prof(i, j):
        u, v = i / nu, j / nv
        a = 1.0 - (2 * u - 1) ** 6
        b = 1.0 - (2 * v - 1) ** 6
        return math.sqrt(max(a * b, 0.0))

    top, bot = {}, {}
    for i in range(nu + 1):
        for j in range(nv + 1):
            n = normal(i, j)
            h = 0.5 * thick * prof(i, j)
            top[i, j] = bm.verts.new(grid[i][j] + n * h)
            bot[i, j] = bm.verts.new(grid[i][j] - n * h)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((top[i, j], top[i + 1, j], top[i + 1, j + 1], top[i, j + 1]))
            bm.faces.new((bot[i, j], bot[i, j + 1], bot[i + 1, j + 1], bot[i + 1, j]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    # stitch the open border (where the taper is not exactly 0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _mk(name, m, bm)


def decal(name, m, target, center, normal, ru, rv=None, u_axis=None,
          lift=0.003, seg=12, nr=2):
    """Disc of radii (ru, rv) shrink-wrapped onto `target` (by ray casting
    along -normal), its ru axis along `u_axis` (default horizontal)."""
    rv = ru if rv is None else rv
    nrm = V(normal).normalized()
    if u_axis is None:
        ref = UP if abs(nrm.z) < 0.9 else V((1, 0, 0))
        u = nrm.cross(ref).normalized()
    else:
        u = (V(u_axis) - nrm * nrm.dot(V(u_axis))).normalized()
    v = nrm.cross(u).normalized()
    deps = bpy.context.evaluated_depsgraph_get()
    tgt = target.evaluated_get(deps)
    inv = tgt.matrix_world.inverted()

    def project(p):
        o = p + nrm * 0.6
        lo, ld = inv @ o, (inv.to_3x3() @ -nrm).normalized()
        hit, loc, n, _ = tgt.ray_cast(lo, ld)
        if not hit:             # off the edge: wrap onto the nearest surface
            hit, loc, n, _ = tgt.closest_point_on_mesh(inv @ p)
        if hit:
            w = tgt.matrix_world @ loc
            wn = (tgt.matrix_world.to_3x3() @ n).normalized()
            return w + wn * lift
        return p

    bm = bmesh.new()
    c = bm.verts.new(project(V(center)))
    rings = [[c]]
    for k in range(1, nr + 1):
        f = k / nr
        ring = []
        for i in range(seg):
            a = TAU * i / seg
            p = V(center) + u * math.cos(a) * ru * f + v * math.sin(a) * rv * f
            ring.append(bm.verts.new(project(p)))
        rings.append(ring)
    for i in range(seg):
        bm.faces.new((c, rings[1][i], rings[1][(i + 1) % seg]))
    for k in range(1, nr):
        a, b = rings[k], rings[k + 1]
        for i in range(seg):
            bm.faces.new((a[i], b[i], b[(i + 1) % seg], a[(i + 1) % seg]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _mk(name, m, bm)
    me = ob.data
    me.update()
    if me.polygons and me.polygons[0].normal.dot(nrm) < 0:
        for p in me.polygons:
            p.flip()
    return ob


def project_pts(target, pts, normal, lift=0.002):
    """Drop points onto `target` along -normal (for smiles, stripes)."""
    nrm = V(normal).normalized()
    deps = bpy.context.evaluated_depsgraph_get()
    tgt = target.evaluated_get(deps)
    inv = tgt.matrix_world.inverted()
    out = []
    for p in pts:
        o = V(p) + nrm * 0.6
        hit, loc, n, _ = tgt.ray_cast(inv @ o, (inv.to_3x3() @ -nrm).normalized())
        if hit:
            w = tgt.matrix_world @ loc
            out.append(w + (tgt.matrix_world.to_3x3() @ n).normalized() * lift)
        else:
            out.append(V(p))
    return out


def reset():
    """C.reset() plus forgetting C.mat's cached (now deleted) materials, so
    several models can be built in one Blender run."""
    C.reset()
    C._mats.clear()


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# ---------------------------------------------------------------- armature


def make_armature(name, bones):
    """bones: list of dicts {name, head, tail, parent, roll_to (optional
    world vector the bone's Z axis should point to)}."""
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    for b in bones:
        e = arm.edit_bones.new(b['name'])
        e.head, e.tail = V(b['head']), V(b['tail'])
        if b.get('roll_to') is not None:
            e.align_roll(V(b['roll_to']))
        if b.get('parent'):
            e.parent = eb[b['parent']]
            if (eb[b['parent']].tail - e.head).length < 1e-5:
                e.use_connect = True
        eb[b['name']] = e
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ob


def skin_axis(ob, a, b, p0, p1, t0=0.0, t1=1.0):
    """Blend from bone `a` to bone `b` along the segment p0 -> p1."""
    C.apply_xf(ob)
    ga = ob.vertex_groups.new(name=a)
    gb = ob.vertex_groups.new(name=b)
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    L2 = max(d.length_squared, 1e-9)
    for v in ob.data.vertices:
        t = (v.co - p0).dot(d) / L2
        w = smooth((t - t0) / max(t1 - t0, 1e-6))
        ga.add([v.index], 1.0 - w, 'REPLACE')
        gb.add([v.index], w, 'REPLACE')
    return ob


def skin(ob, arm, how):
    kind = how[0]
    if kind == 'rigid':
        C.skin_rigid(ob, how[1])
    elif kind == 'near':
        C.skin_near(ob, arm, how[1], power=how[2] if len(how) > 2 else 5.0,
                    top=how[3] if len(how) > 3 else 2)
    elif kind == 'axis':
        skin_axis(ob, *how[1:])
    else:
        raise ValueError(kind)
    return ob


def dedupe_slots(ob):
    """Merge material slots that hold the same material (after a join)."""
    me = ob.data
    first = {}
    remap = []
    for i, m in enumerate(me.materials):
        key = m.name if m else None
        if key not in first:
            first[key] = len(first)
        remap.append(first[key])
    order = sorted(first.items(), key=lambda kv: kv[1])
    mats = [bpy.data.materials[k] for k, _ in order]
    idx = [0] * len(me.polygons)
    me.polygons.foreach_get('material_index', idx)
    idx = [remap[i] for i in idx]
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set('material_index', idx)
    me.update()


# ---------------------------------------------------------------- pose model


class Pose:
    """Semantic pose of one frame. rot: bone -> [pitch, yaw, roll] degrees;
    loc: bone -> world-axes offset (m); scl: bone -> world-axes scale;
    feet: leg -> (ankle target, foot pitch deg) (missing = planted at rest);
    lid: 0 open .. 1 closed (or per side dict); jaw: degrees open;
    reach: (target, weight) for the mouth; post: rotations added after the
    reach solve (chomps, nods)."""

    def __init__(self):
        self.rot = {}
        self.post = {}
        self.loc = {}
        self.scl = {}
        self.feet = {}
        self.lid = 0.0
        self.jaw = 0.0
        self.reach = None
        self.raw = {}

    def r(self, bone, p=0.0, y=0.0, r=0.0, post=False):
        d = self.post if post else self.rot
        a = d.setdefault(bone, [0.0, 0.0, 0.0])
        a[0] += p
        a[1] += y
        a[2] += r
        return self

    def at(self, bone, v):
        a = self.loc.setdefault(bone, V((0, 0, 0)))
        self.loc[bone] = a + V(v)
        return self

    def sc(self, bone, s):
        a = self.scl.get(bone, V((1, 1, 1)))
        self.scl[bone] = V((a.x * s[0], a.y * s[1], a.z * s[2]))
        return self


class Rig:
    """Rest data of an armature plus forward/inverse kinematics in python,
    so actions can be computed exactly (IK feet, CCD reaching) and keyed."""

    def __init__(self, arm_ob, L):
        self.ob = arm_ob
        self.L = L
        self.names = [b.name for b in arm_ob.data.bones]
        self.parent = {b.name: (b.parent.name if b.parent else None)
                       for b in arm_ob.data.bones}
        self.rest = {b.name: b.matrix_local.copy() for b in arm_ob.data.bones}
        self.len = {b.name: b.length for b in arm_ob.data.bones}
        self.rel = {}
        for n in self.names:
            p = self.parent[n]
            self.rel[n] = (self.rest[p].inverted() @ self.rest[n]) if p else self.rest[n]
        self.rq = {n: self.rest[n].to_quaternion() for n in self.names}

    # semantic -> local basis
    def basis(self, n, q=None, loc=None, scl=None):
        rq = self.rq[n]
        lq = rq.inverted() @ q @ rq if q is not None else Quaternion()
        ll = (rq.inverted().to_matrix() @ V(loc)) if loc is not None else V((0, 0, 0))
        ls = V((1, 1, 1))
        if scl is not None:
            Rm = rq.to_matrix()
            for i in range(3):          # local axis i ~ which world axis
                col = Rm.col[i]
                k = max(range(3), key=lambda j: abs(col[j]))
                ls[i] = scl[k]
        return [ll, lq, ls]

    @staticmethod
    def mat(b):
        ll, lq, ls = b
        return (Matrix.Translation(ll) @ lq.to_matrix().to_4x4() @
                Matrix.Diagonal((ls[0], ls[1], ls[2], 1.0)))

    def fk(self, B):
        W = {}
        for n in self.names:
            p = self.parent[n]
            base = (W[p] @ self.rel[n]) if p else self.rel[n]
            W[n] = base @ self.mat(B[n])
        return W

    def world_point(self, W, bone, p_rest):
        """Where a rest-space point carried by `bone` is in pose W."""
        return W[bone] @ (self.rest[bone].inverted() @ V(p_rest))

    # 2-bone leg IK in the parent's space (exact under parent scale)
    def leg_ik(self, B, W, leg, target, foot_dir):
        th, sh, ft = leg['thigh'], leg['shin'], leg['foot']
        par = self.parent[th]
        Mp = W[par]
        Mi = Mp.inverted()
        T = Mi @ V(target)
        Rt = self.rel[th]
        H = Rt.translation
        l1, l2 = self.len[th], self.len[sh]
        K0 = Rt @ V((0, l1, 0))
        A0 = (Rt @ self.rel[sh]) @ V((0, l2, 0))
        axis = A0 - H
        pole = (K0 - H) - axis.normalized() * (K0 - H).dot(axis.normalized())
        if pole.length < 1e-5:
            pole = V((0, -1, 0))
        d = T - H
        dist = clamp(d.length, abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4)
        u = d.normalized()
        pv = pole - u * pole.dot(u)
        if pv.length < 1e-6:
            pv = pole
        pv.normalize()
        ca = clamp((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1)
        a = math.acos(ca)
        K = H + (u * math.cos(a) + pv * math.sin(a)) * l1
        Tc = H + u * dist
        # thigh
        dl = Rt.to_quaternion().inverted() @ (K - H).normalized()
        qt = V((0, 1, 0)).rotation_difference(dl)
        B[th] = [V((0, 0, 0)), qt, V((1, 1, 1))]
        Mth = Rt @ self.mat(B[th])
        Msh0 = Mth @ self.rel[sh]
        dl = Msh0.to_quaternion().inverted() @ (Tc - K).normalized()
        qs = V((0, 1, 0)).rotation_difference(dl)
        B[sh] = [V((0, 0, 0)), qs, V((1, 1, 1))]
        Msh = Msh0 @ self.mat(B[sh])
        Mft0 = Msh @ self.rel[ft]
        fd = (Mi.to_3x3() @ V(foot_dir)).normalized()
        dl = Mft0.to_quaternion().inverted() @ fd
        qf = V((0, 1, 0)).rotation_difference(dl)
        B[ft] = [V((0, 0, 0)), qf, V((1, 1, 1))]


# ---------------------------------------------------------------- age tables

AGES = {
    # factor tables applied to a species' adult parameters
    'baby': dict(height=0.45, head=1.58, eye=1.30, leg=0.80, snout=0.55,
                 neck=0.62, tail=0.62, round=0.55, horn=0.0, frill=0.62,
                 plate=0.55, crest=0.75, arm=0.9, body=1.0, lod=0.66),
    'juv': dict(height=0.70, head=1.25, eye=1.12, leg=0.86, snout=0.80,
                neck=0.82, tail=0.84, round=0.25, horn=0.55, frill=0.84,
                plate=0.8, crest=0.9, arm=0.95, body=1.0, lod=0.84),
    'adult': dict(height=1.0, head=1.0, eye=1.0, leg=1.0, snout=1.0,
                  neck=1.0, tail=1.0, round=0.0, horn=1.0, frill=1.0,
                  plate=1.0, crest=1.0, arm=1.0, body=1.0, lod=1.0),
}


# ---------------------------------------------------------------- layout


def _arc(p0, a0, a1, length, n, back=False):
    """n+1 points along a planar (YZ) arc from p0; the heading's elevation
    goes from a0 to a1 degrees (forward = -Y, or +Y when `back`)."""
    steps = n * 10
    p = V(p0)
    out = [p.copy()]
    sy = 1.0 if back else -1.0
    for i in range(steps):
        a = math.radians(lerp(a0, a1, (i + 0.5) / steps))
        p = p + V((0, sy * math.cos(a), math.sin(a))) * (length / steps)
        if (i + 1) % 10 == 0:
            out.append(p.copy())
    return out


def _scale_tree(x, k, key=''):
    if isinstance(x, bool) or isinstance(x, str) or x is None:
        return x
    if isinstance(x, Vector):
        return x * k
    if isinstance(x, (int, float)):
        if key.endswith('_deg') or key.endswith('_n') or key in ('side',):
            return x
        return x * k
    if isinstance(x, tuple):
        return tuple(_scale_tree(v, k, key) for v in x)
    if isinstance(x, list):
        return [_scale_tree(v, k, key) for v in x]
    if isinstance(x, dict):
        return {kk: _scale_tree(v, k, kk) for kk, v in x.items()}
    return x


def _roundify(r, f):
    m = sum(r) / 3.0
    return tuple(lerp(a, m, f) for a in r)


class Dino:
    """One species at one age. `spec` holds adult parameters (see dinos.py
    for the documented TRIKE example); AGES re-proportions them."""

    def __init__(self, spec, age='adult'):
        self.spec = spec
        self.age = age
        self.A = dict(AGES[age])
        self.A.update(spec.get('age_tweak', {}).get(age, {}))
        self.name = '%s_%s' % (spec['id'], age)
        self.parts = []
        self.mats = {}
        self.plan = spec['plan']

    # -------------------------------------------------------- materials
    def m(self, role):
        if role not in self.mats:
            pal = self.spec['pal']
            col = pal.get(role) or DEFAULT_PAL[role]
            self.mats[role] = C.mat(role, col, rough=0.6 if role in (
                'eye_white', 'pupil', 'iris') else 0.75)
        return self.mats[role]

    def add(self, ob, how):
        self.parts.append((ob, how))
        return ob

    def lod(self, n, lo=6):
        return max(lo, int(round(n * self.A['lod'] * self.spec.get('lod', 1.0) / 2)) * 2)

    # -------------------------------------------------------- layout
    def layout(self):
        s, A = self.spec, self.A
        f = {'quad': self._lay_quad, 'sauropod': self._lay_quad,
             'swimmer': self._lay_quad, 'biped': self._lay_biped,
             'flier': self._lay_biped}[self.plan]
        L = f(s, A)
        top = L['head_c'].z + L['head_r'][2]
        k = s['height'] * A['height'] / top
        self.k = k
        self.L = _scale_tree(L, k)
        return self.L

    def _head_common(self, L, s, A, hb):
        h = s['head']
        hr = tuple(x * A['head'] for x in h['r'])
        off = h.get('off', (0.45, 0.25))
        hc = hb + FWD * hr[1] * off[0] + UP * hr[2] * off[1]
        sn = h.get('snout', (0.62, 0.6, 0.55))
        sl = sn[1] * A['snout'] ** 0.8
        snr = (hr[0] * sn[0], hr[1] * sl, hr[2] * sn[2])
        sdrop = h.get('snout_drop', 0.25)
        snc = hc + FWD * (hr[1] * h.get('snout_fwd', 0.62) + snr[1] * 0.45) - UP * hr[2] * sdrop
        L['head_c'], L['head_r'], L['snout_c'], L['snout_r'] = hc, hr, snc, snr
        L['head_base'] = hb
        hinge = hc + FWD * hr[1] * 0.15 - UP * hr[2] * 0.42
        jtip = snc + FWD * snr[1] * 0.8 - UP * snr[2] * 0.62
        L['jaw_hinge'], L['jaw_tip'] = hinge, jtip
        L['mouth'] = jtip + FWD * snr[1] * 0.15
        L['head_tail'] = hc + FWD * hr[1] * 0.9 + UP * hr[2] * 0.2

    def _lay_quad(self, s, A):
        L = {}
        rx, ry, rz = _roundify(s['torso'], A['round'])
        L['torso_r'] = (rx, ry, rz)
        leg = s['leg'] * A['leg']
        fleg = s.get('fleg', s['leg']) * A['leg']
        hip_y, sh_y = ry * s.get('hip_y', 0.52), -ry * s.get('sh_y', 0.55)
        tilt = math.degrees(math.atan2(fleg - leg, hip_y - sh_y))
        if self.plan == 'swimmer':
            tilt = 0.0
        cz = (leg + fleg) / 2 + rz * s.get('sit_in', 0.85)
        Ct = V((0, s.get('torso_y', 0.0) * ry, cz))
        Rt = _rotm((-tilt, 0, 0))
        L['torso_c'], L['torso_rot_deg'] = Ct, (-tilt, 0, 0)

        def tp(x, y, z):
            return Ct + Rt @ V((x, y, z))
        L['tp'] = None
        lr = s['leg_r'] * (A['leg'] ** 0.25)
        L['leg_r'] = lr
        fh = lr * 0.55
        root = tp(0, hip_y, -rz * 0.15)
        chest = tp(0, -ry * 0.80, rz * s.get('neck_z', 0.30))
        L['root'], L['chest'] = root, chest
        legs = []
        for front, yy in ((False, hip_y), (True, sh_y)):
            for side in (1, -1):
                xw = rx * s.get('leg_x', 0.60)
                hip = tp(side * xw, yy, -rz * 0.32)
                spread = s.get('splay', 0.0)
                ank = V((side * (xw * 1.04 + spread), hip.y + (0.02 if front else -0.02) * ry, fh))
                if self.plan == 'swimmer':      # flippers reach out sideways
                    ank = hip + V((side * s.get('flipper', 1.0) * rx, (0.25 if not front else 0.1) * ry,
                                   -rz * 0.25))
                bend = s.get('knee', 0.06) * (1 if front else -1)
                knee = (hip + ank) / 2 + V((0, bend * (hip.z - ank.z), 0))
                toe = ank + FWD * lr * 1.25
                if self.plan == 'swimmer':
                    toe = ank + (V((side, 0.6, 0)).normalized()) * lr * 3.0
                tag = ('f' if front else '') + ('L' if side > 0 else 'R')
                legs.append(dict(tag=tag, front=front, side=side, hip=hip, knee=knee,
                                 ankle=ank, toe=toe, foot_h=fh))
        L['legs'] = legs
        # neck and head
        nl = s['neck_len'] * A['neck']
        n = s.get('neck_n', 1)
        a0 = s.get('neck_deg', 30)
        a1 = s.get('neck_deg2', a0 * 0.5)
        L['neck_pts'] = _arc(chest, a0, a1, nl, n)
        L['neck_r'] = s.get('neck_r', 0.5) * min(rx, rz) * (1 + 0.15 * (A['head'] - 1))
        self._head_common(L, s, A, L['neck_pts'][-1])
        # tail
        t = s['tail']
        tb = tp(0, ry * 0.80, rz * t.get('z', 0.05))
        L['tail_pts'] = _arc(tb, -t.get('droop_deg', 20), -t.get('droop2_deg', 5),
                             t['len'] * A['tail'], t.get('n', 3), back=True)
        L['tail_r'] = t['r'] * rz * (0.85 + 0.15 * A['tail'])
        return L

    def _lay_biped(self, s, A):
        L = {}
        rx, ry, rz = _roundify(s['torso'], A['round'])
        L['torso_r'] = (rx, ry, rz)
        leg = s['leg'] * A['leg']
        tilt = s.get('tilt_deg', 30) + (8 if self.age == 'baby' else 0)
        root = V((0, 0, leg))
        Rt = _rotm((-tilt, 0, 0))
        Ct = root + Rt @ V((0, -ry * s.get('t_fwd', 0.25), rz * s.get('t_up', 0.45)))
        L['torso_c'], L['torso_rot_deg'] = Ct, (-tilt, 0, 0)

        def tp(x, y, z):
            return Ct + Rt @ V((x, y, z))
        chest = tp(0, -ry * 0.78, rz * s.get('neck_z', 0.30))
        L['root'], L['chest'] = root, chest
        lr = s['leg_r'] * (A['leg'] ** 0.25)
        L['leg_r'] = lr
        fh = lr * 0.5
        legs = []
        for side in (1, -1):
            xw = rx * s.get('leg_x', 0.62)
            hip = V((side * xw, root.y + 0.02 * ry, leg))
            ank = V((side * xw * 1.02, hip.y + 0.06 * leg, fh))
            knee = (hip + ank) / 2 + V((0, -s.get('knee', 0.22) * (hip.z - ank.z), 0))
            toe = ank + FWD * lr * s.get('foot_len', 1.7)
            legs.append(dict(tag='L' if side > 0 else 'R', front=False, side=side, hip=hip,
                             knee=knee, ankle=ank, toe=toe, foot_h=fh))
        L['legs'] = legs
        arms = []
        al = s.get('arm_len', 0.5) * ry * A['arm']
        for side in ((1, -1) if self.plan != 'flier' else ()):
            sh = tp(side * rx * 0.72, -ry * 0.55, rz * s.get('arm_z', 0.0))
            el = sh + V((side * al * 0.12, -al * 0.25, -al * 0.5))
            hd = el + V((0, -al * 0.5, al * 0.05))
            arms.append(dict(tag='L' if side > 0 else 'R', side=side, sh=sh, el=el, hand=hd))
        L['arms'] = arms
        L['arm_r'] = s.get('arm_r', 0.16) * rx
        nl = s['neck_len'] * A['neck']
        n = s.get('neck_n', 1)
        a0 = s.get('neck_deg', 60)
        a1 = s.get('neck_deg2', a0 * 0.4)
        L['neck_pts'] = _arc(chest, a0, a1, nl, n)
        L['neck_r'] = s.get('neck_r', 0.55) * min(rx, rz) * (1 + 0.15 * (A['head'] - 1))
        self._head_common(L, s, A, L['neck_pts'][-1])
        t = s['tail']
        tb = tp(0, ry * 0.72, -rz * t.get('z', 0.1))
        L['tail_pts'] = _arc(tb, -t.get('droop_deg', 10), -t.get('droop2_deg', -5),
                             t['len'] * A['tail'], t.get('n', 4), back=True)
        L['tail_r'] = t['r'] * rz * (0.85 + 0.15 * A['tail'])
        if self.plan == 'flier':
            wl = s.get('wing_len', 1.2) * ry
            ws = []
            for side in (1, -1):
                sh = tp(side * rx * 0.6, -ry * 0.45, rz * 0.35)
                wr = sh + V((side * wl * 0.45, wl * 0.05, wl * 0.06))
                tip = wr + V((side * wl * 0.55, wl * 0.12, -wl * 0.05))
                ws.append(dict(tag='L' if side > 0 else 'R', side=side, sh=sh, wrist=wr, tip=tip))
            L['wings'] = ws
        return L

    # -------------------------------------------------------- armature
    def rig(self):
        L = self.L
        bones = []

        def b(name, h, t, parent=None, roll_to=None):
            bones.append(dict(name=name, head=V(h), tail=V(t), parent=parent, roll_to=roll_to))
        root = L['root']
        b('root', root, root + UP * L['torso_r'][2] * 0.6)
        b('spine', root, L['chest'], 'root')
        prev = 'spine'
        npts = L['neck_pts']
        self.neck = []
        for i in range(len(npts) - 1):
            nm = 'neck_%d' % (i + 1)
            b(nm, npts[i], npts[i + 1], prev)
            self.neck.append(nm)
            prev = nm
        b('head', L['head_base'], L['head_tail'], prev)
        b('jaw', L['jaw_hinge'], L['jaw_tip'], 'head')
        tpts = L['tail_pts']
        self.tail = []
        prev = 'root'
        for i in range(len(tpts) - 1):
            nm = 'tail_%d' % (i + 1)
            b(nm, tpts[i], tpts[i + 1], prev)
            self.tail.append(nm)
            prev = nm
        self.legs = []
        for lg in L['legs']:
            pre = 'f' if lg['front'] else ''
            sd = '.L' if lg['side'] > 0 else '.R'
            par = 'spine' if lg['front'] else 'root'
            th, sh, ft = pre + 'thigh' + sd, pre + 'shin' + sd, pre + 'foot' + sd
            b(th, lg['hip'], lg['knee'], par)
            b(sh, lg['knee'], lg['ankle'], th)
            b(ft, lg['ankle'], lg['toe'], sh)
            self.legs.append(dict(lg, thigh=th, shin=sh, foot=ft))
        self.arms = []
        for a in L.get('arms', []):
            sd = '.L' if a['side'] > 0 else '.R'
            b('arm' + sd, a['sh'], a['el'], 'spine')
            b('forearm' + sd, a['el'], a['hand'], 'arm' + sd)
            self.arms.append(dict(a, arm='arm' + sd, forearm='forearm' + sd))
        self.wings = []
        for w in L.get('wings', []):
            sd = '.L' if w['side'] > 0 else '.R'
            b('wing' + sd, w['sh'], w['wrist'], 'spine')
            b('wing2' + sd, w['wrist'], w['tip'], 'wing' + sd)
            self.wings.append(dict(w, wing='wing' + sd, wing2='wing2' + sd))
        for e in self.eyes:
            b(e['bone'], e['lid_top'], e['lid_bot'], 'head', roll_to=e['n'])
        for extra in self.extra_bones:
            b(*extra)
        self.arm = make_armature(self.name + '_rig', bones)
        self.R = Rig(self.arm, L)
        return self.arm

    # -------------------------------------------------------- build
    def build(self):
        reset()
        self.layout()
        self.eyes = []
        self.extra_bones = []
        self._eye_layout()
        for fn in self.spec.get('pre_rig', ()):     # species hooks, e.g. append to self.extra_bones
            fn(self)                                 # (name, head, tail, parent, roll_to)
        self.rig()
        build_body(self)
        for feat, opts in self.spec.get('parts', []):
            FEATURES[feat](self, **opts)
        arm = self.arm
        objs = []
        stat = {}
        for ob, how in self.parts:
            k = ob.name.split('.')[0]
            stat[k] = stat.get(k, 0) + tris(ob)
        self.tri_stats = sorted(stat.items(), key=lambda kv: -kv[1])
        for ob, how in self.parts:
            skin(ob, arm, how)
            objs.append(ob)
        body = C.bind(self.name, arm, objs)
        dedupe_slots(body)
        self.body = body
        return body

    def _eye_layout(self):
        L, s, A = self.L, self.spec, self.A
        e = s['eye']
        hc, hr = L['head_c'], L['head_r']
        re = e['r'] * (hr[0] + hr[1] + hr[2]) / 3 * A['eye']
        L['eye_r'] = re
        for side in (1, -1):
            az = side * (e['az'] + (4 if self.age == 'baby' else 0))
            P, N = on_ell(hc, hr, az, e['el'] - (5 if self.age == 'baby' else 0))
            flat = e.get('flat', 0.55)
            vert = e.get('vert', 1.08)
            c = P - N * re * flat * e.get('sink', 0.42)
            F = frame(N)
            ry = re * vert * 1.12
            back = N * re * flat * 0.8      # the lid folds into a point behind the eye
            top = c + F.col[1] * ry - back
            bot = c - F.col[1] * ry - back
            self.eyes.append(dict(side=side, P=P, n=N, c=c, F=F, re=re, flat=flat, vert=vert,
                                  bone='eyelid.' + ('L' if side > 0 else 'R'),
                                  lid_top=top, lid_bot=bot))


DEFAULT_PAL = {
    'body': '#9ad07a', 'belly': '#f6ecd2', 'accent': '#f59a3c', 'spots': '#3fae9f',
    'horn': '#fbf1d6', 'eye_white': '#ffffff', 'pupil': '#2a1e2c', 'iris': '#6b4a2e',
    'mouth': '#5a2a3a', 'tongue': '#f2889a', 'blush': '#ff9db0', 'nose': '#5a2a3a',
}


# ---------------------------------------------------------------- body parts


def build_body(D):
    D.ref = {}
    build_torso(D)
    build_neck(D)
    build_head(D)
    build_eyes(D)
    build_tail(D)
    build_legs(D)
    build_arms(D)
    build_wings(D)


def _torso_skin(D):
    L = D.L
    return ('axis', 'root', 'spine', L['root'], L['chest'], 0.05, 0.85)


def build_torso(D):
    L, s = D.L, D.spec
    Ct, tr, rot = L['torso_c'], L['torso_r'], L['torso_rot_deg']
    Rt = _rotm(rot)
    flat = s.get('belly_flat', 0.55 if D.plan not in ('biped', 'flier') else 0.85)

    def fl(u):
        if u.z < -flat:
            u.z = -flat + (u.z + flat) * 0.55
        return u
    t = D.add(ell('torso', D.m('body'), Ct, tr, rot, seg=D.lod(30), rings=D.lod(16),
                  deform=fl), _torso_skin(D))
    D.ref['torso'] = t
    bo = s.get('belly_off', (0.0, -0.06, -0.30) if D.plan != 'biped' else (0.0, -0.30, -0.10))
    bs = s.get('belly_r', (0.84, 0.86, 0.76) if D.plan != 'biped' else (0.80, 0.78, 0.86))
    bc = Ct + Rt @ V((bo[0] * tr[0], bo[1] * tr[1], bo[2] * tr[2]))
    D.add(ell('belly', D.m('belly'), bc, tuple(a * b for a, b in zip(tr, bs)), rot,
              seg=D.lod(24), rings=D.lod(12), deform=fl), _torso_skin(D))


def build_neck(D):
    L, s = D.L, D.spec
    pts = list(L['neck_pts'])
    nr = L['neck_r']
    d0 = (pts[1] - pts[0]).normalized()
    inner = pts[0] - d0 * nr * 0.9
    hc = L['head_c']
    end = L['head_base'] + (hc - L['head_base']) * 0.5
    P = [inner] + pts[:-1] + [pts[-1], end]
    n = len(P)
    taper = s.get('neck_taper', 0.82)
    R = [nr * lerp(1.15, taper, i / (n - 1)) for i in range(n)]
    bones = ['spine'] + D.neck + ['head']
    D.add(tube('neck', D.m('body'), P, R, seg=D.lod(16), cap=False, sub=3), ('near', bones, 4.0, 2))
    if s.get('throat', D.plan in ('biped', 'sauropod', 'flier', 'swimmer')):
        Q = []
        for i, p in enumerate(P):
            j = min(max(i, 1), n - 2)
            d = (P[j + 1] - P[j - 1]).normalized()
            side = d.cross(V((1, 0, 0))).normalized()     # perpendicular in YZ
            if side.dot(FWD + UP * -0.3) < 0:
                side = -side
            Q.append(p + side * R[i] * 0.42)
        D.add(tube('throat', D.m('belly'), Q[1:-1], [r * 0.66 for r in R[1:-1]], seg=D.lod(12), sub=3),
              ('near', bones, 4.0, 2))


def build_head(D):
    L, s = D.L, D.spec
    h = s['head']
    hc, hr, snc, snr = L['head_c'], L['head_r'], L['snout_c'], L['snout_r']
    body = D.m('body')
    hd = D.add(ell('head', body, hc, hr, seg=D.lod(28), rings=D.lod(14),
                   deform=h.get('deform')), ('rigid', 'head'))
    D.ref['head'] = hd
    tap = h.get('snout_taper', (0.22, 0.12))

    def sn(u):
        if u.y < 0:
            u.x *= 1.0 + tap[0] * u.y
            u.z *= 1.0 + tap[1] * u.y
        if u.z < -0.5:
            u.z = -0.5 + (u.z + 0.5) * 0.6
        return u
    snout = D.add(ell('snout', body, snc, snr, seg=D.lod(24), rings=D.lod(12), deform=sn),
                  ('rigid', 'head'))
    D.ref['snout'] = snout
    if h.get('cheeks'):
        ck = h['cheeks']
        for side in (1, -1):
            cc = hc + V((side * hr[0] * ck[0], -hr[1] * ck[1], -hr[2] * ck[2]))
            D.add(ell('cheek', body, cc, (hr[0] * ck[3], hr[0] * ck[3], hr[0] * ck[3] * 0.85),
                      seg=D.lod(14), rings=D.lod(8)), ('rigid', 'head'))
    # lower jaw, mouth inside, tongue
    jm = D.m(h.get('jaw_mat', 'belly'))
    jc = snc - UP * snr[2] * h.get('jaw_drop', 0.5) + V((0, snr[1] * 0.10, 0))
    jr = (snr[0] * 0.88, snr[1] * 0.90, snr[2] * h.get('jaw_h', 0.45))

    def jw(u):
        if u.y < 0:
            u.x *= 1.0 + 0.25 * u.y
        return u
    D.add(ell('jaw', jm, jc, jr, seg=D.lod(22), rings=D.lod(10), deform=jw), ('rigid', 'jaw'))
    mc = snc - UP * snr[2] * 0.30 + V((0, snr[1] * 0.12, 0))
    D.add(ell('mouth_in', D.m('mouth'), mc, (snr[0] * 0.80, snr[1] * 0.80, snr[2] * 0.40),
              seg=D.lod(18), rings=D.lod(8)), ('rigid', 'head'))
    D.add(ell('tongue', D.m('tongue'), jc + UP * jr[2] * 0.62 + V((0, jr[1] * 0.12, 0)),
              (jr[0] * 0.58, jr[1] * 0.66, jr[2] * 0.42), seg=D.lod(14), rings=D.lod(8)),
          ('rigid', 'jaw'))
    # smile: a line round the front of the snout, corners curling up
    sm = h.get('smile', dict(width=62, z=-0.30, curl=0.22))
    pts = []
    nn = 7
    for i in range(nn):
        u = -1 + 2 * i / (nn - 1)
        a = math.radians(u * sm['width'])
        p = snc + V((math.sin(a) * snr[0] * 1.2, -math.cos(a) * snr[1] * 1.2,
                     snr[2] * (sm['z'] + sm['curl'] * u * u)))
        pts.append(p)
    proj = []
    for p in pts:
        d = (p - (snc + UP * (p.z - snc.z))).normalized()
        proj.append(project_pts(snout, [p], d, lift=0.0015)[0])
    D.add(tube('smile', D.m('mouth'), proj, [snr[0] * 0.035] * len(proj), seg=5, sub=2),
          ('rigid', 'head'))
    # nostrils
    if h.get('nostrils', True):
        for side in (1, -1):
            p, n = on_ell(snc, snr, side * h.get('nostril_az', 20), h.get('nostril_el', 30))
            D.add(ell('nostril', D.m('mouth'), p - n * snr[0] * 0.02,
                      (snr[0] * 0.08, snr[0] * 0.06, snr[0] * 0.06), rot=frame(n, UP),
                      seg=6, rings=4), ('rigid', 'head'))
    if h.get('teeth'):
        for side in (1, -1):
            p = snc + V((side * snr[0] * 0.38, -snr[1] * 0.78, -snr[2] * 0.42))
            D.add(tube('fang', D.m('horn'), [p + UP * snr[2] * 0.06, p - UP * snr[2] * 0.14],
                       [snr[0] * 0.07, snr[0] * 0.035], seg=6, sub=1, cap='end'), ('rigid', 'head'))


def build_eyes(D):
    for e in D.eyes:
        c, F, re, flat, vert, N = e['c'], e['F'], e['re'], e['flat'], e['vert'], e['n']
        lo = D.lod(18, 10)
        dome = D.add(ell('eye', D.m('eye_white'), c, (re, re * vert, re * flat), rot=F,
                         seg=lo, rings=D.lod(10, 8), keep=lambda u: u.z > -0.5), ('rigid', 'head'))
        front = c + N * re * flat
        g = FWD - N * N.dot(FWD)
        g = g.normalized() if g.length > 1e-5 else V((0, 0, 0))
        dn = -UP + N * N.dot(UP)
        dn = dn.normalized() if dn.length > 1e-5 else V((0, 0, 0))
        pc = front + g * re * D.spec['eye'].get('gaze', 0.16) + dn * re * 0.06
        hor = V((1, 0, 0)) - N * N.dot(V((1, 0, 0)))
        ps = D.spec['eye'].get('pupil', 0.62)
        if 'iris' in D.spec['pal']:
            D.add(decal('iris', D.m('iris'), dome, pc, N, re * ps * 1.1, re * ps * 1.18,
                        u_axis=hor, lift=re * 0.015 + 0.0005, nr=3), ('rigid', 'head'))
            ps *= 0.62
        D.add(decal('pupil', D.m('pupil'), dome, pc, N, re * ps, re * ps * 1.1, u_axis=hor,
                    lift=re * 0.03 + 0.001, nr=3), ('rigid', 'head'))
        w = V((-0.6, 0, 0.8)) - N * N.dot(V((-0.6, 0, 0.8)))
        w.normalize()
        D.add(decal('glint', D.m('eye_white'), dome, pc + w * re * 0.28, N, re * 0.21,
                    lift=re * 0.055 + 0.0015, seg=10, nr=2), ('rigid', 'head'))
        D.add(decal('glint2', D.m('eye_white'), dome, pc - w * re * 0.30, N, re * 0.09,
                    lift=re * 0.055 + 0.0015, seg=8, nr=1), ('rigid', 'head'))
        # the lid: closed at rest (bone scale 1), folded into the top rim
        lr = (re * 1.13, re * vert * 1.13, re * flat * 1.1 + re * 0.09 + 0.004)
        lid = D.add(ell('lid', D.m('body'), c, lr, rot=F, seg=lo, rings=D.lod(12, 8),
                        keep=lambda u: u.z > -0.35), ('rigid', e['bone']))
        pts = []
        for i in range(7):
            u = -1 + 2 * i / 6
            p = c + F.col[0] * u * re * 0.86 - F.col[1] * re * vert * (0.05 + 0.32 * (1 - u * u))
            pts.append(p)
        pts = project_pts(lid, pts, N, lift=0.001)
        D.add(tube('lash', D.m('pupil'), pts, [re * 0.07] * len(pts), seg=D.lod(5, 4), sub=2),
              ('rigid', e['bone']))
        # cheek blush below and behind the eye
        if D.spec.get('blush', True):
            hc, hr = D.L['head_c'], D.L['head_r']
            ba = D.spec['eye']['az'] + D.spec.get('blush_az', 16)
            bp, bn = on_ell(hc, hr, e['side'] * ba, D.spec['eye']['el'] - D.spec.get('blush_el', 30))
            D.add(decal('blush', D.m('blush'), D.ref['head'], bp, bn, re * 0.62, re * 0.40,
                        u_axis=FWD, lift=0.002), ('rigid', 'head'))


def build_tail(D):
    L, s = D.L, D.spec
    pts = list(L['tail_pts'])
    tr = L['tail_r']
    d0 = (pts[1] - pts[0]).normalized()
    P = [pts[0] - d0 * tr * 1.2] + pts
    n = len(P)
    tip = s['tail'].get('tip', 0.16)
    R = [tr * lerp(1.0, tip, (i / (n - 1)) ** 0.9) for i in range(n)]
    fl = s['tail'].get('flat', 0.85)
    t = D.add(tube('tail', D.m('body'), P, R, seg=D.lod(16), flat=[fl] * n, nrm=UP, cap='end', sub=3),
              ('near', ['root'] + D.tail, 4.0, 2))
    D.ref['tail'] = t


def _flat_bottom(k=0.6):
    def f(u):
        if u.z < -k:
            u.z = -k + (u.z + k) * 0.25
        return u
    return f


def build_legs(D):
    L, s = D.L, D.spec
    lr = L['leg_r']
    biped = D.plan in ('biped', 'flier')
    for lg in D.legs:
        hip, knee, ank, toe = lg['hip'], lg['knee'], lg['ankle'], lg['toe']
        fr = s.get('fleg_r', 1.0) if lg['front'] else 1.0
        r = lr * fr
        if D.plan == 'swimmer':
            D.add(tube('leg', D.m('body'), [hip, knee, ank], [r * 1.2, r, r * 0.9], seg=D.lod(12),
                       cap=False, sub=3), ('near', [lg['thigh'], lg['shin']], 5.0, 2))
            d = (toe - ank)
            D.add(ell('flipper', D.m('body'), ank + d * 0.5, (r * 1.3, d.length * 0.75, r * 0.35),
                      rot=V((0, 1, 0)).rotation_difference(d.normalized()), seg=D.lod(14),
                      rings=D.lod(8)), ('rigid', lg['foot']))
            continue
        how = ('near', [lg['thigh'], lg['shin']], 5.0, 2)
        if biped:
            mid = (hip + knee) / 2
            d = (knee - hip)
            th = s.get('thigh_r', 1.9)
            D.add(ell('thigh', D.m('body'), mid + V((0, 0, d.length * 0.05)),
                      (r * th * 0.8, r * th, d.length * 0.62 + r * 0.4),
                      rot=V((0, 0, 1)).rotation_difference(d.normalized()),
                      seg=D.lod(16), rings=D.lod(10)), ('rigid', lg['thigh']))
            D.add(tube('shin', D.m('body'), [knee, (knee + ank) / 2, ank], [r * 1.1, r * 0.9, r * 0.8],
                       seg=D.lod(12), cap=False, sub=3), ('near', [lg['thigh'], lg['shin']], 6.0, 2))
        else:
            D.add(tube('leg', D.m('body'), [hip, knee, ank + UP * lg['foot_h'] * 0.6],
                       [r * 1.25, r * 1.02, r * 0.95], seg=D.lod(14), cap=False, sub=3), how)
        # foot: a soft flat-bottomed pad with toenails
        fh = lg['foot_h']
        flen = (toe - ank).length
        fc = ank + (toe - ank) * (0.30 if not biped else 0.42)
        frr = (r * (1.18 if not biped else 1.05), max(flen * (0.62 if biped else 0.75), r * 1.15), fh * 1.05)
        fc = V((fc.x, fc.y, frr[2] * 0.62))
        foot = D.add(ell('foot', D.m('body'), fc, frr, seg=D.lod(14), rings=D.lod(8, 6),
                         deform=_flat_bottom(0.62)), ('rigid', lg['foot']))
        nails = s.get('toes', 3)
        for i in range(nails):
            az = (-1 + 2 * i / max(nails - 1, 1)) * (34 if nails > 1 else 0)
            p, n = on_ell(fc, frr, az, -8)
            nr = r * (0.26 if not biped else 0.22)
            D.add(ell('nail', D.m('horn'), p + n * nr * 0.2, (nr, nr * 0.9, nr * 0.75),
                      rot=frame(n, UP), seg=D.lod(8, 6), rings=4), ('rigid', lg['foot']))
        del foot


def build_arms(D):
    L, s = D.L, D.spec
    if not D.arms:
        return
    ar = L['arm_r']
    for a in D.arms:
        sh, el, hd = a['sh'], a['el'], a['hand']
        D.add(tube('arm', D.m('body'), [sh, el, hd], [ar * 1.1, ar * 0.85, ar * 0.8], seg=D.lod(10),
                   cap=False, sub=3),
              ('near', [a['arm'], a['forearm']], 5.0, 2))
        d = (hd - el).normalized()
        D.add(ell('hand', D.m('body'), hd + d * ar * 0.25, (ar * 0.95, ar * 1.0, ar * 0.85),
                  seg=D.lod(12), rings=D.lod(8)), ('rigid', a['forearm']))
        for i, dx in enumerate((-0.45, 0.45)):
            b = hd + d * ar * 0.9 + V((dx * ar, 0, -ar * 0.2))
            D.add(tube('claw', D.m('horn'), [b, b + d * ar * 0.5 - UP * ar * 0.25],
                       [ar * 0.26, ar * 0.08], seg=6, sub=2, cap='end'), ('rigid', a['forearm']))


def build_wings(D):
    L, s = D.L, D.spec
    for w in D.wings:
        sh, wr, tip = w['sh'], w['wrist'], w['tip']
        side = w['side']
        back = s.get('wing_chord', 0.55) * (tip - sh).length

        def fn(u, v, sh=sh, wr=wr, tip=tip, back=back, side=side):
            # leading edge sh -> wr -> tip, trailing edge scalloped back
            if u < 0.5:
                lead = sh.lerp(wr, u / 0.5)
            else:
                lead = wr.lerp(tip, (u - 0.5) / 0.5)
            chord = back * (1 - u ** 1.6) * (0.9 + 0.1 * math.sin(math.pi * u * 3))
            return lead + V((0, chord * v, -chord * v * 0.15))
        D.add(slab('wing', D.m('belly'), fn, 16, 4, L['torso_r'][2] * 0.08, ref=UP),
              ('near', [w['wing'], w['wing2'], 'spine'], 4.0, 2))
        D.add(tube('wingarm', D.m('body'), [sh, wr, tip], [L['arm_r'] * 1.1, L['arm_r'] * 0.8,
                                                           L['arm_r'] * 0.3], seg=D.lod(10)),
              ('near', [w['wing'], w['wing2']], 6.0, 2))


# ---------------------------------------------------------------- features


def f_horns(D, horns=(), nub=0.18):
    """horns: list of dicts {on: 'head'|'snout', az, el, len, r, dir: (x, y, z)
    world direction at the base, curl: (x, y, z) bend towards at the tip};
    len and r are fractions of the head radius. Babies get round nubs."""
    L = D.L
    hr = sum(L['head_r']) / 3
    for hn in horns:
        if hn.get('mirror'):
            sides = (1, -1)
        else:
            sides = (1,)
        for sd in sides:
            c, r = (L['head_c'], L['head_r']) if hn.get('on', 'head') == 'head' else \
                (L['snout_c'], L['snout_r'])
            p, n = on_ell(c, r, sd * hn['az'], hn['el'])
            ln = hn['len'] * hr * D.A['horn']
            rr = hn['r'] * hr * (0.75 + 0.25 * D.A['horn'])
            if ln < rr * 1.4:          # a nub
                rn = rr * (0.8 if D.age == 'baby' else 1.0)
                D.add(ell('nub', D.m('horn'), p + n * rn * 0.35, (rn, rn, rn * 0.9),
                          rot=frame(n, FWD), seg=10, rings=7), ('rigid', 'head'))
                continue
            d = V(hn.get('dir', n)).normalized()
            d.x *= sd
            cu = V(hn.get('curl', (0, -1, 0))).normalized()
            cu.x *= sd
            b = p - n * rr * 0.6
            m1 = b + d * ln * 0.5
            t = m1 + (d * 0.5 + cu * 0.5).normalized() * ln * 0.5
            D.add(tube('horn', D.m('horn'), [b, m1, t], [rr, rr * 0.62, rr * 0.16],
                       seg=D.lod(12, 8), cap='end', sub=3), ('rigid', 'head'))


def f_frill(D, r=1.5, tilt_deg=40, span_deg=230, scallops=7, scallop=0.07,
            thick=0.16, up=0.40, back=0.30, cup=0.10, wrap=0.35, knobs=True, spots=6):
    """A big rounded fan behind the head (ceratopsians); r, thick, up, back
    are fractions of the head radius."""
    L = D.L
    hc, hr = L['head_c'], L['head_r']
    R = r * hr[2] * D.A['frill'] ** 0.9
    fc = hc + UP * hr[2] * up + V((0, hr[1] * back, 0))
    ti = math.radians(tilt_deg)
    span = math.radians(span_deg)
    nrm_up = V((0, math.sin(ti), math.cos(ti)))
    sc = scallop if D.age != 'baby' else scallop * 0.4

    def fn(u, v):
        a = -span / 2 + span * u
        rho = R * v * (1 + sc * math.cos(scallops * a) * v ** 2)
        x = rho * math.sin(a)
        w = rho * math.cos(a)
        # cupped like a shield and wrapped forward at the sides (a collar)
        return fc + V((x, 0, 0)) + nrm_up * w + V((0, cup * R * (rho / R) ** 2
                                                    - wrap * R * (x / R) ** 2, 0))
    front = V((0, -math.cos(ti), math.sin(ti)))
    fr = D.add(slab('frill', D.m('accent'), fn, D.lod(30), D.lod(6, 5), thick * hr[2], ref=front),
               ('rigid', 'head'))
    rng = [(0.30, 0.62, 0.11), (0.70, 0.62, 0.11), (0.5, 0.80, 0.10), (0.14, 0.82, 0.08),
           (0.86, 0.82, 0.08), (0.5, 0.52, 0.08), (0.22, 0.44, 0.07), (0.78, 0.44, 0.07)]
    for i, (u, v, sz) in enumerate(rng[:spots]):
        p = V(fn(u, v))
        D.add(decal('fspot', D.m('spots'), fr, p + front * 0.02, front, sz * R, lift=0.002),
              ('rigid', 'head'))
    if knobs and D.age != 'baby':
        # one round knob on each scallop peak
        kk = 0
        while True:
            a = TAU * kk / scallops
            if a > span / 2 * 0.92:
                break
            for a2 in ((a, -a) if kk else (a,)):
                u = (a2 + span / 2) / span
                p = V(fn(u, 1.0))
                dr = (p - fc).normalized()
                rk = R * (0.085 if D.age == 'adult' else 0.06)
                D.add(ell('knob', D.m('horn'), p + dr * rk * 0.1, (rk, rk, rk), seg=8, rings=5),
                      ('rigid', 'head'))
            kk += 1


def f_spots(D, on='torso', spots=(), mat='spots'):
    """spots: list of (az, el, size) on the torso (size = fraction of the
    torso's smallest radius) or on the tail/head."""
    L = D.L
    if on == 'torso':
        Ct, tr = L['torso_c'], L['torso_r']
        Rt = _rotm(L['torso_rot_deg'])
        rmin = min(tr)
        for az, el, sz in spots:
            p, n = on_ell(V((0, 0, 0)), tr, az, el)
            p, n = Ct + Rt @ p, Rt @ n
            D.add(decal('spot', D.m(mat), D.ref['torso'], p, n, sz * rmin, sz * rmin * 0.9,
                        lift=0.003), _torso_skin(D))
    elif on == 'head':
        hc, hr = L['head_c'], L['head_r']
        rmin = min(hr)
        for az, el, sz in spots:
            p, n = on_ell(hc, hr, az, el)
            D.add(decal('hspot', D.m(mat), D.ref['head'], p, n, sz * rmin, lift=0.002),
                  ('rigid', 'head'))


def f_stripes(D, n=4, width=0.16, length=0.8, start=0.1, end=0.75, tail=3, mat='spots'):
    """Stripes across the back (torso) and over the tail."""
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = _rotm(L['torso_rot_deg'])
    for i in range(n):
        f = lerp(start, end, i / max(n - 1, 1))
        el = 90 - 0
        p, nrm = on_ell(V((0, 0, 0)), tr, 180, lerp(85, 35, f))
        p, nrm = Ct + Rt @ p, Rt @ nrm
        D.add(decal('stripe', D.m(mat), D.ref['torso'], p, nrm, tr[0] * length, tr[1] * width,
                    u_axis=V((1, 0, 0)), lift=0.003), _torso_skin(D))
    pts = L['tail_pts']
    tr0 = L['tail_r']
    for i in range(tail):
        f = (i + 1) / (tail + 1)
        k = f * (len(pts) - 1)
        j = min(int(k), len(pts) - 2)
        p = pts[j].lerp(pts[j + 1], k - j)
        r = tr0 * lerp(1.0, 0.3, f)
        D.add(decal('tstripe', D.m(mat), D.ref['tail'], p + UP * r, UP, r * 0.72, r * 0.3,
                    u_axis=V((1, 0, 0)), lift=0.003), ('near', ['root'] + D.tail, 4.0, 2))


def f_feathers(D, crest=(), arms=0, tail_tuft=0, ruff=0, mat='accent'):
    """Feather tufts: crest = list of (x_off, len, back, width) fractions of
    the head radius on top of the head; arms = feathers per forearm;
    tail_tuft = feathers at the tail tip; ruff = feathers round the neck."""
    L = D.L
    hc, hr = L['head_c'], L['head_r']
    k = D.A['crest']
    for i, (xo, ln, bk, wd) in enumerate(crest):
        p, n = on_ell(hc, hr, xo * 60, 62 - abs(xo) * 10)
        ln *= hr[2] * k
        b = p - n * hr[2] * 0.08
        m1 = b + V((xo * ln * 0.3, bk * ln * 0.3, ln * 0.55))
        t = b + V((xo * ln * 0.7, bk * ln, ln * 0.85))
        D.add(tube('crest', D.m(mat), [b, m1, t], [wd * hr[2] * k, wd * hr[2] * 0.75 * k, wd * hr[2] * 0.15],
                   seg=6, sub=2, cap='end', flat=[0.4, 0.35, 0.3], nrm=V((1, 0, 0))), ('rigid', 'head'))
    for a in D.arms:
        el, hd = a['el'], a['hand']
        for j in range(arms):
            f = 0.25 + 0.6 * j / max(arms - 1, 1)
            b = el.lerp(hd, f)
            ln = L['arm_r'] * (2.2 - 0.5 * j) * k
            d = V((a['side'] * 0.3, 0.8, -0.5)).normalized()
            D.add(tube('afeather', D.m(mat), [b, b + d * ln * 0.5, b + d * ln + V((0, 0, -ln * 0.1))],
                       [L['arm_r'] * 0.55, L['arm_r'] * 0.45, L['arm_r'] * 0.1], seg=6, sub=2, cap='end',
                       flat=[0.35, 0.3, 0.3], nrm=V((a['side'], 0, 0.3))), ('rigid', a['forearm']))
    if tail_tuft:
        pts = L['tail_pts']
        tip = pts[-1]
        d = (pts[-1] - pts[-2]).normalized()
        tr = L['tail_r']
        for j in range(tail_tuft):
            sx = (-1 + 2 * j / max(tail_tuft - 1, 1)) * 0.5
            b = tip - d * tr * 0.5
            dd = (d + V((sx, 0, 0.15))).normalized()
            ln = tr * 2.6 * k
            D.add(tube('tfeather', D.m(mat), [b, b + dd * ln * 0.5, b + dd * ln + UP * ln * 0.15],
                       [tr * 0.5, tr * 0.42, tr * 0.08], seg=6, sub=2, cap='end', flat=[0.35, 0.3, 0.3], nrm=UP),
                  ('rigid', D.tail[-1]))
    if ruff:
        pts = L['neck_pts']
        nr = L['neck_r']
        mid = pts[len(pts) // 2] if len(pts) > 2 else pts[0].lerp(pts[-1], 0.5)
        for j in range(ruff):
            a = math.radians(-70 + 140 * j / max(ruff - 1, 1))
            o = V((math.sin(a), 0.35, math.cos(a) * 0.6 + 0.3)).normalized()
            b = mid + o * nr * 0.7
            ln = nr * 1.1 * k
            D.add(tube('ruff', D.m(mat), [b, b + o * ln * 0.5 + V((0, ln * 0.3, 0)),
                                          b + o * ln * 0.8 + V((0, ln * 0.7, 0))],
                       [nr * 0.3, nr * 0.25, nr * 0.05], seg=6, sub=2, cap='end', flat=[0.4, 0.35, 0.3], nrm=o),
                  ('near', ['spine'] + D.neck + ['head'], 4.0, 2))


def f_ridge(D, n=9, size=0.16, start=0.05, end=0.75, tail=4, mat='accent', round_tip=True):
    """Soft rounded spikes along the back and the tail (size = fraction of
    the torso's height radius)."""
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = _rotm(L['torso_rot_deg'])
    sz = size * tr[2] * D.A['plate']
    torso = D.ref['torso']
    for i in range(n):
        f = lerp(start, end, i / max(n - 1, 1))
        p, nrm = on_ell(V((0, 0, 0)), tr, 0 if f < 0.5 else 180, lerp(30, 90, f / 0.5) if f < 0.5 else lerp(90, 30, (f - 0.5) / 0.5))
        p, nrm = Ct + Rt @ p, Rt @ nrm
        s = sz * (0.7 + 0.3 * math.sin(math.pi * f))
        b = p - nrm * s * 0.3
        D.add(ell('ridge', D.m(mat), b + nrm * s * 0.45, (s * 0.38, s * 0.62, s * 0.9),
                  rot=frame(nrm, V((0, 1, 0))), seg=10, rings=7), _torso_skin(D))
    pts = L['tail_pts']
    trr = L['tail_r']
    for i in range(tail):
        f = (i + 0.6) / (tail + 0.6)
        k = f * (len(pts) - 1)
        j = min(int(k), len(pts) - 2)
        p = pts[j].lerp(pts[j + 1], k - j)
        r = trr * lerp(1.0, 0.25, f) * D.spec['tail'].get('flat', 0.85)
        s = sz * lerp(0.75, 0.35, f)
        b = p + UP * r * 0.85
        D.add(ell('tridge', D.m(mat), b + UP * s * 0.35, (s * 0.35, s * 0.6, s * 0.8),
                  rot=frame(UP, V((0, 1, 0))), seg=10, rings=7), ('near', ['root'] + D.tail, 4.0, 2))


def f_plates(D, n=7, size=0.5, start=0.0, end=1.0, mat='accent'):
    """Stegosaur plates: rounded leaf slabs standing along the back,
    alternating a little left/right (size = fraction of the torso height)."""
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = _rotm(L['torso_rot_deg'])
    sz = size * tr[2] * D.A['plate']
    for i in range(n):
        f = lerp(start, end, i / max(n - 1, 1))
        el = lerp(35, 90, f / 0.5) if f < 0.5 else lerp(90, 35, (f - 0.5) / 0.5)
        p, nrm = on_ell(V((0, 0, 0)), tr, 0 if f < 0.5 else 180, el)
        p, nrm = Ct + Rt @ p, Rt @ nrm
        s = sz * (0.55 + 0.45 * math.sin(math.pi * f))
        xo = (0.06 if i % 2 else -0.06) * tr[0]
        along = V((0, 1, 0)) - nrm * nrm.dot(V((0, 1, 0)))
        along.normalize()

        def fn(u, v, p=p, nrm=nrm, s=s, xo=xo, along=along):
            # u along the back, v up the plate; a rounded leaf outline
            h = s * math.sin(math.pi * u) ** 0.7
            return p - nrm * s * 0.2 + V((xo, 0, 0)) + along * (u - 0.5) * s * 0.9 * (1 - 0.35 * v) + \
                nrm * (h * v + s * 0.2 * v)
        D.add(slab('plate', D.m(mat), fn, 8, 6, s * 0.14, ref=V((1, 0, 0))), _torso_skin(D))


def f_sail(D, height=0.9, start=0.1, end=0.85, mat='accent'):
    """A rounded sail along the back (spino, dimetrodon-ish)."""
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = _rotm(L['torso_rot_deg'])
    H = height * tr[2] * D.A['plate']

    def fn(u, v):
        f = lerp(start, end, u)
        el = lerp(30, 90, f / 0.5) if f < 0.5 else lerp(90, 30, (f - 0.5) / 0.5)
        p, nrm = on_ell(V((0, 0, 0)), tr, 0 if f < 0.5 else 180, el)
        p = Ct + Rt @ p
        h = H * math.sin(math.pi * u) ** 0.7 * (1 + 0.06 * math.sin(u * 30))
        return p - UP * tr[2] * 0.1 + UP * (v * (h + tr[2] * 0.1))
    D.add(slab('sail', D.m(mat), fn, 18, 5, tr[0] * 0.06, ref=V((1, 0, 0))), _torso_skin(D))


def f_bump(D, on='head', az=0, el=60, r=(0.5, 0.6, 0.35), mat='body'):
    """A round bump (brachio nasal crest, pachy dome): r = fractions of the
    head radius."""
    L = D.L
    c, rr = (L['head_c'], L['head_r']) if on == 'head' else (L['snout_c'], L['snout_r'])
    p, n = on_ell(c, rr, az, el)
    hr = sum(L['head_r']) / 3
    D.add(ell('bump', D.m(mat), p - n * hr * r[2] * 0.4, (hr * r[0], hr * r[1], hr * r[2]),
              rot=frame(n, FWD), seg=D.lod(16), rings=D.lod(10)), ('rigid', 'head'))


def f_beak(D, mat='horn', size=1.0):
    """A parrot beak on the snout tip (ceratopsians): upper hook on the head,
    lower tip on the jaw."""
    L = D.L
    snc, snr = L['snout_c'], L['snout_r']
    tip = snc + FWD * snr[1] * 0.92 + UP * snr[2] * 0.05
    r = snr[0] * 0.48 * size
    b = tip - FWD * r * 0.9 + UP * r * 0.2
    D.add(tube('beak', D.m(mat), [b, tip + FWD * r * 0.25 + UP * r * 0.15, tip + FWD * r * 0.55 - UP * r * 0.6],
               [r, r * 0.7, r * 0.12], seg=D.lod(12, 8), flat=[0.85, 0.8, 0.7], nrm=V((1, 0, 0))),
          ('rigid', 'head'))
    jt = L['jaw_tip']
    D.add(ell('lbeak', D.m(mat), jt + UP * r * 0.25, (r * 0.5, r * 0.55, r * 0.36),
              seg=D.lod(10, 8), rings=6), ('rigid', 'jaw'))


FEATURES = {'horns': f_horns, 'frill': f_frill, 'spots': f_spots, 'stripes': f_stripes,
            'feathers': f_feathers, 'ridge': f_ridge, 'plates': f_plates, 'sail': f_sail,
            'bump': f_bump, 'beak': f_beak}


# ---------------------------------------------------------------- solving


def lid_scale(c):
    """Eyelid bone scale for closedness c (0 open .. 1 closed)."""
    c = clamp(c, 0.0, 1.0)
    return V((0.4 + 0.6 * min(1.0, c * 3.0), 0.03 + 0.97 * c, min(1.0, 0.06 + c * 3.0)))


def _solve(D, P):
    R = D.R
    rot = {n: list(v) for n, v in P.rot.items()}
    if P.reach is not None:
        tgt, w, chain = P.reach
        if w > 1e-3:
            delta = _ccd(D, P, rot, tgt, chain)
            for n, d in delta.items():
                rot.setdefault(n, [0, 0, 0])[0] += d * w
    for n, v in P.post.items():
        a = rot.setdefault(n, [0, 0, 0])
        for i in range(3):
            a[i] += v[i]
    jaw = rot.setdefault('jaw', [0, 0, 0])
    jaw[0] += P.jaw
    B = {}
    for n in R.names:
        q = qsem(*rot[n]) if n in rot else None
        B[n] = R.basis(n, q, P.loc.get(n), P.scl.get(n))
    lids = P.lid if isinstance(P.lid, dict) else {'L': P.lid, 'R': P.lid}
    for e in D.eyes:
        sd = 'L' if e['side'] > 0 else 'R'
        B[e['bone']] = [V((0, 0, 0)), Quaternion(), lid_scale(lids[sd])]
    W = R.fk(B)
    for lg in D.legs:
        tag = lg['tag']
        if tag in P.feet:
            tgt, pitch = P.feet[tag][:2]
            yaw = P.feet[tag][2] if len(P.feet[tag]) > 2 else 0.0
        else:
            tgt, pitch, yaw = lg['ankle'], 0.0, 0.0
        fd = (lg['toe'] - lg['ankle']).normalized()
        fd = qsem(pitch, yaw, 0) @ fd
        R.leg_ik(B, W, lg, tgt, fd)
    return B


def _ccd(D, P, rot, tgt, chain):
    """Pitch-only CCD of the mouth towards tgt over chain [(bone, limit
    deg, stiffness)]. Returns {bone: delta pitch}."""
    R = D.R
    rr = {n: list(v) for n, v in rot.items()}
    delta = {b: 0.0 for b, _, _ in chain}
    mouth_rest = D.L['mouth']
    tgt = V(tgt)
    for it in range(14):
        for b, lim, st in reversed(chain):
            B = {n: R.basis(n, qsem(*rr[n]) if n in rr else None, P.loc.get(n), P.scl.get(n))
                 for n in R.names}
            W = R.fk(B)
            E = R.world_point(W, 'head', mouth_rest)
            J = W[b].translation
            a = E - J
            c = tgt - J
            a.x = c.x = 0.0
            if a.length < 1e-6 or c.length < 1e-6:
                continue
            ang = math.degrees(math.atan2(a.cross(c).x, a.dot(c)))
            nd = clamp(delta[b] + ang * st, -lim, lim)
            step = nd - delta[b]
            delta[b] = nd
            rr.setdefault(b, [0, 0, 0])[0] += step
    return delta


# ---------------------------------------------------------------- keying


def key_action(D, name, frames, gen, fps=FPS):
    """Sample gen(t) -> Pose on every frame 0..frames and key every bone."""
    R, arm = D.R, D.arm
    bpy.context.scene.render.fps = fps          # the exporter samples at the scene rate
    bpy.context.scene.render.fps_base = 1.0
    names = R.names
    data = {n: ([], [], []) for n in names}
    prevq = {}
    for f in range(frames + 1):
        t = f / fps
        B = _solve(D, gen(t))
        for n in names:
            ll, lq, ls = B[n]
            if n in prevq and prevq[n].dot(lq) < 0:
                lq = -lq
            prevq[n] = lq
            data[n][0].append(tuple(ll))
            data[n][1].append(tuple(lq))
            data[n][2].append(tuple(ls))
    act = bpy.data.actions.new(name)
    for n in names:
        for prop, k, arr in (('location', 3, data[n][0]), ('rotation_quaternion', 4, data[n][1]),
                             ('scale', 3, data[n][2])):
            for i in range(k):
                fc = act.fcurves.new('pose.bones["%s"].%s' % (n, prop), index=i, action_group=n)
                fc.keyframe_points.add(frames + 1)
                co = []
                for f in range(frames + 1):
                    co += [float(f), arr[f][i]]
                fc.keyframe_points.foreach_set('co', co)
                fc.keyframe_points.foreach_set('interpolation', [1] * (frames + 1))  # LINEAR
                fc.update()
    act.frame_range = (0, frames)
    act.use_frame_range = True
    arm.animation_data_create()
    tr = arm.animation_data.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 0, act)
    st.name = name
    D.actions[name] = (frames, frames / fps)
    return act


def export_glb(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    kw = dict(filepath=path, export_format='GLB', export_apply=False,
              export_animations=True, export_yup=True, use_selection=False,
              export_materials='EXPORT', export_nla_strips=True,
              export_frame_range=False, export_force_sampling=True,
              export_optimize_animation_size=True)
    bpy.ops.export_scene.gltf(**kw)
    print('[dino] wrote', path, os.path.getsize(path) // 1024, 'KB')


# ---------------------------------------------------------------- motions

ANIMS = ('idle', 'walk', 'run', 'eat', 'drink', 'sleep', 'happy', 'pet', 'sit',
         'call', 'play', 'sad')
LOOPS = ('idle', 'walk', 'run', 'sleep', 'sit', 'sad')


class Moves:
    """Generic animation generators driven by the body plan. Each returns
    gen(t) -> Pose; species tweak them with spec['moves'] numbers."""

    def __init__(self, D):
        self.D = D
        L, R = D.L, D.R
        self.H = D.spec['height'] * D.A['height']
        self.legl = sum(R.len[lg['thigh']] + R.len[lg['shin']] for lg in D.legs) / len(D.legs)
        self.biped = D.plan in ('biped', 'flier')
        self.mv = dict(D.spec.get('moves', {}))
        self.mouth = L['mouth']
        self.front_y = min(lg['toe'].y for lg in D.legs)
        self.root_z = L['root'].z
        self.baby = D.age == 'baby'

    # helpers --------------------------------------------------------
    def base(self, t, T, breath=2, amp=1.0):
        """Standing: breathing (root squash) and the species' stance."""
        P = Pose()
        for b, v in self.mv.get('stance', {}).items():
            P.r(b, *v)
        br = wave(t, T / breath)
        a = 0.012 * amp * (1.3 if self.baby else 1.0)
        P.sc('root', (1 + a * br, 1 + a * 0.5 * br, 1 - a * 0.6 * br))
        P.at('root', (0, 0, -self.legl * 0.01 * amp * (1 + br)))
        return P

    def tail(self, P, t, period, yaw=10.0, pitch=0.0, lag=0.7, phase=0.0, post=False):
        n = len(self.D.tail)
        for i, b in enumerate(self.D.tail):
            g = 0.55 + 0.45 * i / max(n - 1, 1)
            P.r(b, pitch * g * wave(t, period, phase - lag * i + math.pi / 2),
                yaw * g * wave(t, period, phase - lag * i), 0, post=post)

    def spread(self, P, chain, p=0.0, y=0.0, r=0.0, post=False):
        n = len(chain)
        for b in chain:
            P.r(b, p / n, y / n, r / n, post=post)

    def blink(self, t, *times):
        c = 0.0
        for t0 in times:
            c = max(c, env(t, t0, t0 + 0.06, t0 + 0.09, t0 + 0.18))
        return c

    def arms(self, P, p=0.0, y=0.0, r=0.0, fp=0.0, post=False):
        for a in self.D.arms:
            s = a['side']
            P.r(a['arm'], p, -s * y, -s * r, post=post)
            P.r(a['forearm'], fp, 0, 0, post=post)

    def feet_at(self, P, fn):
        for lg in self.D.legs:
            P.feet[lg['tag']] = fn(lg)

    def reach_chain(self):
        D = self.D
        nk = [(b, 50.0 if len(D.neck) < 3 else 28.0, 0.6) for b in D.neck]
        if D.plan == 'sauropod':
            return [('spine', 6.0, 0.3)] + nk + [('head', 60.0, 0.7)]
        if self.biped:
            return [('root', 40.0, 0.45), ('spine', 12.0, 0.4)] + nk + [('head', 45.0, 0.7)]
        return [('root', 10.0, 0.3), ('spine', 12.0, 0.4)] + nk + [('head', 60.0, 0.75)]

    def ground_target(self, z=0.04, ahead=0.12):
        D = self.D
        y = min(self.front_y - self.H * ahead * 0.4, self.mouth.y - self.H * 0.05)
        if self.biped:
            y = min(self.front_y - self.H * 0.05, self.mouth.y + self.H * 0.15)
        return V((0, y, self.H * z + D.L['snout_r'][2] * 0.4))

    # loops ------------------------------------------------------------
    def idle(self):
        T = 3.0

        def g(t):
            P = self.base(t, T)
            look = tl(t, [(0, 0), (0.5, 0), (0.95, 18), (1.6, 18), (2.05, -12), (2.45, -12), (2.9, 0), (3.0, 0)])
            tilt = tl(t, [(0, 0), (0.6, 0), (1.0, 8), (1.55, 8), (2.0, -4), (2.5, -4), (2.9, 0), (3.0, 0)])
            nod = tl(t, [(0, 0), (0.95, -4), (1.6, -4), (2.05, 3), (2.45, 3), (2.9, 0), (3.0, 0)])
            self.spread(P, self.D.neck, nod * 0.5, look * 0.45)
            P.r('head', nod * 0.6, look * 0.55, tilt)
            P.r('root', 0, look * 0.06, 0)
            self.tail(P, t, T, yaw=12, pitch=3, lag=0.6)
            P.lid = self.blink(t, 1.1, 2.55)
            P.jaw = 2.0 + 1.5 * wave(t, T / 2)
            if self.biped:
                self.arms(P, -4 * wave(t, T / 2), 0, 3)
            return P
        return T, g

    def _gait_frames(self, v, duty, reach):
        T = 2 * reach * self.legl / (v * duty)
        F = max(8, int(round(T * FPS)))
        return F, F / FPS

    def locomote(self, kind):
        D, mv = self.D, self.mv
        sp = D.spec.get('speeds', {}).get(D.age)
        v = sp[0 if kind == 'walk' else 1] if sp else \
            (0.8 if self.baby else 1.2) * (1.0 if kind == 'walk' else 2.4)
        if self.biped:
            duty = mv.get(kind + '_duty', 0.58 if kind == 'walk' else 0.36)
            phases = {'L': 0.0, 'R': 0.5}
        else:
            duty = mv.get(kind + '_duty', (0.6 if not self.baby else 0.5) if kind == 'walk' else 0.38)
            if kind == 'walk' and D.age == 'adult' and not mv.get('trot'):
                phases = {'L': 0.0, 'fL': 0.25, 'R': 0.5, 'fR': 0.75}
            elif kind == 'walk':
                phases = {'L': 0.0, 'fR': 0.0, 'R': 0.5, 'fL': 0.5}
            else:
                phases = {'L': 0.0, 'R': 0.12, 'fL': 0.5, 'fR': 0.62}
        reach = mv.get(kind + '_reach', (0.40 if kind == 'walk' else 0.5) if not self.biped else
                       (0.52 if kind == 'walk' else 0.66))
        if self.baby:
            reach *= 1.15
        F, T = self._gait_frames(v, duty, reach)
        S = v * T * duty
        lift = self.legl * (0.16 if kind == 'walk' else 0.26) * mv.get('lift', 1.0)
        bob = self.legl * (0.035 if kind == 'walk' else 0.07) * (1.5 if self.baby else 1.0)
        D.speeds[kind] = (v, T)

        def g(t):
            P = self.base(t, T, breath=1, amp=0.3)
            u = t / T
            for lg in D.legs:
                ph = (u + phases[lg['tag']]) % 1.0
                a0 = lg['ankle']
                if ph < duty:
                    s = ph / duty
                    y = a0.y - S / 2 + S * s
                    z = a0.z
                    pitch = 0.0
                    if s > 0.8:                # heel off
                        pitch = 18 * smooth((s - 0.8) / 0.2)
                        z += (lg['toe'] - lg['ankle']).length * math.sin(math.radians(pitch)) * 0.5
                else:
                    s = (ph - duty) / (1 - duty)
                    y = a0.y + S / 2 - S * (0.5 - 0.5 * math.cos(math.pi * s))
                    z = a0.z + lift * math.sin(math.pi * s) ** 0.8
                    pitch = 18 * (1 - s) ** 2 - 14 * math.sin(math.pi * s) * s
                P.feet[lg['tag']] = (V((a0.x, y, z)), pitch)
            if self.biped:
                ph2 = 2 * u - 2 * 0.12
                bz = -bob * (0.5 + 0.5 * math.cos(TAU * ph2))
                if kind == 'run':
                    bz = bob * (0.6 - 1.2 * (0.5 + 0.5 * math.cos(TAU * ph2)))
                P.at('root', (0, 0, bz))
                sway = 4.0 if kind == 'walk' else 3.0
                P.r('root', (2.0 if kind == 'walk' else 9.0) + 1.5 * math.cos(TAU * ph2),
                    -5 * math.sin(TAU * u), sway * math.cos(TAU * (u - duty / 2)))
                P.r('spine', -1.0 * math.cos(TAU * ph2), 3 * math.sin(TAU * u), 0)
                self.arms(P, (14 if kind == 'walk' else 22) * math.sin(TAU * u), 0, 4,
                          fp=-10 if kind == 'run' else 0)
                hp = -(2.0 if kind == 'walk' else 9.0) - 2.0 * math.cos(TAU * (ph2 - 0.1))
                self.spread(P, D.neck, hp * 0.5, 2.5 * math.sin(TAU * u))
                P.r('head', hp * 0.5 + (4 if kind == 'run' else 0), 2.5 * math.sin(TAU * u), 0)
                self.tail(P, t, T, yaw=7 if kind == 'walk' else 5, pitch=3, lag=0.8, phase=math.pi)
                if kind == 'run':
                    self.spread(P, D.tail, -8)
            else:
                k = 2 * u
                bz = -bob * (0.5 + 0.5 * math.cos(TAU * k))
                if kind == 'run':
                    bz = bob * (0.4 - 1.0 * (0.5 + 0.5 * math.cos(TAU * (u - 0.2))))
                    P.r('root', 5 * math.sin(TAU * (u + 0.1)), 0, 0)
                    P.r('spine', -4 * math.sin(TAU * (u + 0.35)), 0, 0)
                else:
                    P.r('root', 1.5 * math.cos(TAU * k), 2 * math.sin(TAU * u), 2.5 * math.sin(TAU * u))
                    P.r('spine', -1.0 * math.cos(TAU * k), -2 * math.sin(TAU * u), -1.5 * math.sin(TAU * u))
                P.at('root', (0, 0, bz))
                hp = -2.0 * math.cos(TAU * (k - 0.15)) - (3 if kind == 'run' else 0)
                self.spread(P, D.neck, hp * 0.5, 3 * math.sin(TAU * u - 0.5))
                P.r('head', hp * 0.5, 3 * math.sin(TAU * u - 0.8), 2 * math.sin(TAU * u))
                self.tail(P, t, T, yaw=10 if kind == 'walk' else 7, pitch=4, lag=0.8, phase=math.pi)
            P.jaw = 4.0 if kind == 'run' else 1.5
            return P
        return T, g

    def walk(self):
        return self.locomote('walk')

    def run(self):
        return self.locomote('run')

    def eat(self):
        T = 1.5
        tgt = self.ground_target()

        def g(t):
            P = self.base(t, T, breath=1, amp=0.5)
            w = tl(t, [(0, 0), (0.38, 1), (1.18, 1), (1.5, 0)])
            P.reach = (tgt, w, self.reach_chain())
            ch = 0.0
            for t0 in (0.42, 0.68, 0.94):
                ch = max(ch, env(t, t0, t0 + 0.07, t0 + 0.1, t0 + 0.22))
            P.jaw = 24 * ch
            P.r('head', -6 * ch, 0, 4 * math.sin(TAU * t / 0.52), post=True)
            self.tail(P, t, 0.5, yaw=10 * w, lag=0.7)
            if self.biped:
                self.arms(P, -25 * w, 0, 6 * w)
            P.lid = env(t, 0.42, 0.5, 1.1, 1.2)
            return P
        return T, g

    def drink(self):
        T = 1.5
        tgt = self.ground_target(z=0.02)

        def g(t):
            P = self.base(t, T, breath=1, amp=0.5)
            w = tl(t, [(0, 0), (0.4, 1), (1.15, 1), (1.5, 0)])
            P.reach = (tgt, w, self.reach_chain())
            lap = env(t, 0.42, 0.5, 1.05, 1.15) * (0.5 + 0.5 * math.sin(TAU * (t - 0.42) / 0.16))
            P.jaw = 12 * lap
            P.r('head', 4 * lap, 0, 0, post=True)
            P.lid = env(t, 0.42, 0.5, 1.08, 1.18)
            self.tail(P, t, 0.75, yaw=6 * w, lag=0.7)
            if self.biped:
                self.arms(P, -20 * w, 0, 6 * w)
            return P
        return T, g

    def _down_pose(self, P, sleep=True):
        """Lying on the belly; feet folded beside the body."""
        D, L = self.D, self.D.L
        tr = L['torso_r']
        if self.biped:
            drop = self.root_z - L['torso_r'][2] * 0.55
            P.at('root', (0, 0, -drop))
            P.r('root', L['torso_rot_deg'][0] * -0.7, 0, 0)
            self.feet_at(P, lambda lg: (V((lg['ankle'].x * 1.45, lg['ankle'].y - self.legl * 0.15,
                                              lg['foot_h'])), -15))
            self.arms(P, -35, 0, 10, fp=-20)
        else:
            Ct = L['torso_c']
            bottom = Ct.z - tr[2] * 0.75
            drop = bottom - 0.01 * self.H
            P.at('root', (0, 0, -drop))
            P.r('root', -L['torso_rot_deg'][0] * 0.6, 0, 0)

            def ft(lg):
                a = lg['ankle']
                if lg['front']:
                    return (V((a.x * 1.15, a.y - tr[1] * 0.35, lg['foot_h'])), -10)
                return (V((a.x * 1.55, a.y + tr[1] * 0.1, lg['foot_h'])), 10, -lg['side'] * 25)
            self.feet_at(P, ft)
        return P

    def sleep(self):
        T = 3.0
        D = self.D
        tgt = V((0.0, self.front_y - self.H * self.mv.get('sleep_fwd', 0.16), D.L['snout_r'][2] * 1.1))

        def g(t):
            P = Pose()
            self._down_pose(P)
            br = wave(t, T)
            P.sc('root', (1 + 0.02 * br, 1 + 0.01 * br, 1 - 0.012 * br))
            P.reach = (tgt, 1.0, self.reach_chain()[1:] if not self.biped else self.reach_chain()[1:])
            P.r('head', -self.mv.get('sleep_lift', 18), 10, 14, post=True)
            self.spread(P, D.neck, 0, 12, post=True)
            for i, b in enumerate(D.tail):
                P.r(b, 6 if i == 0 else 0, 14 + 4 * i, 0)
            self.tail(P, t, T, yaw=2, lag=0.5)
            P.lid = 1.0
            P.jaw = 1.0 + 1.5 * (0.5 + 0.5 * br)
            return P
        return T, g

    def _sit_pose(self, P):
        D, L = self.D, self.D.L
        tr = L['torso_r']
        if self.biped:
            drop = self.legl * 0.55
            P.at('root', (0, 0, -drop))
            P.r('root', -10, 0, 0)
            self.feet_at(P, lambda lg: (V((lg['ankle'].x * 1.25, lg['ankle'].y - self.legl * 0.42,
                                              lg['foot_h'])), -5))
            self.spread(P, D.tail, 28)
            P.r(D.tail[0], -10)
            self.spread(P, D.neck, 8)
            P.r('head', -6)
        else:
            drop = self.legl * 0.62
            sl = (L['chest'] - L['root']).length
            th = math.degrees(math.asin(clamp(drop * 0.95 / sl, 0, 0.9)))
            P.at('root', (0, 0, -drop))
            P.r('root', -th, 0, 0)
            P.r('spine', 2, 0, 0)
            self.spread(P, D.neck, th * 0.35)
            P.r('head', th * 0.45)

            def ft(lg):
                a = lg['ankle']
                if lg['front']:
                    return (a, 0.0)
                return (V((a.x * 1.25, a.y - tr[1] * 0.5, lg['foot_h'])), 0.0)
            self.feet_at(P, ft)
            P.r(D.tail[0], th + 10)
            self.spread(P, D.tail[1:], 8)
        return P

    def sit(self):
        T = 2.0

        def g(t):
            P = self.base(t, T, breath=1, amp=0.8)
            self._sit_pose(P)
            P.r('head', 0, 6 * wave(t, T), 6 * wave(t, T, 0.6), post=True)
            self.tail(P, t, T, yaw=8, lag=0.6)
            P.lid = self.blink(t, 1.3)
            if self.biped:
                self.arms(P, -18, 0, 8)
            return P
        return T, g

    def sad(self):
        T = 3.0
        D = self.D

        def g(t):
            P = self.base(t, T, breath=1, amp=1.2)
            self._sit_pose(P)
            sigh = env(t, 1.0, 1.5, 1.7, 2.4)
            self.spread(P, D.neck, 16 + 4 * sigh, post=True)
            P.r('head', 18 + 3 * wave(t, T), 0, 7, post=True)
            P.r('root', 2 * sigh, 0, 0)
            P.sc('root', (1 + 0.02 * sigh, 1, 1 + 0.02 * sigh))
            self.tail(P, t, T, yaw=5, lag=0.4)
            P.lid = 0.45 + 0.1 * sigh
            if self.biped:
                self.arms(P, 5, 0, 2)
            return P
        return T, g

    # one-shots --------------------------------------------------------
    def happy(self):
        T = 1.0
        D = self.D
        clap = self.mv.get('clap', False)
        hop = self.mv.get('hop', 0.22 if not clap else 0.08) * self.legl

        def g(t):
            P = self.base(t, T, breath=1, amp=0.3)
            sq = tl(t, [(0, 0), (0.14, -1), (0.24, 0.8), (0.42, 0.2), (0.55, -1.0), (0.68, 0.3), (0.8, 0), (1.0, 0)])
            up = 0.0
            if 0.2 <= t <= 0.52:
                u = (t - 0.2) / 0.32
                up = 4 * u * (1 - u)
            if clap:
                up = 0.5 * env(t, 0.15, 0.3, 0.3, 0.45) + 0.5 * env(t, 0.5, 0.62, 0.62, 0.75)
            a = 0.08 * sq
            P.sc('root', (1 - a * 0.6, 1 - a * 0.3, 1 + a))
            z = hop * up - self.legl * 0.06 * max(0, -sq)
            P.at('root', (0, 0, z))
            tuck = hop * up * 0.75

            def ft(lg):
                a0 = lg['ankle']
                return (a0 + V((0, 0, tuck)), -10 * up)
            self.feet_at(P, ft)
            P.r('root', -5 * up, 0, 0)
            self.spread(P, D.neck, -8 * env(t, 0.1, 0.3, 0.7, 0.95))
            P.r('head', -10 * env(t, 0.1, 0.3, 0.7, 0.95), 0, 8 * math.sin(TAU * t * 2))
            self.tail(P, t, 1.0 / 3, yaw=22, pitch=6, lag=0.5)
            self.spread(P, D.tail, -8 * env(t, 0.05, 0.25, 0.75, 1.0))
            P.jaw = 16 * env(t, 0.1, 0.25, 0.75, 0.95)
            P.lid = env(t, 0.3, 0.36, 0.5, 0.58)
            if self.biped:
                if clap:
                    c = 0.5 + 0.5 * math.cos(TAU * t * 4)
                    e = env(t, 0.05, 0.15, 0.85, 1.0)
                    self.arms(P, -55 * e, -(10 + 32 * c) * e - 0, 0, fp=-25 * e)
                    for a in D.arms:
                        P.r(a['arm'], 0, a['side'] * 40 * e * (1 - c) - a['side'] * 10 * e, 0)
                else:
                    self.arms(P, -40 * env(t, 0.1, 0.25, 0.7, 0.9), 0, 25 * up, fp=-20 * up)
            return P
        return T, g

    def pet(self):
        T = 1.2
        D = self.D
        mz = self.mouth.z
        hz = clamp(mz, 0.5, 1.05) if self.H > 1.2 else mz + self.H * 0.06
        far = self.H > 2.0
        tgt = V((0, self.mouth.y - self.H * (0.18 if far else 0.06), hz))

        def g(t):
            P = self.base(t, T, breath=1, amp=0.5)
            w = tl(t, [(0, 0), (0.32, 1), (0.95, 1), (1.2, 0)])
            P.reach = (tgt, w, self.reach_chain())
            if not far:
                P.at('root', (0, -self.H * 0.03 * w, 0))
            nz = env(t, 0.3, 0.4, 0.9, 1.0)
            P.r('head', -6 * nz, 0, (10 * math.sin(TAU * (t - 0.3) / 0.6)) * nz + 6 * w, post=True)
            P.lid = tl(t, [(0, 0), (0.22, 0), (0.34, 1), (0.98, 1), (1.1, 0), (1.2, 0)])
            self.tail(P, t, 0.3, yaw=20 * w, lag=0.5)
            P.jaw = 8 * w
            P.sc('root', (1 + 0.03 * nz, 1, 1 - 0.02 * nz))
            if self.biped:
                self.arms(P, -20 * w, 0, 5, fp=-15 * w)
            return P
        return T, g

    def call(self):
        T = 1.0
        D = self.D

        def g(t):
            P = self.base(t, T, breath=1, amp=0.3)
            inh = env(t, 0.0, 0.2, 0.2, 0.32)
            roar = env(t, 0.22, 0.34, 0.72, 0.92)
            vib = math.sin(TAU * t * 11) * env(t, 0.34, 0.4, 0.7, 0.8)
            self.spread(P, D.neck, 10 * inh - 22 * roar)
            P.r('head', 8 * inh - 16 * roar, 0, 3 * vib)
            P.r('root', 4 * inh - 5 * roar, 0, 0)
            P.sc('root', (1 + 0.04 * roar, 1, 1 + 0.05 * roar - 0.04 * inh))
            P.jaw = 6 * inh + 34 * roar
            P.lid = env(t, 0.3, 0.38, 0.7, 0.8)
            self.spread(P, D.tail, -10 * roar)
            self.tail(P, t, 0.25, yaw=6 * roar, lag=0.5)
            if self.biped:
                self.arms(P, -30 * roar, 0, 20 * roar, fp=-20 * roar)
            return P
        return T, g

    def play(self):
        T = 0.8
        D = self.D

        def g(t):
            P = self.base(t, T, breath=1, amp=0.3)
            bow = env(t, 0.0, 0.22, 0.26, 0.42)
            lunge = env(t, 0.26, 0.4, 0.46, 0.72)
            dy = self.H * (0.04 * bow - 0.10 * lunge)
            P.at('root', (0, dy, -self.legl * 0.12 * bow))
            if self.biped:
                P.r('root', 14 * bow + 16 * lunge, 0, 0)
                self.spread(P, D.neck, 10 * bow - 10 * lunge)
                P.r('head', 6 * bow + 14 * lunge, 0, 0)
                self.arms(P, -30 * lunge, 0, 10)
            else:
                P.r('root', 9 * bow + 3 * lunge, 0, 0)
                self.spread(P, D.neck, 10 * bow)
                P.r('head', 16 * bow + 18 * lunge, 0, 0)
            P.sc('root', (1 + 0.04 * bow - 0.02 * lunge, 1, 1 - 0.05 * bow + 0.04 * lunge))
            self.spread(P, D.tail, -12 * bow)
            self.tail(P, t, 0.27, yaw=18, lag=0.5)
            P.jaw = 12 * lunge
            return P
        return T, g


def animate(D, only=None):
    """Key all ART-SPEC animations (or `only`) for a built Dino."""
    D.actions = {}
    D.speeds = {}
    M = Moves(D)
    custom = D.spec.get('anims', {})     # {name: fn(M) -> (T, gen)}: per-species overrides
    # names in `anims` that are not in ANIMS are extra actions (e.g. carno 'skid')
    for a in (only or tuple(ANIMS) + tuple(k for k in custom if k not in ANIMS)):
        T, g = custom[a](M) if a in custom else getattr(M, a)()
        F = int(round(T * FPS))
        key_action(D, a, F, g)
    return D.actions
