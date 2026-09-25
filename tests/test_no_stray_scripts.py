"""No script that spends model quota hides where pytest or an import would run it (#147 B4).

test_embed.py, scratch/test_rag.py and backend/extract/sample.py called live models when
run or imported, and three of them matched test_*.py, so `pytest test_embed.py` spent
quota. Tests live in tests/; a backend module only defines things when imported.
"""
from __future__ import annotations

import importlib
import pkgutil
import socket
from pathlib import Path

import pytest

import backend

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".venv", ".git", "node_modules", "tests"}


def test_every_test_file_is_under_tests() -> None:
    stray = [p for p in ROOT.rglob("test_*.py") if not IGNORED & set(p.relative_to(ROOT).parts)]

    assert stray == []


def test_importing_the_backend_does_nothing_but_define(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """No network and no output: backend/extract/sample.py printed and extracted on import."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("a backend module reached the network when imported")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    for module in pkgutil.walk_packages(backend.__path__, "backend."):
        importlib.import_module(module.name)

    assert capsys.readouterr().out == ""
