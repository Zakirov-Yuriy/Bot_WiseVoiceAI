from .interfaces import (
    TranscriptionServiceInterface,
    PaymentServiceInterface,
    FileProcessingServiceInterface,
    Segment
)
from .transcription import (
    OpenRouterClient,
    AudioProcessor,
    upload_to_assemblyai,
    transcribe_with_assemblyai,
    process_audio_file,
    format_results_with_speakers,
    format_results_plain,
    generate_summary_timecodes,
    openrouter_client
)
from .payment import create_yoomoney_payment
from .file_processing import (
    save_text_to_pdf,
    save_text_to_txt,
    save_text_to_md,
    save_text_to_docx,
    download_youtube_audio,
    convert_to_mp3,
    create_custom_thumbnail,
    THUMBNAIL_CACHE
)
from ..ui import user_selections, progress_manager, user_settings


# Concrete implementations that implement the interfaces
class AssemblyAITranscriptionService:
    """Реализация сервиса транскрибации через AssemblyAI"""

    async def process_audio_file(self, file_path: str, user_id: int, progress_callback=None):
        return await process_audio_file(file_path, user_id, progress_callback)

    def format_results_with_speakers(self, segments):
        return format_results_with_speakers(segments)

    def format_results_plain(self, segments):
        return format_results_plain(segments)

    async def generate_summary_timecodes(self, segments):
        return await generate_summary_timecodes(segments)


class YooMoneyPaymentService:
    """Реализация сервиса платежей через YooMoney"""

    async def create_payment(self, user_id: int, amount: int, description: str):
        return await create_yoomoney_payment(user_id, amount, description)


class LocalFileProcessingService:
    """Реализация сервиса обработки файлов"""

    def save_text_to_pdf(self, text: str, output_path: str) -> None:
        return save_text_to_pdf(text, output_path)

    def save_text_to_txt(self, text: str, output_path: str) -> None:
        return save_text_to_txt(text, output_path)

    def save_text_to_md(self, text: str, output_path: str) -> None:
        return save_text_to_md(text, output_path)

    def save_text_to_docx(self, text: str, output_path: str) -> None:
        return save_text_to_docx(text, output_path)

    async def download_youtube_audio(self, url: str, progress_callback=None) -> str:
        return await download_youtube_audio(url, progress_callback)

    async def convert_to_mp3(self, input_path: str) -> str:
        return await convert_to_mp3(input_path)

    def create_custom_thumbnail(self, thumbnail_path=None):
        return create_custom_thumbnail(thumbnail_path)


# Default service instances
transcription_service: TranscriptionServiceInterface = AssemblyAITranscriptionService()
payment_service: PaymentServiceInterface = YooMoneyPaymentService()
file_processing_service: FileProcessingServiceInterface = LocalFileProcessingService()


__all__ = [
    # Interfaces
    'TranscriptionServiceInterface',
    'PaymentServiceInterface',
    'FileProcessingServiceInterface',
    'Segment',

    # Concrete implementations
    'AssemblyAITranscriptionService',
    'YooMoneyPaymentService',
    'LocalFileProcessingService',

    # Default service instances
    'transcription_service',
    'payment_service',
    'file_processing_service',

    # Direct function imports for backward compatibility
    'OpenRouterClient',
    'AudioProcessor',
    'upload_to_assemblyai',
    'transcribe_with_assemblyai',
    'process_audio_file',
    'format_results_with_speakers',
    'format_results_plain',
    'generate_summary_timecodes',
    'openrouter_client',
    'create_yoomoney_payment',
    'save_text_to_pdf',
    'save_text_to_txt',
    'save_text_to_md',
    'save_text_to_docx',
    'download_youtube_audio',
    'convert_to_mp3',
    'create_custom_thumbnail',
    'THUMBNAIL_CACHE',
    'user_selections',
    'progress_manager',
    'user_settings'
]
