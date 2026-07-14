
import pytest

from utils.retry import RetryableError, retry_with_backoff


class TestRetryWithBackoff:
    def test_success_first_attempt(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0)
        def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_retryable_error(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("busy")
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 3

    def test_exhausts_retries(self):
        @retry_with_backoff(max_retries=2, base_delay=0)
        def func():
            raise RetryableError("always busy")

        with pytest.raises(RetryableError):
            func()

    def test_non_retryable_error_passes_through(self):
        @retry_with_backoff(max_retries=3, base_delay=0)
        def func():
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            func()

    def test_non_retryable_fails_immediately(self):
        call_count = 0

        @retry_with_backoff(max_retries=5, base_delay=0)
        def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            func()
        assert call_count == 1
