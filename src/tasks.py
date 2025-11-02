"""
Celery tasks for background processing of transcription and file operations.
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional
from .celery_app import celery_app
from .services.transcription import process_audio_file, AudioProcessor
from .services.file_processing import convert_to_mp3
from .cache import cache_manager

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='src.tasks.transcribe_audio_task')
def transcribe_audio_task(self, file_path: str, user_id: int) -> Dict[str, Any]:
    """
    Background task for audio transcription.

    Args:
        file_path: Path to the audio file
        user_id: User ID for caching and identification

    Returns:
        Dict containing transcription results or error information
    """
    # Create new event loop for async operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        logger.info(f"Starting transcription task for user {user_id}, file: {file_path}")

        # Update task state
        self.update_state(state='PROGRESS', meta={'progress': 10, 'message': 'Initializing...'})

        # Check cache first (async call)
        cached_result = loop.run_until_complete(cache_manager.get_transcription_result(file_path, user_id))
        if cached_result:
            logger.info(f"Using cached result for user {user_id}")
            return {
                'status': 'completed',
                'result': cached_result,
                'cached': True
            }

        # Create progress callback for Celery
        def progress_callback(progress: float, message: str):
            self.update_state(
                state='PROGRESS',
                meta={'progress': int(progress * 100), 'message': message}
            )

        # Process the audio file (async call)
        segments = loop.run_until_complete(process_audio_file(file_path, user_id, progress_callback))

        # Cache the result (async call)
        loop.run_until_complete(cache_manager.set_transcription_result(file_path, user_id, segments))

        logger.info(f"Transcription completed for user {user_id}, segments: {len(segments)}")

        return {
            'status': 'completed',
            'result': segments,
            'cached': False
        }

    except Exception as e:
        logger.error(f"Transcription task failed for user {user_id}: {str(e)}")
        self.update_state(
            state='FAILURE',
            meta={'error': str(e), 'traceback': str(e.__traceback__)}
        )
        raise
    finally:
        loop.close()


@celery_app.task(bind=True, name='src.tasks.process_file_task')
def process_file_task(self, file_path: str, target_format: str = 'mp3') -> Dict[str, Any]:
    """
    Background task for file processing (conversion, etc.).

    Args:
        file_path: Path to the input file
        target_format: Target format for conversion

    Returns:
        Dict containing processing results
    """
    # Create new event loop for async operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        logger.info(f"Starting file processing task for file: {file_path}")

        self.update_state(state='PROGRESS', meta={'progress': 10, 'message': 'Initializing...'})

        if target_format.lower() == 'mp3':
            # Convert to MP3
            self.update_state(state='PROGRESS', meta={'progress': 50, 'message': 'Converting to MP3...'})
            output_path = loop.run_until_complete(convert_to_mp3(file_path))

            self.update_state(state='PROGRESS', meta={'progress': 90, 'message': 'Finalizing...'})

            logger.info(f"File conversion completed: {output_path}")

            return {
                'status': 'completed',
                'output_path': output_path,
                'original_path': file_path
            }
        else:
            raise ValueError(f"Unsupported target format: {target_format}")

    except Exception as e:
        logger.error(f"File processing task failed: {str(e)}")
        self.update_state(
            state='FAILURE',
            meta={'error': str(e), 'traceback': str(e.__traceback__)}
        )
        raise
    finally:
        loop.close()


@celery_app.task(bind=True, name='src.tasks.batch_transcription_task')
def batch_transcription_task(self, file_paths: list, user_id: int) -> Dict[str, Any]:
    """
    Background task for batch transcription processing.

    Args:
        file_paths: List of file paths to process
        user_id: User ID for the batch operation

    Returns:
        Dict containing batch results
    """
    # Create new event loop for async operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        logger.info(f"Starting batch transcription for user {user_id}, files: {len(file_paths)}")

        results = {}
        total_files = len(file_paths)

        for i, file_path in enumerate(file_paths):
            progress = int((i / total_files) * 100)
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': progress,
                    'message': f'Processing file {i+1}/{total_files}',
                    'current_file': os.path.basename(file_path)
                }
            )

            try:
                # Process individual file (async call)
                segments = loop.run_until_complete(process_audio_file(file_path, user_id))
                results[file_path] = {
                    'status': 'completed',
                    'segments': segments
                }
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {str(e)}")
                results[file_path] = {
                    'status': 'failed',
                    'error': str(e)
                }

        logger.info(f"Batch transcription completed for user {user_id}")

        return {
            'status': 'completed',
            'results': results,
            'total_files': total_files,
            'successful': sum(1 for r in results.values() if r['status'] == 'completed')
        }

    except Exception as e:
        logger.error(f"Batch transcription task failed: {str(e)}")
        self.update_state(
            state='FAILURE',
            meta={'error': str(e), 'traceback': str(e.__traceback__)}
        )
        raise
    finally:
        loop.close()


@celery_app.task(bind=True, name='src.tasks.cleanup_task')
def cleanup_task(self, file_paths: list) -> Dict[str, Any]:
    """
    Background task for cleaning up temporary files.

    Args:
        file_paths: List of file paths to clean up

    Returns:
        Dict containing cleanup results
    """
    try:
        logger.info(f"Starting cleanup task for {len(file_paths)} files")

        cleaned = []
        failed = []

        for file_path in file_paths:
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    cleaned.append(file_path)
                elif os.path.isdir(file_path):
                    # Remove directory and contents
                    import shutil
                    shutil.rmtree(file_path)
                    cleaned.append(file_path)
                else:
                    failed.append(f"Path not found: {file_path}")
            except Exception as e:
                failed.append(f"Failed to remove {file_path}: {str(e)}")

        logger.info(f"Cleanup completed: {len(cleaned)} cleaned, {len(failed)} failed")

        return {
            'status': 'completed',
            'cleaned': cleaned,
            'failed': failed
        }

    except Exception as e:
        logger.error(f"Cleanup task failed: {str(e)}")
        self.update_state(
            state='FAILURE',
            meta={'error': str(e), 'traceback': str(e.__traceback__)}
        )
        raise
