"""
Middleware for rate limiting and other request processing.
"""

import time
from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from .cache import cache_manager
from .logging_config import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware for aiogram bot.

    Limits requests per user based on time windows.
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        requests_per_hour: int = 100,
        burst_limit: int = 10
    ):
        super().__init__()
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_limit = burst_limit

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Check rate limits before processing the event.
        """
        user_id = self._get_user_id(event)

        if user_id:
            # Check rate limits
            if not await self._check_rate_limits(user_id):
                logger.warning(f"Rate limit exceeded for user {user_id}")
                # Don't process the event if rate limit is exceeded
                return

        # Process the event
        return await handler(event, data)

    def _get_user_id(self, event: Message | CallbackQuery) -> int | None:
        """Extract user ID from event."""
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return None

    async def _check_rate_limits(self, user_id: int) -> bool:
        """
        Check if user is within rate limits.

        Returns True if request should be allowed, False if rate limited.
        """
        current_time = int(time.time())

        # Check minute limit
        minute_key = f"ratelimit:{user_id}:minute:{current_time // 60}"
        minute_count = await self._get_and_increment_counter(minute_key)

        # Check hour limit
        hour_key = f"ratelimit:{user_id}:hour:{current_time // 3600}"
        hour_count = await self._get_and_increment_counter(hour_key)

        # Check burst limit (last 10 seconds)
        burst_key = f"ratelimit:{user_id}:burst:{current_time // 10}"
        burst_count = await self._get_and_increment_counter(burst_key)

        # Check limits
        if burst_count > self.burst_limit:
            logger.warning(f"Burst rate limit exceeded for user {user_id}: {burst_count}/{self.burst_limit}")
            return False

        if minute_count > self.requests_per_minute:
            logger.warning(f"Minute rate limit exceeded for user {user_id}: {minute_count}/{self.requests_per_minute}")
            return False

        if hour_count > self.requests_per_hour:
            logger.warning(f"Hour rate limit exceeded for user {user_id}: {hour_count}/{self.requests_per_hour}")
            return False

        return True

    async def _get_and_increment_counter(self, key: str) -> int:
        """Get current counter value and increment it."""
        try:
            # Get current value
            current_value = await cache_manager.get_user_data(0, key)  # Use user_id 0 for system keys
            if current_value is None:
                current_value = 0

            # Increment and store
            new_value = current_value + 1
            await cache_manager.set_user_data(0, key, new_value)

            return new_value
        except Exception as e:
            logger.warning(f"Error managing rate limit counter {key}: {e}")
            return 0  # Allow request if Redis fails


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging all incoming events.
    """

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Log incoming events.
        """
        user_id = None
        event_type = type(event).__name__

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            content = event.text or event.caption or f"[{event.content_type}]"
            logger.info(f"Message from user {user_id}: {content[:100]}...")
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            logger.info(f"Callback from user {user_id}: {event.data}")

        # Measure processing time
        start_time = time.time()
        try:
            result = await handler(event, data)
            processing_time = time.time() - start_time
            logger.debug(f"Processed {event_type} for user {user_id} in {processing_time:.3f}s")
            return result
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error processing {event_type} for user {user_id} after {processing_time:.3f}s: {e}")
            raise


class UserContextMiddleware(BaseMiddleware):
    """
    Middleware for adding user context to handler data.
    """

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Add user context information to handler data.
        """
        user_id = None
        user_info = {}

        if isinstance(event, Message) and event.from_user:
            user = event.from_user
            user_id = user.id
            user_info = {
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'language_code': user.language_code,
                'is_premium': getattr(user, 'is_premium', False)
            }
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user
            user_id = user.id
            user_info = {
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'language_code': user.language_code,
                'is_premium': getattr(user, 'is_premium', False)
            }

        # Add user info to handler data
        data['user_info'] = user_info
        data['user_id'] = user_id

        return await handler(event, data)
