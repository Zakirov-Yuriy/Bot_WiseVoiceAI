import asyncio
import logging
import os
import tempfile
import subprocess
import io
import yt_dlp
import httpx
import uuid
import json
import requests
import time
import secrets
from typing import List, Dict, Optional, Callable, Any, Tuple, TypedDict

from ..config import (
    ASSEMBLYAI_BASE_URL, HEADERS, API_TIMEOUT, FFMPEG_BIN, FFPROBE_BIN,
    SEGMENT_DURATION, OPENROUTER_API_KEYS, OPENROUTER_BASE_URL, OPENROUTER_MODEL, FONT_PATH,
    YOOMONEY_WALLET, YOOMONEY_BASE_URL, SUBSCRIPTION_AMOUNT, THUMBNAIL_COLOR
)
from ..exceptions import PaymentError, TranscriptionError, FileProcessingError, APIError, NetworkError
from ..circuit_breaker import CircuitBreaker


logger = logging.getLogger(__name__)


class Segment(TypedDict):
    speaker: str
    text: str


# =============================
#     OpenRouter Client with API Key Rotation
# =============================
class OpenRouterClient:
    """Клиент для работы с OpenRouter API с автоматической ротацией ключей при 429."""

    def __init__(self, api_keys: List[str], base_url: str = OPENROUTER_BASE_URL, model: str = OPENROUTER_MODEL):
        self.api_keys = api_keys or []
        self.base_url = base_url
        self.model = model
        self.current_key_index = 0
        self.keys_tried = 0
        logger.info(f"Инициализирован OpenRouter клиент с {len(self.api_keys)} ключами")

    def get_current_key(self) -> Optional[str]:
        """Получить текущий ключ."""
        if not self.api_keys:
            return None
        return self.api_keys[self.current_key_index % len(self.api_keys)]

    def switch_to_next_key(self):
        """Переключиться на следующий ключ."""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self.keys_tried += 1
        logger.info(f"Переключаемся на следующий OPENROUTER API ключ, индекс {self.current_key_index}")

    async def make_request(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Выполнить запрос к OpenRouter с автоматической ротацией ключей."""
        if not self.api_keys:
            logger.error("OPENROUTER_API_KEYS не настроены")
            raise ValueError("OPENROUTER_API_KEYS не настроены")

        url = f"{self.base_url}/chat/completions"
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }

        for attempt in range(len(self.api_keys)):
            api_key = self.get_current_key()
            logger.debug(f"Попытка запроса к OpenRouter с ключом индекс {self.current_key_index}")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, headers=headers, json=data, timeout=60)
                    if response.status_code == 429:
                        logger.warning(f"Получен 429 (Too Many Requests) с ключом {self.current_key_index}, переключаемся на следующий")
                        self.switch_to_next_key()
                        continue
                    response.raise_for_status()
                    return response.json()['choices'][0]['message']['content'].strip()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning(f"HTTP 429 с ключом {self.current_key_index}, пробуем следующий")
                    self.switch_to_next_key()
                    continue
                else:
                    logger.error(f"OpenRouter API ошибка {e.response.status_code}: {e}")
                    raise
            except Exception as e:
                logger.error(f"Ошибка запроса к OpenRouter: {e}")
                if attempt < len(self.api_keys) - 1:
                    self.switch_to_next_key()
                    continue
                raise

        logger.error("Все OPENROUTER API ключи вернули ошибки или 429")
        raise Exception("Все OPENROUTER API ключи исчерпаны")


# Создаём экземпляр клиента
openrouter_client = OpenRouterClient(OPENROUTER_API_KEYS)


# ---------- Аудио-обработка / API ----------

class AudioProcessor:
    @staticmethod
    def split_audio(input_path: str, segment_time: int = SEGMENT_DURATION) -> list[str]:
        output_dir = tempfile.mkdtemp(prefix="fragments_")
        output_pattern = os.path.join(output_dir, "fragment_%03d.mp3")
        ffmpeg_path = FFMPEG_BIN
        command = [ffmpeg_path, "-i", input_path, "-f", "segment", "-segment_time", str(segment_time), "-c", "copy", output_pattern]

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return sorted([
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if f.startswith("fragment_") and f.endswith(".mp3")
            ])
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise RuntimeError("Ошибка при разделении аудио") from e

    @staticmethod
    def cleanup(files: List[str]) -> None:
        for path in files:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    for f in os.listdir(path):
                        os.remove(os.path.join(path, f))
                    os.rmdir(path)
            except (OSError, FileNotFoundError) as e:
                logger.warning(f"Ошибка удаления {path}: {e}")


async def upload_to_assemblyai(file_path: str, retries: int = 3) -> str:
    async def _make_request():
        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    f"{ASSEMBLYAI_BASE_URL}/upload",
                    headers=HEADERS,
                    files={"file": f},
                    timeout=API_TIMEOUT
                )
            response.raise_for_status()
            return response.json()["upload_url"]

    circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30, expected_exception=(httpx.RequestError, httpx.HTTPStatusError, KeyError))

    for attempt in range(retries):
        try:
            result = await circuit_breaker.call(_make_request)
            return result
        except (httpx.RequestError, httpx.HTTPStatusError, KeyError) as e:
            logger.warning(f"Попытка {attempt + 1}/{retries} загрузки файла не удалась: {str(e)}")
            if attempt == retries - 1:
                raise TranscriptionError("Не удалось загрузить файл на сервер AssemblyAI") from e
            time.sleep(2 ** attempt)


async def transcribe_with_assemblyai(audio_url: str, retries: int = 3) -> Dict[str, Any]:
    headers = {
        "authorization": HEADERS['authorization'],
        "content-type": "application/json"
    }
    payload = {
        "audio_url": audio_url,
        "speaker_labels": True,
        "punctuate": True,
        "format_text": True,
        "language_detection": True
    }

    async def _make_request():
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ASSEMBLYAI_BASE_URL}/transcript",
                headers=headers, json=payload
            )
            resp.raise_for_status()
            transcript_id = resp.json()["id"]
            while True:
                status = await client.get(
                    f"{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}",
                    headers=headers
                )
                result = status.json()
                if result["status"] == "completed":
                    return result
                elif result["status"] == "error":
                    raise TranscriptionError(result["error"])
                await asyncio.sleep(3)

    circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30, expected_exception=(httpx.RequestError, httpx.HTTPStatusError, TranscriptionError, KeyError))

    for attempt in range(retries):
        try:
            result = await circuit_breaker.call(_make_request)
            return result
        except (httpx.RequestError, httpx.HTTPStatusError, TranscriptionError, KeyError) as e:
            logger.warning(f"Попытка {attempt + 1}/{retries} транскрипции не удалась: {str(e)}")
            if attempt == retries - 1:
                raise TranscriptionError("Не удалось выполнить транскрипцию") from e
            time.sleep(2 ** attempt)


async def process_audio_file(file_path: str, user_id: int, progress_callback: Optional[Callable] = None) -> List[Segment]:
    try:
        logger.info(f"Обработка аудиофайла: {file_path}")
        if progress_callback:
            await progress_callback(0.01, "Загружаю файл для обработки...")
        audio_url = await upload_to_assemblyai(file_path)
        if progress_callback:
            await progress_callback(0.30, "Запускаю транскрибацию...")
        result = await transcribe_with_assemblyai(audio_url)
        if progress_callback:
            await progress_callback(0.90, "Формирую результаты...")
        segments = []
        if "utterances" in result and result["utterances"]:
            for utt in result["utterances"]:
                segments.append({
                    "speaker": utt.get("speaker", "?"),
                    "text": (utt.get("text") or "").strip()
                })
        elif "text" in result:
            segments.append({"speaker": "?", "text": (result["text"] or "").strip()})
        if progress_callback:
            await progress_callback(1.0, "Обработка завершена!")
        logger.info(f"Транскрибация завершена, найдено {len(segments)} сегментов")
        return segments
    except (TranscriptionError, FileProcessingError) as e:
        logger.error(f"Ошибка в process_audio_file: {str(e)}")
        raise


def format_results_with_speakers(segments: List[Segment]) -> str:
    return "\n\n".join(f"Спикер {seg['speaker']}:\n{seg['text']}" for seg in segments)


def format_results_plain(segments: List[Segment]) -> str:
    return "\n\n".join(seg["text"] for seg in segments)


async def generate_summary_timecodes(segments: List[Segment]) -> str:
    full_text_with_timestamps = ""
    for i, seg in enumerate(segments):
        start_minute = i * SEGMENT_DURATION // 60
        start_second = i * SEGMENT_DURATION % 60
        start_code = f"{start_minute:02}:{start_second:02}"
        full_text_with_timestamps += f"[{start_code}] {seg['text']}\n\n"
    prompt = f"""
Проанализируй полную расшифровку аудио с тайм-кодами и создай структурированное оглавление.
Текст с тайм-кодами:
{full_text_with_timestamps}
Инструкции:
1. Выдели ОСНОВНЫЕ смысловые блоки и темы
2. Группируй несколько последовательных сегментов в один логический блок
3. Для каждого блока укажи время начала
4. Дай емкое описание содержания блока
5. Сохраняй хронологический порядок
Формат ответа:
Тайм-коды
MM:SS - [Основная тема/событие]
[Дополнительные детали]
MM:SS - [Следующая основная тема]
...
"""

    try:
        return await openrouter_client.make_request([{"role": "user", "content": prompt}], temperature=0.2)
    except Exception as e:
        logger.warning(f"Попытка генерации тайм-кодов с OpenRouter не удалась: {e}")
        logger.info("Используем fallback для тайм-кодов")

    # Fallback
    fallback_result = "Тайм-коды\n\n"
    for i, seg in enumerate(segments):
        start_minute = i * SEGMENT_DURATION // 60
        start_second = i * SEGMENT_DURATION % 60
        start_code = f"{start_minute:02}:{start_second:02}"
        fallback_result += f"{start_code} - {seg['text'][:50]}...\n"
    return fallback_result
