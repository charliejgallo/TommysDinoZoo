#!/usr/bin/env python3
"""Compose the style-sample board (docs/img/muestra-estilo.png) from game
screenshots taken with --shot (see the README's dev section)."""
import sys
from PIL import Image, ImageDraw, ImageFont

S = sys.argv[1]   # folder with the shots
F = 'game/assets/fonts/Fredoka.ttf'


def font(sz, w=600):
    f = ImageFont.truetype(F, sz)
    f.set_variation_by_axes([w, 100])   # axes: weight, width
    return f


frames = [('title.png', 'Portada'), ('b.png', 'La pradera a la tarde'),
          ('c.png', 'Darle helecho a un bebé triceratops'), ('d.png', 'Mimos: corazones y burbuja de "tengo hambre"'),
          ('g.png', 'El rex y el braquio, grandotes mimosos'), ('e.png', 'El patio: tiendita, huerta, tablero, incubadora'),
          ('f.png', 'De noche, con los faroles'), ('lineup.png', 'Tommy y los dinos de la muestra')]
W, H, pad, cap, top, cols, rows = 800, 450, 28, 46, 124, 2, 4
img = Image.new('RGB', (cols * W + (cols + 1) * pad, top + rows * (H + cap + pad) + pad), '#fff7e6')
d = ImageDraw.Draw(img)
d.text((pad, 26), "Tommy's Dino Zoo — muestra de estilo", font=font(54), fill='#e0703c')
d.text((pad + 4, 90), "Capturas reales del juego en Godot 4", font=font(26, 450), fill='#7a5236')
for i, (fn, c) in enumerate(frames):
    x = pad + (i % cols) * (W + pad)
    y = top + (i // cols) * (H + cap + pad)
    im = Image.open(f'{S}/{fn}').convert('RGB')
    if fn == 'lineup.png':
        w, h = im.size
        im = im.crop((0, int(h * 0.22), w, int(h * 0.72)))
    img.paste(im.resize((W, H), Image.LANCZOS), (x, y))
    d.rounded_rectangle((x - 2, y - 2, x + W + 2, y + H + 2), radius=8, outline='#7a5236', width=3)
    d.text((x + 4, y + H + 8), c, font=font(28), fill='#7a5236')
img.save('docs/img/muestra-estilo.png')
print(img.size)
