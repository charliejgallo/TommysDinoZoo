"""props_lib.py - reusable building blocks for Tommy's Dino Zoo props and
held items (fences, trees, plants, rocks, farm furniture, buildings).

Everything here returns plain mesh objects in world space (Blender metres,
+Z up, model front = -Y); props.py composes them, joins them with
`finish()` and exports. Built on tdz_common (C); nothing there is changed.

Shapes:
  lathe            revolve an (r, z) profile; `rfun(theta, z)` modulates the
                   radius (pumpkin ribs, scallops, lumps)
  round_corners    round the corners of a 2D polyline (soft clay bevels for
                   lathe and extrude profiles)
  extrude          a 2D (x, z) profile extruded along Y, edges bevelled
  hollow_box       a box with a hollowed top (troughs, planters, beds), its
                   inside in a second material, corners rounded
  plank            rounded box from point a to point b (rails, slats, beams)
  post             rounded round post with a domed top
  lumpy            noisy icosphere (rocks, hay, lumps of straw)
  shell_cap        drape a second material over part of a mesh (moss, snow)
  canopy           leafy crown from clustered blobs (trees, bushes)
  scatter_on       place things on a surface by ray casting (fruit, berries)
  frond            double-sided comb-edged leaf (ferns, palm leaflets)
  blade            thick flat leaf/grass blade along a curve
  torus            ring (rims, bands, nest, handles)
  paint_faces      split one mesh into several materials by a rule
  sphere           small low-poly sphere (berries, knobs, finials)

Palette: `M(role)` returns the shared material of that role (see PAL);
props should prefer these roles so a scene has few materials.
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

import tdz_common as C

# --------------------------------------------------------------- palette
# role -> '#rrggbb' or ('#rrggbb', {mat kwargs}). sRGB hex.
PAL = {
    # wood and paint
    'wood': '#dda66c', 'wood_dark': '#9b6440', 'white': '#fbf3e3',
    'paint_red': '#f0645a', 'paint_blue': '#6bb8f2', 'paint_yellow': '#ffd25a',
    'paint_mint': '#9fe2c4', 'paint_pink': '#ffaec4', 'paint_green': '#3f8f72',
    'paint_lilac': '#c5a9f2',
    # plants
    'leaf': '#78c85a', 'leaf_dark': '#4e9e4a', 'fern': '#45b884',
    'fern_dark': '#2f8d6a', 'grass': '#95d65a', 'bark': '#a8714a',
    'plant_stem': '#5d9e3e', 'moss': '#8fcb5c',
    # ground and stone
    'stone': '#c2bbb1', 'stone_dark': '#9a938b', 'soil': '#94603f',
    'soil_dark': '#6f452c', 'straw': '#f2cb6c', 'straw_dark': '#d29c48',
    # building
    'roof': '#e8584c', 'roof_dark': '#b8443d', 'wall': '#fff1da',
    'window': '#bfe5fb',
    'brick': '#d98a6a', 'metal': '#c7d1da', 'metal_dark': '#5f6d7b',
    # fruit and flowers
    'apple': '#ee4646', 'berry': '#4c6fe2', 'pumpkin': '#f8962f',
    'petal_pink': '#ffb2cc', 'petal_lilac': '#c8a8f6', 'petal_yellow': '#ffe27a',
    'petal_white': '#fffaf2', 'flower_center': '#ffb23a', 'coconut': '#8f5d3a',
    'shroom': '#f2645c',
    # misc
    'water': '#6fd2ec', 'glass': ('#d4f2fb', {'alpha': 0.45, 'rough': 0.1}),
    'bulb': ('#fff0a0', {'emit': 3.0}), 'led': ('#ff7f9c', {'emit': 2.5}),
    'paper': '#fffaf0', 'paper_yellow': '#fff1a8', 'paper_blue': '#d4ecff',
    'cork': '#e3b47a', 'bag': '#f07c6c', 'bristle': '#f4dca6',
    'fish': '#6fb6ec', 'fish_belly': '#e8f5ff', 'eye_white': '#ffffff',
    'pupil': '#1d1b22', 'blush': '#ff9db0',
}


def M(role):
    """Shared material for a palette role (creates it on first use)."""
    v = PAL[role]
    if isinstance(v, tuple):
        return C.mat(role, v[0], **v[1])
    return C.mat(role, v)


def begin():
    """Fresh empty scene (call before building each model)."""
    C.reset()
    C._mats.clear()


# --------------------------------------------------------------- mesh utils


def mesh_obj(name, verts, faces, material=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material is not None:
        me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = smooth
    return ob


def _bm_obj(bm, name, material, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material is not None:
        me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = smooth
    return ob


def place(ob, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    """Set the object transform (rot in degrees, XYZ Euler)."""
    ob.location = loc
    ob.rotation_mode = 'XYZ'
    ob.rotation_euler = [math.radians(r) for r in rot]
    if scale is not None:
        ob.scale = scale
    return ob


def orient(ob, loc, xaxis, up=(0, 0, 1)):
    """Point the object's local +X along `xaxis`, +Z as close to `up`."""
    x = Vector(xaxis).normalized()
    z = Vector(up)
    z = (z - x * z.dot(x))
    if z.length < 1e-6:
        z = Vector((0, 1, 0)) - x * x.y
    z.normalize()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(loc)
    ob.matrix_world = m
    return ob


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def flip(ob):
    for p in ob.data.polygons:
        p.flip()
    return ob


def transform_objs(objs, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    """Bake a rigid transform into several objects (move a sub-assembly)."""
    m = Matrix.Translation(Vector(loc)) @ \
        Matrix.Rotation(math.radians(rot[2]), 4, 'Z') @ \
        Matrix.Rotation(math.radians(rot[1]), 4, 'Y') @ \
        Matrix.Rotation(math.radians(rot[0]), 4, 'X') @ \
        Matrix.Scale(scale, 4)
    bpy.context.view_layer.update()
    for o in objs:
        C.apply_xf(o)
        o.data.transform(m)
        o.data.update()
    return objs


def duplicate(ob, name=None):
    o2 = ob.copy()
    o2.data = ob.data.copy()
    o2.name = name or ob.name + '_d'
    bpy.context.scene.collection.objects.link(o2)
    return o2


def finish(name, objs, smooth_angle=60.0):
    """Join `objs` into one mesh `name`, auto-smooth (soft bevels stay
    smooth, hard corners split) and keep ngons flat. Returns the object."""
    bpy.context.view_layer.update()   # matrix_world from .location/.rotation
    ob = C.join_static(name, [o for o in objs if o is not None])
    me = ob.data
    me.use_auto_smooth = True
    me.auto_smooth_angle = math.radians(smooth_angle)
    for p in me.polygons:
        if len(p.vertices) > 4:
            p.use_smooth = False
    return ob


# --------------------------------------------------------------- 2D profiles


def round_corners(pts, r, n=3, closed=False):
    """Replace each corner of polyline `pts` by a quadratic arc of size `r`
    (a number or one value per point; 0 keeps the corner sharp)."""
    P = [Vector((p[0], p[1])) for p in pts]
    R = list(r) if isinstance(r, (list, tuple)) else [r] * len(P)
    out = []
    m = len(P)
    for i in range(m):
        if not closed and (i == 0 or i == m - 1):
            out.append(P[i])
            continue
        a, b, c = P[(i - 1) % m], P[i], P[(i + 1) % m]
        rr = R[i]
        if rr <= 0:
            out.append(b)
            continue
        d1 = min(rr, (b - a).length * 0.5)
        d2 = min(rr, (c - b).length * 0.5)
        p0 = b + (a - b).normalized() * d1
        p2 = b + (c - b).normalized() * d2
        for k in range(n + 1):
            t = k / n
            out.append(p0 * (1 - t) ** 2 + b * 2 * t * (1 - t) + p2 * t * t)
    return [(v.x, v.y) for v in out]


def arc_pts(cx, cy, r, a0, a1, n):
    """Points on a circle arc from angle a0 to a1 (degrees)."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


# --------------------------------------------------------------- solids


def lathe(name, material, prof, loc=(0, 0, 0), rot=(0, 0, 0), seg=24,
          rfun=None, smooth=True, scale=None):
    """Revolve profile [(r, z), ...] (bottom to top) around Z. A point with
    r == 0 becomes a pole; open ends with r > 0 get a flat cap.
    `rfun(theta, z)` multiplies the radius (ribs, lobes, wobble)."""
    bm = bmesh.new()
    rings = []
    for (r, z) in prof:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
            continue
        ring = []
        for k in range(seg):
            th = 2 * math.pi * k / seg
            rr = r * (rfun(th, z) if rfun else 1.0)
            ring.append(bm.verts.new((rr * math.cos(th), rr * math.sin(th), z)))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for k in range(seg):
                bm.faces.new((a[0], b[k], b[(k + 1) % seg]))
        elif len(b) == 1:
            for k in range(seg):
                bm.faces.new((a[k], b[0], a[(k + 1) % seg]))
        else:
            for k in range(seg):
                bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
    # caps on open ends
    if len(rings[0]) > 1:
        bm.faces.new(list(reversed(rings[0])))
    if len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _bm_obj(bm, name, material, smooth)
    return place(ob, loc, rot, scale)


def extrude(name, material, pts, depth, loc=(0, 0, 0), rot=(0, 0, 0),
            bevel=0.0, seg=2):
    """Closed 2D profile `pts` [(x, z), ...] extruded `depth` along Y
    (centred), the front/back edges bevelled by `bevel`."""
    bm = bmesh.new()
    front = [bm.verts.new((x, -depth / 2, z)) for x, z in pts]
    back = [bm.verts.new((x, depth / 2, z)) for x, z in pts]
    n = len(pts)
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for k in range(n):
        bm.faces.new((front[k], back[k], back[(k + 1) % n], front[(k + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel > 0:
        cap = set(front) | set(back)
        edges = [e for e in bm.edges
                 if (e.verts[0] in cap and e.verts[1] in cap and
                     abs(e.verts[0].co.y - e.verts[1].co.y) < 1e-6)]
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=seg,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    ob = _bm_obj(bm, name, material)
    return place(ob, loc, rot)


def hollow_box(name, material, inner, loc, size, wall, depth, corner=0.0,
               bevel=0.02, rot=(0, 0, 0), cseg=4):
    """Box standing on `loc` (bottom centre) with its top hollowed `depth`
    deep inside walls `wall` thick (troughs, planters, beds, crates). The
    inside faces get material `inner`. `corner` rounds the vertical edges
    (plan view), `bevel` softens the rest."""
    sx, sy, sz = size
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, 0, sz / 2)), verts=bm.verts)
    if corner > 0:
        vert_edges = [e for e in bm.edges
                      if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-6]
        bmesh.ops.bevel(bm, geom=vert_edges, offset=corner, segments=cseg,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    top = [f for f in bm.faces if f.normal.z > 0.99][0]
    bmesh.ops.inset_region(bm, faces=[top], thickness=wall, depth=0.0)
    ret = bmesh.ops.extrude_face_region(bm, geom=[top])
    nv = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=Vector((0, 0, -depth)), verts=nv)
    bmesh.ops.delete(bm, geom=[top], context='FACES')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel > 0:
        sharp = [e for e in bm.edges
                 if len(e.link_faces) == 2 and e.calc_face_angle(0) > 0.6]
        bmesh.ops.bevel(bm, geom=sharp, offset=bevel, segments=2,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    ob = _bm_obj(bm, name, material)
    me = ob.data
    me.materials.append(inner)
    ix, iy = sx / 2 - wall * 0.6, sy / 2 - wall * 0.6
    for p in me.polygons:
        c = p.center
        if abs(c.x) < ix and abs(c.y) < iy and \
                sz - depth - bevel - 1e-3 < c.z < sz - 1e-3:
            p.material_index = 1
    return place(ob, loc, rot)


def rbox(name, material, loc, size, rot=(0, 0, 0), bevel=0.03, seg=2):
    """Rounded box (tdz_common.box) - shorthand."""
    return C.box(name, material, loc, size, rot=rot, bevel=bevel, seg=seg)


def plank(name, material, a, b, width, thick, bevel=0.015, up=(0, 0, 1),
          seg=2, over=0.0):
    """Rounded box from point a to point b; `width` across (local Y),
    `thick` along `up` (local Z). `over` extends both ends."""
    a, b = Vector(a), Vector(b)
    L = (b - a).length + 2 * over
    ob = C.box(name, material, (0, 0, 0), (L, width, thick), bevel=bevel,
               seg=seg)
    return orient(ob, (a + b) / 2, b - a, up)


def post(name, material, base, h, r, seg=12, top=1.0):
    """Round post from `base` up to height h with a domed top (`top` scales
    the dome height)."""
    x, y, z = base
    prof = [(0, z - 0.02), (r, z - 0.02)]
    prof += [(r, z + h - r * top)]
    for k in range(1, 4):
        a = math.pi / 2 * k / 4
        prof.append((r * math.cos(a), z + h - r * top + r * top * math.sin(a)))
    prof.append((0, z + h))
    ob = lathe(name, material, prof, (x, y, 0), seg=seg)
    return ob


def sphere(name, material, loc, r, seg=10, rings=7, squash=(1, 1, 1)):
    return C.ellipsoid(name, material, loc,
                       (r * squash[0], r * squash[1], r * squash[2]),
                       seg=seg, rings=rings)


def torus(name, material, loc, R, r, seg=24, rseg=10, rot=(0, 0, 0),
          rfun=None, squash=1.0):
    """Ring of major radius R and tube radius r (lying in XY).
    `rfun(theta)` scales the tube radius around the ring; `squash` scales
    the tube's height."""
    bm = bmesh.new()
    rings = []
    for i in range(seg):
        th = 2 * math.pi * i / seg
        rr = r * (rfun(th) if rfun else 1.0)
        ring = []
        for k in range(rseg):
            ph = 2 * math.pi * k / rseg
            d = R + rr * math.cos(ph)
            ring.append(bm.verts.new((d * math.cos(th), d * math.sin(th),
                                      rr * math.sin(ph) * squash)))
        rings.append(ring)
    for i in range(seg):
        a, b = rings[i], rings[(i + 1) % seg]
        for k in range(rseg):
            bm.faces.new((a[k], a[(k + 1) % rseg], b[(k + 1) % rseg], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _bm_obj(bm, name, material)
    return place(ob, loc, rot)


def lumpy(name, material, loc, radii, subdiv=3, amp=0.12, freq=1.6, seed=0,
          flat_bottom=None, rot=(0, 0, 0)):
    """Noisy icosphere: a rounded rock / lump. `flat_bottom` (local z) clamps
    vertices below it so the thing sits on the ground."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    off = Vector((seed * 7.31, seed * 3.17, seed * 5.53))
    for v in bm.verts:
        d = v.co.normalized()
        n = noise.noise(d * freq + off)
        v.co = Vector((d.x * radii[0], d.y * radii[1], d.z * radii[2])) * \
            (1.0 + amp * n)
        if flat_bottom is not None and v.co.z < flat_bottom:
            v.co.z = flat_bottom + (v.co.z - flat_bottom) * 0.15
    ob = _bm_obj(bm, name, material)
    return place(ob, loc, rot)


def shell_cap(src, name, material, test, offset=0.012):
    """Copy the faces of `src` whose vertices all pass `test(co, normal)`
    (world space) and push them out by `offset`: moss on a rock, snow on a
    roof, icing. Returns the new object (src unchanged)."""
    bpy.context.view_layer.update()
    C.apply_xf(src)
    me = src.data
    keep = set()
    vok = [test(v.co, v.normal) for v in me.vertices]
    for p in me.polygons:
        if all(vok[i] for i in p.vertices):
            keep.add(p.index)
    vmap = {}
    verts, faces = [], []
    for p in me.polygons:
        if p.index not in keep:
            continue
        f = []
        for i in p.vertices:
            if i not in vmap:
                v = me.vertices[i]
                vmap[i] = len(verts)
                verts.append(v.co + v.normal * offset)
            f.append(vmap[i])
        faces.append(f)
    return mesh_obj(name, verts, faces, material)


def paint_faces(ob, mats, rule):
    """Give `ob` several materials: rule(centre, normal) -> index into
    `mats` for each face (in object space)."""
    me = ob.data
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        p.material_index = rule(p.center, p.normal)
    return ob


# --------------------------------------------------------------- foliage


def ico(name, material, loc, radii, subdiv=2, rot=(0, 0, 0)):
    """Icosphere ellipsoid: rounder silhouette per triangle than a UV
    sphere (bmesh counts the base icosahedron as 1: subdiv 2 = 80 tris,
    3 = 320, 4 = 1280)."""
    return lumpy(name, material, loc, radii, subdiv=subdiv, amp=0.0, rot=rot)


def canopy(name, mats, center, radii, n=9, blob=(0.45, 0.6), seed=1,
           seg=14, rings=9, core=0.82, lower_mat=None, lower_z=-0.15,
           spread=0.78, subdiv=3, core_subdiv=2, lump=0.0):
    """Leafy crown from clustered blobs: a core plus `n` blobs spread over
    its surface (Fibonacci sphere, a bit jittered). `blob` is the blob
    radius range as a fraction of the mean radius. Blobs whose direction
    points below `lower_z` use `lower_mat` (a darker leaf) for depth.
    Blobs are icospheres (`subdiv`), or UV spheres (`seg`, `rings`) when
    subdiv is 0. Returns a list of objects."""
    rng = random.Random(seed)
    cx, cy, cz = center
    rx, ry, rz = radii
    rm = (rx + ry + rz) / 3

    def blobf(nm, m, p, r3, rot):
        if subdiv:
            return lumpy(nm, m, p, r3, subdiv=subdiv, amp=lump, freq=2.2,
                         seed=rng.randint(0, 99), rot=rot)
        return C.ellipsoid(nm, m, p, r3, seg=seg, rings=rings, rot=rot)
    out = [ico(name + '_core', mats, center,
               (rx * core, ry * core, rz * core), subdiv=core_subdiv)]
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - (i + 0.5) / n * 1.55       # skip the bottom of the sphere
        rr = math.sqrt(max(0.0, 1 - z * z))
        th = ga * i + rng.uniform(-0.3, 0.3)
        d = Vector((rr * math.cos(th), rr * math.sin(th), z))
        br = rm * rng.uniform(*blob)
        p = Vector((cx + d.x * rx * spread, cy + d.y * ry * spread,
                    cz + d.z * rz * spread))
        m = lower_mat if (lower_mat is not None and z < lower_z) else mats
        out.append(blobf('%s_b%d' % (name, i), m, p, (br, br, br * 0.9),
                         (0, 0, math.degrees(th))))
    return out


def scatter_on(targets, n, seed, make, zmin=-1e9, center=None,
               dirs=None, tries=300, min_gap=0.0):
    """Ray-cast from outside toward `center` (default: the targets' bounds
    centre) in random directions and call make(i, loc, normal) at each hit
    on one of `targets` (whose loc.z >= zmin, at least `min_gap` from the
    previous hits). Returns the made objects."""
    hits = []
    deps = bpy.context.evaluated_depsgraph_get()
    rng = random.Random(seed)
    if center is None:
        pts = [o.matrix_world @ Vector(c) for o in targets for c in o.bound_box]
        center = sum(pts, Vector()) / len(pts)
    center = Vector(center)
    tset = {o.name for o in targets}
    out = []
    i = 0
    for t in range(tries):
        if len(out) >= n:
            break
        if dirs is not None:
            if t >= len(dirs):
                break
            d = Vector(dirs[t]).normalized()
        else:
            u, v = rng.uniform(-1, 1), rng.uniform(0, 2 * math.pi)
            s = math.sqrt(1 - u * u)
            d = Vector((s * math.cos(v), s * math.sin(v), u))
        org = center + d * 20
        hit, loc, nrm, _, obj, _ = bpy.context.scene.ray_cast(deps, org, -d)
        if not hit or obj.name not in tset or loc.z < zmin:
            continue
        if any((loc - q).length < min_gap for q in hits):
            continue
        o = make(i, loc, nrm)
        if o is not None:
            hits.append(loc.copy())
            out.extend(o if isinstance(o, list) else [o])
            i += 1
    return out


def frond(name, material, base, phi, length, rise, droop, width, teeth=8,
          comb=0.45, fold=0.3, thick=0.008, curl=0.0, side=None, up=None):
    """A double-sided comb-edged leaf (fern frond, palm leaflet) along a
    spine that leaves `base` in compass direction `phi` (radians), rising
    `rise` and drooping `droop` (fractions of `length`). The blade spreads
    along `side` (default: horizontal, across the spine) and its face looks
    along `up` (default +Z; e.g. (0, -1, 0) for an upright leaf facing the
    front)."""
    n = teeth * 4 + 1
    h = Vector((math.cos(phi), math.sin(phi), 0))
    side = Vector(side).normalized() if side else \
        Vector((-math.sin(phi), math.cos(phi), 0))
    U = Vector(up).normalized() if up else Vector((0, 0, 1))
    Z = Vector((0, 0, 1))
    b = Vector(base)
    top, bot = [], []
    for k in range(n):
        t = k / (n - 1)
        p = b + h * length * t * (1 - 0.1 * t) + \
            Z * length * (rise * t - droop * t * t)
        if curl:
            c = t ** 3 * curl
            p = p - h * c * length * 0.25 - Z * c * length * 0.12
        w = width * math.sin(math.pi * min(1.0, t) ** 0.75) * (1 - 0.3 * t)
        w *= (1 - comb) + comb * abs(math.cos(math.pi * teeth * t))
        w = max(w, 0.006)
        dz = U * (-fold * w)
        row = [p - side * w + dz, p + U * 0.008, p + side * w + dz]
        top.append(row)
        bot.append([q - U * thick for q in row])
    verts, faces = [], []
    for rows in (top, bot):
        for row in rows:
            verts.extend(row)
    off = 3 * n
    for k in range(n - 1):
        a = 3 * k
        f1 = (a, a + 3, a + 4, a + 1)
        f2 = (a + 1, a + 4, a + 5, a + 2)
        faces += [f1, f2]
        faces += [tuple(i + off for i in reversed(f1)),
                  tuple(i + off for i in reversed(f2))]
    ob = mesh_obj(name, verts, faces, material)
    # top faces should face `up`
    me = ob.data
    if me.polygons[0].normal.dot(U) < 0:
        flip(ob)
    return ob


def blade(name, material, pts, width, thick=0.25, seg=8, tip=0.15):
    """Thick flat leaf / grass blade swept through `pts` (radius `width`,
    tapering to `tip`×width at the end; `thick` = section flatness)."""
    n = len(pts)
    radii = [width * (0.55 + 0.45 * math.sin(math.pi * min(1, (i + 0.6) / n)))
             for i in range(n)]
    radii[-1] = width * tip
    return C.tube(name, material, pts, radii, seg=seg,
                  flatten=[(1.0, thick)] * n)


def ribbon(name, material, pts, widths, side=None):
    """Cheap double-sided strip along polyline `pts` (grass blades, straw,
    ribbons): width per point (0 = pointed tip). The strip spreads along
    `side` (default: horizontal, across the first segment)."""
    P = [Vector(p) for p in pts]
    if side is None:
        d = P[1] - P[0]
        sd = d.cross(Vector((0, 0, 1)))
        if sd.length < 1e-6:
            sd = Vector((1, 0, 0))
    else:
        sd = Vector(side)
    sd.normalize()
    verts, faces = [], []
    for p, w in zip(P, widths):
        verts += [p - sd * w / 2, p + sd * w / 2]
    n = len(P)
    for k in range(n - 1):
        a = 2 * k
        faces.append((a, a + 1, a + 3, a + 2))
    # back side: same positions, separate verts, reversed faces
    off = len(verts)
    verts += [v.copy() for v in verts]
    for f in list(faces):
        faces.append(tuple(i + off for i in reversed(f)))
    ob = mesh_obj(name, verts, faces, material)
    return ob


def scallop_row(name, material, p0, p1, down, normal, n, band, depth,
                lift=0.04, thick=0.035, res=6):
    """A row of fish-scale shingles: a strip whose top edge runs p0 -> p1
    (tucked into the surface) and whose bottom edge hangs `band` + a
    scallop of `depth` along `down`, lifted `lift` off the surface along
    `normal`, with a lip of `thick` back down to it. Overlapping rows make
    a storybook roof (also: skirts, frills, awnings)."""
    p0, p1 = Vector(p0), Vector(p1)
    dn, nm = Vector(down).normalized(), Vector(normal).normalized()
    m = n * res
    top, bot, lip = [], [], []
    for k in range(m + 1):
        f = (k % res) / res if k < m else 1.0
        if k % res == 0:
            f = 0.0
        sc = math.sqrt(max(0.0, 1 - (2 * f - 1) ** 2))
        p = p0.lerp(p1, k / m)
        top.append(p - nm * 0.01)
        b = p + dn * (band + depth * sc) + nm * lift
        bot.append(b)
        lip.append(b - nm * thick)
    verts = top + bot + lip
    N = m + 1
    faces = []
    for k in range(m):
        faces.append((k, k + 1, N + k + 1, N + k))
        faces.append((N + k, N + k + 1, 2 * N + k + 1, 2 * N + k))
    ob = mesh_obj(name, verts, faces, material)
    if ob.data.polygons[0].normal.dot(nm) < 0:
        flip(ob)
    return ob


def arc(p0, p1, bulge, n=6, axis=(0, 0, 1)):
    """Points from p0 to p1 bowed by `bulge` along `axis` (handles, stems)."""
    p0, p1, ax = Vector(p0), Vector(p1), Vector(axis)
    return [tuple(p0.lerp(p1, k / (n - 1)) +
                  ax * bulge * math.sin(math.pi * k / (n - 1)))
            for k in range(n)]
