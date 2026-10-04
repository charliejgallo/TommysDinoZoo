"""test_pipeline.py - smallest rigged, animated model through the whole
Blender -> glb -> Godot path (a blob dino with a wagging tail)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdz_common as C  # noqa: E402

A = C.args()
out = A.get('out', os.path.join(os.path.dirname(__file__), '..', '..',
                                'game', 'assets', 'models'))
C.reset()
body_m = C.mat('body', '#7ccf6a')
belly_m = C.mat('belly', '#f3e6b0')
eye_m = C.mat('pupil', '#1d1b22', rough=0.2)

arm = C.armature('blob_rig', [
    ('root', (0, 0, 0), (0, 0, 0.3), None),
    ('head', (0, -0.15, 0.45), (0, -0.25, 0.7), 'root'),
    ('tail1', (0, 0.2, 0.3), (0, 0.45, 0.25), 'root'),
    ('tail2', (0, 0.45, 0.25), (0, 0.7, 0.22), 'tail1'),
])
body = C.ellipsoid('body', body_m, (0, 0, 0.3), (0.22, 0.28, 0.22))
belly = C.ellipsoid('belly', belly_m, (0, -0.06, 0.26), (0.17, 0.2, 0.17))
head = C.ellipsoid('head', body_m, (0, -0.25, 0.58), (0.17, 0.17, 0.15))
tail = C.tube('tail', body_m, [(0, 0.2, 0.3), (0, 0.45, 0.26),
                               (0, 0.7, 0.24)], [0.13, 0.08, 0.03])
eye = C.ellipsoid('eye', eye_m, (0.08, -0.39, 0.63), (0.03, 0.02, 0.04))
eye2 = C.mirror_x(eye)
for p in (body, belly):
    C.skin_rigid(p, 'root')
for p in (head, eye, eye2):
    C.skin_rigid(p, 'head')
C.skin_near(tail, arm, ['tail1', 'tail2'])
C.bind('blob', arm, [body, belly, head, eye, eye2, tail])
C.action(arm, 'idle', 30, C.cycle(30, [
    {'tail1': (0, 0, 20), 'tail2': (0, 0, 25), 'head': (5, 0, 0)},
    {'tail1': (0, 0, -20), 'tail2': (0, 0, -25), 'head': (-5, 0, 0)},
]))
C.action(arm, 'hop', 20, {
    0: {'root': {'loc': (0, 0, 0)}},
    10: {'root': {'loc': (0, 0.25, 0)}},  # bone-local Y = world up here
    20: {'root': {'loc': (0, 0, 0)}},
})
C.export_glb(os.path.join(out, 'test_blob.glb'))
