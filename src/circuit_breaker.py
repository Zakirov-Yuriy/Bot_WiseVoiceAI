import asyncio
import logging
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, expected_exception: type = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.last_failure_time = None

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        logger.info("Circuit breaker reset to CLOSED")

    def _on_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.last_failure_time = asyncio.get_event_loop().time()
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
        else:
            logger.warning(f"Circuit breaker failure count: {self.failure_count}")

    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return asyncio.get_event_loop().time() - self.last_failure_time >= self.recovery_timeout
