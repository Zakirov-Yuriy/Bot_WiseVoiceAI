from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable, Any, Tuple, Protocol, TypedDict


class Segment(TypedDict):
    speaker: str
    text: str


class TranscriptionServiceInterface(Protocol):
    """Интерфейс для сервиса транскрибации"""

    async def process_audio_file(self, file_path: str, user_id: int, progress_callback: Optional[Callable] = None) -> List[Segment]:
        """Обработать аудиофайл и вернуть сегменты с транскрибацией"""
        ...

    def format_results_with_speakers(self, segments: List[Segment]) -> str:
        """Форматировать результаты с указанием спикеров"""
        ...

    def format_results_plain(self, segments: List[Segment]) -> str:
        """Форматировать результаты без спикеров"""
        ...

    async def generate_summary_timecodes(self, segments: List[Segment]) -> str:
        """Сгенерировать сводку с тайм-кодами"""
        ...


class PaymentServiceInterface(Protocol):
    """Интерфейс для сервиса платежей"""

    async def create_payment(self, user_id: int, amount: int, description: str) -> Tuple[Optional[str], Optional[str]]:
        """Создать платеж и вернуть URL и метку"""
        ...


class FileProcessingServiceInterface(Protocol):
    """Интерфейс для сервиса обработки файлов"""

    def save_text_to_pdf(self, text: str, output_path: str) -> None:
        """Сохранить текст в PDF"""
        ...

    def save_text_to_txt(self, text: str, output_path: str) -> None:
        """Сохранить текст в TXT"""
        ...

    def save_text_to_md(self, text: str, output_path: str) -> None:
        """Сохранить текст в MD"""
        ...

    def save_text_to_docx(self, text: str, output_path: str) -> None:
        """Сохранить текст в DOCX"""
        ...

    async def download_youtube_audio(self, url: str, progress_callback: Optional[Callable] = None) -> str:
        """Скачать аудио из YouTube"""
        ...

    async def convert_to_mp3(self, input_path: str) -> str:
        """Конвертировать файл в MP3"""
        ...

    def create_custom_thumbnail(self, thumbnail_path: Optional[str] = None) -> Optional[Any]:
        """Создать thumbnail"""
        ...
