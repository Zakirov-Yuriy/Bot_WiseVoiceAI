"""
Monitoring and error tracking setup with Sentry.
"""

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from .config import SENTRY_DSN
from .logging_config import get_logger

logger = get_logger(__name__)


def init_sentry():
    """
    Initialize Sentry error tracking.

    Only initializes if SENTRY_DSN is configured.
    """
    if not SENTRY_DSN:
        logger.info("Sentry DSN not configured, skipping Sentry initialization")
        return

    try:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            # Integrations
            integrations=[
                LoggingIntegration(
                    level=20,  # INFO level (Capture info and above as breadcrumbs)
                    event_level=40  # ERROR level (Send errors as events)
                ),
                AsyncioIntegration(),
            ],

            # Performance monitoring
            traces_sample_rate=0.1,  # Capture 10% of transactions

            # Release tracking
            release="wisevoiceai@1.0.0",

            # Environment
            environment="production",

            # Error filtering
            before_send=before_send,

            # User context
            send_default_pii=False,  # Don't send personally identifiable information
        )

        logger.info("Sentry error tracking initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")


def before_send(event, hint):
    """
    Filter and modify events before sending to Sentry.

    Args:
        event: The event dictionary
        hint: Contains additional information about the event

    Returns:
        Modified event or None to drop the event
    """
    # Don't send events for expected errors
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']

        # Filter out common expected errors
        expected_errors = [
            'RateLimitExceeded',
            'ValidationError',
            'TelegramBadRequest',
            'NetworkError',
        ]

        if exc_type and any(expected in str(exc_type.__name__) for expected in expected_errors):
            # Still log but don't send to Sentry
            logger.warning(f"Filtered expected error from Sentry: {exc_type.__name__}: {exc_value}")
            return None

    return event


def set_user_context(user_id: int, username: str = None, **kwargs):
    """
    Set user context for Sentry events.

    Args:
        user_id: Telegram user ID
        username: Telegram username
        **kwargs: Additional user context
    """
    user_context = {
        'id': str(user_id),
        'username': username,
    }
    user_context.update(kwargs)

    sentry_sdk.set_user(user_context)


def set_extra_context(**kwargs):
    """
    Set extra context for Sentry events.
    """
    sentry_sdk.set_extra(**kwargs)


def capture_exception(error: Exception, **kwargs):
    """
    Capture an exception with additional context.

    Args:
        error: The exception to capture
        **kwargs: Additional context
    """
    if kwargs:
        set_extra_context(**kwargs)

    sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = 'info', **kwargs):
    """
    Capture a message with additional context.

    Args:
        message: The message to capture
        level: Log level ('fatal', 'error', 'warning', 'info', 'debug')
        **kwargs: Additional context
    """
    if kwargs:
        set_extra_context(**kwargs)

    sentry_sdk.capture_message(message, level=level)


def add_breadcrumb(message: str, category: str = 'custom', level: str = 'info', **kwargs):
    """
    Add a breadcrumb for debugging.

    Args:
        message: Breadcrumb message
        category: Category for the breadcrumb
        level: Severity level
        **kwargs: Additional data
    """
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=kwargs
    )


class SentryMiddleware:
    """
    Middleware to add Sentry context for each request.
    """

    def __init__(self):
        self._initialized = False

    async def __call__(self, handler, event, data):
        """
        Add Sentry context for the current request.
        """
        user_id = data.get('user_id')
        user_info = data.get('user_info', {})

        if user_id:
            set_user_context(
                user_id=user_id,
                username=user_info.get('username'),
                first_name=user_info.get('first_name'),
                last_name=user_info.get('last_name'),
                language_code=user_info.get('language_code'),
                is_premium=user_info.get('is_premium', False)
            )

        # Add breadcrumb for request tracking
        add_breadcrumb(
            message=f"Processing {type(event).__name__}",
            category='request',
            level='info',
            user_id=user_id
        )

        try:
            return await handler(event, data)
        except Exception as e:
            # Capture exception with context
            capture_exception(e, user_id=user_id, event_type=type(event).__name__)
            raise


# Performance monitoring decorator
def monitor_performance(operation: str):
    """
    Decorator to monitor performance of functions.

    Args:
        operation: Name of the operation being monitored
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with sentry_sdk.start_transaction(op=operation, name=func.__name__):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


# Health check function
def health_check():
    """
    Perform a health check and report to Sentry.

    Returns:
        Dict with health status
    """
    try:
        # Check if Sentry is initialized
        if sentry_sdk.Hub.current.client:
            return {
                'status': 'healthy',
                'sentry_enabled': True,
                'sentry_dsn_configured': bool(SENTRY_DSN)
            }
        else:
            return {
                'status': 'healthy',
                'sentry_enabled': False,
                'sentry_dsn_configured': bool(SENTRY_DSN)
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        capture_exception(e, component='health_check')
        return {
            'status': 'unhealthy',
            'error': str(e)
        }
