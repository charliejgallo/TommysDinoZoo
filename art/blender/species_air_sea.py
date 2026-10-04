"""species_air_sea.py - the flying and swimming creatures of Tommy's Dino Zoo.

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P dinos.py -- \\
        --only ptera_baby,ptera_juv,ptera_adult,egg_ptera   (archaeo, microraptor, plesio)

dinos.py merges SPECIES / EGGS from here (they replace its PTERA / PLESIO
drafts). The body plans are special enough to get their own Dino subclasses
(spec['dino_class'], see dino_lib.Dino.__new__) and their own Moves:

  ptera        Pteranodon. Rest pose = wings spread (the membrane is modelled
               flat and only folds on the ground); on the ground it walks on
               four legs like a bat: the wrists are the front feet (IK) and the
               long wing finger folds up along the arm. Bones: arm/forearm
               (wing arm), wing/wing2 (wing finger), and `carry` (child of
               `jaw`, at the beak tip: attach carried things there, e.g. a fish).
  archaeo      Archaeopteryx: a little colourful bird-dino; `call` is its dawn
               song. Two wing sets: the flight wing (rest pose = spread; rigid
               feather fans on arm/forearm/wing, so nothing stretches) and a
               folded feather leaf on each flank (bones fold/fold2.L/.R).
               Ground actions scale arm.L/.R to 0.02 (the flight wing shrinks
               into the shoulder); fly/glide scale fold.L/.R to 0.02 instead,
               so a crossfade idle -> fly pops the wings open.
  microraptor  Same bird rig + shin feathers (hind wings) and a tail fan.
  plesio       Plesiosaurus, lives in the lagoon pond. Every action is a swim
               version; flippers are thigh/shin/foot (+ f... front) chains.

EXTRA ANIMATIONS (beyond the 12 of ART-SPEC section 4; loops marked *):
  ptera        fly* (flapping, body level)  glide* 3.0 s
  archaeo      fly*
  microraptor  glide* 3.0 s  (fly* too: a short flutter, used to take off)
  plesio       dive 2.0 s (one-shot: dips under and comes back)

SPEEDS each model was animated for (m/s; the root stays in place, the game
moves the node; walk/run feet do not slide). Cycle seconds in brackets.

  model              walk         run          fly          glide
  ptera_baby         0.50 (0.47)  1.20 (0.30)  2.0 (0.50)   2.4 (3.0)
  ptera_juv          0.65 (0.43)  1.50 (0.33)  2.5 (0.63)   2.9 (3.0)
  ptera_adult        0.80 (0.57)  1.80 (0.43)  3.0 (0.77)   3.5 (3.0)
  archaeo_baby       0.40 (0.27)  0.75 (0.27)  1.5 (0.20)    -
  archaeo_juv        0.50 (0.27)  0.95 (0.27)  1.8 (0.23)    -
  archaeo_adult      0.60 (0.37)  1.05 (0.43)  2.0 (0.27)    -
  microraptor_baby   0.45 (0.27)  0.85 (0.27)  1.6 (0.20)   2.0 (3.0)
  microraptor_juv    0.55 (0.30)  1.05 (0.33)  2.0 (0.23)   2.5 (3.0)
  microraptor_adult  0.65 (0.43)  1.25 (0.47)  2.4 (0.27)   3.0 (3.0)
  plesio_baby        swim (walk) 0.50 (1.20)   fast swim (run) 1.20 (0.80)
  plesio_juv         swim (walk) 0.70 (1.40)   fast swim (run) 1.60 (0.90)
  plesio_adult       swim (walk) 0.90 (1.60)   fast swim (run) 2.00 (1.00)
  (the build prints the exact numbers; fly/glide speeds are suggestions
  the motion was designed for - wings do not touch anything.)

PLACING THEM IN THE GAME
  * plesio: its origin is WATER_Z = 0.27 m below the water line for every
    age, so put the node at y = water_y - 0.27 (pond surface -0.08 ->
    y = -0.35). The body is then half under water and the neck stands
    ~1.2 m (adult) out of it. `dive` sinks it ~1.4 m and brings it back.
  * fliers: fly/glide keep the root at its standing height (the body is
    level), so put the node at y = desired body height - root height:
    ptera adult flies nicely at node y 1.6-2.2, archaeo/microraptor at
    0.8-1.4 (they are tiny). Land by crossfading fly -> idle while easing
    the node down to y = 0.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dino_lib as DL  # noqa: E402
import tdz_common as C  # noqa: E402

V = Vector
UP, FWD, TAU = DL.UP, DL.FWD, DL.TAU
smooth, env, tl, wave, lerp = DL.smooth, DL.env, DL.tl, DL.wave, DL.lerp
Pose = DL.Pose

WATER_Z = 0.27          # plesio: local height of the water surface
WING_AGE = {'baby': 0.78, 'juv': 0.9, 'adult': 1.0}


# ======================================================================
# geometry helpers
# ======================================================================

def sheet(name, mats, fn, nu, nv, thick, ref=None, mat_of=None):
    """A thin closed sheet (wing membrane, feather fan): fn(u, v) -> mid
    surface point; thickness thick(u, v) (0 on the border, so the rim is a
    soft knife edge). Returns (object, uvs) where uvs[i] = (u, v) of vertex
    i, so it can be skinned by parameter. mat_of(u, v) -> material slot."""
    bm = bmesh.new()
    G = [[V(fn(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]

    def normal(i, j):
        i0, i1 = max(i - 1, 0), min(i + 1, nu)
        j0, j1 = max(j - 1, 0), min(j + 1, nv)
        n = (G[i1][j] - G[i0][j]).cross(G[i][j1] - G[i][j0])
        if n.length < 1e-12:
            return V(ref) if ref is not None else UP
        n.normalize()
        if ref is not None and n.dot(V(ref)) < 0:
            n = -n
        return n
    uvs = []
    top, bot = {}, {}
    for i in range(nu + 1):
        for j in range(nv + 1):
            u, v = i / nu, j / nv
            border = i in (0, nu) or j in (0, nv)
            h = 0.0 if border else 0.5 * thick(u, v)
            n = normal(i, j)
            top[i, j] = bm.verts.new(G[i][j] + n * h)
            uvs.append((u, v))
            if border:
                bot[i, j] = top[i, j]
            else:
                bot[i, j] = bm.verts.new(G[i][j] - n * h)
                uvs.append((u, v))
    for i in range(nu):
        for j in range(nv):
            uc, vc = (i + 0.5) / nu, (j + 0.5) / nv
            mi = mat_of(uc, vc) if mat_of else 0
            for f in ((top[i, j], top[i + 1, j], top[i + 1, j + 1], top[i, j + 1]),
                      (bot[i, j], bot[i, j + 1], bot[i + 1, j + 1], bot[i + 1, j])):
                if len(set(f)) < 3:
                    continue
                q = [x for k, x in enumerate(f) if x not in f[:k]]
                try:
                    face = bm.faces.new(q)
                    face.material_index = mi
                except ValueError:
                    pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    return ob, uvs


def weigh(ob, uvs, wfn):
    """Vertex groups from parameters: wfn(u, v) -> {bone: weight}."""
    groups = {}
    for i, (u, v) in enumerate(uvs):
        w = wfn(u, v)
        s = sum(w.values()) or 1.0
        for b, x in w.items():
            if x <= 1e-4:
                continue
            if b not in groups:
                groups[b] = ob.vertex_groups.new(name=b)
            groups[b].add([i], x / s, 'REPLACE')
    return ob


def polyline(pts, u):
    """Point at fraction u (by arc length) of a polyline (extrapolates)."""
    segs = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    tot = sum(segs)
    d = u * tot
    if d <= 0:
        return pts[0] + (pts[1] - pts[0]).normalized() * d
    for i, s in enumerate(segs):
        if d <= s or i == len(segs) - 1:
            return pts[i] + (pts[i + 1] - pts[i]) * (d / max(s, 1e-9))
        d -= s


def catmull(pts, per=6):
    out = []
    P = [V(p) for p in pts]
    for i in range(len(P) - 1):
        p0, p1, p2 = P[max(i - 1, 0)], P[i], P[i + 1]
        p3 = P[min(i + 2, len(P) - 1)]
        for s in range(per):
            t = s / per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return out


# ======================================================================
# shared Dino subclass: own layout / rig / build, the lib's parts reused
# ======================================================================

class AirSeaDino(DL.Dino):

    def lay(self, s, A):
        raise NotImplementedError

    def layout(self):
        s, A = self.spec, self.A
        L = self.lay(s, A)
        top = L['head_c'].z + L['head_r'][2]
        base = L.get('ref_z', 0.0)
        k = s['height'] * A['height'] / (top - base)
        self.k = k
        L = DL._scale_tree(L, k)
        dz = L.pop('shift_z', 0.0)
        if dz:
            L = _shift(L, V((0, 0, dz)))
        self.L = L
        return L

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
        self.wingarms = []
        for a in L.get('arms', []):
            sd = '.L' if a['side'] > 0 else '.R'
            b('arm' + sd, a['sh'], a['el'], 'spine')
            b('forearm' + sd, a['el'], a['hand'], 'arm' + sd)
            d = dict(a, arm='arm' + sd, forearm='forearm' + sd)
            if 'tip' in a:
                b('wing' + sd, a['hand'], a['tip'], 'forearm' + sd)
                d['wing'] = 'wing' + sd
            if 'tip2' in a:
                b('wing2' + sd, a['tip'], a['tip2'], 'wing' + sd)
                d['wing2'] = 'wing2' + sd
            self.wingarms.append(d)
        self.wings = []
        for e in self.eyes:
            b(e['bone'], e['lid_top'], e['lid_bot'], 'head', roll_to=e['n'])
        for extra in self.extra_bones:
            b(*extra)
        self.arm = DL.make_armature(self.name + '_rig', bones)
        self.R = DL.Rig(self.arm, L)
        return self.arm

    def build(self):
        DL.reset()
        self.layout()
        self.eyes = []
        self.extra_bones = []
        self._eye_layout()
        self.pre_rig()
        self.rig()
        self.post_rig()
        self.ref = {}
        self.build_parts()
        for feat, opts in self.spec.get('parts', []):
            (FEATS.get(feat) or DL.FEATURES[feat])(self, **opts)
        stat = {}
        for ob, how in self.parts:
            k = ob.name.split('.')[0]
            stat[k] = stat.get(k, 0) + DL.tris(ob)
        self.tri_stats = sorted(stat.items(), key=lambda kv: -kv[1])
        objs = []
        for ob, how in self.parts:
            if how[0] != 'pre':
                DL.skin(ob, self.arm, how)
            objs.append(ob)
        body = C.bind(self.name, self.arm, objs)
        DL.dedupe_slots(body)
        self.body = body
        return body

    def pre_rig(self):
        pass

    def post_rig(self):
        pass

    def build_parts(self):
        raise NotImplementedError

    def head_parts(self):
        DL.build_neck(self)
        DL.build_head(self)
        DL.build_eyes(self)


def _shift(x, d):
    if isinstance(x, Vector):
        return x + d
    if isinstance(x, list):
        return [_shift(v, d) for v in x]
    if isinstance(x, dict):
        return {k: (_shift(v, d) if k not in ('n',) else v) for k, v in x.items()}
    return x


# ======================================================================
# Pteranodon
# ======================================================================

class Ptera(AirSeaDino):
    """Flier with a membrane wing: arm (shoulder-elbow), forearm (elbow-
    wrist), wing (wrist-knuckle of the long finger), wing2 (to the tip)."""

    def lay(self, s, A):
        L = DL.Dino._lay_biped(self, s, A)
        Ct, Rt = L['torso_c'], DL._rotm(L['torso_rot_deg'])
        rx, ry, rz = L['torso_r']

        def tp(x, y, z):
            return Ct + Rt @ V((x, y, z))
        top = L['head_c'].z + L['head_r'][2]
        half = s['span'] / 2.0 / s['height'] * top * WING_AGE[self.age]
        arms, wlegs = [], []
        hand_r = L['leg_r'] * 0.9
        for side in (1, -1):
            sh = tp(side * rx * 0.62, -ry * 0.42, rz * 0.38)
            reach = half - abs(sh.x)
            # the arm must reach the ground from the shoulder with a bend
            la = sh.z * s.get('arm_k', 1.22)
            l1, l2 = la * 0.42, la * 0.58
            el = sh + V((side * l1 * 0.93, l1 * 0.32, l1 * 0.16))
            wr = el + V((side * l2 * 0.95, -l2 * 0.30, l2 * 0.05))
            rest = reach - abs(wr.x - sh.x)
            mid = wr + V((side * rest * 0.5, rest * 0.10, rest * 0.01))
            tip = mid + V((side * rest * 0.5, rest * 0.24, -rest * 0.03))
            arms.append(dict(tag='L' if side > 0 else 'R', side=side, sh=sh, el=el, hand=wr,
                             tip=mid, tip2=tip))
            # on the ground: the wrist is a front foot, the finger folds up-back
            gw = V((side * (abs(sh.x) + la * 0.30), sh.y - la * 0.12, hand_r * 0.9))
            dist = (gw - sh).length
            if dist > 0.93 * la:
                print('[ptera] warning: wrist cannot reach the ground (%.2f > %.2f)' % (dist, 0.93 * la))
            fold = V((side * 0.22, 0.42, 0.88)).normalized()
            wlegs.append(dict(tag='f' + ('L' if side > 0 else 'R'), front=True, side=side, hip=sh,
                              knee=el, ankle=gw, toe=gw + fold * (mid - wr).length, foot_h=hand_r))
        L['arms'] = arms
        L['wlegs'] = wlegs
        L['hand_r'] = hand_r
        L['arm_r'] = s.get('arm_r', 0.13) * rx
        L.pop('wings', None)
        return L

    def pre_rig(self):
        # `carry`: where a carried thing goes (in the beak, under the jaw tip)
        L = self.L
        jt = L['jaw_tip']
        self.extra_bones.append(('carry', jt - UP * L['snout_r'][2] * 0.2,
                                 jt - UP * L['snout_r'][2] * 0.6, 'jaw'))

    def post_rig(self):
        self.hind = list(self.legs)
        self.wlegs = []
        for w, a in zip(self.L['wlegs'], self.wingarms):
            self.wlegs.append(dict(w, thigh=a['arm'], shin=a['forearm'], foot=a['wing']))
        self.ground_legs = self.hind + self.wlegs
        self.legs = self.ground_legs

    def build_parts(self):
        DL.build_torso(self)
        self.head_parts()
        # the beak: snout and jaw in `horn` colour, a pointy tip
        sn = self.ref['snout']
        sn.data.materials[0] = self.m('horn')
        L = self.L
        snc, snr = L['snout_c'], L['snout_r']
        tipb = snc + FWD * snr[1] * 0.70 + UP * snr[2] * 0.02
        ln = snr[1] * 0.75 * (0.6 if self.age == 'baby' else 1.0)
        self.add(DL.tube('beaktip', self.m('horn'), [tipb, tipb + FWD * ln * 0.55 - UP * ln * 0.04,
                                                     tipb + FWD * ln - UP * ln * 0.12],
                         [snr[0] * 0.55, snr[0] * 0.36, snr[0] * 0.06], seg=self.lod(12, 8),
                         flat=[0.75, 0.7, 0.7], nrm=UP, sub=3, cap='end'), ('rigid', 'head'))
        DL.build_tail(self)
        self.legs = self.hind
        DL.build_legs(self)
        self.legs = self.ground_legs
        self.build_wing_parts()

    def build_wing_parts(self):
        L, s = self.L, self.spec
        tr = L['torso_r']
        ar = L['arm_r']
        for a in self.wingarms:
            side = a['side']
            sh, el, wr, mid, tip = a['sh'], a['el'], a['hand'], a['tip'], a['tip2']
            inner = sh - V((side * ar * 1.2, 0, 0))
            self.add(DL.tube('wingarm', self.m('body'), [inner, sh, el, wr],
                             [ar * 1.4, ar * 1.25, ar * 1.0, ar * 0.85], seg=self.lod(12, 8), sub=3,
                             cap='end'),
                     ('near', ['spine', a['arm'], a['forearm']], 6.0, 2))
            self.add(DL.tube('finger', self.m('body'), [wr, mid, tip], [ar * 0.75, ar * 0.5, ar * 0.16],
                             seg=self.lod(10, 6), sub=3, cap='end'),
                     ('near', [a['wing'], a['wing2']], 6.0, 2))
            self.add(DL.ell('knuckle', self.m('body'), wr, (ar * 0.95, ar * 0.95, ar * 0.9),
                            seg=self.lod(10, 8), rings=6), ('rigid', a['forearm']))
            # three little fingers (the front "toes" on the ground)
            hd = (wr - el).normalized()
            for k in (-1, 0, 1):
                p = wr + hd * ar * 0.5 + FWD * ar * 0.6 + V((side * k * ar * 0.45, 0, -ar * 0.4))
                d = (FWD * 0.9 - UP * 0.4 + V((side * k * 0.3, 0, 0))).normalized()
                self.add(DL.tube('claw', self.m('horn'), [p, p + d * ar * 0.8],
                                 [ar * 0.30, ar * 0.10], seg=6, sub=2, cap='end'), ('rigid', a['forearm']))
            # the membrane: leading edge = arm + finger, trailing edge curves
            # from the tip back to the hip
            lead = catmull([sh + V((-side * ar * 0.3, 0, 0)), el, wr, mid, tip], per=8)
            hip = L['root'] + V((side * tr[0] * 0.55, tr[1] * 0.15, tr[2] * 0.05))
            n = len(lead) - 1
            cd = s.get('chord', 0.9)

            C0 = max(hip.y - sh.y, 0.0) + tr[1] * 0.25
            span = (tip - sh).length

            def fn(u, v, lead=lead, hip=hip, side=side, sh=sh, tip=tip, C0=C0, span=span):
                p = polyline(lead, u)
                # chord: the body length at the root, a broad rounded wing,
                # a gently concave trailing edge out to the tip
                c = cd * (C0 * (1 - u) ** 0.6 + span * 0.20 * math.sin(math.pi * u ** 0.9) * (1 - u) ** 0.35)
                q = p + V((-side * c * 0.08 * u, c, -c * 0.10))
                if u < 0.15:                       # the root edge hugs the flank
                    q = q.lerp(hip + V((0, 0, 0)), (1 - u / 0.15) ** 2 * 0.0)
                m = p.lerp(q, v)
                camber = (q - p).length * 0.08 * math.sin(math.pi * v)
                return m + UP * camber
            th = tr[2] * 0.05

            def thick(u, v):
                return th * (1 - 0.6 * u)

            def mat_of(u, v):
                return 1 if v > 0.80 else 0
            # parameter u of the joints along the leading edge
            lens = [(lead[i + 1] - lead[i]).length for i in range(n)]
            tot = sum(lens)
            acc, ujoint = 0.0, []
            for i in range(n):
                if i % 8 == 0:
                    ujoint.append(acc / tot)
                acc += lens[i]
            ujoint.append(1.0)          # [0, el, wr, mid, 1]
            bones = [a['arm'], a['forearm'], a['wing'], a['wing2']]

            def wfn(u, v, ujoint=ujoint, bones=bones):
                w = {}
                for i, bn in enumerate(bones):
                    a0, a1 = ujoint[i], ujoint[i + 1]
                    pad = 0.06
                    x = min(smooth((u - (a0 - pad)) / (2 * pad)) if i else 1.0,
                            1.0 - smooth((u - (a1 - pad)) / (2 * pad)) if i < 3 else 1.0)
                    if x > 0:
                        w[bn] = x
                tot = sum(w.values()) or 1.0
                for k in w:
                    w[k] /= tot
                # near the body the membrane follows the body
                body = (1.0 - smooth(u / max(ujoint[2], 1e-3))) ** 1.3 * (0.25 + 0.75 * v)
                out = {k: x * (1 - body) for k, x in w.items()}
                out['spine'] = out.get('spine', 0) + body
                return out
            ob, uvs = sheet('membrane', [self.m('belly'), self.m('spots')], fn, self.lod(26, 14),
                            self.lod(8, 5), thick, ref=UP, mat_of=mat_of)
            weigh(ob, uvs, wfn)
            self.add(ob, ('pre',))


def f_ptera_crest(D, length=1.6, height=0.55, thick=0.16, up_deg=28, mat='accent'):
    """The Pteranodon crest: a flat rounded blade sweeping back-up from the
    top of the head (fractions of the head radius)."""
    L = D.L
    hc, hr = L['head_c'], L['head_r']
    k = D.A['crest'] ** 1.6 if D.age != 'adult' else 1.0
    R = sum(hr) / 3
    ln, hh = length * R * k, height * R * k
    base = hc + UP * hr[2] * 0.62 + V((0, hr[1] * 0.05, 0))
    a = math.radians(up_deg)
    d = V((0, math.cos(a), math.sin(a)))
    upn = V((0, -math.sin(a), math.cos(a)))

    def fn(u, v):
        # u along the crest, v across its height (bottom -> top)
        w = hh * (1 - u ** 1.8) * (0.55 + 0.45 * math.sin(math.pi * min(u * 1.4, 1.0)))
        p = base + d * (u * ln) + upn * ((v - 0.35) * w)
        return p - d * hr[1] * 0.35 * (1 - u) ** 3
    ob, uvs = sheet('crest', [D.m(mat)], fn, D.lod(14, 8), D.lod(6, 4),
                    lambda u, v: thick * R * (1 - 0.7 * u), ref=V((1, 0, 0)))
    weigh(ob, uvs, lambda u, v: {'head': 1.0})
    D.add(ob, ('pre',))


# ======================================================================
# feathered birds (archaeo, microraptor)
# ======================================================================

class Bird(AirSeaDino):
    """Biped bird-dino with two wing sets:
      * the flight wing (rest pose = spread): arm/forearm/wing (hand) carry
        rigid feather fans, so nothing stretches when it flaps;
      * the folded wing: a feather leaf on each flank on fold.L/.R ->
        fold2.L/.R, which the ground actions flick (lib Moves.arms()).
    Ground actions scale the flight wing to HIDE (it shrinks into the
    shoulder); fly/glide scale the leaves away instead. A crossfade from
    idle to fly therefore pops the wings open."""
    HIDE = 0.02

    def lay(self, s, A):
        L = DL.Dino._lay_biped(self, s, A)
        Ct, Rt = L['torso_c'], DL._rotm(L['torso_rot_deg'])
        rx, ry, rz = L['torso_r']
        wl = s.get('wing_len', 2.0) * ry * WING_AGE[self.age]
        arms, folds = [], []
        for side in (1, -1):
            # flight wing, spread level and a little swept back
            sh = Ct + Rt @ V((side * rx * 0.72, -ry * 0.38, rz * 0.32))
            el = sh + V((side * wl * 0.27, wl * 0.03, wl * 0.03))
            wr = el + V((side * wl * 0.33, -wl * 0.02, 0))
            tip = wr + V((side * wl * 0.40, wl * 0.10, -wl * 0.01))
            arms.append(dict(tag='L' if side > 0 else 'R', side=side, sh=sh, el=el, hand=wr, tip=tip))
            # folded leaf on the flank (torso-local frame)
            f0 = Ct + Rt @ V((side * rx * 0.80, -ry * 0.45, rz * 0.30))
            f1 = Ct + Rt @ V((side * rx * 0.92, ry * 0.30, rz * 0.02))
            f2 = Ct + Rt @ V((side * rx * 0.55, ry * 1.12, -rz * 0.10))
            folds.append(dict(side=side, a=f0, b=f1, c=f2))
        L['arms'] = arms
        L['folds'] = folds
        L['arm_r'] = s.get('arm_r', 0.14) * rx
        L['wl'] = wl
        return L

    def pre_rig(self):
        for f in self.L['folds']:
            sd = '.L' if f['side'] > 0 else '.R'
            self.extra_bones.append(('fold' + sd, f['a'], f['b'], 'spine'))
            self.extra_bones.append(('fold2' + sd, f['b'], f['c'], 'fold' + sd))

    def post_rig(self):
        self.folds = []
        for f in self.L['folds']:
            sd = '.L' if f['side'] > 0 else '.R'
            self.folds.append(dict(f, arm='fold' + sd, forearm='fold2' + sd, el=f['b'], hand=f['c']))
        self.arms = self.folds          # the lib's Moves.arms() flick the folded leaves
        self.ground_legs = list(self.legs)
        self.hind = self.ground_legs

    def hide(self, P, flying):
        h = (self.HIDE,) * 3
        for a in (self.folds if flying else self.wingarms):
            P.sc(a['arm'], h)
        return P

    def build_parts(self):
        DL.build_torso(self)
        self.head_parts()
        DL.build_tail(self)
        DL.build_legs(self)
        self.build_wing_parts()
        self.build_fold_parts()
        self.build_tail_feathers()

    def fan(self, name, a, b, fdir, chord, lobes, bone, nrm, u0=-0.12, u1=1.08,
            tips=True, nu=10, nv=4, thick=None):
        """Rigid feather fan hanging from segment a->b; fdir(u) = feather
        direction, chord(u) its length, scalloped trailing edge."""
        d = (b - a)
        tk = thick if thick is not None else chord(0.5) * 0.10

        def fn(u, v):
            uu = lerp(u0, u1, u)
            c = chord(u) * (0.84 + 0.16 * math.sin(math.pi * lobes * u) ** 2)
            return a + d * uu + fdir(u) * (c * v) - nrm * (c * 0.10 * math.sin(math.pi * v))
        ob, uvs = sheet(name, [self.m('accent'), self.m('spots')], fn, self.lod(nu, 6), nv,
                        lambda u, v: tk * (1 - 0.5 * v), ref=nrm,
                        mat_of=(lambda u, v: 1 if v > 0.72 else 0) if tips else None)
        weigh(ob, uvs, lambda u, v: {bone: 1.0})
        return self.add(ob, ('pre',))

    def build_wing_parts(self):
        L = self.L
        ar = L['arm_r']
        tr = L['torso_r']
        dep = tr[2] * self.spec.get('wing_chord', 1.0)
        for a in self.wingarms:
            sd = a['side']
            sh, el, wr, tip = a['sh'], a['el'], a['hand'], a['tip']
            back = V((0, 1, -0.06)).normalized()
            self.add(DL.tube('arm', self.m('body'), [sh - V((sd * ar, 0, 0)), sh, el, wr],
                             [ar * 1.2, ar * 1.15, ar * 0.95, ar * 0.8], seg=self.lod(10, 6), sub=2),
                     ('near', [a['arm'], a['forearm']], 6.0, 2))
            self.fan('coverts', sh, el, lambda u: back, lambda u: dep * (0.62 + 0.25 * u), 2, a['arm'], UP,
                     tips=False, u0=-0.2, u1=1.1)
            self.fan('secondaries', el, wr, lambda u: back, lambda u: dep * (1.0 + 0.15 * u), 3,
                     a['forearm'], UP, u0=-0.08)
            # primaries fan out towards the tip
            self.fan('primaries', wr, tip,
                     lambda u, sd=sd: (back + V((sd * 1.1 * u ** 1.2, 0, 0))).normalized(),
                     lambda u: dep * (1.15 - 0.25 * u), 4, a['wing'], UP, u0=-0.06, u1=1.0)
            for k in (-1, 1):
                p = wr + V((sd * ar * 0.3 * k, -ar * 0.6, 0))
                dd = V((sd * 0.3, -0.9, -0.3)).normalized()
                self.add(DL.tube('claw', self.m('horn'), [p, p + dd * ar * 1.1],
                                 [ar * 0.30, ar * 0.08], seg=6, sub=2, cap='end'), ('rigid', a['forearm']))

    def build_fold_parts(self):
        """The folded wing: a feather leaf hugging the flank (tips band)."""
        L = self.L
        tr = L['torso_r']
        Ct, Rt = L['torso_c'], DL._rotm(L['torso_rot_deg'])
        rx, ry, rz = tr
        W = rz * self.spec.get('fold_w', 1.05)
        for f in self.folds:
            sd = f['side']

            def fn(u, v, sd=sd):
                y = lerp(-0.50, 1.18, u) * ry
                w = W * math.sin(math.pi * min(1.0, 0.12 + u * 0.95)) ** 0.7 * (1.0 - 0.15 * u)
                ztop = rz * lerp(0.42, 0.05, u ** 1.3)
                z = ztop - w * v
                q = 1.0 - (y / (ry * 1.04)) ** 2 - (z / (rz * 1.04)) ** 2
                x = rx * math.sqrt(max(q, 0.0)) + rx * 0.06 + rx * 0.10 * math.sin(math.pi * v) * (1 - u)
                x = max(x, rx * 0.28)
                return Ct + Rt @ V((sd * x, y, z))
            nrm = Rt @ V((sd, 0, 0))

            def mat_of(u, v):
                return 1 if (v > 0.70 or u > 0.86) else 0
            ob, uvs = sheet('fold', [self.m('accent'), self.m('spots')], fn, self.lod(14, 8), 5,
                            lambda u, v: rx * 0.07 * (1 - 0.6 * v), ref=nrm, mat_of=mat_of)
            weigh(ob, uvs, lambda u, v, f=f: {f['arm']: 1.0 - smooth((u - 0.35) / 0.4),
                                             f['forearm']: smooth((u - 0.35) / 0.4)})
            self.add(ob, ('pre',))

    def build_tail_feathers(self):
        pass


class Archaeo(Bird):
    def build_tail_feathers(self):
        """Archaeopteryx: a feather vane along both sides of the long tail."""
        L, s = self.L, self.spec
        pts = catmull(L['tail_pts'], per=6)
        tr = L['tail_r']
        W = tr * s.get('tail_vane', 2.2) * (0.85 if self.age == 'baby' else 1.0)

        def fn(u, v):
            uu = lerp(0.18, 1.12, u)
            p = polyline(pts, uu)
            w = W * (0.35 + 0.65 * u ** 0.7) * (1 - u ** 6) ** 0.5 * \
                (0.9 + 0.1 * abs(math.sin(math.pi * 4 * u)))
            return p + V((w * (2 * v - 1), 0, 0)) + UP * tr * 0.25
        ob, uvs = sheet('tailvane', [self.m('accent'), self.m('spots')], fn, self.lod(16, 10),
                        self.lod(6, 4), lambda u, v: tr * 0.22 * (1 - 0.5 * u), ref=UP,
                        mat_of=lambda u, v: 1 if (abs(2 * v - 1) > 0.66 or u > 0.88) else 0)
        segs = [(L['tail_pts'][i], L['tail_pts'][i + 1]) for i in range(len(self.tail))]
        tot = sum((b - a).length for a, b in segs)

        def wfn(u, v):
            uu = lerp(0.18, 1.12, u) * tot
            w = {}
            acc = 0.0
            for i, (a, b) in enumerate(segs):
                ln = (b - a).length
                c = acc + ln * 0.5
                w[self.tail[i]] = max(0.0, 1.0 - abs(uu - c) / ln) ** 1.5
                acc += ln
            if sum(w.values()) < 1e-6:
                w[self.tail[-1]] = 1.0
            return w
        weigh(ob, uvs, wfn)
        self.add(ob, ('pre',))


class Micro(Bird):
    def build_tail_feathers(self):
        """Microraptor: a rhombus fan at the tail tip + leg feathers."""
        L, s = self.L, self.spec
        pts = catmull(L['tail_pts'], per=6)
        tr = L['tail_r']
        W = tr * s.get('tail_vane', 2.6)

        def fn(u, v):
            uu = lerp(0.52, 1.25, u)
            p = polyline(pts, uu)
            w = W * math.sin(math.pi * min(1.0, u * 1.05)) ** 0.75 * (1.0 - 0.25 * u)
            w = max(w, 1e-4)
            return p + V((w * (2 * v - 1), 0, 0)) + UP * tr * 0.2
        ob, uvs = sheet('tailfan', [self.m('accent'), self.m('spots')], fn, self.lod(12, 8),
                        self.lod(6, 4), lambda u, v: tr * 0.2, ref=UP,
                        mat_of=lambda u, v: 1 if u > 0.62 else 0)
        weigh(ob, uvs, lambda u, v: {self.tail[-1]: 0.3 + 0.7 * u, self.tail[-2]: 0.7 * (1 - u)})
        self.add(ob, ('pre',))
        # hind-leg feathers: fans hanging back from the shins
        for lg in self.legs:
            kn, an = lg['knee'], lg['ankle']
            out = V((lg['side'], 0, 0))
            f = V((lg['side'] * 0.25, 1.0, -0.15)).normalized()
            dep = (an - kn).length * s.get('leg_feather', 0.85)
            self.fan('legfeather', kn + (an - kn) * 0.05, an, lambda u, f=f: f,
                     lambda u, dep=dep: dep * (0.65 + 0.45 * u), 3, lg['shin'], out,
                     u0=0.0, u1=1.0, nu=8, nv=3)


# ======================================================================
# Plesiosaurus
# ======================================================================

class Plesio(AirSeaDino):

    def lay(self, s, A):
        L = {}
        rx, ry, rz = DL._roundify(s['torso'], A['round'] * 0.6)
        L['torso_r'] = (rx, ry, rz)
        Ct = V((0, 0, rz * s.get('float', 0.12)))      # the water line is z = 0 (nominal)
        L['torso_c'], L['torso_rot_deg'] = Ct, (0.0, 0.0, 0.0)

        def tp(x, y, z):
            return Ct + V((x, y, z))
        root = tp(0, ry * 0.30, -rz * 0.05)
        chest = tp(0, -ry * 0.72, rz * 0.30)
        L['root'], L['chest'] = root, chest
        lr = s['leg_r'] * rz
        L['leg_r'] = lr
        legs = []
        for front in (False, True):
            for side in (1, -1):
                yy = -ry * 0.42 if front else ry * 0.45
                fl = s['flipper'] * rx * (1.0 if front else 0.78) * (0.92 if self.age == 'baby' else 1.0)
                hip = tp(side * rx * 0.78, yy, -rz * 0.30)
                d = V((side * 0.88, 0.40 if front else 0.55, -0.12)).normalized()
                knee = hip + d * fl * 0.36
                d2 = V((side * 0.78, 0.60 if front else 0.75, -0.10)).normalized()
                ank = knee + d2 * fl * 0.34
                d3 = V((side * 0.55, 0.82 if front else 0.88, -0.06)).normalized()
                toe = ank + d3 * fl * 0.30
                legs.append(dict(tag=('f' if front else '') + ('L' if side > 0 else 'R'), front=front,
                                 side=side, hip=hip, knee=knee, ankle=ank, toe=toe, foot_h=lr * 0.5))
        L['legs'] = legs
        # the neck: an S rising out of the water (elevation profile)
        nl = s['neck_len'] * A['neck']
        n = s.get('neck_n', 5)
        prof = s.get('neck_prof', [(0.0, 28), (0.35, 70), (0.72, 96), (1.0, 66)])
        steps = n * 12
        p = chest.copy()
        pts = [p.copy()]
        for i in range(steps):
            a = math.radians(tl((i + 0.5) / steps, prof))
            p = p + V((0, -math.cos(a), math.sin(a))) * (nl / steps)
            if (i + 1) % 12 == 0:
                pts.append(p.copy())
        L['neck_pts'] = pts
        L['neck_r'] = s.get('neck_r', 0.42) * min(rx, rz) * A.get('neck_thick', 1.0)
        self._head_common(L, s, A, pts[-1])
        t = s['tail']
        tb = tp(0, ry * 0.80, -rz * 0.02)
        L['tail_pts'] = DL._arc(tb, -t.get('droop_deg', 8), -t.get('droop2_deg', 0),
                                t['len'] * A['tail'], t.get('n', 3), back=True)
        L['tail_r'] = t['r'] * rz * (0.85 + 0.15 * A['tail'])
        L['ref_z'] = 0.0                  # height counts from the water line
        L['shift_z'] = 0.0
        return L

    def layout(self):
        L = AirSeaDino.layout(self)
        L = _shift(L, V((0, 0, WATER_Z)))
        self.L = L
        return L

    def post_rig(self):
        self.flippers = list(self.legs)
        self.ground_legs = self.flippers     # (only for the lib's Moves bookkeeping;
        #                                      the actions run with no IK legs)

    def build_parts(self):
        s = self.spec
        DL.build_torso(self)
        self.head_parts()
        self.throat()
        DL.build_tail(self)
        L = self.L
        lr = L['leg_r']
        for lg in self.flippers:
            hip, knee, ank, toe = lg['hip'], lg['knee'], lg['ankle'], lg['toe']
            w = lr * (1.0 if lg['front'] else 0.85)
            inner = hip - (knee - hip).normalized() * w * 0.8
            tipx = toe + (toe - ank).normalized() * w * 0.15
            pts = [inner, hip, knee, ank, tipx]
            rad = [w * 0.85, w * 1.05, w * 1.25, w * 0.95, w * 0.22]
            ob = DL.tube('flipper', self.m('body'), pts, rad, seg=self.lod(14, 10),
                         flat=[0.5, 0.36, 0.28, 0.26, 0.4], nrm=UP, sub=3, cap='end')
            self.add(ob, ('near', ['root' if not lg['front'] else 'spine', lg['thigh'], lg['shin'],
                                   lg['foot']], 5.0, 2))
            # a pale edge on the flipper tip
            self.add(DL.ell('fliptip', self.m('belly'), ank + (toe - ank) * 0.62,
                            (w * 0.55, (toe - ank).length * 0.42, w * 0.22),
                            rot=V((0, 1, 0)).rotation_difference((toe - ank).normalized()),
                            seg=self.lod(10, 8), rings=6), ('rigid', lg['foot']))
        del s

    def head_parts(self):
        self.neck_tube()
        DL.build_head(self)
        DL.build_eyes(self)

    def neck_tube(self):
        """DL.build_neck with the ring frame on X: the S-neck passes the
        vertical, where an UP-framed tube flips and pinches."""
        L, s = self.L, self.spec
        pts = list(L['neck_pts'])
        nr = L['neck_r']
        d0 = (pts[1] - pts[0]).normalized()
        inner = pts[0] - d0 * nr * 0.9
        end = L['head_base'] + (L['head_c'] - L['head_base']) * 0.5
        P = [inner] + pts + [end]
        n = len(P)
        taper = s.get('neck_taper', 0.82)
        R = [nr * lerp(1.15, taper, i / (n - 1)) for i in range(n)]
        bones = ['spine'] + self.neck + ['head']
        self.add(DL.tube('neck', self.m('body'), P, R, seg=self.lod(16), cap=False, sub=3,
                         nrm=V((1, 0, 0))), ('near', bones, 4.0, 2))

    def throat(self):
        """Cream stripe down the front of the S-neck (offset in the neck's
        own plane, so it never pokes out on the bends)."""
        L = self.L
        pts = catmull(L['neck_pts'] + [L['head_base'] + (L['head_c'] - L['head_base']) * 0.3], per=3)
        nr = L['neck_r']
        n = len(pts)
        taper = self.spec.get('neck_taper', 0.82)
        Q, R = [], []
        for i, p in enumerate(pts):
            j0, j1 = max(i - 1, 0), min(i + 1, n - 1)
            t = (pts[j1] - pts[j0]).normalized()
            fr = V((0, -t.z, t.y)).normalized()
            r = nr * lerp(1.15, taper, i / (n - 1))
            Q.append(p + fr * r * 0.45)
            R.append(r * 0.62)
        Q, R = Q[1:-1], R[1:-1]
        bones = ['spine'] + self.neck + ['head']
        self.add(DL.tube('throat', self.m('belly'), Q, R, seg=self.lod(12, 8), sub=2, nrm=V((1, 0, 0))),
                 ('near', bones, 4.0, 2))


# ======================================================================
# moves
# ======================================================================

def _cache_moves(D, cls):
    m = getattr(D, '_asmoves', None)
    if m is None or not isinstance(m, cls):
        m = cls(D)
        D._asmoves = m
    return m


def _anim(cls, name, legs='ground'):
    def fn(M):
        D = M.D
        mv = _cache_moves(D, cls)
        D.legs = D.ground_legs if legs == 'ground' else []
        T, g = getattr(mv, name)()
        if isinstance(D, Bird):
            flying = legs != 'ground'
            return T, (lambda t: D.hide(g(t), flying))
        return T, g
    return fn


class FlyMixin:
    """Shared flight helpers (body level, legs tucked, head forward)."""

    def tilt(self):
        return -self.D.L['torso_rot_deg'][0]

    def flight_body(self, P, t, pitch_extra=0.0, roll=0.0):
        D = self.D
        til = self.tilt()
        P.r('root', til + pitch_extra, 0, roll)
        nk = D.neck
        # stretch the neck forward and keep the head level
        P.r(nk[0], self.mv.get('fly_neck', 18), 0, 0)
        for b in nk[1:]:
            P.r(b, self.mv.get('fly_neck2', 6), 0, 0)
        tot = til + pitch_extra + self.mv.get('fly_neck', 18) + self.mv.get('fly_neck2', 6) * (len(nk) - 1)
        P.r('head', -tot + 4, 0, -roll * 0.6)
        # legs trail back
        for lg in self.D.legs_all if hasattr(self.D, 'legs_all') else self.D.hind:
            P.r(lg['thigh'], self.mv.get('fly_thigh', 55), 0, 0)
            P.r(lg['shin'], self.mv.get('fly_shin', 25), 0, 0)
            P.r(lg['foot'], self.mv.get('fly_foot', 45), 0, 0)
        # the body pitched forward by `til`: bring the tail back to level
        n = len(D.tail)
        for i, b in enumerate(D.tail):
            P.r(b, (til + pitch_extra) / n - self.mv.get('fly_tail', 6) / n, 0, 0)
        return P


class PteraMoves(FlyMixin, DL.Moves):
    def __init__(self, D):
        D.legs = D.ground_legs
        DL.Moves.__init__(self, D)
        self.biped = False

    def base(self, t, T, breath=2, amp=1.0):
        P = DL.Moves.base(self, t, T, breath, amp)
        return P

    def fly(self):
        D = self.D
        T = {'baby': 0.5, 'juv': 0.63, 'adult': 0.77}[D.age]
        v = D.spec['fly_speed'][D.age]
        D.speeds['fly'] = (v, T)
        H = self.H

        def g(t):
            P = Pose()
            u = t / T
            # downstroke 0..0.45 (fast), upstroke 0.45..1
            ph = TAU * u
            flap = 34 * math.cos(ph) + 6            # + = up
            lag = 34 * math.cos(ph - 0.9) + 4
            P.at('root', (0, 0, H * 0.035 * math.sin(ph - 0.4) + H * 0.02))
            self.flight_body(P, t, pitch_extra=-3 + 2 * math.sin(ph))
            for a in D.wingarms:
                sd = a['side']
                P.r(a['arm'], -self.tilt() + 2 - 3 * math.sin(ph), -sd * 6 * math.sin(ph), -sd * flap)
                P.r(a['forearm'], 0, sd * 8 * max(0, -math.sin(ph)), -sd * 0.25 * (lag - flap))
                P.r(a['wing'], 0, -sd * 6 * max(0, -math.sin(ph)), -sd * 0.35 * (lag - flap) - sd * 4)
                P.r(a['wing2'], 0, 0, -sd * 0.4 * (lag - flap))
            P.lid = self.blink(t, T * 0.5) if T > 0.6 else 0.0
            P.jaw = 2
            return P
        return T, g

    def glide(self):
        D = self.D
        T = 3.0
        v = D.spec['fly_speed'][D.age] * 1.18
        D.speeds['glide'] = (v, T)
        H = self.H

        def g(t):
            P = Pose()
            bank = 7 * math.sin(TAU * t / T)
            P.at('root', (0, 0, H * 0.025 * math.sin(TAU * t / T * 2) + H * 0.02))
            self.flight_body(P, t, pitch_extra=-2 + 1.5 * math.sin(TAU * t / T * 2), roll=bank)
            for a in D.wingarms:
                sd = a['side']
                dih = 5 + 2.5 * math.sin(TAU * t / T * 2 + sd)
                P.r(a['arm'], -self.tilt() + 2, 0, -sd * dih)
                P.r(a['forearm'], 0, 0, sd * 2)
                P.r(a['wing'], 0, 0, -sd * (2 + 2 * math.sin(TAU * t / T * 3 + 0.5)))
                P.r(a['wing2'], 0, 0, -sd * (3 + 2 * math.sin(TAU * t / T * 3)))
            look = 14 * math.sin(TAU * t / T)
            P.r('head', 0, look, 0)
            P.lid = self.blink(t, 1.2, 2.4)
            P.jaw = 2
            return P
        return T, g


class BirdMoves(FlyMixin, DL.Moves):
    def __init__(self, D):
        D.legs = D.ground_legs
        DL.Moves.__init__(self, D)

    def arms(self, P, p=0.0, y=0.0, r=0.0, fp=0.0, post=False):
        """The lib's arm gestures, mapped onto the folded leaves: 'raise'
        lifts the leaf tips, 'out' flares the lower edge away."""
        for f in self.D.folds:
            sd = f['side']
            P.r(f['arm'], 0.35 * p, -sd * 0.3 * y, -sd * 0.9 * r, post=post)
            P.r(f['forearm'], 0.3 * fp, 0, -sd * 0.2 * r, post=post)

    def fly(self, glide=False):
        D = self.D
        sp = D.spec['fly_speed'][D.age]
        if glide:
            T = 3.0
            D.speeds['glide'] = (sp * 1.25, T)
        else:
            T = {'baby': 0.2, 'juv': 0.23, 'adult': 0.27}[D.age]
            D.speeds['fly'] = (sp, T)
        H = self.H
        til = self.tilt()

        def g(t):
            P = Pose()
            u = t / T
            ph = TAU * u
            if glide:
                flap = 7 + 2.5 * math.sin(TAU * t / T * 2)
                roll = 8 * math.sin(TAU * t / T)
                pe = -4 + 1.5 * math.sin(TAU * t / T * 2)
                P.at('root', (0, 0, H * 0.03 * math.sin(TAU * t / T * 2) + H * 0.04))
            else:
                flap = 40 * math.cos(ph) + 6
                roll = 0.0
                pe = -6 + 3 * math.sin(ph)
                P.at('root', (0, 0, H * 0.05 * math.sin(ph - 0.5) + H * 0.04))
            self.flight_body(P, t, pitch_extra=pe, roll=roll)
            for a in D.wingarms:
                sd = a['side']
                P.r(a['arm'], -(til + pe) + 3, -sd * (0 if glide else 6 * math.sin(ph)), -sd * flap)
                if not glide:
                    tuck = max(0.0, math.sin(ph))          # fold the hand a little on the upstroke
                    P.r(a['forearm'], 0, sd * 4 * tuck, -sd * 9 * math.cos(ph - 0.8))
                    P.r(a['wing'], 0, -sd * 10 * tuck, -sd * 12 * math.cos(ph - 1.3))
                else:
                    P.r(a['wing'], 0, 0, -sd * (3 + 2 * math.sin(TAU * t / T * 3)))
            if glide and D.spec.get('four_wings'):
                for lg in D.legs:
                    sd = lg['side']
                    P.r(lg['thigh'], 18, -sd * 22, -sd * 8)
                    P.r(lg['shin'], 6, 0, 0)
            look = 10 * math.sin(TAU * t / 3.0) if glide else 0
            P.r('head', 0, look, 0)
            if not glide:
                self.spread(P, D.tail, 3 * math.sin(ph - 1.5))
            else:
                self.tail(P, t, T, yaw=4, pitch=2, lag=0.4)
            P.lid = self.blink(t, 1.3, 2.5) if glide else 0.0
            P.jaw = 3
            return P
        return T, g

    def glide(self):
        return self.fly(glide=True)

    def call(self):
        """Archaeopteryx sings: head up, beak trills three notes, wings lift."""
        if not self.D.spec.get('singer'):
            return DL.Moves.call(self)
        T = 1.0
        D = self.D

        def g(t):
            P = self.base(t, T, breath=1, amp=0.3)
            up = env(t, 0.0, 0.18, 0.82, 1.0)
            notes = 0.0
            for t0, a in ((0.2, 1.0), (0.42, 0.7), (0.6, 1.0), (0.74, 0.8)):
                notes = max(notes, a * env(t, t0, t0 + 0.04, t0 + 0.08, t0 + 0.14))
            self.spread(P, D.neck, -16 * up)
            P.r('head', -14 * up - 6 * notes, 0, 10 * math.sin(TAU * t * 1.0) * up)
            P.r('root', -4 * up, 0, 0)
            P.sc('root', (1 + 0.05 * up, 1, 1 + 0.06 * up))       # puffed chest
            P.jaw = 6 * up + 26 * notes
            P.lid = 0.55 * up
            self.arms(P, -10 * up, 0, 18 * up)
            self.tail(P, t, 0.25, yaw=8 * up, lag=0.5)
            self.spread(P, D.tail, -8 * up)
            return P
        return T, g


class PlesioMoves(DL.Moves):
    """Every action is a swim version. Flippers are posed by hand."""

    def __init__(self, D):
        self.D = D
        L = D.L
        self.H = D.spec['height'] * D.A['height']
        self.legl = L['torso_r'][2]
        self.biped = False
        self.mv = dict(D.spec.get('moves', {}))
        self.mouth = L['mouth']
        self.front_y = L['mouth'].y
        self.root_z = L['root'].z
        self.baby = D.age == 'baby'

    def chain(self):
        D = self.D
        return [('root', 6.0, 0.25), ('spine', 8.0, 0.3)] + \
            [(b, 26.0, 0.55) for b in D.neck] + [('head', 50.0, 0.7)]

    def float_(self, P, t, T, amp=1.0, k=1):
        """Bobbing on the water: up/down, gentle roll and pitch."""
        H = self.H
        P.at('root', (0, 0, H * 0.012 * amp * math.sin(TAU * t / T * k)))
        P.r('root', 1.2 * amp * math.sin(TAU * t / T * k + 1.0), 0, 1.6 * amp * math.sin(TAU * t / T))
        br = wave(t, T / (2 * k))
        a = 0.01 * amp
        P.sc('root', (1 + a * br, 1 + a * 0.5 * br, 1 - a * 0.6 * br))
        return P

    def paddle(self, P, t, T, amp=1.0, front_ph=0.0, hind_ph=math.pi, scull=False):
        """Rowing strokes: sweep back with the blade flat (power), return
        feathered; front and hind pairs in counter-phase."""
        for lg in self.D.flippers:
            sd = lg['side']
            ph = TAU * t / T + (front_ph if lg['front'] else hind_ph)
            if scull:
                sw = 8 * amp * math.sin(ph)
                ud = 5 * amp * math.sin(ph + 1.2)
                tw = 12 * amp * math.cos(ph)
            else:
                sw = 26 * amp * math.sin(ph)              # + = sweep back
                ud = 12 * amp * math.cos(ph)              # + = up
                tw = 24 * amp * math.cos(ph)
            P.r(lg['thigh'], tw * 0.4, sd * sw * 0.6, -sd * ud * 0.6)
            P.r(lg['shin'], tw * 0.3, sd * sw * 0.25, -sd * ud * 0.25)
            P.r(lg['foot'], tw * 0.3, sd * sw * 0.2 * math.sin(ph - 0.6), -sd * ud * 0.35)
        return P

    def neck_sway(self, P, t, T, yaw=6.0, pitch=2.0, k=1, phase=0.0):
        D = self.D
        n = len(D.neck)
        for i, b in enumerate(D.neck):
            g = 1.0 - 0.4 * i / max(n - 1, 1)
            P.r(b, pitch * g * math.sin(TAU * t / T * k + phase - 0.5 * i),
                yaw * g * math.sin(TAU * t / T * k + phase - 0.6 * i), 0)
        # the head stays calm (counter the chain a little)
        P.r('head', -pitch * 0.8 * math.sin(TAU * t / T * k + phase - 0.5 * n),
            -yaw * 0.9 * math.sin(TAU * t / T * k + phase - 0.6 * n), 0)

    # loops ------------------------------------------------------------
    def idle(self):
        T = 3.0

        def g(t):
            P = self.float_(Pose(), t, T)
            look = tl(t, [(0, 0), (0.5, 0), (0.95, 20), (1.6, 20), (2.05, -14), (2.45, -14), (2.9, 0), (3.0, 0)])
            tilt = tl(t, [(0, 0), (0.6, 0), (1.0, 9), (1.55, 9), (2.0, -5), (2.5, -5), (2.9, 0), (3.0, 0)])
            self.neck_sway(P, t, T, yaw=4, pitch=2.5)
            self.spread(P, self.D.neck, 0, look * 0.4)
            P.r('head', 0, look * 0.6, tilt)
            self.paddle(P, t, T / 2, amp=0.8, scull=True)
            self.tail(P, t, T, yaw=10, pitch=2, lag=0.6)
            P.lid = self.blink(t, 1.1, 2.55)
            P.jaw = 2.0 + 1.5 * wave(t, T / 2)
            return P
        return T, g

    def swim(self, kind):
        D = self.D
        v = D.spec['speeds'][D.age][0 if kind == 'walk' else 1]
        T = {'walk': {'baby': 1.2, 'juv': 1.4, 'adult': 1.6},
             'run': {'baby': 0.8, 'juv': 0.9, 'adult': 1.0}}[kind][D.age]
        D.speeds[kind] = (v, T)
        fast = kind == 'run'

        def g(t):
            P = Pose()
            u = t / T
            H = self.H
            P.at('root', (0, 0, H * (0.012 if not fast else 0.02) * math.sin(TAU * u * 2 + 0.6) -
                          (H * 0.02 if fast else 0)))
            P.r('root', (1.5 if not fast else 4.0) + 1.2 * math.sin(TAU * u * 2), 0,
                2.0 * math.sin(TAU * u))
            self.paddle(P, t, T, amp=1.0 if not fast else 1.25)
            # the neck leans forward when fast, sways a little
            lean = 10 if fast else 3
            self.spread(P, D.neck, lean * 1.6)
            P.r('head', -lean * 1.4, 0, 0)
            self.neck_sway(P, t, T, yaw=5 if not fast else 3, pitch=2, k=1)
            self.tail(P, t, T, yaw=12 if not fast else 16, pitch=3, lag=0.7)
            P.lid = self.blink(t, T * 0.6) if not fast else 0.0
            P.jaw = 2.0 if not fast else 5.0
            return P
        return T, g

    def walk(self):
        return self.swim('walk')

    def run(self):
        return self.swim('run')

    def _reach_water(self, z_above, fwd):
        L = self.D.L
        return V((0, self.mouth.y - self.H * fwd, WATER_Z + z_above + L['snout_r'][2] * 0.2))

    ARCH = (14, 10, 20, 30, 30)          # neck pitch shape of a swan-like dip (5 bones)

    def _neck_shape(self, shape):
        n = len(self.D.neck)
        if n == len(shape):
            return shape
        return [shape[min(int(i * len(shape) / n), len(shape) - 1)] for i in range(n)]

    def arch_k(self, z_target, build):
        """Smallest k for which pose build(P, k) puts the mouth at z_target
        (scan then bisect on the real FK)."""
        D = self.D

        def mz(k):
            P = Pose()
            build(P, k)
            B = DL._solve(D, P)
            W = D.R.fk(B)
            return D.R.world_point(W, 'head', D.L['mouth']).z
        prev = 0.0
        k = 0.0
        best = (mz(0.0), 0.0)
        while k < 2.2:
            k += 0.05
            z = mz(k)
            best = min(best, (z, k))
            if z <= z_target:
                lo, hi = prev, k
                for _ in range(20):
                    m = 0.5 * (lo + hi)
                    if mz(m) > z_target:
                        lo = m
                    else:
                        hi = m
                return 0.5 * (lo + hi)
            prev = k
        return best[1]

    def dip(self, z_above, head=16, shape=None):
        shp = self._neck_shape(shape or self.ARCH)
        D = self.D

        def build(P, k, w=1.0):
            for b, a in zip(D.neck, shp):
                P.r(b, a * k * w)
            P.r('head', head * k * w)
        k = self.arch_k(WATER_Z + z_above + D.L['snout_r'][2] * 0.3, build)
        return lambda P, w: build(P, k, w)

    def eat(self):
        T = 1.5
        dip = self.dip(0.03)

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.5)
            w = tl(t, [(0, 0), (0.38, 1), (1.18, 1), (1.5, 0)])
            dip(P, w)
            ch = 0.0
            for t0 in (0.42, 0.68, 0.94):
                ch = max(ch, env(t, t0, t0 + 0.07, t0 + 0.1, t0 + 0.22))
            P.jaw = 26 * ch
            P.r('head', -8 * ch, 0, 4 * math.sin(TAU * t / 0.52))
            self.paddle(P, t, 0.75, amp=0.5, scull=True)
            self.tail(P, t, 0.5, yaw=10 * w, lag=0.7)
            P.lid = env(t, 0.42, 0.5, 1.1, 1.2)
            return P
        return T, g

    def drink(self):
        T = 1.5
        dip = self.dip(-0.02, head=22)

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.5)
            w = tl(t, [(0, 0), (0.4, 1), (1.15, 1), (1.5, 0)])
            dip(P, w)
            lap = env(t, 0.42, 0.5, 1.05, 1.15) * (0.5 + 0.5 * math.sin(TAU * (t - 0.42) / 0.16))
            P.jaw = 12 * lap
            P.r('head', 4 * lap, 0, 0)
            P.lid = env(t, 0.42, 0.5, 1.08, 1.18)
            self.paddle(P, t, 0.75, amp=0.4, scull=True)
            self.tail(P, t, 0.75, yaw=6 * w, lag=0.7)
            return P
        return T, g

    def sleep(self):
        """Floats with the neck curled round to one side, chin resting on
        the water by its flank."""
        T = 3.0
        D = self.D
        yaw = self._neck_shape((12, 24, 32, 32, 26))
        shp = self._neck_shape((14, 14, 20, 26, 24))

        def build(P, k):
            for b, a, y in zip(D.neck, shp, yaw):
                P.r(b, a * k, y, 0)
            P.r('head', 10 * k, 24, 16)
        k = self.arch_k(WATER_Z + D.L['snout_r'][2] * 0.4, build)

        def g(t):
            P = Pose()
            br = wave(t, T)
            P.at('root', (0, 0, -self.H * 0.02 + self.H * 0.006 * br))
            P.sc('root', (1 + 0.02 * br, 1 + 0.01 * br, 1 - 0.012 * br))
            P.r('root', 0, 0, 1.0 * math.sin(TAU * t / T))
            build(P, k)
            for lg in D.flippers:
                P.r(lg['thigh'], 0, lg['side'] * 10, lg['side'] * 4)
            self.paddle(P, t, T, amp=0.25, scull=True)
            for i, b in enumerate(D.tail):
                P.r(b, 0, -10 - 4 * i, 0)
            self.tail(P, t, T, yaw=2, lag=0.5)
            P.lid = 1.0
            P.jaw = 1.0 + 1.5 * (0.5 + 0.5 * br)
            return P
        return T, g

    def sit(self):
        """Resting afloat: neck tall and proud, flippers still, dozy blinks."""
        T = 2.0
        D = self.D

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.6)
            self.spread(P, D.neck, -6)
            P.r('head', 4, 6 * wave(t, T), 6 * wave(t, T, 0.6))
            for lg in D.flippers:
                P.r(lg['thigh'], 0, lg['side'] * (8 if lg['front'] else 4), -lg['side'] * 4)
            self.paddle(P, t, T, amp=0.4, scull=True)
            self.tail(P, t, T, yaw=8, lag=0.6)
            P.lid = 0.25 + 0.75 * self.blink(t, 1.3)
            P.jaw = 2.0
            return P
        return T, g

    def sad(self):
        """Neck drooping in a low arch, chin just above the water."""
        T = 3.0
        D = self.D
        dip = self.dip(0.12, head=26, shape=(10, 8, 20, 30, 30))

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.4)
            P.at('root', (0, 0, -self.H * 0.03))
            sigh = env(t, 1.0, 1.5, 1.7, 2.4)
            dip(P, 0.92 + 0.08 * sigh)
            P.r('head', 3 * wave(t, T), 0, 8)
            P.sc('root', (1 + 0.02 * sigh, 1, 1 + 0.02 * sigh))
            self.paddle(P, t, T, amp=0.3, scull=True)
            for lg in D.flippers:
                P.r(lg['thigh'], 0, 0, lg['side'] * 8)
            self.tail(P, t, T, yaw=4, lag=0.4)
            P.lid = 0.45 + 0.1 * sigh
            return P
        return T, g

    # one-shots --------------------------------------------------------
    def happy(self):
        T = 1.0
        D = self.D

        def g(t):
            P = Pose()
            up = 0.0
            if 0.15 <= t <= 0.6:
                u = (t - 0.15) / 0.45
                up = 4 * u * (1 - u)
            P.at('root', (0, 0, self.H * 0.07 * up - self.H * 0.02 * env(t, 0.0, 0.1, 0.12, 0.2)))
            P.r('root', -5 * up, 0, 0)
            wig = 12 * math.sin(TAU * t * 3) * env(t, 0.05, 0.2, 0.75, 0.95)
            for i, b in enumerate(D.neck):
                P.r(b, -3 * env(t, 0.1, 0.3, 0.7, 0.95), wig * (0.4 + 0.3 * i / len(D.neck)), 0)
            P.r('head', -10 * env(t, 0.1, 0.3, 0.7, 0.95), -wig * 0.8, 8 * math.sin(TAU * t * 2))
            for lg in D.flippers:
                sd = lg['side']
                splash = 30 * math.sin(TAU * t * 4) * env(t, 0.05, 0.15, 0.8, 0.95)
                P.r(lg['thigh'], 0, 0, -sd * (splash + 10 * up))
                P.r(lg['foot'], 0, 0, -sd * splash * 0.5)
            self.tail(P, t, 1.0 / 3, yaw=22, pitch=6, lag=0.5)
            P.jaw = 18 * env(t, 0.1, 0.25, 0.75, 0.95)
            P.lid = env(t, 0.25, 0.32, 0.55, 0.62)
            return P
        return T, g

    def pet(self):
        """Lowers the head to Tommy standing on the shore in front."""
        T = 1.2
        D = self.D
        hh = {'baby': 0.42, 'juv': 0.52, 'adult': 0.62}[D.age]
        tgt = V((0, self.mouth.y - self.H * 0.30, WATER_Z + 0.08 + hh))

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.4)
            w = tl(t, [(0, 0), (0.34, 1), (0.95, 1), (1.2, 0)])
            P.reach = (tgt, w, self.chain())
            P.at('root', (0, -self.H * 0.05 * w, 0))
            nz = env(t, 0.3, 0.4, 0.9, 1.0)
            P.r('head', 10 * w - 6 * nz, 0, (10 * math.sin(TAU * (t - 0.3) / 0.6)) * nz + 8 * w, post=True)
            P.lid = tl(t, [(0, 0), (0.24, 0), (0.36, 1), (0.98, 1), (1.1, 0), (1.2, 0)])
            self.tail(P, t, 0.3, yaw=18 * w, lag=0.5)
            self.paddle(P, t, 0.6, amp=0.5 * w, scull=True)
            P.jaw = 8 * w
            return P
        return T, g

    def call(self):
        T = 1.0
        D = self.D

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.3)
            inh = env(t, 0.0, 0.2, 0.2, 0.32)
            roar = env(t, 0.22, 0.34, 0.72, 0.92)
            vib = math.sin(TAU * t * 11) * env(t, 0.34, 0.4, 0.7, 0.8)
            self.spread(P, D.neck, 8 * inh - 14 * roar)
            P.r('head', 8 * inh - 22 * roar, 0, 3 * vib)
            P.at('root', (0, 0, self.H * 0.02 * roar))
            P.sc('root', (1 + 0.04 * roar, 1, 1 + 0.05 * roar - 0.04 * inh))
            P.jaw = 6 * inh + 34 * roar
            P.lid = env(t, 0.3, 0.38, 0.7, 0.8)
            for lg in D.flippers:
                P.r(lg['thigh'], 0, 0, -lg['side'] * 14 * roar)
            self.tail(P, t, 0.25, yaw=6 * roar, lag=0.5)
            return P
        return T, g

    def play(self):
        """Bops a ball floating in front with the snout."""
        T = 0.8
        D = self.D
        dip = self.dip(0.16, head=6, shape=(18, 14, 18, 24, 22))

        def g(t):
            P = self.float_(Pose(), t, T, amp=0.3)
            bow = env(t, 0.0, 0.22, 0.26, 0.40)
            lunge = env(t, 0.26, 0.40, 0.46, 0.75)
            P.r('root', -3 * bow + 4 * lunge, 0, 0)
            self.spread(P, D.neck, -10 * bow)
            P.r('head', -8 * bow, 0, 0)
            dip(P, lunge)
            P.at('root', (0, -self.H * 0.06 * lunge, 0))
            self.paddle(P, t, T, amp=0.8 * lunge)
            self.tail(P, t, 0.27, yaw=18, lag=0.5)
            P.jaw = 10 * lunge
            P.lid = env(t, 0.38, 0.42, 0.5, 0.56)
            return P
        return T, g

    def dive(self):
        """Dips under and comes back (2 s): nose down, tail flick, sinks
        below the water line and pops back up to the rest pose."""
        T = 2.0
        D = self.D
        H = self.H

        def g(t):
            P = Pose()
            dn = tl(t, [(0, 0), (0.15, -0.06), (0.35, 0.15), (0.8, 1.0), (1.2, 1.0), (1.75, -0.08),
                        (1.88, 0.03), (2.0, 0.0)])
            nose = tl(t, [(0, 0), (0.15, -6), (0.5, 40), (0.95, 30), (1.25, -14), (1.7, -6), (2.0, 0)])
            P.at('root', (0, -H * 0.12 * env(t, 0.2, 0.7, 1.2, 1.8), -H * 1.15 * dn))
            P.r('root', nose, 0, 0)
            curl = env(t, 0.1, 0.45, 1.2, 1.7)
            self.spread(P, D.neck, 22 * curl - 6 * env(t, 1.2, 1.5, 1.6, 1.95))
            P.r('head', 18 * curl, 0, 0)
            kick = env(t, 0.3, 0.5, 1.3, 1.6)
            for i, b in enumerate(D.tail):
                P.r(b, -18 * env(t, 0.25, 0.5, 0.7, 1.0) + 6 * kick * math.sin(TAU * t * 2 - i), 0, 0)
            self.paddle(P, t, 0.5, amp=1.2 * kick)
            for lg in D.flippers:
                P.r(lg['thigh'], 0, lg['side'] * 18 * env(t, 0.05, 0.3, 0.4, 0.6), 0)
            P.lid = env(t, 0.3, 0.4, 1.3, 1.45)
            P.jaw = 2 + 10 * env(t, 1.45, 1.6, 1.75, 1.95)
            return P
        return T, g


# ======================================================================
# features local to this module
# ======================================================================

FEATS = {'ptera_crest': f_ptera_crest}


def _anims(cls, extra=(), flight=()):
    names = list(DL.ANIMS) + list(extra)
    return {n: _anim(cls, n, legs='air' if n in flight else 'ground') for n in names}


# ======================================================================
# species
# ======================================================================

PTERA = dict(
    id='ptera', plan='flier', height=1.0, dino_class=Ptera, lod=0.85,
    pal=dict(body='#f2a46a', belly='#ffe0bd', accent='#ff5d5d', spots='#f0884f',
             horn='#ffe39a', eye_white='#ffffff', pupil='#2a1e2c', mouth='#6a2840',
             tongue='#f58aa4', blush='#ff9ab8'),
    torso=(0.17, 0.22, 0.18), tilt_deg=44, t_fwd=0.25, leg=0.22, leg_r=0.055, knee=0.22,
    thigh_r=1.8, foot_len=1.6, span=2.2, arm_k=1.25, arm_r=0.15, chord=1.3,
    neck_len=0.21, neck_deg=80, neck_deg2=46, neck_n=2, neck_r=0.46,
    head=dict(r=(0.20, 0.22, 0.19), off=(0.4, 0.22), snout=(0.48, 1.05, 0.40), snout_fwd=0.55,
              snout_drop=0.12, snout_taper=(0.45, 0.35), jaw_mat='horn', nostrils=False,
              smile=dict(width=58, z=-0.32, curl=0.26)),
    eye=dict(r=0.31, az=44, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.16, r=0.30, n=2, droop_deg=24, droop2_deg=10, tip=0.3),
    toes=3,
    parts=[
        ('ptera_crest', dict(length=1.7, height=1.05, thick=0.14, up_deg=22)),
        ('spots', dict(spots=[(180, 62, 0.28), (155, 44, 0.20), (205, 44, 0.20)])),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}, walk_reach=0.32, run_reach=0.36,
               fly_neck=20, fly_neck2=8, fly_thigh=58, fly_shin=20, fly_foot=50),
    speeds={'baby': (0.5, 1.2), 'juv': (0.65, 1.5), 'adult': (0.8, 1.8)},
    fly_speed={'baby': 2.0, 'juv': 2.5, 'adult': 3.0},
)
PTERA['anims'] = _anims(PteraMoves, ('fly', 'glide'), flight=('fly', 'glide'))

ARCHAEO = dict(
    id='archaeo', plan='biped', height=0.4, dino_class=Archaeo, lod=0.86,
    pal=dict(body='#ff9cc4', belly='#fff0d8', accent='#36c9b4', spots='#ffd33f',
             horn='#fff1d0', eye_white='#ffffff', pupil='#2a1e2c', mouth='#6a2840',
             tongue='#f58aa4', blush='#ff7fa8'),
    torso=(0.21, 0.24, 0.22), tilt_deg=34, t_fwd=0.22, leg=0.28, leg_r=0.058, knee=0.24,
    thigh_r=1.85, foot_len=1.8, arm_r=0.15, wing_len=2.3, wing_chord=1.3,
    neck_len=0.12, neck_deg=80, neck_deg2=44, neck_n=2, neck_r=0.5,
    head=dict(r=(0.22, 0.23, 0.21), off=(0.40, 0.25), snout=(0.52, 0.62, 0.44), snout_fwd=0.5,
              snout_drop=0.22, snout_taper=(0.42, 0.25), smile=dict(width=64, z=-0.30, curl=0.28)),
    eye=dict(r=0.33, az=40, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.70, r=0.30, n=4, droop_deg=6, droop2_deg=-14, tip=0.3, flat=0.75),
    tail_vane=2.3, toes=3, singer=True,
    parts=[
        ('feathers', dict(crest=[(0.0, 1.0, 0.8, 0.18), (-0.25, 0.75, 0.7, 0.14), (0.25, 0.75, 0.7, 0.14)])),
        ('spots', dict(spots=[(180, 60, 0.22), (160, 40, 0.16), (200, 40, 0.16)], mat='spots')),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}, fly_neck=12, fly_neck2=6, fly_thigh=60, fly_shin=30,
               fly_foot=60, fly_tail=0),
    speeds={'baby': (0.4, 0.75), 'juv': (0.5, 0.95), 'adult': (0.6, 1.05)},
    fly_speed={'baby': 1.5, 'juv': 1.8, 'adult': 2.0},
)
ARCHAEO['anims'] = _anims(BirdMoves, ('fly',), flight=('fly',))

MICRO = dict(
    id='microraptor', plan='biped', height=0.45, dino_class=Micro, four_wings=True, lod=0.84,
    pal=dict(body='#5d42b8', belly='#ddd3fb', accent='#3ed2ff', spots='#c66bff',
             horn='#f6f0e2', eye_white='#ffffff', pupil='#20172e', mouth='#5e2448',
             tongue='#f58aa4', blush='#ff8fc8'),
    torso=(0.20, 0.25, 0.21), tilt_deg=30, t_fwd=0.22, leg=0.32, leg_r=0.056, knee=0.24,
    thigh_r=1.85, foot_len=1.8, arm_r=0.14, wing_len=2.4, wing_chord=1.3, leg_feather=1.0,
    neck_len=0.14, neck_deg=70, neck_deg2=36, neck_n=2, neck_r=0.48,
    head=dict(r=(0.21, 0.23, 0.20), off=(0.40, 0.25), snout=(0.58, 0.72, 0.46), snout_fwd=0.5,
              snout_drop=0.2, snout_taper=(0.32, 0.18), teeth=True,
              smile=dict(width=68, z=-0.32, curl=0.28)),
    eye=dict(r=0.32, az=40, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.80, r=0.34, n=4, droop_deg=8, droop2_deg=-10, tip=0.25, flat=0.8),
    tail_vane=2.6, toes=3,
    parts=[
        ('feathers', dict(crest=[(0.0, 1.1, 0.9, 0.17), (-0.22, 0.8, 0.8, 0.13), (0.22, 0.8, 0.8, 0.13)])),
        ('stripes', dict(n=3, width=0.12, length=0.7, start=0.3, end=0.8, tail=3, mat='spots')),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}, fly_neck=14, fly_neck2=6, fly_thigh=60, fly_shin=20,
               fly_foot=60, fly_tail=0),
    speeds={'baby': (0.45, 0.85), 'juv': (0.55, 1.05), 'adult': (0.65, 1.25)},
    fly_speed={'baby': 1.6, 'juv': 2.0, 'adult': 2.4},
)
MICRO['anims'] = _anims(BirdMoves, ('glide', 'fly'), flight=('glide', 'fly'))

PLESIO = dict(
    id='plesio', plan='swimmer', height=1.2, dino_class=Plesio, lod=0.88,
    pal=dict(body='#ffcf6e', belly='#fff3d6', accent='#ff9a5c', spots='#f5a142',
             horn='#fbf3e0', eye_white='#ffffff', pupil='#2a1e2c', mouth='#6a2840',
             tongue='#f58aa4', blush='#ff8fa8'),
    torso=(0.32, 0.44, 0.24), float=0.12, leg_r=0.30, flipper=1.35, throat=False,
    neck_len=1.30, neck_n=5, neck_r=0.48, neck_taper=0.60,
    neck_prof=[(0.0, 26), (0.3, 58), (0.62, 86), (0.85, 84), (1.0, 52)],
    head=dict(r=(0.21, 0.24, 0.20), off=(0.38, 0.18), snout=(0.66, 0.60, 0.55), snout_fwd=0.5,
              snout_drop=0.22, smile=dict(width=66, z=-0.30, curl=0.28)),
    eye=dict(r=0.33, az=42, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.50, r=0.42, n=3, droop_deg=8, droop2_deg=0, tip=0.18, flat=0.75),
    parts=[
        ('spots', dict(spots=[(180, 62, 0.30), (150, 44, 0.20), (210, 44, 0.20), (125, 30, 0.14),
                              (235, 30, 0.14), (0, 70, 0.16)])),
        ('ridge', dict(n=5, size=0.20, start=0.25, end=0.7, tail=2, mat='accent')),
    ],
    speeds={'baby': (0.5, 1.2), 'juv': (0.7, 1.6), 'adult': (0.9, 2.0)},
    age_tweak={'baby': dict(neck=0.95, head=1.5, round=0.4, neck_thick=1.35, lod=0.6),
               'juv': dict(neck=1.0, head=1.22, neck_thick=1.12)},
)
PLESIO['anims'] = {n: _anim(PlesioMoves, n, legs='none') for n in list(DL.ANIMS) + ['dive']}

SPECIES = {'ptera': PTERA, 'archaeo': ARCHAEO, 'microraptor': MICRO, 'plesio': PLESIO}
EGGS = {
    'ptera': dict(shell='#fff1dc', spots='#ff8a6a'),
    'archaeo': dict(shell='#e9fbf6', spots='#ff9cc4'),
    'microraptor': dict(shell='#ece8ff', spots='#5546b0'),
    'plesio': dict(shell='#fff8e2', spots='#ffb648'),
}
