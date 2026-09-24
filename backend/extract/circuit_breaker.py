"""A circuit breaker in front of a model, so a dead gateway is not retried on every call.

CircuitBreaker(...).wrap(model) turns `model` into another ModelCall, so it slots in front of
whichever model should be protected - for example:

    qwen_breaker = CircuitBreaker()
    extractor_model = with_fallback(qwen_breaker.wrap(qwen_model), gemini_model,
                                    enabled=lambda: bool(gemini_key()))

Behaviour:
- Closed (normal): every call goes through to the wrapped model. A success resets the
  failure count to zero.
- After `threshold` consecutive failures, the breaker opens: for the next `cooldown` seconds,
  the wrapped model is not called at all - a CircuitOpen is raised immediately, so a caller
  such as with_fallback moves to its second model without waiting on the first at all.
- Once `cooldown` seconds have passed, the breaker goes half-open: exactly one call is let
  through to test whether the model has recovered. Success closes the breaker again; failure
  re-opens it and the cooldown starts over.

One CircuitBreaker instance holds state across calls, so create it once (module level) and
reuse it - a fresh instance per call would never remember a failure.
Thread-safe: extract calls run concurrently (SI and BL at once), so state is behind a lock.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 60.0


class CircuitOpen(RuntimeError):
    """The wrapped model is being skipped after repeated failures."""


class CircuitBreaker:
    def __init__(self, threshold: int = DEFAULT_THRESHOLD,
                cooldown: float = DEFAULT_COOLDOWN_SECONDS,
                clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None

    def _should_try(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at >= self.cooldown:
                return True  # cooldown elapsed: half-open, let one call through
            return False

    def _record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def _record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                if self._opened_at is not None:
                    log.warning("circuit re-opened after a failed half-open probe")
                else:
                    log.warning("circuit open after %d consecutive failures", self._failures)
                self._opened_at = self._clock()

    def wrap(self, model: Callable[[str], object]) -> Callable[[str], object]:
        def call(text: str):
            if not self._should_try():
                raise CircuitOpen(
                    f"skipping: {self.threshold} consecutive failures, retry after cooldown")
            try:
                result = model(text)
            except Exception:
                self._record_failure()
                raise
            self._record_success()
            return result

        return call