"""The review screen has to hold up on whatever the reader opens it with.

The README tells judges to install this on Android and iOS, so the phone case
is not hypothetical. The layout was two breakpoints and two magic numbers -
`repeat(3,1fr)` and `calc(100vh - 260px)` - both sized for one generic
handset. A folding phone is 260px closed and 673px open; a phone in landscape
is 800x360. None of those are the handset the numbers were picked for.

These tests hold the properties that make it work at any size, rather than
checking one device.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
I18N = (ROOT / "frontend/i18n.js").read_text(encoding="utf-8")


def test_drawing_under_the_notch_is_compensated_for() -> None:
    """`viewport-fit=cover` asks the browser to draw under the notch and the
    home indicator. On its own that is a bug: the installed iOS app put the
    header underneath the notch. It is only correct paired with insets."""
    assert "viewport-fit=cover" in INDEX
    assert INDEX.count("safe-area-inset") >= 4


def test_the_sticky_header_clears_the_notch() -> None:
    top = re.search(r"\.top\{[^}]*\}", INDEX).group(0)

    assert "env(safe-area-inset-top)" in top
    assert "max(" in top, "a bare inset collapses to 0 on a device without one"


def test_the_sticky_footer_clears_the_home_indicator() -> None:
    pager = re.search(r"\.pager\{[^}]*position:sticky[^}]*\}", INDEX).group(0)

    assert "env(safe-area-inset-bottom)" in pager


def test_the_status_tiles_take_as_many_columns_as_fit() -> None:
    """Five tiles in `repeat(3,1fr)` is right for one width and wrong for every
    other. auto-fit is five columns on a desktop, three on a phone and two on a
    folded cover screen, with no breakpoint deciding."""
    kpis = re.search(r"\.kpis\{[^}]*\}", INDEX).group(0)

    assert "auto-fit" in kpis and "minmax(" in kpis
    assert "repeat(3,1fr)" not in INDEX, "a fixed column count is back"
    assert "repeat(5,1fr)" not in INDEX


def test_the_longest_label_in_any_language_still_has_room() -> None:
    """The tiles were sized against English. Malay runs to two and a half times
    the length, and the language switch is on the differentiation slide."""
    longest = 0
    for label in ("Action required", "Needs review", "Verified", "Done", "Other mail"):
        for translated in re.findall(re.escape(f'"{label}"') + r'\s*:\s*"([^"]+)"', I18N):
            longest = max(longest, len(translated))

    assert longest >= 18, "expected Malay to be the long case; check i18n.js"
    kpis = re.search(r"\.kpis\{[^}]*\}", INDEX).group(0)
    assert "auto-fit" in kpis, f"a {longest}-character label needs wrapping columns"


def test_two_panes_appear_when_there_is_room_in_both_directions() -> None:
    """A Fold open is 673x841 and was getting the one-column phone layout. A
    phone in landscape is 800x360 and was getting the desktop layout, where
    `body{overflow:hidden}` left almost nothing on screen. Height decides too."""
    assert "@media (min-width:660px) and (min-height:600px)" in INDEX
    assert "@media (max-width:659px), (max-height:599px)" in INDEX
    assert "820px" not in INDEX and "821px" not in INDEX, "an old breakpoint survives"


def test_the_script_and_the_stylesheet_agree_on_which_layout_is_on() -> None:
    """The JS clears the selected email when the layout is one-pane. It asked
    about 820px after the CSS moved to 659, so on an unfolded Fold a search
    cleared the selection while both panes were still on screen."""
    assert 'matchMedia("(max-width:659px), (max-height:599px)")' in INDEX
    assert INDEX.count("ONE_PANE") >= 2
    assert 'matchMedia("(max-width:820px)")' not in INDEX


def test_the_list_height_is_not_a_number_picked_for_one_screen() -> None:
    """`calc(100vh - 260px)` assumed a fixed chrome height, and `vh` ignores
    the mobile URL bar appearing and disappearing."""
    assert "calc(100vh - 260px)" not in INDEX
    assert "calc(100dvh - 260px)" not in INDEX
    assert "min-height:60dvh" in INDEX


def test_text_follows_the_reader_s_own_size_setting() -> None:
    """px ignores a phone set to large text and a browser zoomed to 200%."""
    leftover = re.findall(r"font-size:\d+px", INDEX)

    assert not leftover, f"font sizes still fixed in px: {leftover[:5]}"
    assert len(re.findall(r"font-size:[\d.]+rem", INDEX)) >= 30
    assert "font:0.9375rem/1.45" in INDEX


@pytest.mark.parametrize("selector", [".btn", ".tab"])
def test_the_things_you_tap_are_big_enough_to_tap(selector: str) -> None:
    """44px is Apple's minimum and 48dp is Android's. These were about 38."""
    rule = re.search(re.escape(selector) + r"\{[^}]*\}", INDEX).group(0)

    assert "min-height:44px" in rule


def test_high_contrast_does_not_flatten_the_screen() -> None:
    """Windows high contrast discards author colours. Without explicit borders
    the cards, the selected row and the badges all lose their edges."""
    assert "@media (forced-colors: active)" in INDEX
    block = INDEX[INDEX.index("@media (forced-colors: active)"):]

    assert "CanvasText" in block and "Highlight" in block


def test_the_resizable_list_cannot_swallow_the_whole_screen() -> None:
    """--listw is remembered per device. Restored on a narrower screen, a 380px
    list left nothing for the document pane."""
    assert "clamp(240px,var(--listw,380px),46vw)" in INDEX


def test_the_python_version_render_builds_with_is_pinned() -> None:
    """Without this Render picks its own default and can change it on any
    rebuild, while CI stays green on 3.11 and 3.12 and tells you nothing."""
    pinned = (ROOT / "runtime.txt").read_text(encoding="utf-8").strip()

    assert pinned.startswith("python-3.1"), pinned
