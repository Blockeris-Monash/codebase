from PIL import Image, ImageDraw

ORANGE = (232, 98, 12)      # --accent from frontend/index.html
WHITE  = (255, 255, 255)
SS     = 4                  # supersample factor

def glyph_B(size):
    """A geometric B drawn from rounded rectangles — no font dependency.
    Lower bowl is wider than the upper one, the way a drawn B always is."""
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    u = size / 1000.0
    def R(x0, y0, x1, y1, r, corners, fill):
        a, b, c, e = x0*u, y0*u, x1*u, y1*u
        # Pillow rejects a radius over half the shorter side; clamp in pixel space
        rad = min(r*u, (c-a)/2 - 0.51, (e-b)/2 - 0.51)
        if rad <= 0:
            d.rectangle([a, b, c, e], fill=fill)
            return
        d.rounded_rectangle([a, b, c, e], radius=rad, fill=fill, corners=corners)
    # stem + both bowls, all white, merged into one shape
    R(150, 100, 310, 900,  20, (True, False, False, True), WHITE)   # stem
    R(150, 100, 660, 497, 188, (False, True, True, False), WHITE)   # upper bowl
    R(150, 493, 745, 900, 196, (False, True, True, False), WHITE)   # lower bowl
    # counters punched back out in the tile colour
    R(310, 210, 520, 388,  82, (False, True, True, False), ORANGE)  # upper counter
    R(310, 602, 600, 790,  88, (False, True, True, False), ORANGE)  # lower counter
    return g

def tile(px, radius_frac, bleed):
    """bleed=True -> full-bleed square for maskable/apple. False -> rounded tile."""
    big = px * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bleed:
        d.rectangle([0, 0, big, big], fill=ORANGE)
    else:
        d.rounded_rectangle([0, 0, big-1, big-1], radius=int(big*radius_frac), fill=ORANGE)
    # 58% of the tile keeps the glyph inside the maskable safe circle (inner 80%)
    # Always draw the glyph large, then scale down — small geometry breaks Pillow
    gs = int(big * 0.58)
    g = glyph_B(1024).resize((gs, gs), Image.LANCZOS)
    img.alpha_composite(g, ((big-gs)//2, (big-gs)//2))
    return img.resize((px, px), Image.LANCZOS)

for name, px, rf, bleed in [
    ("icon-192.png",        192, 0.22, True),
    ("icon-512.png",        512, 0.22, True),
    ("apple-touch-icon.png",180, 0.00, True),
    ("favicon-32.png",       32, 0.18, False),
    ("logo-256.png",        256, 0.22, False),
]:
    im = tile(px, rf, bleed)
    if name == "apple-touch-icon.png":
        im = im.convert("RGB")          # iOS dislikes alpha here
    im.save(name)
    print(f"  {name:22} {px}x{px}")
