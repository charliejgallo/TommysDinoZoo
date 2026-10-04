"""tdz_common.py - shared helpers to build Tommy's Dino Zoo models in Blender
(3.3+) from Python and export them as .glb for Godot 4.

Every model is procedural: a script builds parts from a few primitives
(ellipsoids, swept tubes, cones, rounded boxes), skins them to an armature
and keys a handful of actions, then calls export_glb(). Nothing is modelled
by hand, so a model can be re-made, re-coloured or re-proportioned by editing
numbers.

    Blender -b -P <script>.py -- --out ../../game/assets/models

Conventions (Godot side relies on these, see docs/ART-SPEC.md):
  * Units are metres. Blender +Z up, the model faces -Y (Blender front view);
    the glTF exporter turns that into Godot +Y up, facing +Z.
  * Tommy is 1.0 m tall; everything else is scaled against him.
  * Origin on the ground between the feet.
  * Materials are named by palette role ("skin", "hair", "cap", "shirt",
    "body", "belly", "spots", "eye_white", "pupil", ...). Godot recolours by
    that name, so keep it stable. Colours are linear sRGB values of the base
    colour; no textures (flat cartoon colours, shading comes from the light).
  * Actions are pushed to NLA tracks; each becomes one glTF animation with
    the action's name ("idle", "walk", "eat", ...). Loops are decided in Godot.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- arguments


def args():
    """Arguments after `--` as a dict: --out x --only a,b --flag."""
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = {}
    i = 0
    while i < len(a):
        if a[i].startswith('--'):
            k = a[i][2:]
            if i + 1 < len(a) and not a[i + 1].startswith('--'):
                out[k] = a[i + 1]
                i += 2
            else:
                out[k] = True
                i += 1
        else:
            i += 1
    return out


# ---------------------------------------------------------------- scene


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()   # cached materials die with the old scene
    bpy.context.scene.render.fps = 30
    for c in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures,
              bpy.data.actions, bpy.data.objects):
        for x in list(c):
            c.remove(x)


def hex_rgb(h):
    """'#ff8800' -> linear rgb tuple."""
    h = h.lstrip('#')
    s = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                 for c in s)


_mats = {}


def mat(name, color, rough=0.75, metal=0.0, emit=0.0, alpha=1.0):
    """A flat material named `name` (palette role). `color` '#rrggbb'."""
    key = name
    m = _mats.get(key)
    if m is None or m.name not in bpy.data.materials:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        _mats[key] = m
    b = m.node_tree.nodes['Principled BSDF']
    rgb = hex_rgb(color)
    b.inputs['Base Color'].default_value = (*rgb, 1.0)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit > 0:
        b.inputs['Emission'].default_value = (*rgb, 1.0)
        b.inputs['Emission Strength'].default_value = emit
    if alpha < 1.0:
        b.inputs['Alpha'].default_value = alpha
        m.blend_method = 'BLEND'
    return m


def _obj_from_bm(bm, name, material):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material is not None:
        me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def _xf(ob, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    ob.location = loc
    ob.rotation_euler = [math.radians(r) for r in rot]
    if scale is not None:
        ob.scale = scale
    return ob


# ---------------------------------------------------------------- primitives


def ellipsoid(name, material, loc, radii, rot=(0, 0, 0), seg=24, rings=14):
    """Ellipsoid with semi-axes `radii` (x, y, z) centred at `loc`."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings,
                              radius=1.0)
    bmesh.ops.scale(bm, vec=Vector(radii), verts=bm.verts)
    ob = _obj_from_bm(bm, name, material)
    return _xf(ob, loc, rot)


def box(name, material, loc, size, rot=(0, 0, 0), bevel=0.0, seg=3):
    """Box of full `size` (x, y, z), rounded by `bevel` metres."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel,
                        segments=seg, profile=0.5, affect='EDGES')
    ob = _obj_from_bm(bm, name, material)
    if bevel <= 0:
        for p in ob.data.polygons:
            p.use_smooth = False
    return _xf(ob, loc, rot)


def cylinder(name, material, loc, r, h, rot=(0, 0, 0), seg=20, r2=None,
             smooth=True):
    """Cylinder (or cone/frustum when r2 is given) standing on `loc`."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=r, radius2=r if r2 is None else r2,
                          depth=h)
    bmesh.ops.translate(bm, vec=Vector((0, 0, h / 2)), verts=bm.verts)
    ob = _obj_from_bm(bm, name, material)
    if not smooth:
        for p in ob.data.polygons:
            p.use_smooth = False
    else:
        _flat_caps(ob)
    return _xf(ob, loc, rot)


def _flat_caps(ob):
    for p in ob.data.polygons:
        if abs(p.normal.z) > 0.99:
            p.use_smooth = False


def cone(name, material, base, tip, r, seg=12):
    """Cone from a circle of radius r at `base` to a point at `tip`."""
    base, tip = Vector(base), Vector(tip)
    d = tip - base
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=seg,
                          radius1=r, radius2=0.0, depth=d.length)
    bmesh.ops.translate(bm, vec=Vector((0, 0, d.length / 2)), verts=bm.verts)
    ob = _obj_from_bm(bm, name, material)
    ob.location = base
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d)
    return ob


def tube(name, material, pts, radii, seg=16, cap=True, flatten=None):
    """Smooth tube swept through `pts` with a radius per point; rounded caps.

    `flatten` (optional) is a per-point (sx, sz) scaling of the section in
    the tube's local side/up frame, for oval necks and flat tails.
    Points are interpolated with Catmull-Rom (4 sub-steps per span).
    """
    P = [Vector(p) for p in pts]
    R = list(radii)
    F = list(flatten) if flatten else [(1.0, 1.0)] * len(P)
    # Catmull-Rom densify
    dp, dr, df = [], [], []
    sub = 4
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
            off = side * math.cos(a) * dr[i] * df[i][0] + \
                up * math.sin(a) * dr[i] * df[i][1]
            ring.append(bm.verts.new(p + off))
        rings.append((ring, p, t, side, up, dr[i], df[i]))
    for i in range(len(rings) - 1):
        a, b = rings[i][0], rings[i + 1][0]
        for k in range(seg):
            bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
    if cap:
        for end, sign in ((rings[0], -1), (rings[-1], 1)):
            ring, p, t, side, up, r, f = end
            prev = ring
            steps = 4
            for s in range(1, steps):
                ang = (math.pi / 2) * s / steps
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
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _obj_from_bm(bm, name, material)


def decal_on(name, material, target, center, normal_hint, radius,
             aspect=(1.0, 1.0), lift=0.003, seg=16):
    """A small flat disc projected just above `target`'s surface (eyes,
    spots, blush). `center` is a point near the surface in world space; the
    disc is shrink-wrapped by ray casting from outside along `normal_hint`.
    """
    nrm = Vector(normal_hint).normalized()
    ref = Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((1, 0, 0))
    u = nrm.cross(ref).normalized()
    v = nrm.cross(u).normalized()
    bm = bmesh.new()
    deps = bpy.context.evaluated_depsgraph_get()
    tgt = target.evaluated_get(deps)
    inv = tgt.matrix_world.inverted()

    def project(p):
        o = p + nrm * 0.5
        lo, ld = inv @ o, (inv.to_3x3() @ -nrm).normalized()
        hit, loc, n, _ = tgt.ray_cast(lo, ld)
        if hit:
            w = tgt.matrix_world @ loc
            wn = (tgt.matrix_world.to_3x3() @ n).normalized()
            return w + wn * lift
        return p

    c = bm.verts.new(project(Vector(center)))
    ring = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        p = Vector(center) + u * math.cos(a) * radius * aspect[0] + \
            v * math.sin(a) * radius * aspect[1]
        ring.append(bm.verts.new(project(p)))
    for k in range(seg):
        bm.faces.new((c, ring[k], ring[(k + 1) % seg]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _obj_from_bm(bm, name, material)
    # face outward
    me = ob.data
    if me.polygons and me.polygons[0].normal.dot(nrm) < 0:
        for p in me.polygons:
            p.flip()
    return ob


def mirror_x(ob, name=None):
    """Duplicate `ob` mirrored across X=0 (applies transforms first)."""
    apply_xf(ob)
    me = ob.data.copy()
    for vtx in me.vertices:
        vtx.co.x = -vtx.co.x
    for p in me.polygons:
        p.flip()
    o2 = bpy.data.objects.new(name or ob.name + '_m', me)
    bpy.context.scene.collection.objects.link(o2)
    for vg in ob.vertex_groups:
        o2.vertex_groups.new(name=vg.name)
    return o2


def apply_xf(ob):
    """Bake the object transform into the mesh."""
    if ob.parent is None:
        # matrix_world is only refreshed by a depsgraph update; build it
        # from the transform channels so freshly placed parts are right
        ob.matrix_world = ob.matrix_basis.copy()
    me = ob.data
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    if ob.rotation_mode == 'QUATERNION':
        ob.rotation_quaternion = (1, 0, 0, 0)


# ---------------------------------------------------------------- armature


def armature(name, bones):
    """bones: list of (name, head, tail, parent or None). Returns the object.

    Bone rolls are left at 0; actions rotate in bone-local space (Y along
    the bone).
    """
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    for bn, h, t, par in bones:
        b = arm.edit_bones.new(bn)
        b.head, b.tail = Vector(h), Vector(t)
        if par:
            b.parent = eb[par]
            if (eb[par].tail - b.head).length < 1e-4:
                b.use_connect = True
        eb[bn] = b
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'XYZ'
    return ob


def _bone_segments(arm_ob):
    segs = {}
    for b in arm_ob.data.bones:
        segs[b.name] = (arm_ob.matrix_world @ b.head_local,
                        arm_ob.matrix_world @ b.tail_local)
    return segs


def _dist_seg(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (a + ab * t - p).length


def skin_rigid(ob, bone):
    """Every vertex of `ob` follows `bone` 100%."""
    apply_xf(ob)
    vg = ob.vertex_groups.new(name=bone)
    vg.add(list(range(len(ob.data.vertices))), 1.0, 'REPLACE')
    return ob


def skin_near(ob, arm_ob, bones, power=6.0, top=2):
    """Smooth weights from distance to each listed bone segment (necks,
    tails, bodies): w ~ 1/d^power, keeping the `top` strongest."""
    apply_xf(ob)
    segs = _bone_segments(arm_ob)
    groups = {b: ob.vertex_groups.new(name=b) for b in bones}
    for v in ob.data.vertices:
        ds = [(max(_dist_seg(v.co, *segs[b]), 1e-4), b) for b in bones]
        ds.sort()
        ds = ds[:top]
        ws = [1.0 / d ** power for d, _ in ds]
        s = sum(ws)
        for (d, b), w in zip(ds, ws):
            groups[b].add([v.index], w / s, 'REPLACE')
    return ob


def bind(name, arm_ob, parts):
    """Join skinned `parts` into one mesh named `name`, parented to the
    armature with an Armature modifier."""
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    body = parts[0]
    body.name = name
    body.data.name = name
    body.parent = arm_ob
    mod = body.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm_ob
    # merge duplicate material slots that came in with the join
    return body


def join_static(name, parts):
    """Join parts of a prop (no skeleton) into one mesh."""
    for p in parts:
        apply_xf(p)
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    ob = parts[0]
    ob.name = name
    ob.data.name = name
    return ob


# ---------------------------------------------------------------- actions


def action(arm_ob, name, frames, keys, fps=30):
    """Key an action and push it to its own NLA track.

    `keys`: dict frame -> {bone: (rx, ry, rz) degrees | {'rot': (...),
    'loc': (...), 'scale': (...)}}; rotations are bone-local Euler XYZ in
    degrees, locations bone-local metres (bone Y = along the bone).
    Frames are integers at `fps`; the action spans 0..frames.
    """
    scn = bpy.context.scene
    scn.render.fps = fps
    arm_ob.animation_data_create()
    act = bpy.data.actions.new(name)
    arm_ob.animation_data.action = act
    # rest everything at the first key so unlisted bones stay put
    for pb in arm_ob.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    for f in sorted(keys):
        for bn, val in keys[f].items():
            pb = arm_ob.pose.bones[bn]
            rot = val.get('rot') if isinstance(val, dict) else val
            loc = val.get('loc') if isinstance(val, dict) else None
            scl = val.get('scale') if isinstance(val, dict) else None
            if rot is not None:
                pb.rotation_euler = [math.radians(r) for r in rot]
                pb.keyframe_insert('rotation_euler', frame=f)
            if loc is not None:
                pb.location = loc
                pb.keyframe_insert('location', frame=f)
            if scl is not None:
                pb.scale = scl
                pb.keyframe_insert('scale', frame=f)
    act.frame_range = (0, frames)
    act.use_frame_range = True
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.easing = 'AUTO'
    tr = arm_ob.animation_data.nla_tracks.new()
    tr.name = name
    tr.strips.new(name, 0, act)
    arm_ob.animation_data.action = None
    for pb in arm_ob.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    return act


def cycle(frames, poses):
    """Spread poses evenly over a looping action: the last key repeats the
    first so the loop is seamless. Returns a keys dict for action()."""
    n = len(poses)
    keys = {}
    for i, p in enumerate(poses):
        keys[round(frames * i / n)] = p
    keys[frames] = poses[0]
    return keys


# ---------------------------------------------------------------- export


def export_glb(path, objects=None):
    """Export the scene (or `objects`) to a .glb with all NLA actions."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    if objects:
        for o in objects:
            o.select_set(True)
    kw = dict(filepath=path, export_format='GLB', export_apply=False,
              export_animations=True, export_yup=True,
              use_selection=bool(objects), export_materials='EXPORT')
    try:
        bpy.ops.export_scene.gltf(export_nla_strips=True, **kw)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    print('[tdz] wrote', path)
