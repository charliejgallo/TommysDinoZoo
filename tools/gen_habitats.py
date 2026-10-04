#!/usr/bin/env python3
"""Lay out the decoration and furniture of each habitat into
game/content/base/map.json ("habitat_props"), deterministically.

Each habitat gets: its basics near the gate (trough, water trough, a bed),
a few signature pieces at hand-picked spots, and scattered nature that
avoids the gate path, the pond, the fences and everything else (1 m grid).
Bump REV when the layout changes: old saves get the new pieces added.
"""
import json
import math
import random

REV = 1
MAP = 'game/content/base/map.json'
PACK = 'game/content/base/pack.json'
m = json.load(open(MAP))
pack = json.load(open(PACK))
props = pack['props']


def size(pid):
    return props[pid]['size']


class Zone:
    def __init__(self, zid):
        z = m['zones'][zid]
        self.id = zid
        self.x0, self.z0, self.x1, self.z1 = z['rect']
        self.gate = z['gate']
        self.used = set()
        self.out = []
        # keep a corridor from the gate to the centre clear
        cx, cz = (self.x0 + self.x1) / 2, (self.z0 + self.z1) / 2
        gx, gz = self.gate
        for t in range(0, 101):
            x = gx + (cx - gx) * t / 100 * 0.55
            z = gz + (cz - gz) * t / 100 * 0.55
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    self.used.add((math.floor(x) + dx, math.floor(z) + dz))

    def cells(self, pid, x, z, rot=0):
        w, d = size(pid)
        if rot % 2:
            w, d = d, w
        return [(math.floor(x - w / 2 + 0.5) + i, math.floor(z - d / 2 + 0.5) + j)
                for i in range(w) for j in range(d)]

    def fits(self, pid, x, z, rot=0, margin=1):
        w, d = size(pid)
        if x - w / 2 < self.x0 + margin or x + w / 2 > self.x1 - margin:
            return False
        if z - d / 2 < self.z0 + margin or z + d / 2 > self.z1 - margin:
            return False
        shore = pid in ('reeds', 'beach_rock')
        if self.id == 'lagoon' and pond_dist(x, z) < (0.25 if shore else max(w, d) / 2 + 0.6) and pid != 'lilypads':
            return False
        return not any(c in self.used for c in self.cells(pid, x, z, rot))

    def put(self, pid, x, z, rot=0, force=False, margin=1):
        if not force and not self.fits(pid, x, z, rot, margin):
            return False
        for c in self.cells(pid, x, z, rot):
            self.used.add(c)
            # breathing room around big things
        self.out.append([pid, round(x, 2), round(z, 2), rot, {}])
        return True

    def scatter(self, pid, n, rng, tries=200):
        placed = 0
        for _ in range(tries):
            if placed >= n:
                break
            w, d = size(pid)
            x = rng.uniform(self.x0 + 1, self.x1 - 1)
            z = rng.uniform(self.z0 + 1, self.z1 - 1)
            x = math.floor(x) + (0.5 if w % 2 else 0.0)
            z = math.floor(z) + (0.5 if d % 2 else 0.0)
            if self.put(pid, x, z, rng.choice([0, 0, 1, 2, 3]) if w == d else 0):
                placed += 1
        return placed

    def near_gate(self, dist):
        cx, cz = (self.x0 + self.x1) / 2, (self.z0 + self.z1) / 2
        gx, gz = self.gate
        L = math.hypot(cx - gx, cz - gz)
        return gx + (cx - gx) / L * dist, gz + (cz - gz) / L * dist


lag = m['zones']['lagoon']['rect']
PC = ((lag[0] + lag[2]) / 2 + 3, (lag[1] + lag[3]) / 2 - 3)
PR = ((lag[2] - lag[0]) * 0.24, (lag[3] - lag[1]) * 0.19)


def pond_dist(x, z):
    q = math.hypot((x - PC[0]) / PR[0], (z - PC[1]) / PR[1])
    return (q - 1.0) * min(PR)


def basics(z, rng, bed='nest', food='trough'):
    gx, gz = z.near_gate(4.5)
    # side by side, perpendicular to the gate direction
    cx, cz = (z.x0 + z.x1) / 2, (z.z0 + z.z1) / 2
    vert = abs(z.gate[1] - cz) > abs(z.gate[0] - cx)
    for i, pid in enumerate((food, 'water_trough')):
        off = (-3 if i == 0 else 3)
        x, zz = (gx + off, gz) if vert else (gx, gz + off)
        x = math.floor(x) + (0.0 if size(pid)[0] % 2 == 0 else 0.5)
        zz = math.floor(zz) + 0.5
        if not z.put(pid, x, zz):
            z.scatter(pid, 1, rng)
    z.scatter(bed, 1, rng) if not z.put(bed, *z.near_gate(9.0)) else None


rng = random.Random(7)
zones = {k: Zone(k) for k in m['zones'] if k != 'meadow'}

f = zones['forest']
basics(f, rng)
for x, zz in ((-29, -17), (-19, -18), (-30, -2), (-24, -13)):
    f.put('tree_giant', x + 0.5, zz + 0.5)
f.scatter('tree_tall', 7, rng)
f.scatter('giant_fern', 6, rng)
f.scatter('cycad', 4, rng)
f.scatter('log', 2, rng)
f.scatter('stump', 2, rng)
f.scatter('moss_rock', 2, rng)
f.scatter('fern_clump', 4, rng)
f.scatter('mushroom' if 'mushroom' in props else 'flowers', 0, rng)
f.scatter('scratch_post', 1, rng)
f.scatter('tall_feeder', 1, rng)

L = zones['lagoon']
basics(L, rng)
# reeds and rocks around the shore, lily pads on the water, a dock
for i in range(14):
    a = i / 14 * math.tau
    r = 1.0 + 0.9
    x = PC[0] + math.cos(a) * (PR[0] + 0.7)
    zz = PC[1] + math.sin(a) * (PR[1] + 0.7)
    pid = 'reeds' if i % 3 else 'beach_rock'
    L.put(pid, math.floor(x) + 0.5, math.floor(zz) + 0.5)
for i in range(5):
    a = rng.uniform(0, math.tau)
    rr = rng.uniform(0.3, 0.7)
    L.out.append(['lilypads', round(PC[0] + math.cos(a) * PR[0] * rr, 2), round(PC[1] + math.sin(a) * PR[1] * rr, 2), 0, {}])
L.out.append(['dock', round(PC[0] - PR[0] + 0.3, 2), round(PC[1] + 1.0, 2), 1, {}])   # shore end west, water end east
L.put('fishing_sign', round(PC[0] - PR[0] - 2.5) + 0.5, round(PC[1] + 3) + 0.5)
L.scatter('palm', 4, rng)
L.scatter('driftwood', 2, rng)
L.scatter('flowers', 3, rng)
L.scatter('shower', 1, rng)

c = zones['canyon']
basics(c, rng, food='trough')
for x in range(int(c.x0) + 3, int(c.x1) - 2, 4):
    c.put('canyon_wall', x, c.z1 - 0.6, margin=0)
c.put('mesa', -29, 14)
c.put('mesa', -18, 22)
c.put('rock_arch', -24.5, 18.5)
c.scatter('dig_spot', 5, rng)
c.scatter('boulder_red', 6, rng)
c.scatter('desert_shrub', 5, rng)
c.scatter('sand_dune', 3, rng)
c.scatter('dino_slide', 1, rng)
c.scatter('ball_pile', 1, rng)

k = zones['cliff']
basics(k, rng, bed='nest_pillar')
k.put('cliff', 29, 22)
k.put('cliff', 31, 16)
k.put('waterfall', 21.5, 23)
k.put('aviary_arch', 16.5, 21.5) or k.scatter('aviary_arch', 1, rng)
k.scatter('perch', 5, rng)
k.scatter('nest_pillar', 2, rng)
k.scatter('rock', 4, rng)
k.scatter('flowers', 4, rng)
k.scatter('bush', 3, rng)

r = zones['rexvalley']
basics(r, rng)
r.put('hot_spring', 5.5, -40.5)
r.put('fossil', -5, -38.5)
r.put('big_boulder', -6.5, -43.5)
r.scatter('palm_big', 4, rng)
r.scatter('giant_fern', 4, rng)
r.scatter('bone_toy', 2, rng)
r.scatter('mud_pool', 1, rng)
r.scatter('cycad', 3, rng)
r.scatter('boulder_red', 3, rng)
r.out.append(['volcano', 0, -53, 0, {}])   # scenery beyond the fence

# the meadow gets a few toys too
mz = Zone('meadow')
for p in m['props']:
    for cc in mz.cells(p[0], p[1], p[2]) if p[0] in props else []:
        mz.used.add(cc)
mz.scatter('ball_pile', 1, rng)
mz.scatter('shower', 1, rng)

out = []
for zz in list(zones.values()) + [mz]:
    out += zz.out
m['habitat_props'] = out
m['habitat_rev'] = REV
json.dump(m, open(MAP, 'w'), indent=1)
counts = {}
for o in out:
    counts[o[0]] = counts.get(o[0], 0) + 1
print(len(out), 'props', counts)
