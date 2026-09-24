"""A second model behind the first, so one provider being down is not the end.

with_fallback(first, second) is itself a ModelCall (text in, seven fields out), so it goes
anywhere a model does, for example AiExtractor(with_fallback(qwen_model, gemini_model)).

The first model is tried once. If it raises, or gives no answer within first_timeout seconds,
the second one answers. `enabled` is asked on every call: when it says no (for example there
is no Gemini key), the first model is used exactly as if there were no fallback, with no
timeout, so a slow but working call is still waited for. A hung first call is not waited for: it finishes on its own thread
while the second model works, so a stalled gateway costs first_timeout seconds and not the
gateway's own much longer retry chain.

Every call is recorded for the technical reports (backend/reports.py), named by `names`.
Every caller today stands Gemini behind Qwen, hence the default.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as NoAnswerInTime

from backend import reports
from backend.extract.ai import ModelCall

log = logging.getLogger(__name__)

# The live check takes about 25 s and the slowest measured was 44 s, so 60 s never cuts
# off a healthy Qwen call and still turns a stalled one into a quick switch.
DEFAULT_FIRST_TIMEOUT_SECONDS = 60.0


def with_fallback(first: ModelCall, second: ModelCall,
                  first_timeout: float = DEFAULT_FIRST_TIMEOUT_SECONDS,
                  enabled: Callable[[], bool] = lambda: True,
                  names: tuple[str, str] = ("Qwen", "Gemini")) -> ModelCall:
    def call(text: str):
        if not enabled():
            return timed(names[0], first, text)

        pool = ThreadPoolExecutor(max_workers=1)
        started = time.perf_counter()
        try:
            answer = pool.submit(first, text).result(timeout=first_timeout)
        except NoAnswerInTime:
            reason = f"no answer in {first_timeout:g}s"
        except Exception as error:
            reason = str(error) or type(error).__name__
        else:
            reports.record(names[0], reports.ANSWERED, time.perf_counter() - started)
            return answer
        finally:
            pool.shutdown(wait=False)  # do not wait for a hung call; it ends on its own

        reports.record(names[0], reason, time.perf_counter() - started)
        log.warning("first model failed (%s), using the second", reason)
        return timed(names[1], second, text)

    return call


def timed(name: str, model: ModelCall, text: str):
    """One model call, recorded whether it answers or raises."""
    started = time.perf_counter()
    try:
        answer = model(text)
    except Exception as error:
        reports.record(name, str(error) or type(error).__name__, time.perf_counter() - started)
        raise
    reports.record(name, reports.ANSWERED, time.perf_counter() - started)

    return answer
