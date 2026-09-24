"""Phase C: a landing page to start from, and a look that says shipping beyond the logo.

The mentor asked for a first step (choose where the mail comes from) and a design that looks less like
every other team's. The site opens on a landing page on every visit; the inbox lives at #/inbox. Each
checked email shows its route, and the count tiles carry a container-side stripe.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]


def block(start: str, end: str = "\n}\n") -> str:
    at = SCRIPT.index(start)
    return SCRIPT[at:SCRIPT.index(end, at) + len(end)]


def branch(action: str) -> str:
    lines = [line for line in SCRIPT.splitlines() if f'a==="{action}"' in line]
    assert len(lines) == 1, f"expected one branch for {action!r}, found {len(lines)}"
    return lines[0]


def test_the_site_opens_on_the_landing_page() -> None:
    route = re.search(r"const onHome = .*\n", SCRIPT).group(0)
    assert '!location.hash' in route and '"#/"' in route
    assert "homePage()" in block("function render(){")


def test_the_landing_page_offers_demo_gmail_and_upload() -> None:
    home = block("function homePage(){")
    assert 'data-a="inbox"' in home, "no way into the demo inbox"
    assert 'data-a="signin"' in home, "no way to connect Gmail"
    assert 't("Upload SI and BL files")' in home and 't("Planned")' in home
    assert 't("Coming soon")' in home, "the live mailbox is not built yet and must say so"


def test_the_inbox_has_its_own_address_and_the_logo_goes_home() -> None:
    assert 'location.hash="#/inbox"' in branch("inbox")
    assert 'location.hash="#/"' in branch("home")
    assert 'class="brand" data-a="home"' in SCRIPT


def route_of(rows: list[dict]) -> str:
    js = "\n".join([
        "const T = s=>s, t = s=>s;",
        "const esc = s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));",
        "const ICO = p=>'<svg>'+p+'</svg>'; const ICON = {SHIP:'<svg/>'};",
        block("function routeHTML(e){"),
        f"console.log(routeHTML({{rows:{json.dumps(rows)}}}));",
    ])
    return subprocess.run(["node"], input=js, capture_output=True, text=True, check=True).stdout


def test_an_email_shows_its_route_from_the_shipping_instruction() -> None:
    rows = [
        {"field": "port_of_loading", "si_raw": "BUATAN, INDONESIA", "bl_raw": "BUATAN (IDBUA)"},
        {"field": "port_of_discharge", "si_raw": "", "bl_raw": "BUSAN <KR>"},
    ]
    html = route_of(rows)
    assert "BUATAN, INDONESIA" in html
    assert "BUSAN &lt;KR&gt;" in html, "a blank SI port falls back to the BL, escaped"
    assert route_of([]).strip() == "", "no ports, no route line"


def test_the_tiles_carry_a_container_stripe() -> None:
    assert re.search(r"\.kpi::before\{[^}]*repeating-linear-gradient", INDEX)
