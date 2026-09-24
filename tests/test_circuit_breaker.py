"""The circuit breaker in front of Qwen: after repeated failures, skip it entirely for a
cooldown, rather than paying for a failed call on every email while the gateway is down.

A fake clock stands in for time.monotonic, so these run instantly with no real sleeping."""
from __future__ import annotations

import pytest

from backend.extract.circuit_breaker import CircuitBreaker, CircuitOpen


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def broken(text: str) -> str:
    raise RuntimeError("gateway unreachable")


def test_calls_pass_through_while_closed() -> None:
    breaker = CircuitBreaker(threshold=3, cooldown=10, clock=FakeClock())
    model = breaker.wrap(lambda text: "ok")

    assert model("doc") == "ok"


def test_opens_after_threshold_consecutive_failures() -> None:
    breaker = CircuitBreaker(threshold=3, cooldown=10, clock=FakeClock())
    model = breaker.wrap(broken)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            model("doc")

    with pytest.raises(CircuitOpen):
        model("doc")


def test_open_circuit_never_calls_the_wrapped_model() -> None:
    calls = []

    def counted(text: str) -> str:
        calls.append(text)
        raise RuntimeError("down")

    breaker = CircuitBreaker(threshold=2, cooldown=10, clock=FakeClock())
    model = breaker.wrap(counted)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            model("doc")
    with pytest.raises(CircuitOpen):
        model("doc")

    assert len(calls) == 2  # the 3rd call never reached the model


def test_a_success_resets_the_failure_count() -> None:
    calls = iter(["fail", "fail", "ok", "ok"])

    def flaky(text: str) -> str:
        outcome = next(calls)
        if outcome == "fail":
            raise RuntimeError("down")
        return outcome

    breaker = CircuitBreaker(threshold=3, cooldown=10, clock=FakeClock())
    model = breaker.wrap(flaky)

    with pytest.raises(RuntimeError):
        model("doc")
    with pytest.raises(RuntimeError):
        model("doc")
    assert model("doc") == "ok"  # success before hitting the threshold

    # two more failures would have tripped it pre-reset; now it takes three fresh ones
    assert model("doc") == "ok"


def test_stays_open_until_the_cooldown_elapses() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=1, cooldown=30, clock=clock)
    model = breaker.wrap(broken)

    with pytest.raises(RuntimeError):
        model("doc")

    clock.now = 29.9
    with pytest.raises(CircuitOpen):
        model("doc")

    clock.now = 30.0
    with pytest.raises(RuntimeError):  # cooldown elapsed: the real model is tried again
        model("doc")


def test_half_open_success_closes_the_circuit() -> None:
    clock = FakeClock()
    calls = iter(["fail", "fail", "fail", "ok"])

    def recovering(text: str) -> str:
        outcome = next(calls)
        if outcome == "fail":
            raise RuntimeError("down")
        return outcome

    breaker = CircuitBreaker(threshold=3, cooldown=10, clock=clock)
    model = breaker.wrap(recovering)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            model("doc")
    with pytest.raises(CircuitOpen):
        model("doc")  # still within cooldown

    clock.now = 10.0
    assert model("doc") == "ok"  # half-open probe succeeds, circuit closes

    # closed again: the very next failure alone should not trip it
    def one_more_failure(text: str) -> str:
        raise RuntimeError("down")

    breaker2 = CircuitBreaker(threshold=3, cooldown=10, clock=clock)
    model2 = breaker2.wrap(one_more_failure)
    with pytest.raises(RuntimeError):
        model2("doc")
    with pytest.raises(RuntimeError):  # 2nd failure, still under threshold=3
        model2("doc")


def test_half_open_failure_reopens_and_restarts_the_cooldown() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=1, cooldown=10, clock=clock)
    model = breaker.wrap(broken)

    with pytest.raises(RuntimeError):
        model("doc")  # opens at t=0

    clock.now = 10.0
    with pytest.raises(RuntimeError):
        model("doc")  # half-open probe fails, re-opens at t=10

    clock.now = 19.9
    with pytest.raises(CircuitOpen):
        model("doc")  # cooldown restarted, still within 10s of the re-open

    clock.now = 20.0
    with pytest.raises(RuntimeError):
        model("doc")  # cooldown elapsed again


def test_composes_with_with_fallback_so_gemini_answers_while_open() -> None:
    """The real wiring in app.py: circuit_breaker.wrap(qwen_model) is `first` in with_fallback."""
    from backend.extract.fallback import with_fallback

    breaker = CircuitBreaker(threshold=2, cooldown=100, clock=FakeClock())
    protected_qwen = breaker.wrap(broken)
    model = with_fallback(protected_qwen, lambda text: "gemini answered", enabled=lambda: True)

    for _ in range(2):
        assert model("doc") == "gemini answered"  # fallback covers the first two failures too
    # breaker is now open; with_fallback still gets a fast failure and reaches Gemini
    assert model("doc") == "gemini answered"