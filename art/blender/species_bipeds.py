"""species_bipeds.py - iguanodon, parasaur, therizino and galli for
Tommy's Dino Zoo (merged into dinos.py's SPECIES / EGGS automatically).

    cd art/blender
    /Applications/Blender.app/Contents/MacOS/Blender -b -P dinos.py -- \\
        --only galli_baby,galli_juv,galli_adult,egg_galli [--stats]

Who is who (docs/DESIGN.md section 4):
  iguanodon  1.5 m  butter yellow, coral back bumps, ochre spots. Walks on
             four legs (quad plan) and rears up on two: `happy` stands up
             and waves with the thumb spike, `call` rears to call; extra
             loop `stand` (standing on two legs, looking round).
  parasaur   1.7 m  coral peach, sea-teal backward crest (`accent`), rose
             stripes. `call` = head up and three toots through the crest.
  therizino  2.0 m  caramel teddy, fluffy cream tufts (ruff, back, arms,
             thighs, tail plume), tiny head, round belly, long blunt mitten
             claws. `idle` scratches its tummy with a mitten; extra loop
             `scratch` = rubs its back up and down against a tree behind it.
  galli      1.1 m  raspberry pink ostrich runner, lemon feathers, plum
             stripes, big eyes, beak. Fastest runner (4.0 m/s adult);
             bird-like snappy head turns in `idle`.

Walk / run speeds each model was animated for (m/s; root in place, feet
plant at exactly this speed; the build prints the cycle times):

  model             walk m/s (cycle s)   run m/s (cycle s)
  iguanodon_baby    0.80 (0.47)          1.80 (0.37)
  iguanodon_juv     1.00 (0.47)          2.20 (0.40)
  iguanodon_adult   1.20 (0.60)          2.60 (0.53)
  parasaur_baby     0.80 (0.43)          2.00 (0.37)
  parasaur_juv      1.10 (0.50)          2.60 (0.43)
  parasaur_adult    1.40 (0.63)          3.20 (0.57)
  therizino_baby    0.70 (0.50)          1.60 (0.47)
  therizino_juv     0.90 (0.60)          2.00 (0.53)
  therizino_adult   1.10 (0.77)          2.40 (0.73)
  galli_baby        0.80 (0.47)          2.60 (0.30)
  galli_juv         1.30 (0.43)          3.40 (0.33)
  galli_adult       1.80 (0.50)          4.00 (0.43)

Animations: the 12 of ART-SPEC (idle* walk* run* eat drink sleep* happy
pet sit* call play sad*) at 30 fps, every bone keyed every frame, plus the
extras above (iguanodon `stand`* 3.0 s, therizino `scratch`* 2.0 s).
Materials: the 10 roles of the style sample (body, belly, accent, spots,
horn, eye_white, pupil, mouth, tongue, blush).
"""
import math
import os
import sys

from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dino_lib as DL  # noqa: E402

V = Vector
UP = DL.UP
FWD = DL.FWD
TAU = DL.TAU

PAL_COMMON = dict(horn='#fbf3e0', eye_white='#ffffff', pupil='#241c30', mouth='#6a2840',
                  tongue='#f58aa4', blush='#ff9ab8')


def _pal(**kw):
    p = dict(PAL_COMMON)
    p.update(kw)
    return p


# ======================================================================
# local feature helpers (registered into DL.FEATURES under bp_* names)
# ======================================================================

def f_bp_thumbs(D, size=1.0):
    """Iguanodon thumb spikes on the inner side of each front foot (rigid
    to the foot, so they rise and wave when the paw is lifted)."""
    for lg in D.legs:
        if not lg['front']:
            continue
        r = D.L['leg_r'] * D.spec.get('fleg_r', 1.0)
        a, to = lg['ankle'], lg['toe']
        s = lg['side']
        k = size * (0.55 if D.age == 'baby' else 0.8 if D.age == 'juv' else 1.0)
        b = V((a.x - s * r * 0.72, a.y - r * 0.35, lg['foot_h'] * 1.5))
        d = V((-s * 0.35, -0.45, 1.0)).normalized()
        ln = r * 1.35 * k
        D.add(DL.tube('thumb', D.m('horn'), [b - d * r * 0.25, b + d * ln * 0.5, b + d * ln],
                      [r * 0.36 * max(k, 0.7), r * 0.24 * max(k, 0.7), r * 0.07], seg=D.lod(10, 7),
                      sub=2, cap='end'), ('rigid', lg['foot']))
        del to


def f_bp_shoulders(D, size=1.3, front_only=False):
    """Round shoulder / hip balls closing the top of each column leg (so a
    leg lifted off the ground, e.g. a rearing iguanodon's, has no open end)."""
    for lg in D.legs:
        if front_only and not lg['front']:
            continue
        r = D.L['leg_r'] * (D.spec.get('fleg_r', 1.0) if lg['front'] else 1.0) * size
        d = (lg['knee'] - lg['hip']).normalized()
        D.add(DL.ell('shoulder', D.m('body'), lg['hip'] + d * r * 0.15, (r, r, r * 1.1),
                     rot=V((0, 0, 1)).rotation_difference(d).to_matrix(), seg=D.lod(14, 10),
                     rings=D.lod(9, 7)), ('rigid', lg['thigh']))


def f_bp_bands(D, n=4, start=0.15, end=0.75, arc=55, width=0.07, tail=3, mat='spots'):
    """Clean painted bands across the back: thin flat tubes following the
    torso's cross-section over the top (decal stripes shatter on the narrow
    biped torsos). start/end = positions from the middle (0) to the rump
    (1); arc = half-angle of each band round the back; width = fraction of
    the torso's smallest radius."""
    L = D.L
    Ct, (rx, ry, rz) = L['torso_c'], L['torso_r']
    Rt = DL._rotm(L['torso_rot_deg'])
    w = width * min(rx, ry, rz) * (1.15 if D.age == 'baby' else 1.0)
    for i in range(n):
        f = DL.lerp(start, end, i / max(n - 1, 1))
        y0 = ry * f
        k = math.sqrt(max(1 - (y0 / ry) ** 2, 0.05))
        a_ = arc * (1.0 - 0.25 * f)
        pts, nrm = [], []
        for j in range(7):
            psi = math.radians(90 - a_ + 2 * a_ * j / 6)
            q = V((rx * k * math.cos(psi), y0, rz * k * math.sin(psi)))
            nn = V((q.x / rx ** 2, q.y / ry ** 2, q.z / rz ** 2)).normalized()
            pts.append(Ct + Rt @ (q + nn * w * 0.12))
            nrm.append(Rt @ nn)
        tw = [w * (0.55 + 0.45 * math.sin(math.pi * j / 6)) for j in range(7)]
        D.add(DL.tube('band', D.m(mat), pts, tw, seg=6, sub=2, flat=[0.3] * 7, nrm=nrm[3]),
              DL._torso_skin(D))
    # the same bands over the tail
    tp = L['tail_pts']
    tr0 = L['tail_r']
    tip = D.spec['tail'].get('tip', 0.16)
    fl = D.spec['tail'].get('flat', 0.85)
    for i in range(tail):
        f = (i + 1) / (tail + 1.3)
        kk = f * (len(tp) - 1)
        j = min(int(kk), len(tp) - 2)
        c = tp[j].lerp(tp[j + 1], kk - j)
        d = (tp[j + 1] - tp[j]).normalized()
        up = (UP - d * d.dot(UP)).normalized()
        sx = d.cross(up).normalized()
        n_ = len(tp) - 1
        # radius of the tail tube here (build_tail: lerp(1, tip, (i/(n-1))**0.9) over n+1 points)
        r = tr0 * DL.lerp(1.0, tip, ((kk + 1) / (n_ + 1)) ** 0.9) * 1.03
        a_ = 62
        pts = []
        for q in range(7):
            psi = math.radians(90 - a_ + 2 * a_ * q / 6)
            pts.append(c + sx * math.cos(psi) * r + up * math.sin(psi) * r * fl)
        tw = [w * 0.8 * (0.55 + 0.45 * math.sin(math.pi * q / 6)) * (1 - 0.3 * f) for q in range(7)]
        D.add(DL.tube('tband', D.m(mat), pts, tw, seg=6, sub=2, flat=[0.3] * 7, nrm=up),
              ('near', ['root'] + D.tail, 4.0, 2))


def f_bp_bumps(D, n=6, size=0.22, start=0.1, end=0.85, tail=3, mat='accent'):
    """Round low bumps along the back and tail (iguanodon): like the ridge
    but soft domes."""
    L = D.L
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = DL._rotm(L['torso_rot_deg'])
    sz = size * tr[2] * D.A['plate']
    for i in range(n):
        f = DL.lerp(start, end, i / max(n - 1, 1))
        el = DL.lerp(40, 90, f / 0.5) if f < 0.5 else DL.lerp(90, 40, (f - 0.5) / 0.5)
        p, nrm = DL.on_ell(V((0, 0, 0)), tr, 0 if f < 0.5 else 180, el)
        p, nrm = Ct + Rt @ p, Rt @ nrm
        s = sz * (0.65 + 0.35 * math.sin(math.pi * f))
        D.add(DL.ell('bump', D.m(mat), p + nrm * s * 0.22, (s * 0.55, s * 0.72, s * 0.62),
                     rot=DL.frame(nrm, V((0, 1, 0))), seg=D.lod(14, 10), rings=D.lod(9, 7)), DL._torso_skin(D))
    pts = L['tail_pts']
    trr = L['tail_r']
    for i in range(tail):
        f = (i + 0.5) / (tail + 0.6)
        k = f * (len(pts) - 1)
        j = min(int(k), len(pts) - 2)
        p = pts[j].lerp(pts[j + 1], k - j)
        r = trr * DL.lerp(1.0, 0.25, f) * D.spec['tail'].get('flat', 0.85)
        s = sz * DL.lerp(0.65, 0.35, f)
        D.add(DL.ell('tbump', D.m(mat), p + UP * r * 0.9, (s * 0.5, s * 0.7, s * 0.55),
                     seg=D.lod(14, 10), rings=D.lod(9, 7)), ('near', ['root'] + D.tail, 4.0, 2))


def f_bp_crest(D, length=1.7, r=0.22, el=58, rise=0.42, mat='accent'):
    """Parasaurolophus crest: a long rounded tube from the top of the head
    sweeping backwards (length, r = fractions of the mean head radius).
    Babies have a short nub, juveniles a medium one."""
    L = D.L
    hc, hr = L['head_c'], L['head_r']
    hm = sum(hr) / 3
    k = {'baby': 0.42, 'juv': 0.72}.get(D.age, 1.0)
    p, n = DL.on_ell(hc, hr, 180, el)
    p2, _ = DL.on_ell(hc, hr, 0, 70)
    b = p.lerp(p2, 0.45) - n * hm * 0.1
    ln = length * hm * k
    rr = r * hm * (0.8 + 0.2 * k)
    pts = [b, b + V((0, ln * 0.35, ln * rise * 0.55)), b + V((0, ln * 0.72, ln * rise * 0.85)),
           b + V((0, ln, ln * rise * 0.95))]
    D.add(DL.tube('crest', D.m(mat), pts, [rr * 1.15, rr, rr * 0.92, rr * 0.82], seg=D.lod(14, 10),
                       sub=3, cap='end', flat=[0.95, 0.9, 0.85, 0.85], nrm=V((1, 0, 0))), ('rigid', 'head'))


def _puff(D, mat, base, d, length, width, how, out=None, flat=0.75, sink=0.3, seg=16, rings=10):
    """One soft fluff puff: a smooth teardrop ellipsoid lying along `d` (the
    pointed end), flattened along `out` (the surface normal), its root
    sunk into the body."""
    from mathutils import Matrix
    y = V(d).normalized()
    o = V(out) if out is not None else UP
    z = o - y * o.dot(y)
    if z.length < 1e-4:
        z = V((1, 0, 0)) - y * y.x
    z.normalize()
    x = y.cross(z)
    Rm = Matrix((x, y, z)).transposed()

    def tear(u):
        k = 1.0 - 0.38 * max(u.y, 0.0) ** 2
        u.x *= k
        u.z *= k
        return u
    c = base + y * length * (0.5 - sink * 0.5)
    D.add(DL.ell('puff', D.m(mat), c, (width, length * 0.5, width * flat), rot=Rm,
                 seg=D.lod(seg, 10), rings=D.lod(rings, 7), deform=tear), how)


def f_bp_fluff(D, mane=7, back=2, mat='accent'):
    """Therizinosaur fluff: a few big soft puffs (a mane round the neck base
    running down the back, elbow and thigh fringes, a pom-pom tail and a
    head tuft) - few and round so they read as fluff, not spikes."""
    L = D.L
    baby = D.age == 'baby'
    if baby:
        mane, back = 5, 1
    pts = L['neck_pts']
    nr = L['neck_r']
    d = (pts[1] - pts[0]).normalized()
    ax = V((1, 0, 0))
    bk = d.cross(ax).normalized()           # the back side of the neck
    if bk.dot(V((0, 1, 0))) < 0:
        bk = -bk
    c0 = pts[0].lerp(pts[1], 0.3)
    for j in range(mane):
        a = math.radians(-105 + 210 * j / max(mane - 1, 1))
        o = (bk * math.cos(a) + ax * math.sin(a)).normalized()
        b = c0 + o * nr * 0.85
        dd = (o * 0.55 - d * 0.75).normalized()
        ln = nr * (1.25 + 0.15 * math.cos(a))
        _puff(D, mat, b, dd, ln, ln * 0.5, ('near', ['spine'] + D.neck, 4.0, 2), out=o)
    Ct, tr = L['torso_c'], L['torso_r']
    Rt = DL._rotm(L['torso_rot_deg'])
    for i in range(back):
        p, n = DL.on_ell(V((0, 0, 0)), tr, 180, 58 - 22 * i)
        p, n = Ct + Rt @ p, Rt @ n
        dd = (V((0, 0.3, -1.0)) - n * n.dot(V((0, 0.3, -1.0)))).normalized()
        ln = min(tr) * (0.75 - 0.12 * i)
        _puff(D, mat, p - dd * ln * 0.25, dd, ln, ln * 0.5, DL._torso_skin(D), out=n)
    ar = L['arm_r']
    for a in D.arms:
        b = a['sh'].lerp(a['el'], 0.75) + V((a['side'] * ar * 0.3, ar * 0.6, 0))
        dd = V((a['side'] * 0.15, 0.55, -0.85)).normalized()
        ln = ar * 2.6
        _puff(D, mat, b, dd, ln, ln * 0.45, ('rigid', a['arm']), out=V((a['side'], 0.8, 0)), seg=12, rings=8)
    for lg in D.legs:
        hip, knee = lg['hip'], lg['knee']
        b = hip.lerp(knee, 0.45) + V((lg['side'] * L['leg_r'] * 0.9, L['leg_r'] * 1.5, 0))
        dd = V((lg['side'] * 0.2, 0.3, -1.0)).normalized()
        ln = L['leg_r'] * 2.6
        _puff(D, mat, b, dd, ln, ln * 0.48, ('rigid', lg['thigh']), out=V((lg['side'], 0.7, 0)), seg=12, rings=8)
    # pom-pom tail
    tp = L['tail_pts']
    trr = L['tail_r']
    dt = (tp[-1] - tp[-2]).normalized()
    tip = tp[-1] - dt * trr * 0.6
    _puff(D, mat, tip, (dt + UP * 0.15), trr * 3.0, trr * 1.15, ('rigid', D.tail[-1]), out=UP,
          sink=0.15, seg=18, rings=11)
    if not baby:
        for sd in (1, -1):
            _puff(D, mat, tip - dt * trr * 0.4, (dt + V((sd * 0.55, 0, -0.1))), trr * 2.2, trr * 0.8,
                  ('rigid', D.tail[-1]), out=V((sd, 0, 0.4)), sink=0.2, seg=12, rings=8)
    # head tuft
    hc, hr = L['head_c'], L['head_r']
    for i, (az, el, sz) in enumerate(((0, 72, 1.0), (180, 62, 0.8))):
        p, n = DL.on_ell(hc, hr, az, el)
        dd = (n * 0.75 + V((0, 0.65, 0))).normalized()
        ln = hr[2] * 0.8 * sz * D.A['crest']
        _puff(D, mat, p - n * hr[2] * 0.06, dd, ln, ln * 0.42, ('rigid', 'head'), out=V((1, 0, 0)),
              flat=0.6, sink=0.15, seg=10, rings=6)


def f_bp_mittens(D, n=3, length=3.2, r=0.5):
    """Long blunt claws like soft mittens (therizino): rounded capsules
    hanging from each hand (length, r = fractions of the arm radius)."""
    L = D.L
    ar = L['arm_r']
    k = {'baby': 0.6, 'juv': 0.82}.get(D.age, 1.0)
    for a in D.arms:
        el, hd = a['el'], a['hand']
        d = (hd - el).normalized()
        down = (d * 0.55 - UP * 0.85).normalized()
        side = V((a['side'], 0, 0))
        for i in range(n):
            u = (-1 + 2 * i / max(n - 1, 1)) if n > 1 else 0.0
            b = hd + d * ar * 0.55 + side * u * ar * 0.55 - UP * ar * 0.2
            ln = ar * length * k * (1.0 - 0.15 * abs(u))
            dd = (down + side * u * 0.12).normalized()
            curl = dd + d * 0.45
            pts = [b, b + dd * ln * 0.55, b + dd * ln * 0.8 + curl.normalized() * ln * 0.2]
            rr = ar * r * (0.85 + 0.15 * k)
            D.add(DL.tube('mitten', D.m('horn'), pts, [rr, rr * 0.9, rr * 0.72], seg=D.lod(9, 7), sub=2,
                          cap=True), ('rigid', a['forearm']))


def f_bp_beak(D, mat='horn', size=1.0):
    """A small rounded bird beak covering the snout tip (gallimimus)."""
    L = D.L
    snc, snr = L['snout_c'], L['snout_r']
    c = snc + FWD * snr[1] * 0.50 + UP * snr[2] * 0.02

    def tip(u):
        if u.y < 0:
            u.x *= 1.0 + 0.32 * u.y
            u.z *= 1.0 + 0.18 * u.y
        return u
    D.add(DL.ell('beak', D.m(mat), c, (snr[0] * 0.82 * size, snr[1] * 0.62 * size, snr[2] * 0.80 * size),
                 seg=D.lod(16, 10), rings=D.lod(10, 6), deform=tip,
                 keep=lambda u: u.y < 0.25), ('rigid', 'head'))


DL.FEATURES.update({'bp_thumbs': f_bp_thumbs, 'bp_bands': f_bp_bands, 'bp_shoulders': f_bp_shoulders, 'bp_bumps': f_bp_bumps, 'bp_crest': f_bp_crest,
                    'bp_fluff': f_bp_fluff, 'bp_mittens': f_bp_mittens, 'bp_beak': f_bp_beak})


# ======================================================================
# animation helpers
# ======================================================================

def _rear(M, P, ang, wave_side=0, wave=0.0, paws=1.0):
    """Quad rearing up onto the hind legs by `ang` degrees (nose up), the
    front paws tucked at the chest; `wave_side` (+1 L / -1 R) lifts that
    paw high, `wave` in -1..1 swings it side to side."""
    D, L, R = M.D, M.D.L, M.D.R
    if ang <= 1e-3 and not wave_side:
        return P
    P.r('root', -ang, 0, 0)
    P.at('root', (0, -M.legl * 0.04 * ang / 50.0, M.legl * 0.04 * ang / 50.0))
    # tail stays off the ground, neck and head level out
    P.r(D.tail[0], ang * 0.75)
    M.spread(P, D.tail[1:], ang * 0.2)
    M.spread(P, D.neck, ang * 0.42)
    P.r('head', ang * 0.32)
    pivot = L['root'] + P.loc.get('root', V((0, 0, 0)))
    q = Quaternion(V((1, 0, 0)), math.radians(-ang))
    k = DL.clamp(ang / 50.0, 0.0, 1.0)
    for lg in D.legs:
        if not lg['front']:
            continue
        lf = R.len[lg['thigh']] + R.len[lg['shin']]
        sh = pivot + q @ (lg['hip'] - L['root'])
        s = lg['side']
        tuck = sh + V((s * lf * 0.08, -lf * 0.5, -lf * 0.32)) * paws
        tgt = lg['ankle'].lerp(tuck, k)
        pitch = -55 * k
        yaw = 0.0
        if wave_side == s:
            hi = sh + V((s * lf * (0.28 + 0.16 * wave), -lf * 0.45, lf * 0.35))
            tgt = tgt.lerp(hi, k)
            pitch = -95 * k
            yaw = s * 25 * wave * k
        P.feet[lg['tag']] = (tgt, pitch, yaw)
    return P


def igu_happy(M):
    T = 1.0
    D = M.D

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        up = DL.env(t, 0.0, 0.24, 0.8, 1.0)
        wv = math.sin(TAU * (t - 0.24) / 0.28) * DL.env(t, 0.24, 0.3, 0.72, 0.8)
        _rear(M, P, 54 * up, wave_side=1, wave=wv)
        P.r('head', -6 * up, -8 * up, 10 * up + 4 * wv * up, post=True)
        M.tail(P, t, 1.0 / 3, yaw=20, pitch=4, lag=0.5)
        P.jaw = 9 * DL.env(t, 0.15, 0.3, 0.75, 0.95)
        P.lid = DL.env(t, 0.52, 0.58, 0.66, 0.74)
        return P
    return T, g


def igu_call(M):
    T, base = M.call()

    def g(t):
        P = base(t)
        up = DL.env(t, 0.05, 0.3, 0.75, 0.98)
        _rear(M, P, 34 * up)
        return P
    return T, g


def igu_stand(M):
    """Extra loop: standing up on the hind legs, looking around."""
    T = 3.0
    D = M.D

    def g(t):
        P = M.base(t, T, breath=2, amp=0.8)
        _rear(M, P, 52 + 1.5 * DL.wave(t, T / 2))
        look = DL.tl(t, [(0, 0), (0.4, 0), (0.8, 20), (1.5, 20), (1.9, -16), (2.5, -16), (2.9, 0), (3.0, 0)])
        M.spread(P, D.neck, 0, look * 0.45, post=True)
        P.r('head', 0, look * 0.55, look * 0.15, post=True)
        M.tail(P, t, T, yaw=10, pitch=2, lag=0.6)
        P.lid = M.blink(t, 1.2, 2.6)
        P.jaw = 3 + 2 * DL.wave(t, T / 2)
        return P
    return T, g


def para_call(M):
    """Head up, the crest becomes a trumpet: inhale, then three toots."""
    T = 1.0
    D = M.D

    def g(t):
        P = M.base(t, T, breath=1, amp=0.3)
        inh = DL.env(t, 0.0, 0.16, 0.16, 0.28)
        upw = DL.env(t, 0.1, 0.28, 0.86, 1.0)
        toot = 0.0
        for t0 in (0.32, 0.5, 0.68):
            toot = max(toot, DL.env(t, t0, t0 + 0.04, t0 + 0.09, t0 + 0.15))
        M.spread(P, D.neck, 6 * inh - 24 * upw)
        P.r('head', 6 * inh - 26 * upw - 5 * toot, 0, 4 * math.sin(TAU * t * 2) * upw)
        P.r('root', 3 * inh - 4 * upw, 0, 0)
        P.sc('root', (1 + 0.05 * inh + 0.03 * toot, 1, 1 + 0.03 * inh + 0.04 * toot))
        P.at('root', (0, 0, M.legl * 0.04 * toot))
        P.jaw = 4 * inh + 6 * upw + 10 * toot
        P.lid = DL.env(t, 0.26, 0.32, 0.82, 0.9)
        M.spread(P, D.tail, -6 * upw)
        M.tail(P, t, 1.0 / 3, yaw=8 * upw, lag=0.5)
        M.arms(P, -30 * upw, 0, 15 * upw, fp=-25 * upw - 10 * toot)
        return P
    return T, g


def theri_idle(M):
    """Base idle plus a slow tummy scratch with the right mitten."""
    T, base = M.idle()

    def g(t):
        P = base(t)
        e = DL.env(t, 0.5, 0.85, 2.0, 2.4)
        sc = math.sin(TAU * t * 3.0) * e
        P.r('arm.R', -38 * e, -14 * e, 0)
        P.r('forearm.R', -30 * e + 14 * sc, 0, 0)
        P.r('head', 6 * e, 0, -6 * e, post=True)
        P.lid = max(P.lid, 0.6 * DL.env(t, 0.9, 1.1, 1.9, 2.1))
        P.jaw += 6 * e
        return P
    return T, g


def theri_scratch(M):
    """Extra loop: back to a tree, rubbing up and down, blissful."""
    T = 2.0
    D = M.D

    def g(t):
        P = M.base(t, T, breath=2, amp=0.5)
        u = math.sin(TAU * t / (T / 2))         # two rubs per loop
        w = math.sin(TAU * t / T)
        P.r('root', -9 + 2 * u, 6 * w, 7 * w)
        P.at('root', (0, M.legl * 0.06, -M.legl * (0.07 + 0.06 * (0.5 + 0.5 * u))))
        P.r('spine', -4, -4 * w, -4 * w)
        M.spread(P, D.neck, 6, -6 * w, 0)
        P.r('head', -10, 0, 10 * w)
        M.arms(P, -30, -10, 12, fp=-35)
        M.tail(P, t, T / 2, yaw=14, pitch=4, lag=0.5)
        P.lid = 1.0
        P.jaw = 10 + 4 * u
        return P
    return T, g


def galli_idle(M):
    """Bird-like idle: quick snappy head turns between still holds."""
    T = 3.0
    D = M.D

    def snap(t, keys):
        # holds with fast (0.08 s) transitions
        v = keys[0][1]
        for t0, val in keys[1:]:
            v = v + (val - v) * DL.smooth((t - t0) / 0.08)
        return v

    def g(t):
        P = M.base(t, T)
        look = snap(t, [(0, 0), (0.5, 26), (1.05, -8), (1.5, -30), (2.1, 10), (2.6, 0)])
        tilt = snap(t, [(0, 0), (0.5, 10), (1.05, 0), (1.5, -12), (2.1, 6), (2.6, 0)])
        nod = snap(t, [(0, 0), (1.05, 8), (1.5, -2), (2.1, 4), (2.6, 0)])
        M.spread(P, D.neck, nod * 0.5, look * 0.4)
        P.r('head', nod * 0.5, look * 0.6, tilt)
        M.tail(P, t, T / 2, yaw=10, pitch=3, lag=0.6)
        P.lid = M.blink(t, 0.8, 2.3)
        P.jaw = 1.5
        M.arms(P, -4 * DL.wave(t, T / 2), 0, 3)
        return P
    return T, g


def galli_happy(M):
    """A bouncy double hop with a fluff-up shake."""
    T, base = M.happy()

    def g(t):
        P = base(t)
        sh = math.sin(TAU * t * 6) * DL.env(t, 0.55, 0.65, 0.85, 0.98)
        P.r('root', 0, 0, 6 * sh, post=True)
        P.r('head', 0, 10 * sh, 0, post=True)
        return P
    return T, g


# ======================================================================
# species
# ======================================================================

IGUANODON = dict(
    id='iguanodon', plan='quad', height=1.5, lod=0.85,
    pal=_pal(body='#f2cf6b', belly='#fbf0d6', accent='#ff8466', spots='#e09a42'),
    torso=(0.33, 0.50, 0.32), leg=0.34, fleg=0.25, leg_r=0.10, fleg_r=0.78, knee=0.06,
    hip_y=0.50, sh_y=0.52, leg_x=0.52, neck_z=0.38,
    neck_len=0.36, neck_deg=64, neck_deg2=30, neck_n=2, neck_r=0.48,
    head=dict(r=(0.22, 0.27, 0.22), off=(0.40, 0.25), snout=(0.68, 0.90, 0.60),
              snout_fwd=0.55, snout_drop=0.22, snout_taper=(0.12, 0.10),
              smile=dict(width=66, z=-0.30, curl=0.26)),
    eye=dict(r=0.28, az=40, el=18, flat=0.5, gaze=0.18),
    tail=dict(len=0.78, r=0.50, n=4, droop_deg=16, droop2_deg=-4, tip=0.16, flat=0.85),
    toes=3,
    parts=[
        ('bp_bumps', dict(n=6, size=0.24, start=0.12, end=0.88, tail=3)),
        ('bp_thumbs', dict(size=1.0)),
        ('bp_shoulders', dict()),
        ('spots', dict(spots=[(180, 62, 0.26), (150, 42, 0.20), (210, 42, 0.20), (120, 25, 0.15),
                              (240, 25, 0.15), (40, 55, 0.15), (320, 55, 0.15), (165, 80, 0.16)])),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}),
    anims={'happy': igu_happy, 'call': igu_call, 'stand': igu_stand},
    speeds={'baby': (0.8, 1.8), 'juv': (1.0, 2.2), 'adult': (1.2, 2.6)},
)

PARASAUR = dict(
    id='parasaur', plan='biped', height=1.7, lod=0.9,
    pal=_pal(body='#f6a283', belly='#fbecd8', accent='#2fb7c4', spots='#e46f86'),
    torso=(0.38, 0.46, 0.40), tilt_deg=24, t_fwd=0.2, leg=0.42, leg_r=0.11, knee=0.2,
    thigh_r=1.75, foot_len=1.5, arm_len=0.62, arm_r=0.15, arm_z=0.0,
    neck_len=0.20, neck_deg=66, neck_deg2=30, neck_n=2, neck_r=0.55,
    head=dict(r=(0.26, 0.30, 0.25), off=(0.42, 0.22), snout=(0.84, 0.80, 0.50),
              snout_fwd=0.5, snout_drop=0.20, snout_taper=(-0.10, 0.18),
              smile=dict(width=74, z=-0.30, curl=0.28)),
    eye=dict(r=0.29, az=40, el=24, flat=0.5, gaze=0.2),
    tail=dict(len=0.95, r=0.48, n=4, droop_deg=14, droop2_deg=-6, tip=0.2, flat=0.95),
    toes=3,
    parts=[
        ('bp_crest', dict(length=1.9, r=0.22, rise=0.34)),
        ('bp_bands', dict(n=4, start=-0.2, end=0.55, arc=44, width=0.09, tail=3)),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}),
    anims={'call': para_call},
    age_tweak={'baby': dict(lod=0.62)},
    speeds={'baby': (0.8, 2.0), 'juv': (1.1, 2.6), 'adult': (1.4, 3.2)},
)

THERIZINO = dict(
    id='therizino', plan='biped', height=2.0, lod=0.78,
    pal=_pal(body='#cf9c78', belly='#fbecd6', accent='#f9e2c4', spots='#a8714f'),
    torso=(0.44, 0.44, 0.50), tilt_deg=38, t_fwd=0.15, t_up=0.5, leg=0.40, leg_r=0.13, knee=0.18,
    thigh_r=1.9, foot_len=1.5, arm_len=1.05, arm_r=0.15, arm_z=0.15,
    belly_r=(0.84, 0.82, 0.88), belly_off=(0.0, -0.28, -0.08),
    neck_len=0.34, neck_deg=82, neck_deg2=42, neck_n=2, neck_r=0.42, neck_taper=0.75,
    head=dict(r=(0.18, 0.21, 0.18), off=(0.42, 0.25), snout=(0.62, 0.66, 0.55),
              snout_fwd=0.5, snout_drop=0.2, snout_taper=(0.3, 0.15),
              smile=dict(width=60, z=-0.30, curl=0.26)),
    eye=dict(r=0.31, az=40, el=20, flat=0.5, gaze=0.2),
    tail=dict(len=0.62, r=0.42, n=3, droop_deg=24, droop2_deg=4, tip=0.3, flat=0.9),
    toes=3,
    parts=[
        ('bp_fluff', dict()),
        ('bp_mittens', dict()),
        ('bp_bands', dict(n=0, tail=2, width=0.1)),
    ],
    moves=dict(stance={'head': (-4, 0, 0), 'forearm.L': (28, 0, 0), 'forearm.R': (28, 0, 0)}),
    anims={'idle': theri_idle, 'scratch': theri_scratch},
    age_tweak={'baby': dict(lod=0.48)},
    speeds={'baby': (0.7, 1.6), 'juv': (0.9, 2.0), 'adult': (1.1, 2.4)},
)

GALLI = dict(
    id='galli', plan='biped', height=1.1, lod=0.9,
    pal=_pal(body='#ea86b4', belly='#fdeee0', accent='#ffd650', spots='#bd5a98'),
    torso=(0.22, 0.28, 0.22), tilt_deg=18, t_fwd=0.2, leg=0.58, leg_r=0.06, knee=0.28,
    thigh_r=1.55, foot_len=1.9, arm_len=0.62, arm_r=0.15, arm_z=0.0,
    neck_len=0.44, neck_deg=84, neck_deg2=40, neck_n=3, neck_r=0.40, neck_taper=0.72,
    head=dict(r=(0.19, 0.22, 0.18), off=(0.42, 0.25), snout=(0.58, 0.82, 0.46),
              snout_fwd=0.5, snout_drop=0.18, snout_taper=(0.32, 0.15), jaw_mat='horn',
              smile=dict(width=60, z=-0.30, curl=0.24)),
    eye=dict(r=0.36, az=44, el=22, flat=0.5, gaze=0.2),
    tail=dict(len=0.85, r=0.42, n=4, droop_deg=6, droop2_deg=-10, tip=0.2, flat=0.8),
    toes=3,
    parts=[
        ('feathers', dict(crest=[(0.0, 0.9, 0.8, 0.18), (-0.25, 0.65, 0.7, 0.14), (0.25, 0.65, 0.7, 0.14)],
                          arms=2, tail_tuft=3)),
        ('bp_beak', dict()),
        ('bp_bands', dict(n=3, start=-0.1, end=0.55, arc=46, width=0.09, tail=3)),
    ],
    moves=dict(stance={'head': (-4, 0, 0)}),
    anims={'idle': galli_idle, 'happy': galli_happy},
    age_tweak={'baby': dict(lod=0.56)},
    speeds={'baby': (0.8, 2.6), 'juv': (1.3, 3.4), 'adult': (1.8, 4.0)},
)

SPECIES = {'iguanodon': IGUANODON, 'parasaur': PARASAUR, 'therizino': THERIZINO, 'galli': GALLI}
EGGS = {
    'iguanodon': dict(shell='#fbe9ad', spots='#f07f5c'),
    'parasaur': dict(shell='#fde3d6', spots='#2fb7c4'),
    'therizino': dict(shell='#f2dcc2', spots='#a8714f'),
    'galli': dict(shell='#fde6f0', spots='#e270a6'),
}
