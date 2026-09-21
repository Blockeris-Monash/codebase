"""A second model behind the first, so one provider being down is not the end.

with_fallback(first, second) is itself a ModelCall (text in, seven fields out), so it goes
anywhere a model does, for example AiExtractor(with_fallback(qwen_model, gemini_model)).

The first model is tried once. If it raises, or gives no answer within first_timeout seconds,
the second one answers. A hung first call is not waited for: it finishes on its own thread
while the second model works, so a stalled gateway costs first_timeout seconds and not the
gateway's own much longer retry chain.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as NoAnswerInTime

from backend.extract.ai import ModelCall

log = logging.getLogger(__name__)

# The live check takes about 25 s and the slowest measured was 44 s, so 60 s never cuts
# off a healthy Qwen call and still turns a stalled one into a quick switch.
DEFAULT_FIRST_TIMEOUT_SECONDS = 60.0


def with_fallback(first: ModelCall, second: ModelCall,
                  first_timeout: float = DEFAULT_FIRST_TIMEOUT_SECONDS) -> ModelCall:
    def call(text: str):
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(first, text).result(timeout=first_timeout)
        except NoAnswerInTime:
            reason = f"no answer in {first_timeout:g}s"
        except Exception as error:
            reason = str(error) or type(error).__name__
        finally:
            pool.shutdown(wait=False)  # do not wait for a hung call; it ends on its own

        log.warning("first model failed (%s), using the second", reason)
        return second(text)

    return call
