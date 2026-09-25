"""Colour-blind friendly and Monotone colours (Meeting 7, job 9).

Action required, Needs review and Verified were red, brown and green. For someone with red-green
colour blindness (about 1 man in 12), the red and brown of Action required and Needs review look
almost the same in light mode, and the red and green are close too. The Settings menu now has a
choice of Colours that works with Light and Dark mode: Standard colours; Colour-blind friendly
(Action required magenta, Verified blue, Needs review keeps its amber); or Monotone (the whole
page in greys, for people who see no colour at all). The choice is remembered on this device.

The palette is checked here, not only named: each pair of status colours must stay clearly apart
under simulated protanopia, deuteranopia and tritanopia (Machado et al. 2009, full severity), and
each must stay readable as text on its panel.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STYLE = INDEX[:INDEX.index("</style>")]

# ---------------------------------------------------------------- colour maths

MACHADO = {
    "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritanopia": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}
APART = 25       # CIELAB delta E: well past "clearly a different colour"
READABLE = 4.5   # WCAG AA for normal text


def linear(hex_colour: str) -> list[float]:
    def one(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    h = hex_colour.lstrip("#")
    return [one(int(h[i:i + 2], 16)) for i in (0, 2, 4)]


def lab(rgb: list[float]) -> tuple[float, float, float]:
    x = 0.4124 * rgb[0] + 0.3576 * rgb[1] + 0.1805 * rgb[2]
    y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    z = 0.0193 * rgb[0] + 0.1192 * rgb[1] + 0.9505 * rgb[2]
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    fx, fy, fz = f(x / 0.95047), f(y), f(z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def seen_by(hex_colour: str, vision: str) -> tuple[float, float, float]:
    rgb, m = linear(hex_colour), MACHADO[vision]
    return lab([min(1.0, max(0.0, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3)])


def apart(a: str, b: str, vision: str) -> float:
    return sum((p - q) ** 2 for p, q in zip(seen_by(a, vision), seen_by(b, vision))) ** 0.5


def contrast(a: str, b: str) -> float:
    lum = lambda h: sum(w * c for w, c in zip((0.2126, 0.7152, 0.0722), linear(h)))  # noqa: E731
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens(selector: str) -> dict[str, str]:
    """The colour tokens one CSS block sets, e.g. {"--bad": "#b0145f", ...}."""
    at = STYLE.index(selector + "{")
    body = STYLE[at + len(selector) + 1:STYLE.index("}", at)]
    return dict(re.findall(r"(--[\w-]+):(#[0-9a-fA-F]{6})", body))


LIGHT = tokens(":root")
DARK = tokens(':root[data-theme="dark"]')


def colour_blind(mode: str) -> dict[str, str]:
    """The page's colours with the switch on: the mode's own, then the switch's overrides."""
    if mode == "light":
        return {**LIGHT, **tokens(':root[data-palette="cb"]')}
    return {**DARK, **tokens(':root[data-palette="cb"][data-theme="dark"]')}


def monotone(mode: str) -> dict[str, str]:
    if mode == "light":
        return {**LIGHT, **tokens(':root[data-palette="mono"]')}
    return {**DARK, **tokens(':root[data-palette="mono"][data-theme="dark"]')}

# ---------------------------------------------------------------- the palette


@pytest.mark.parametrize("vision", MACHADO)
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_three_statuses_stay_apart_for_colour_blind_eyes(mode: str, vision: str) -> None:
    ours = colour_blind(mode)
    for a, b in (("--bad", "--rev"), ("--bad", "--ok"), ("--rev", "--ok")):
        gap = apart(ours[a], ours[b], vision)
        assert gap >= APART, f"{mode}, {vision}: {a} {ours[a]} and {b} {ours[b]} are only {gap:.1f} apart"


def test_the_old_palette_is_why_this_exists() -> None:
    """Red and brown in light mode are nearly one colour for deuteranopia."""
    assert apart(LIGHT["--bad"], LIGHT["--rev"], "deuteranopia") < APART


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("palette", [colour_blind, monotone])
def test_status_text_stays_readable(palette, mode: str) -> None:
    ours = palette(mode)
    for name in ("--bad", "--rev", "--ok"):
        assert contrast(ours[name], ours["--panel"]) >= READABLE, f"{mode} {name} on the panel"
        assert contrast(ours[name], ours[name + "-soft"]) >= READABLE, f"{mode} {name} on its own soft tint"


@pytest.mark.parametrize("palette", ["cb", "mono"])
def test_dark_mode_from_the_system_gets_the_same_colours(palette: str) -> None:
    system = STYLE[STYLE.index(f'@media (prefers-color-scheme:dark){{:root[data-palette="{palette}"]:not([data-theme="light"]){{'):]
    body = system[:system.index("}")]
    assert dict(re.findall(r"(--[\w-]+):(#[0-9a-fA-F]{6})", body)) == tokens(f':root[data-palette="{palette}"][data-theme="dark"]')


# ---------------------------------------------------------------- monotone

def lightness(hex_colour: str) -> float:
    return lab(linear(hex_colour))[0]


def test_monotone_turns_the_whole_page_grey() -> None:
    assert re.search(r':root\[data-palette="mono"\]\{filter:grayscale\(1\)', STYLE)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_monotone_statuses_are_greys_told_apart_by_lightness(mode: str) -> None:
    """With no colour at all, the three statuses differ by how light they are (and by their icons)."""
    ours = monotone(mode)
    for name in ("--bad", "--rev", "--ok", "--bad-soft", "--rev-soft", "--ok-soft"):
        r, g, b = (ours[name][i:i + 2] for i in (1, 3, 5))
        assert r == g == b, f"{mode} {name} {ours[name]} is not a grey"
    text = sorted(lightness(ours[n]) for n in ("--bad", "--rev", "--ok"))
    assert min(b - a for a, b in zip(text, text[1:])) >= 12, f"{mode}: status greys too close {text}"

# ---------------------------------------------------------------- the switch


def function(name: str) -> str:
    body = INDEX[INDEX.index(f"function {name}("):]
    return body[:body.index("\n}")]


def test_the_settings_menu_offers_one_choice_of_three_colours_under_colour_mode() -> None:
    menu = function("settingsHTML")

    assert '[["",T("Standard colours")],["cb",T("Colour-blind friendly")],["mono",T("Monotone")]]' in menu
    assert 'role="menuitemradio"' in menu and 'data-a="palette"' in menu
    assert '${t("Colour mode")}</div>${mode}' in menu
    assert menu.index("${mode}") < menu.index('t("Colours")') < menu.index("${palettes}")


def test_the_choice_changes_the_page_and_is_remembered() -> None:
    assert re.search(r'a==="palette"\)\{[^\n]*setPalette\(k\)', INDEX)
    save = function("setPalette")
    assert 'document.documentElement.dataset.palette' in save
    assert 'localStorage.setItem("blockeris.palette"' in save
    # applied before the first paint, so the page never flashes red and green first
    head = INDEX[:INDEX.index("</head>")]
    assert 'localStorage.getItem("blockeris.palette")' in head
    # whoever turned on Colour-blind friendly before Monotone existed keeps it
    assert 'localStorage.getItem("blockeris.cb")==="on"' in head
    assert "data-cb" not in INDEX


def test_it_is_built_so_it_is_no_longer_on_the_roadmap() -> None:
    assert 'T("Colour-blind friendly themes")' not in INDEX
