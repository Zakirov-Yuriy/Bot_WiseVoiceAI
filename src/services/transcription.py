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
from ..cache import cache_manager
from ..exceptions import PaymentError, TranscriptionError, FileProcessingError, APIError, NetworkError
from ..circuit_breaker import CircuitBreaker

# AWS imports for microservice integration
try:
    import boto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    boto3 = None


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


# =============================
#     AWS Microservice Client
# =============================
class TranscriptionMicroserviceClient:
    """Клиент для работы с микросервисом транскрибации на AWS Lambda + S3"""

    def __init__(self,
                 s3_bucket: str,
                 lambda_function: str,
                 region: str = "us-east-1",
                 use_microservice: bool = False):
        self.s3_bucket = s3_bucket
        self.lambda_function = lambda_function
        self.region = region
        self.use_microservice = use_microservice and AWS_AVAILABLE

        if self.use_microservice:
            self.s3_client = boto3.client('s3', region_name=region)
            self.lambda_client = boto3.client('lambda', region_name=region)
            logger.info(f"Инициализирован AWS микросервис клиент: S3={s3_bucket}, Lambda={lambda_function}")
        else:
            logger.info("AWS микросервис отключен, используется локальная обработка")

    async def upload_file_to_s3(self, file_path: str, user_id: int, file_id: str) -> str:
        """Загрузить файл в S3"""
        if not self.use_microservice:
            raise RuntimeError("Микросервис не настроен")

        s3_key = f"transcription/{user_id}/{file_id}.mp3"

        try:
            self.s3_client.upload_file(file_path, self.s3_bucket, s3_key)
            logger.info(f"Файл загружен в S3: {s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Ошибка загрузки в S3: {e}")
            raise TranscriptionError(f"Не удалось загрузить файл в S3: {str(e)}")

    async def invoke_lambda_transcription(self, s3_key: str, user_id: int, file_id: str) -> str:
        """Вызвать Lambda функцию для транскрибации"""
        if not self.use_microservice:
            raise RuntimeError("Микросервис не настроен")

        payload = {
            "s3_key": s3_key,
            "user_id": user_id,
            "file_id": file_id,
            "bucket": self.s3_bucket
        }

        try:
            response = self.lambda_client.invoke(
                FunctionName=self.lambda_function,
                InvocationType='Event',  # Асинхронный вызов
                Payload=json.dumps(payload)
            )
            logger.info(f"Lambda функция вызвана для файла {file_id}")
            return file_id
        except ClientError as e:
            logger.error(f"Ошибка вызова Lambda: {e}")
            raise TranscriptionError(f"Не удалось вызвать Lambda функцию: {str(e)}")

    async def get_transcription_result(self, file_id: str, timeout: int = 300) -> Optional[List[Segment]]:
        """Получить результат транскрибации из S3"""
        if not self.use_microservice:
            return None

        result_key = f"transcription/results/{file_id}.json"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=result_key)
                result_data = json.loads(response['Body'].read().decode('utf-8'))

                if result_data.get('status') == 'completed':
                    segments = result_data.get('segments', [])
                    logger.info(f"Результат транскрибации получен для файла {file_id}")
                    return segments
                elif result_data.get('status') == 'error':
                    error_msg = result_data.get('error', 'Неизвестная ошибка')
                    logger.error(f"Ошибка транскрибации для файла {file_id}: {error_msg}")
                    raise TranscriptionError(f"Ошибка обработки файла: {error_msg}")

            except self.s3_client.exceptions.NoSuchKey:
                # Результат еще не готов
                await asyncio.sleep(5)
                continue
            except ClientError as e:
                logger.error(f"Ошибка получения результата из S3: {e}")
                raise TranscriptionError(f"Не удалось получить результат: {str(e)}")

        logger.warning(f"Таймаут ожидания результата для файла {file_id}")
        return None

    async def process_with_microservice(self, file_path: str, user_id: int, progress_callback: Optional[Callable] = None) -> List[Segment]:
        """Обработать файл через микросервис"""
        file_id = str(uuid.uuid4())

        # Загружаем файл в S3
        if progress_callback:
            await progress_callback(0.1, "Загружаю файл в облако...")
        s3_key = await self.upload_file_to_s3(file_path, user_id, file_id)

        # Вызываем Lambda
        if progress_callback:
            await progress_callback(0.3, "Запускаю обработку...")
        await self.invoke_lambda_transcription(s3_key, user_id, file_id)

        # Ждем результат
        if progress_callback:
            await progress_callback(0.5, "Ожидаю завершения обработки...")
        result = await self.get_transcription_result(file_id)

        if result is None:
            raise TranscriptionError("Превышено время ожидания обработки файла")

        if progress_callback:
            await progress_callback(1.0, "Обработка завершена!")

        return result


# Создаём экземпляр микросервис клиента (если настроен)
def create_microservice_client():
    """Создать клиент микросервиса на основе переменных окружения"""
    s3_bucket = os.getenv("TRANSCRIPTION_S3_BUCKET")
    lambda_function = os.getenv("TRANSCRIPTION_LAMBDA_FUNCTION")
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    use_microservice = os.getenv("USE_TRANSCRIPTION_MICROSERVICE", "false").lower() == "true"

    if use_microservice and s3_bucket and lambda_function:
        return TranscriptionMicroserviceClient(
            s3_bucket=s3_bucket,
            lambda_function=lambda_function,
            region=aws_region,
            use_microservice=True
        )
    else:
        return TranscriptionMicroserviceClient(
            s3_bucket="",
            lambda_function="",
            use_microservice=False
        )

microservice_client = create_microservice_client()


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

        # Check cache first
        cached_result = await cache_manager.get_transcription_result(file_path, user_id)
        if cached_result:
            logger.info("Using cached transcription result")
            if progress_callback:
                await progress_callback(1.0, "Обработка завершена!")
            return cached_result

        # Use microservice if available, otherwise local processing
        if microservice_client.use_microservice:
            logger.info("Используем микросервис транскрибации")
            segments = await microservice_client.process_with_microservice(file_path, user_id, progress_callback)
        else:
            logger.info("Используем локальную обработку транскрибации")
            segments = await process_audio_file_local(file_path, user_id, progress_callback)

        # Cache the result
        await cache_manager.set_transcription_result(file_path, user_id, segments)

        logger.info(f"Транскрибация завершена, найдено {len(segments)} сегментов")
        return segments
    except (TranscriptionError, FileProcessingError) as e:
        logger.error(f"Ошибка в process_audio_file: {str(e)}")
        raise


async def process_audio_file_local(file_path: str, user_id: int, progress_callback: Optional[Callable] = None) -> List[Segment]:
    """Локальная обработка аудиофайла (оригинальная логика)"""
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

    return segments


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
        timecodes = await openrouter_client.make_request([{"role": "user", "content": prompt}], temperature=0.2)
        # Очищаем от возможных специальных символов
        timecodes = timecodes.replace("*", "").strip()
        return timecodes
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


async def generate_transcription_summary(segments: List[Segment]) -> str:
    """Генерирует структурированную выжимку (сводку) из транскрибации"""
    full_text = "\n".join(seg['text'] for seg in segments)

    prompt = f"""
Проанализируй полную расшифровку аудио и создай структурированную выжимку (сводку) в формате, подобном бизнес-встречам.

Полная транскрибация:
{full_text}

Инструкции:
1. Определи ОСНОВНУЮ ТЕМУ встречи/разговора
2. Выдели ключевые разделы и подразделы с описанием содержания
3. Для каждого раздела дай краткое, но информативное описание
4. Используй простой текст без специальных символов форматирования
5. В конце добавь раздел "ИТОГ" с главными выводами
6. Будь максимально точным и не придумывай информацию

Формат ответа:
"Выжимка [тема встречи]"

1. [Название первого раздела]

[Описание содержания первого раздела]

2. [Название второго раздела]

[Описание содержания второго раздела]

...

[Рекомендации/решения если применимо]

ИТОГ

[Главные выводы из разговора]
"""

    try:
        summary = await openrouter_client.make_request([{"role": "user", "content": prompt}], temperature=0.2)
        # Очищаем от возможных специальных символов
        summary = summary.replace("🧩", "").replace("💡", "").replace("✅", "").replace("*", "").strip()
        return summary
    except Exception as e:
        logger.warning(f"Попытка генерации выжимки с OpenRouter не удалась: {e}")
        logger.info("Используем fallback для выжимки")

    # Fallback - простая выжимка
    fallback_result = '"Выжимка встречи"\n\n'
    fallback_result += "1. Основная тема\n\n"
    fallback_result += f"Разговор касался {full_text[:200]}...\n\n"
    fallback_result += "ИТОГ\n\n"
    fallback_result += "Ключевые моменты обсуждены в транскрибации выше."
    return fallback_result
