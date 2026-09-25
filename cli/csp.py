"""Write the page's security headers into frontend/vercel.json, or check they are current.

    python -m cli.csp            # rewrite the headers
    python -m cli.csp --check    # exit 1 if vercel.json is out of date (CI and the tests)

The content security policy lets a script run only from this site, from the exact
supabase-js file both pages load (which also carries an integrity hash), or when its
text hashes to one of the page's own inline scripts. So editing an inline script in
index.html or admin.html means running this again: --check says so, rather than the
browser silently refusing the script in production.

The backend and Supabase origins are read from frontend/config.js, so no URL is written
twice. Upgrading supabase-js: change the version in both pages, fetch the new file, put
`sha384-<base64 of its sha384>` in their integrity attributes, and run this.

Stdlib only, like cli.validate_contracts, so it runs anywhere the tests do.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
VERCEL = FRONTEND / "vercel.json"
CONFIG = FRONTEND / "config.js"
PAGES = ("index.html", "admin.html")
EVERY_PATH = "/(.*)"

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
EXTERNAL_SCRIPT = re.compile(r'<script[^>]*\bsrc="(https://[^"]+)"', re.S)
CONFIG_ORIGIN = re.compile(r'(?:var DEPLOYED|window\.SUPABASE_URL)\s*=\s*"(https://[^"/]+)')

FONTS_CSS = "https://fonts.googleapis.com"
FONTS_FILES = "https://fonts.gstatic.com"


def script_hash(text: str) -> str:
    """The CSP source for one inline script: sha256 of its exact text, base64."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode()}'"


def page_sources() -> tuple[list[str], list[str]]:
    """Every inline script's hash, and every external script URL, across both pages."""
    hashes: list[str] = []
    external: list[str] = []
    for page in PAGES:
        html = (FRONTEND / page).read_text(encoding="utf-8")
        hashes += [script_hash(m.group(1)) for m in INLINE_SCRIPT.finditer(html)]
        external += EXTERNAL_SCRIPT.findall(html)
    return sorted(set(hashes)), sorted(set(external))


def api_origins() -> list[str]:
    origins = CONFIG_ORIGIN.findall(CONFIG.read_text(encoding="utf-8"))
    if len(origins) != 2:
        raise SystemExit(f"expected the backend and Supabase origins in {CONFIG.name}, found {origins}")
    return origins


def policy() -> str:
    hashes, external = page_sources()
    directives = {
        "default-src": ["'self'"],
        "script-src": ["'self'", *external, *hashes],
        # Hundreds of style="" attributes; injected style cannot run code, scripts are what this guards.
        "style-src": ["'self'", "'unsafe-inline'", FONTS_CSS],
        "font-src": [FONTS_FILES],
        "img-src": ["'self'", "data:"],
        "connect-src": ["'self'", *api_origins()],
        "worker-src": ["'self'"],
        "manifest-src": ["'self'"],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'none'"],
        "object-src": ["'none'"],
        "form-action": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


def security_headers() -> list[dict[str, str]]:
    return [
        {"key": "Content-Security-Policy", "value": policy()},
        {"key": "X-Content-Type-Options", "value": "nosniff"},
        # The Gmail link carries the reviewer's address in its query; other sites get the origin only.
        {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
        {"key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()"},
        # Sign-in is a redirect, never a popup, so no page needs this one as its opener.
        {"key": "Cross-Origin-Opener-Policy", "value": "same-origin"},
    ]


def with_headers(config: dict) -> dict:
    """`config` with the every-path security headers set, and every other entry kept."""
    others = [entry for entry in config.get("headers", []) if entry.get("source") != EVERY_PATH]
    return {**config, "headers": [{"source": EVERY_PATH, "headers": security_headers()}, *others]}


def rendered(config: dict) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if vercel.json is out of date")
    args = parser.parse_args()

    current = VERCEL.read_text(encoding="utf-8")
    wanted = rendered(with_headers(json.loads(current)))
    if args.check:
        if current != wanted:
            print(f"{VERCEL.relative_to(FRONTEND.parent)} is out of date: run python -m cli.csp")
            return 1
        print("security headers are current")
        return 0

    VERCEL.write_text(wanted, encoding="utf-8", newline="\n")
    print(f"wrote the security headers into {VERCEL.relative_to(FRONTEND.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
