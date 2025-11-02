"""
Celery configuration and task definitions for background processing.
"""

import os
from celery import Celery
from .config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

# Create Celery app
celery_app = Celery(
    'bot_wisevoiceai',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['src.tasks']
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,

    # Result backend settings
    result_expires=3600,  # 1 hour
    result_cache_max=10000,

    # Routing
    task_routes={
        'src.tasks.transcribe_audio_task': {'queue': 'transcription'},
        'src.tasks.process_file_task': {'queue': 'file_processing'},
    },

    # Task time limits
    task_time_limit=1800,  # 30 minutes
    task_soft_time_limit=1500,  # 25 minutes
)

# Optional: Configure logging
if __name__ == '__main__':
    celery_app.start()
