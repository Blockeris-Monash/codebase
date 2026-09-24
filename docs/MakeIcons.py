from PIL import Image, ImageDraw

ORANGE = (232, 98, 12)      # --accent from frontend/index.html
WHITE  = (255, 255, 255)
SS     = 4                  # supersample factor
SMALL_ICON_PX = 48          # at or below this the full mark stops reading

def glyph_ship(size):
    """The Ship Happens mark: the same ship the app draws in its header.

    Traced from the inline SVG in frontend/index.html, which works in a 64-unit
    box — mast, funnel, two deck houses, a row of windows and a trapezoid hull.
    Redrawn here rather than rasterised because the shapes are all rectangles
    and one polygon, and pulling in an SVG renderer for that would be a
    dependency for a script that runs once.

    Was a Blockeris "B". The app is called Ship Happens, and a judge who
    installs it should recognise the thing they were shown.
    """
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    u = size / 64.0                       # the SVG's own unit
    def box(x, y, w, h, r=1):
        d.rounded_rectangle([x * u, y * u, (x + w) * u, (y + h) * u],
                            radius=max(1, int(r * u)), fill=WHITE)

    d.rectangle([31.4 * u, 12 * u, 32.6 * u, 20 * u], fill=WHITE)   # mast
    d.rectangle([29.5 * u, 15 * u, 34.5 * u, 16.1 * u], fill=WHITE)  # yard
    box(28, 20, 8, 5)                                                # funnel house
    box(24.5, 25, 15, 6)                                             # upper deck
    box(21, 31, 22, 7)                                               # lower deck
    for wx in (23, 26, 29, 32, 35, 38):                              # windows
        d.rectangle([wx * u, 33.5 * u, (wx + 1.6) * u, 35.1 * u], fill=ORANGE)
    d.polygon([(18 * u, 38 * u), (46 * u, 38 * u),                   # hull
               (41 * u, 52 * u), (23 * u, 52 * u)], fill=WHITE)
    d.rectangle([31.2 * u, 39 * u, 32.8 * u, 52 * u], fill=ORANGE)   # keel
    return g


def glyph_ship_small(size):
    """The same ship with the detail removed, for a favicon.

    At 32px the windows, the yard and the keel merge into a white blob - the
    full mark stops reading at about 64px. This keeps the three shapes that
    still carry the silhouette: hull, one deck house, mast.
    """
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    u = size / 64.0
    d.rectangle([30.6 * u, 12 * u, 33.4 * u, 22 * u], fill=WHITE)     # mast, thicker
    d.rounded_rectangle([22 * u, 26 * u, 42 * u, 38 * u],             # one deck house
                        radius=max(1, int(2 * u)), fill=WHITE)
    d.polygon([(15 * u, 38 * u), (49 * u, 38 * u),                    # hull, wider
               (43 * u, 54 * u), (21 * u, 54 * u)], fill=WHITE)
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
    # 58% of the tile keeps the glyph inside the maskable safe circle (inner 80%).
    # A favicon has no safe circle to respect and needs every pixel it can get,
    # so it takes the simplified mark at a larger fraction.
    draw_glyph, fraction = (glyph_ship_small, 0.80) if px <= SMALL_ICON_PX else (glyph_ship, 0.58)
    gs = int(big * fraction)
    # Always draw the glyph large, then scale down — small geometry breaks Pillow
    g = draw_glyph(1024).resize((gs, gs), Image.LANCZOS)
    img.alpha_composite(g, ((big-gs)//2, (big-gs)//2))
    return img.resize((px, px), Image.LANCZOS)

for name, px, rf, bleed in [
    ("icon-192.png",        192, 0.22, True),
    ("icon-512.png",        512, 0.22, True),
    ("apple-touch-icon.png",180, 0.00, True),
    ("favicon-32.png",       32, 0.18, False),
]:
    im = tile(px, rf, bleed)
    if name == "apple-touch-icon.png":
        im = im.convert("RGB")          # iOS dislikes alpha here
    im.save(name)
    print(f"  {name:22} {px}x{px}")
