import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from config import BASE_BACKOFF_SECONDS, MAX_RETRIES

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    base_delay: int = BASE_BACKOFF_SECONDS,
):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    return result
                except RetryableError as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = (2**attempt) * base_delay
                    logger.warning(
                        "Retryable error (attempt %d/%d): %s. Waiting %ds...",
                        attempt + 1,
                        max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                except Exception:
                    raise

        return wrapper

    return decorator


class RetryableError(Exception):
    pass
