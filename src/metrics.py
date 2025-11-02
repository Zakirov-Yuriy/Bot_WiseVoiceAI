"""
Prometheus metrics collection for monitoring bot performance.
"""

import time
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
from .config import PROMETHEUS_PORT

# Request metrics
REQUEST_COUNT = Counter(
    'bot_requests_total',
    'Total number of requests processed',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'bot_request_duration_seconds',
    'Request processing duration in seconds',
    ['method', 'endpoint']
)

# User metrics
ACTIVE_USERS = Gauge(
    'bot_active_users',
    'Number of active users in the last hour'
)

USER_REQUESTS = Counter(
    'bot_user_requests_total',
    'Total requests per user',
    ['user_id']
)

# Transcription metrics
TRANSCRIPTION_COUNT = Counter(
    'bot_transcriptions_total',
    'Total number of transcriptions processed',
    ['status', 'cached']
)

TRANSCRIPTION_DURATION = Histogram(
    'bot_transcription_duration_seconds',
    'Transcription processing duration in seconds',
    ['cached']
)

# File processing metrics
FILE_PROCESSING_COUNT = Counter(
    'bot_file_processing_total',
    'Total number of files processed',
    ['operation', 'status']
)

FILE_PROCESSING_DURATION = Histogram(
    'bot_file_processing_duration_seconds',
    'File processing duration in seconds',
    ['operation']
)

# Cache metrics
CACHE_HITS = Counter(
    'bot_cache_hits_total',
    'Total number of cache hits',
    ['cache_type']
)

CACHE_MISSES = Counter(
    'bot_cache_misses_total',
    'Total number of cache misses',
    ['cache_type']
)

CACHE_SIZE = Gauge(
    'bot_cache_entries',
    'Number of entries in cache',
    ['cache_type']
)

# Error metrics
ERROR_COUNT = Counter(
    'bot_errors_total',
    'Total number of errors',
    ['error_type', 'component']
)

# Rate limiting metrics
RATE_LIMIT_EXCEEDED = Counter(
    'bot_rate_limits_exceeded_total',
    'Total number of rate limit violations',
    ['limit_type']
)

# System metrics
MEMORY_USAGE = Gauge(
    'bot_memory_usage_bytes',
    'Current memory usage in bytes'
)

# Info metric for version tracking
BOT_INFO = Info('bot_info', 'Bot information')
BOT_INFO.info({'version': '1.0.0', 'name': 'WiseVoiceAI'})


class MetricsCollector:
    """Collector for bot metrics"""

    def __init__(self):
        self._started = False

    def start_server(self):
        """Start Prometheus metrics server"""
        if not self._started:
            try:
                start_http_server(PROMETHEUS_PORT)
                self._started = True
                print(f"Prometheus metrics server started on port {PROMETHEUS_PORT}")
            except Exception as e:
                print(f"Failed to start Prometheus server: {e}")

    def record_request(self, method: str, endpoint: str, status: str, duration: float = None):
        """Record request metrics"""
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()

        if duration is not None:
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    def record_transcription(self, status: str, cached: bool, duration: float = None):
        """Record transcription metrics"""
        TRANSCRIPTION_COUNT.labels(status=status, cached=str(cached)).inc()

        if duration is not None:
            TRANSCRIPTION_DURATION.labels(cached=str(cached)).observe(duration)

    def record_file_processing(self, operation: str, status: str, duration: float = None):
        """Record file processing metrics"""
        FILE_PROCESSING_COUNT.labels(operation=operation, status=status).inc()

        if duration is not None:
            FILE_PROCESSING_DURATION.labels(operation=operation).observe(duration)

    def record_cache_hit(self, cache_type: str):
        """Record cache hit"""
        CACHE_HITS.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str):
        """Record cache miss"""
        CACHE_MISSES.labels(cache_type=cache_type).inc()

    def update_cache_size(self, cache_type: str, size: int):
        """Update cache size metric"""
        CACHE_SIZE.labels(cache_type=cache_type).set(size)

    def record_error(self, error_type: str, component: str):
        """Record error"""
        ERROR_COUNT.labels(error_type=error_type, component=component).inc()

    def record_rate_limit_exceeded(self, limit_type: str):
        """Record rate limit violation"""
        RATE_LIMIT_EXCEEDED.labels(limit_type=limit_type).inc()

    def update_active_users(self, count: int):
        """Update active users count"""
        ACTIVE_USERS.set(count)

    def record_user_request(self, user_id: int):
        """Record user request"""
        USER_REQUESTS.labels(user_id=str(user_id)).inc()

    def update_memory_usage(self, usage_bytes: int):
        """Update memory usage"""
        MEMORY_USAGE.set(usage_bytes)


# Global metrics collector instance
metrics_collector = MetricsCollector()


def init_metrics():
    """Initialize metrics collection"""
    metrics_collector.start_server()


# Helper functions for easy metric recording
def record_request(method: str, endpoint: str, status: str, duration: float = None):
    """Helper to record request metrics"""
    metrics_collector.record_request(method, endpoint, status, duration)


def record_transcription(status: str, cached: bool, duration: float = None):
    """Helper to record transcription metrics"""
    metrics_collector.record_transcription(status, cached, duration)


def record_file_processing(operation: str, status: str, duration: float = None):
    """Helper to record file processing metrics"""
    metrics_collector.record_file_processing(operation, status, duration)


def record_cache_hit(cache_type: str):
    """Helper to record cache hit"""
    metrics_collector.record_cache_hit(cache_type)


def record_cache_miss(cache_type: str):
    """Helper to record cache miss"""
    metrics_collector.record_cache_miss(cache_type)


def record_error(error_type: str, component: str):
    """Helper to record error"""
    metrics_collector.record_error(error_type, component)


def record_rate_limit_exceeded(limit_type: str):
    """Helper to record rate limit violation"""
    metrics_collector.record_rate_limit_exceeded(limit_type)
