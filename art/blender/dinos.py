"""dinos.py - the species of Tommy's Dino Zoo, built with dino_lib.

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P dinos.py -- \\
        [--only trike_adult,trike_baby,egg_trike] [--out ../../game/assets/models]
        [--list]

Each species is one dict of adult numbers (lengths in nominal units: the
model is scaled afterwards so the top of its head stands at `height` metres;
ages re-proportion it first, see dino_lib.AGES). Parts are feature names
from dino_lib.FEATURES with their options.

Walk / run speeds each model was animated for (m/s; root stays in place,
the game moves the node at this speed so the feet do not slide):
  SPEEDS_DOC (filled in below and printed by --list)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dino_lib as DL  # noqa: E402
import tdz_common as C  # noqa: E402

# --------------------------------------------------------------------------
# Triceratops: the starter dino. Lilac body, cream belly, orange frill with
# teal spots (the Monster Hop trike, softer). Pushes the ball with its horns.
# --------------------------------------------------------------------------
TRIKE = dict(
    id='trike', plan='quad', height=1.4,
    pal=dict(body='#ac95d8', belly='#f7ebd3', accent='#f8963c', spots='#3cb6a6',
             horn='#fbf0d4', eye_white='#ffffff', pupil='#2b2033', mouth='#6e2c48',
             tongue='#f48aa2', blush='#ff9ab8'),
    torso=(0.36, 0.48, 0.32), leg=0.17, leg_r=0.095, knee=0.05,
    neck_len=0.10, neck_deg=35, neck_n=1, neck_r=0.52,
    head=dict(r=(0.25, 0.24, 0.23), off=(0.40, 0.30), snout=(0.60, 0.62, 0.58),
              snout_fwd=0.60, snout_drop=0.30, cheeks=(0.55, 0.15, 0.25, 0.42)),
    eye=dict(r=0.27, az=40, el=16, flat=0.55, gaze=0.18),
    tail=dict(len=0.42, r=0.52, n=3, droop_deg=28, droop2_deg=2, tip=0.18),
    parts=[
        ('frill', dict(r=1.62, tilt_deg=38, span_deg=232, scallops=7, up=0.42, back=0.35)),
        ('horns', dict(horns=[
            dict(az=26, el=50, len=1.25, r=0.17, dir=(0.12, -0.45, 0.88), curl=(0.0, -1.0, 0.15),
                 mirror=True),
            dict(on='snout', az=0, el=58, len=0.5, r=0.17, dir=(0, -0.3, 0.95), curl=(0, -1, 0.3)),
        ])),
        ('beak', dict()),
        ('spots', dict(spots=[(180, 62, 0.30), (150, 45, 0.22), (210, 45, 0.22),
                              (165, 80, 0.20), (120, 30, 0.16), (240, 30, 0.16),
                              (35, 70, 0.16), (325, 70, 0.16)])),
    ],
    speeds={'baby': (0.8, 1.8), 'juv': (1.0, 2.2), 'adult': (1.2, 2.6)},
)

SPECIES = {'trike': TRIKE}
EGGS = {'trike': dict(shell='#f8eedb', spots='#b49ade')}


def build_one(name, out):
    if name.startswith('egg_'):
        return build_egg(name[4:], out)
    sid, age = name.rsplit('_', 1)
    D = DL.Dino(SPECIES[sid], age)
    D.build()
    DL.animate(D)
    path = os.path.join(out, name + '.glb')
    DL.export_glb(path)
    print('[dino] %s tris=%d bones=%d mats=%d' % (name, DL.tris(D.body), len(D.R.names),
                                                  len(D.body.data.materials)))
    for a, (f, t) in D.actions.items():
        print('[dino]   %-6s %3d frames %.2f s' % (a, f, t))
    for k, (v, T) in D.speeds.items():
        print('[dino]   speed %s %.2f m/s cycle %.2f s' % (k, v, T))
    return D


def build_egg(sid, out):
    import math
    from mathutils import Vector as V
    C.reset()
    e = EGGS[sid]
    shell = C.mat('body', e['shell'])
    spot = C.mat('spots', e['spots'])
    h = 0.25
    arm = DL.make_armature('egg_rig', [dict(name='root', head=(0, 0, 0), tail=(0, 0, h * 0.5))])

    def egg(u):
        # narrower top, rounder bottom
        k = 1.0 - 0.18 * u.z
        return V((u.x * k, u.y * k, u.z))
    ob = DL.ell('egg', shell, (0, 0, h * 0.5), (h * 0.37, h * 0.37, h * 0.5), seg=24, rings=16,
                deform=egg)
    parts = [ob]
    for i, (az, el, s) in enumerate([(20, 30, 0.22), (130, 10, 0.18), (250, 40, 0.2), (200, -20, 0.16),
                                     (310, -5, 0.17), (80, -30, 0.15), (0, 70, 0.12), (170, 55, 0.14)]):
        p, n = DL.on_ell((0, 0, h * 0.5), (h * 0.37 * (1 - 0.18 * math.sin(math.radians(el))),) * 2 +
                         (h * 0.5,), az, el)
        parts.append(DL.decal('spot', spot, ob, p, n, h * s * 0.45, lift=0.0015))
    for p in parts:
        C.skin_rigid(p, 'root')
    body = C.bind('egg_' + sid, arm, parts)
    DL.dedupe_slots(body)

    class E:
        pass
    D = E()
    D.R = DL.Rig(arm, {})
    D.arm, D.eyes, D.legs, D.actions = arm, [], [], {}

    def still(t):
        return DL.Pose()

    def wobble(t):
        P = DL.Pose()
        k = DL.env(t, 0.0, 0.1, 0.7, 1.0)
        P.r('root', 4 * math.sin(DL.TAU * t * 2.2 + 0.4) * k, 0, 9 * math.sin(DL.TAU * t * 3) * k)
        P.at('root', (0, 0, 0.004 * abs(math.sin(DL.TAU * t * 3)) * k))
        return P
    DL.key_action(D, 'idle', 30, still)
    DL.key_action(D, 'wobble', 30, wobble)
    path = os.path.join(out, 'egg_%s.glb' % sid)
    DL.export_glb(path)
    print('[dino] egg_%s tris=%d' % (sid, DL.tris(body)))


def main():
    A = C.args()
    out = A.get('out', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                                    'game', 'assets', 'models'))
    only = A.get('only')
    names = only.split(',') if isinstance(only, str) else \
        ['%s_%s' % (s, a) for s in SPECIES for a in ('baby', 'juv', 'adult')] + \
        ['egg_' + s for s in EGGS]
    for n in names:
        build_one(n, out)


main()
