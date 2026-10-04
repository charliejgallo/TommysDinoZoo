# Tommy's Dino Zoo — art spec

Everything an art agent needs. The game design is in `docs/DESIGN.md`
(Spanish); read sections 4 (dinos) and 5-8 for what things are for.

## 0. Workflow

All art is **procedural Blender Python**, never hand-modelled, so it can be
re-made and tweaked by numbers. Blender 3.3 lives at
`/Applications/Blender.app/Contents/MacOS/Blender`; Godot 4.7 is `godot`.

```
cd art/blender
/Applications/Blender.app/Contents/MacOS/Blender -b -P <script>.py -- [--only a,b]
cd ../../game && godot --headless --path . --import          # after new .glb
godot --path . --resolution 1200x700 -- --scene=res://scenes/viewer.tscn \
    --models=tommy,trike_adult --anim=walk --t=0.4 --cam=close --shot=/abs/out.png
```

- Shared helpers: `art/blender/tdz_common.py` (primitives: `ellipsoid`, `box`
  with bevel, `cylinder`/frustum, `cone`, `tube` (smooth swept tube with
  per-point radius and oval section, rounded caps), `decal_on` (flat disc
  shrink-wrapped onto a surface: eyes, spots, blush), `mirror_x`;
  `armature`, `skin_rigid`, `skin_near` (smooth weights by distance to bone
  segments), `bind`, `join_static`; `action` + `cycle` for keyed actions;
  `export_glb`). Extend it when useful (keep it backwards compatible; other
  agents use it at the same time — add new functions rather than changing
  signatures). `art/blender/test_pipeline.py` is the smallest example.
- Output: `game/assets/models/<name>.glb`. Scripts: `art/blender/<topic>.py`.
- **Always check in Godot** with the viewer (`--cam=game` is the real game
  camera: 48° down, 11 m, fov 30; `close` is 0.45× that distance, `front`
  is a low front view, `wide` fits a long row; `--yaw=deg` turns models;
  `--grid` draws 1 m lines; omit `--t` to see it play). Look at your shots.
  The viewer applies the game's toon shader to every material, so judge
  colours there, not in Blender.
- Write scratch renders/shots to your scratchpad, not into the repo.

## 1. Style

Cute cartoon "clay toy" look, like the Monster Hop dinos and Tommy
(`ESP32S3_AmoledOS/apps/monsterhop/tools/blender/monsters_dino.py`,
`chars.py`; renders in `.../apps/monsterhop/assets/monsters/_cards_dino.png`
and `.../assets/chars/_sample_2x.png`): rounded chunky shapes, **big heads,
big round eyes with a white catchlight**, short stubby legs, soft pastel
colours with a few saturated accents (spots, stripes, frills), no scary
teeth (at most two tiny blunt fangs for the meat eaters), smiles. Simple
silhouettes that read from 11 m away at 1600×900: Tommy is ~120 px tall
on screen. Smooth shading, moderate poly counts.

**No textures.** Flat colour per material; the shader does the shading
(two soft bands + darker rim at grazing angles). Detail comes from
geometry and decals (spots as `decal_on` discs, stripes as thin bands).

## 2. Units, axes, origins

- Metres. Blender +Z up, **model faces -Y** in Blender (front view); in
  Godot that becomes facing +Z. Origin on the ground under the body centre
  (characters) or footprint centre (props).
- Scale: Tommy 1.0 m tall (with cap). Dinos are miniaturised (adult height
  to the top of the head when standing): compy 0.35, microraptor 0.45,
  protoceratops 0.6, raptor 0.9, gallimimus 1.1, dilophosaurus 1.2,
  pachy 1.0, archaeopteryx 0.4, iguanodon 1.5, trike 1.4, stego 1.5,
  ankylo 1.0, parasaurolophus 1.7, carnotaurus 1.6, therizino 2.0,
  spino 2.0, pteranodon 1.0 (standing, wingspan 2.2), plesiosaur 1.2 (in
  water, neck up), trex 2.4, brachio 4.0.
- Babies are ~45% of the adult height, juveniles ~70%.
- Props sit on a **1 m grid**: footprint in whole metres (1×1, 2×1, 2×2,
  3×3...), centred on the origin; things that line up (fences) span exactly
  1 m between post centres.

## 3. Materials (palette roles)

Material **names are roles** the game uses to recolour (wardrobe, dino
colour variants, seasonal tints). Keep them exactly:

- Tommy: `skin`, `hair`, `eye_white`, `pupil`, `mouth`, `blush`, `cap`,
  `cap_brim`, `shirt`, `shirt_stripe`, `emblem`, `pants`, `shoes`,
  `shoe_sole`.
- Dinos: `body` (main hide), `belly` (belly/throat/underside), `accent`
  (frill, crest, plates, feathers, sail), `spots` (spots/stripes), `horn`
  (horns, claws, beak, tiny teeth — off-white), `eye_white`, `pupil`,
  `iris` (optional coloured ring), `mouth` (dark inside), `tongue`,
  `blush`, `nose`.
- Props: free names, but prefer shared ones so a scene has few materials:
  `wood`, `wood_dark`, `leaf`, `leaf_dark`, `grass`, `bark`, `stone`,
  `metal`, `roof`, `white`, `straw`, `water`, `glass` (alpha ok),
  `paint_red`, `paint_blue`, `paint_yellow`, plus specifics (`berry`,
  `pumpkin`, `petal_pink`...).
- Use `C.mat(name, '#rrggbb')`. Colours are sRGB hex.

## 4. Skeletons and animation

Armature with named bones (bone Y along the bone; actions rotate in
bone-local Euler degrees). The game needs these names:

**Tommy** (`tommy.glb`): `root` (hips; moving it lifts the whole body),
`spine`, `chest`, `neck`, `head`, `upper_arm.L/.R`, `forearm.L/.R`,
`hand.L/.R`, `thigh.L/.R`, `shin.L/.R`, `foot.L/.R`, plus `eyelid.L/.R`
(scale 0 → 1 closes the eye) and `mouth_open` (head child; scale 0 hidden → 1 open
mouth). NPCs share this skeleton. **`hand.R`** is
where the carried small item attaches (the item's origin is its grip
point); **both hands** hold big items (egg, box, pumpkin) in front of the
chest — `carry_*` animations put the hands there. Caps, back items and
hand items are **separate .glb** files attached at runtime to `head`,
`chest`, `hand.R` (their origin = the attach point, already at the right
place relative to the bone head when the bone has identity pose).

Tommy's animations (30 fps; loops marked ↻):
`idle`↻ (breathing, a look around), `walk`↻ (0.5 s/cycle at 1.6 m/s),
`run`↻ (0.4 s/cycle at 3.5 m/s), `pickup` (crouch-grab-stand, 0.7 s),
`carry_idle`↻, `carry_walk`↻ (both arms holding a box at the chest),
`pet` (stroke forward at chest height, 1.0 s), `pet_low` (crouch and
stroke low, for babies, 1.0 s), `give` (offer with right hand, 0.8 s),
`use` (generic tool motion: tip a watering can / brush, 1.0 s),
`dig` (shovel scoop, 0.9 s), `happy` (jump with both arms up, 0.8 s),
`wave` (1.0 s), `yawn` (stretch + yawn, 1.6 s), `sleep`↻ (lying curled,
breathing), `sit`↻ (sitting on the ground), `talk`↻ (gesturing).
Walk/run should not slide: the root stays in place (the game moves the
node); feet plant at the right speed.

**Dinos** (`<id>_<age>.glb`, age = `baby`, `juv`, `adult`): required bones
`root` (hips), `spine` (towards the chest), `neck_1..n` (n ≥ 1), `head`,
`jaw`, `tail_1..n`, legs `thigh.L/.R`, `shin.L/.R`, `foot.L/.R` (+ the
front pair `fthigh/fshin/ffoot.L/.R` for quadrupeds, or `arm.L/.R`,
`forearm.L/.R` for bipeds), and `eyelid.L/.R` (scale to close). Fliers add
`wing.L/.R` (+`wing2`). The game reads `head` (where to pet, where food
goes) and `root`.

Dino animations (loops ↻): `idle`↻ (breathing, tail sway, blink),
`walk`↻, `run`↻, `eat` (head down, chomp ×3, 1.5 s), `drink` (1.5 s),
`sleep`↻ (lying down, eyes closed, slow breathing), `happy` (hop or
wiggle with tail wag, 1.0 s), `pet` (leans in, eyes closed, tail wag,
1.2 s), `sit`↻, `call` (cute roar/chirp, mouth open, 1.0 s), `play`
(nudge/chase a ball: head butt forward, 0.8 s), `sad`↻ (sits, head low,
slow tail). Babies have the same list. Walk speeds: babies 0.8 m/s,
adults 1.0-2.0 m/s (bigger = slower legs but longer stride); list the speed
you animated for in the script's docstring so the game matches it.

Animation helpers: `C.action(arm, name, frames, keys)` (keys at integer
frames, bezier), `C.cycle(frames, [pose, pose, ...])` for seamless loops.

## 5. Budgets

Tommy ≤ 8k triangles; adult dino ≤ 10k (brachio/rex ≤ 14k); baby ≤ 6k;
prop ≤ 3k (house ≤ 8k, tree ≤ 4k); held item ≤ 800. Keep materials few
(the role lists in section 3 are the ceiling; Tommy uses 12). glb ≤ 1 MB each.

## 6. Names

- `tommy.glb`, `cap_<style>.glb`, `back_<style>.glb`.
- `<dino>_<baby|juv|adult>.glb` with dino ids: `trike`, `stego`, `ankylo`,
  `brachio`, `parasaur`, `pachy`, `iguanodon`, `proto`, `galli`,
  `therizino`, `trex`, `raptor`, `spino`, `dilo`, `carno`, `compy`,
  `microraptor`, `ptera`, `archaeo`, `plesio`; `egg_<dino>.glb` (each
  species' egg: same egg shape, its own colours/spots, ~0.25 m).
- Props `prop_<id>.glb`, held items `item_<id>.glb`, NPCs `npc_<id>.glb`
  (NPCs share Tommy's skeleton and animation names).
