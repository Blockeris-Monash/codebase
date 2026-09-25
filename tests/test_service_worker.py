"""The service worker keeps only good pages, and never answers a script with HTML (#147 B2).

sw.js cached every response, 404s and 500s included, and served them offline; it waited
on a hung network for ever; and any failed request, a script included, was answered
with index.html, which the browser then tried to run. sw.js runs here in node with a
fake cache and a fake network.
"""
from __future__ import annotations

import json

import pytest

from tests.js_runner import FRONTEND, run_node

SW = json.dumps(str(FRONTEND / "sw.js"))


def fetched(network: str, url: str = "https://app.example/app.js", mode: str = "cors",
            cached: dict | None = None) -> dict:
    """What the worker answered for one GET, and what it put in the cache.

    `network` is JavaScript for what fetch does: e.g. `ok(200, "basic")`, `fail`, `hang`."""
    return run_node(f"""
        const store = new Map(Object.entries({json.dumps(cached or {})}));
        const ok = (status, type) => async () => ({{ok: status < 400, status, type, body: "net " + status,
                                                   clone() {{ return this; }}}});
        const fail = async () => {{ throw new TypeError("offline"); }};
        const hang = () => new Promise(() => {{}});
        globalThis.fetch = {network};
        globalThis.Response = {{error: () => ({{status: 0, type: "error", body: "error"}})}};
        globalThis.caches = {{
            open: async () => ({{put: async (request, response) => store.set(request.url, response.body)}}),
            match: async key => {{
                const body = store.get(typeof key === "string" ? key : key.url);
                return body === undefined ? undefined : {{status: 200, body}};
            }},
        }};
        const handlers = {{}};
        globalThis.self = {{location: {{origin: "https://app.example"}},
                           addEventListener: (name, handler) => {{ handlers[name] = handler; }}}};
        globalThis.setTimeout = (fn) => {{ if ({json.dumps(network)} === "hang") fn(); return 0; }};
        const {{readFileSync}} = await import("node:fs");
        (0, eval)(readFileSync({SW}, "utf8"));
        let answer;
        handlers.fetch({{request: {{method: "GET", url: {json.dumps(url)}, mode: {json.dumps(mode)}}},
                        respondWith: p => {{ answer = p; }}}});
        const response = await answer;
        await new Promise(r => setImmediate(r));
        console.log(JSON.stringify({{body: response.body, cached: Object.fromEntries(store)}}));
    """)


def test_a_good_page_is_cached() -> None:
    assert fetched("ok(200, 'basic')")["cached"] == {"https://app.example/app.js": "net 200"}


@pytest.mark.parametrize("status", [404, 500])
def test_an_error_response_is_passed_on_but_never_cached(status: int) -> None:
    result = fetched(f"ok({status}, 'basic')")

    assert result["body"] == f"net {status}"
    assert result["cached"] == {}


def test_a_failed_script_is_never_answered_with_the_page() -> None:
    result = fetched("fail", cached={"./index.html": "<html>"})

    assert result["body"] == "error"


def test_a_failed_navigation_falls_back_to_the_page() -> None:
    result = fetched("fail", url="https://app.example/", mode="navigate", cached={"./index.html": "<html>"})

    assert result["body"] == "<html>"


def test_a_hung_network_gives_way_to_the_cache() -> None:
    result = fetched("hang", cached={"https://app.example/app.js": "cached js"})

    assert result["body"] == "cached js"
