import asyncio
import logging
import os
import tempfile
import subprocess
from getpass import getpass
from PIL import Image, ImageDraw, ImageFont
import io
import yt_dlp
import httpx
import uuid
import time
import json
import requests
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import DocumentAttributeFilename
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Конфигурация из переменных окружения
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_SESSION_NAME = os.getenv('TELEGRAM_SESSION_NAME', 'userbot')
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
FFMPEG_DIR = os.getenv('FFMPEG_PATH', r"D:\Programming\ffmpeg-7.1.1-essentials_build\bin")
FONT_PATH = os.getenv('FONT_PATH', r"C:\Users\zakco\PycharmProjects\WiseVoiceAI\DejaVuSans.ttf")
CUSTOM_THUMBNAIL_PATH = os.getenv('CUSTOM_THUMBNAIL_PATH')

# Проверка обязательных переменных
if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, ASSEMBLYAI_API_KEY, OPENROUTER_API_KEY]):
    raise ValueError("Не все обязательные переменные окружения установлены")

ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
HEADERS = {"authorization": ASSEMBLYAI_API_KEY}

# Настройки обработки
SEGMENT_DURATION = 60  # seconds
MESSAGE_CHUNK_SIZE = 4000  # characters
API_TIMEOUT = 300  # seconds

# Добавление FFMPEG в PATH
os.environ["PATH"] += os.pathsep + FFMPEG_DIR

# Локализация (упрощенная версия)
locales = {
    'ru': {
        'welcome': "Привет! Отправьте мне аудиофайл или ссылку на YouTube видео для транскрибации.",
        'downloading_video': "Скачивание видео... {bar} {percent}",
        'processing_audio': "Обработка аудио... {bar} {percent}%",
        'uploading_file': "Загружаю файл для обработки...",
        'no_speech': "Не удалось распознать речь в аудио",
        'error': "Произошла ошибка: {error}",
        'done': "Обработка завершена!",
        'caption_with_speakers': "Транскрипция с распознаванием спикеров",
        'caption_plain': "Транскрипция (текст без спикеров)",
        'invalid_link': "Пожалуйста, отправьте действительную ссылку на YouTube",
        'unsupported_format': "Неподдерживаемый формат файла",
        'try_again': "Отправляйте ссылки или файлы прямо сюда ⬇️ — и бот сделает транскрибацию за вас",
        'timeout_error': "Превышено время ожидания обработки",
        'telegram_timeout': "Таймаут соединения с Telegram",
    },
    'en': {
        'welcome': "Hi! Send me an audio file or YouTube link for transcription.",
        'downloading_video': "Downloading video... {bar} {percent}",
        'processing_audio': "Processing audio... {bar} {percent}%",
        'uploading_file': "Uploading file for processing...",
        'no_speech': "No speech detected in the audio",
        'error': "An error occurred: {error}",
        'done': "Processing complete!",
        'caption_with_speakers': "Transcript with speaker identification",
        'caption_plain': "Transcript (plain text)",
        'invalid_link': "Please provide a valid YouTube link",
        'unsupported_format': "Unsupported file format",
        'try_again': "Send links or files here ⬇️ and the bot will transcribe them for you",
        'timeout_error': "Processing timeout exceeded",
        'telegram_timeout': "Telegram connection timeout",
    }
}

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Регистрация шрифта для PDF
try:
    pdfmetrics.registerFont(TTFont("DejaVu", FONT_PATH))
except Exception as e:
    logger.error(f"Failed to register font: {e}")
    pdfmetrics.registerFont(TTFont("Helvetica", "Helvetica"))


class ProgressManager:
    """Менеджер для управления прогрессом"""

    def __init__(self):
        self.last_update_times = {}
        self.last_progress_values = {}  # Храним последние значения прогресса
        self.min_update_interval = 3.0  # Уменьшил интервал до 3 секунд
        self.min_progress_change = 0.05  # Минимальное изменение прогресса для обновления

    async def update_progress(self, progress, message, lang: str = 'ru'):
        """Обновляет сообщение с прогресс-баром"""
        try:
            message_id = message.id

            # Если progress - строка, обновляем сразу (для текстовых статусов)
            if isinstance(progress, str):
                await message.edit(progress)
                self.last_update_times[message_id] = time.time()
                return

            # Проверяем интервал между обновлениями и изменение прогресса
            current_time = time.time()
            last_update = self.last_update_times.get(message_id, 0)
            last_progress = self.last_progress_values.get(message_id, -1)

            # Не обновляем слишком часто или если изменение слишком маленькое
            if (current_time - last_update < self.min_update_interval and
                progress < 0.99 and
                abs(progress - last_progress) < self.min_progress_change):
                return

            # Создаем прогресс-бар
            progress = max(0.0, min(1.0, float(progress)))
            bar_length = 10
            filled = int(progress * bar_length)
            bar = '🟪' * filled + '⬜' * (bar_length - filled)
            percent = int(progress * 100)

            # Разные стили для разных этапов
            if progress < 0.3:
                emoji = "📥"
                text = f"{emoji} Скачивание...\n{bar} {percent}%"
            elif progress < 0.7:
                emoji = "⚙️"
                text = f"{emoji} Обработка...\n{bar} {percent}%"
            else:
                emoji = "📊"
                text = f"{emoji} Форматирование...\n{bar} {percent}%"

            try:
                await message.edit(text)
                self.last_update_times[message_id] = current_time
                self.last_progress_values[message_id] = progress
            except FloodWaitError as e:
                logger.warning(f"FloodWait: ждем {e.seconds} секунд")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                if "not modified" not in str(e):
                    logger.warning(f"Не удалось обновить прогресс: {str(e)}")
        except Exception as e:
            if "not modified" not in str(e):
                logger.warning(f"Не удалось обновить прогресс: {str(e)}")


# Создаем глобальный экземпляр менеджера
progress_manager = ProgressManager()


def get_string(key: str, lang: str = 'ru', **kwargs) -> str:
    """Возвращает локализованную строку по ключу"""
    lang_dict = locales.get(lang, locales['ru'])
    text = lang_dict.get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def save_text_to_pdf(text: str, output_path: str):
    """Сохраняет текст в PDF файл"""
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)

    styles = getSampleStyleSheet()
    style = styles['Normal']
    style.fontName = 'DejaVu' if 'DejaVu' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
    style.fontSize = 12
    style.leading = 15

    paragraphs = [Paragraph(p.replace('\n', '<br />'), style) for p in text.split('\n\n')]
    elems = []
    for p in paragraphs:
        elems.append(p)
        elems.append(Spacer(1, 12))

    doc.build(elems)


class AudioProcessor:
    """Класс для обработки аудиофайлов"""

    @staticmethod
    def split_audio(input_path: str, segment_time: int = SEGMENT_DURATION) -> list[str]:
        """Разбивает аудио на фрагменты"""
        output_dir = tempfile.mkdtemp(prefix="fragments_")
        output_pattern = os.path.join(output_dir, "fragment_%03d.mp3")

        ffmpeg_path = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
        command = [
            ffmpeg_path,
            "-i", input_path,
            "-f", "segment",
            "-segment_time", str(segment_time),
            "-c", "copy",
            output_pattern
        ]

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
    def cleanup(files: list[str]):
        """Удаляет временные файлы"""
        for path in files:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    for f in os.listdir(path):
                        os.remove(os.path.join(path, f))
                    os.rmdir(path)
            except Exception as e:
                logger.warning(f"Ошибка удаления {path}: {e}")


async def upload_to_assemblyai(file_path: str) -> str:
    """Загружает файл в AssemblyAI и возвращает URL"""
    try:
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
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {str(e)}")
        raise RuntimeError("Не удалось загрузить файл на сервер AssemblyAI") from e


async def transcribe_with_assemblyai(audio_url: str) -> dict:
    """Запускает транскрипцию в AssemblyAI и ждёт результата"""
    headers = {
        "authorization": ASSEMBLYAI_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "audio_url": audio_url,
        "speaker_labels": True,
        "language_detection": True,
        "punctuate": True,
        "format_text": True
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers, json=payload
        )
        resp.raise_for_status()
        transcript_id = resp.json()["id"]

        while True:
            status = await client.get(
                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                headers=headers
            )
            result = status.json()
            if result["status"] == "completed":
                return result
            elif result["status"] == "error":
                raise Exception(result["error"])
            await asyncio.sleep(3)


async def download_youtube_audio(url: str, progress_callback: callable = None) -> str:
    """Скачивает аудио с YouTube"""
    loop = asyncio.get_running_loop()
    progress_queue = asyncio.Queue()
    last_percent = -1  # Для отслеживания последнего процента

    def progress_hook(data):
        if data['status'] == 'downloading' and progress_callback:
            try:
                percent_str = data.get('_percent_str', '0%')
                percent_value = float(percent_str.strip().replace('%', ''))
                # Отправляем только если процент изменился значительно
                if abs(percent_value - last_percent) >= 5:  # Обновляем каждые 5%
                    loop.call_soon_threadsafe(progress_queue.put_nowait, percent_value)
            except:
                pass

    def sync_download():
        temp_dir = tempfile.gettempdir()
        unique_id = str(uuid.uuid4())
        outtmpl = os.path.join(temp_dir, f"{unique_id}")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "ffmpeg_location": FFMPEG_DIR,
            "progress_hooks": [progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
            "quiet": True,
            "no_warnings": False,
            "extract_flat": False,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                expected_filename = f"{outtmpl}.mp3"
                if os.path.exists(expected_filename):
                    return expected_filename
                else:
                    for file in os.listdir(temp_dir):
                        if file.startswith(os.path.basename(unique_id)):
                            return os.path.join(temp_dir, file)
                    raise FileNotFoundError(f"Скачанный аудиофайл не найден: {expected_filename}")
        except Exception as e:
            logger.error(f"Ошибка скачивания YouTube: {str(e)}")
            raise RuntimeError(f"Ошибка скачивания видео: {str(e)}") from e

    async def process_progress():
        while True:
            try:
                data = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                if progress_callback:
                    await progress_callback(data)
            except asyncio.TimeoutError:
                if download_task.done():
                    break
            except Exception as e:
                logger.warning(f"Ошибка обработки прогресса: {str(e)}")
                break

    download_task = loop.run_in_executor(None, sync_download)
    progress_task = asyncio.create_task(process_progress())

    try:
        result = await download_task
        return result
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass


def format_results_with_speakers(segments: list[dict]) -> str:
    """Форматирует результаты с указанием спикеров"""
    return "\n\n".join(
        f"Спикер {seg['speaker']}:\n{seg['text']}"
        for seg in segments
    )


def format_results_plain(segments: list[dict]) -> str:
    """Форматирует результаты без спикеров"""
    return "\n\n".join(seg["text"] for seg in segments)


def generate_summary_timecodes(segments: list[dict]) -> str:
    """Генерирует тайм-коды с помощью AI"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

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

    data = {
        "model": "z-ai/glm-4.5-air:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=60)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception:
        fallback_result = "Тайм-коды\n\n"
        for i, seg in enumerate(segments):
            start_minute = i * SEGMENT_DURATION // 60
            start_second = i * SEGMENT_DURATION % 60
            start_code = f"{start_minute:02}:{start_second:02}"
            fallback_result += f"{start_code} - {seg['text'][:50]}...\n"
        return fallback_result


async def convert_to_mp3(input_path: str) -> str:
    """Конвертирует аудиофайл в MP3 формат"""
    output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name

    ffmpeg_path = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    command = [
        ffmpeg_path,
        "-i", input_path,
        "-acodec", "libmp3lame",
        "-q:a", "2",
        "-y",
        output_path
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Ошибка конвертации файла: {input_path}")

        return output_path
    except Exception as e:
        logger.error(f"Ошибка конвертации: {str(e)}")
        return input_path


async def process_audio_file(file_path: str, progress_callback=None) -> list[dict]:
    """Обрабатывает аудиофайл"""
    try:
        if progress_callback:
            await progress_callback(0.01, "Загружаю файл в AssemblyAI...")

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
    except Exception as e:
        logger.error(f"Ошибка в process_audio_file: {e}")
        return []


THUMBNAIL_CACHE = {}


def create_custom_thumbnail(thumbnail_path: str = None):
    """Создает кастомную иконку для PDF файла с высоким качеством"""
    cache_key = thumbnail_path or "default"

    if cache_key in THUMBNAIL_CACHE:
        thumbnail_bytes = io.BytesIO(THUMBNAIL_CACHE[cache_key])
        thumbnail_bytes.seek(0)
        return thumbnail_bytes

    try:
        if thumbnail_path and os.path.exists(thumbnail_path):
            with Image.open(thumbnail_path) as img:
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background

                target_size = (320, 320)
                img.thumbnail(target_size, Image.LANCZOS)

                square_img = Image.new('RGB', target_size, (255, 255, 255))
                x_offset = (target_size[0] - img.width) // 2
                y_offset = (target_size[1] - img.height) // 2
                square_img.paste(img, (x_offset, y_offset))

                thumbnail_bytes = io.BytesIO()
                square_img.save(thumbnail_bytes, format='JPEG', quality=95, optimize=True)
                thumbnail_bytes.seek(0)

                THUMBNAIL_CACHE[cache_key] = thumbnail_bytes.getvalue()
                thumbnail_bytes.seek(0)
                return thumbnail_bytes
        else:
            target_size = (320, 320)
            img = Image.new('RGB', target_size, color=(230, 50, 50))
            draw = ImageDraw.Draw(img)

            margin = 10
            draw.rectangle([margin, margin, target_size[0] - margin, target_size[1] - margin],
                           outline=(255, 255, 255), width=4)

            try:
                font = ImageFont.truetype("arial.ttf", 80)
            except:
                font = ImageFont.load_default()

            text = "PDF"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (target_size[0] - text_width) // 2
            y = (target_size[1] - text_height) // 2

            draw.text((x, y), text, fill=(255, 255, 255), font=font)

            thumbnail_bytes = io.BytesIO()
            img.save(thumbnail_bytes, format='JPEG', quality=95, optimize=True)
            thumbnail_bytes.seek(0)

            THUMBNAIL_CACHE[cache_key] = thumbnail_bytes.getvalue()
            thumbnail_bytes.seek(0)
            return thumbnail_bytes

    except Exception as e:
        logger.error(f"Ошибка создания thumbnail: {e}")
        return None


async def handle_message(event, client):
    """Обработчик входящих сообщений"""
    try:
        lang = 'ru'
        message = event.message
        chat_id = message.chat_id

        EMOJI = {
            'downloading': '📥',
            'processing': '⚙️',
            'success': '✅',
            'error': '❌',
            'file': '📄',
            'speakers': '👥',
            'text': '📝',
            'timecodes': '⏱️'
        }

        # Отправляем начальное сообщение о прогрессе
        progress_message = await client.send_message(
            chat_id,
            f"{EMOJI['processing']} Начинаю обработку...\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%"
        )

        if message.text and message.text.startswith(('http://', 'https://')):
            # Обработка YouTube ссылки
            url = message.text.strip()

            async def download_progress(percent_value):
                try:
                    progress = percent_value / 100.0
                    await progress_manager.update_progress(progress, progress_message, lang)
                except Exception as e:
                    logger.warning(f"Ошибка обработки прогресса загрузки: {e}")

            audio_path = await download_youtube_audio(url, progress_callback=download_progress)

        elif message.media:
            # Скачиваем файл
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".temp").name
            await message.download_media(file=temp_path)

            # Конвертируем если нужно
            if hasattr(message.media, 'document') or hasattr(message.media, 'audio'):
                audio_path = await convert_to_mp3(temp_path)
                os.remove(temp_path)
            else:
                audio_path = temp_path

        else:
            await progress_message.edit(f"{EMOJI['error']} {get_string('invalid_link', lang)}")
            return

        # Обработка аудио с обновлением прогресса
        async def update_audio_progress(progress, status_text=None):
            if isinstance(progress, (int, float)):
                await progress_manager.update_progress(progress, progress_message, lang)
            elif status_text:
                await progress_message.edit(f"{EMOJI['processing']} {status_text}")

        results = await process_audio_file(audio_path, progress_callback=update_audio_progress)

        if not results or not any(seg.get('text') for seg in results):
            await progress_message.edit(f"{EMOJI['error']} {get_string('no_speech', lang)}")
            # Удаляем временный файл
            try:
                os.remove(audio_path)
            except:
                pass
            return

        # Создаем PDF файлы
        text_with_speakers = format_results_with_speakers(results)
        text_plain = format_results_plain(results)
        timecodes_text = generate_summary_timecodes(results)

        # Создаем временные файлы для PDF
        pdf_files = []
        try:
            for i, (content, filename) in enumerate([
                (text_with_speakers, "👥 Транскрипция со спикерами.pdf"),
                (text_plain, "📝 Транскрипция без спикеров.pdf"),
                (timecodes_text, "⏱️ Транскрипт с тайм-кодами.pdf")
            ]):
                if content.strip():
                    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    temp_pdf.close()
                    save_text_to_pdf(content, temp_pdf.name)
                    pdf_files.append((temp_pdf.name, filename))

            # Создаем thumbnail
            thumbnail_bytes = create_custom_thumbnail(CUSTOM_THUMBNAIL_PATH)

            # Отправляем PDF файлы
            for pdf_path, filename in pdf_files:
                try:
                    await client.send_file(
                        chat_id,
                        pdf_path,
                        caption=filename.replace(".pdf", ""),
                        attributes=[DocumentAttributeFilename(filename)],
                        thumb=thumbnail_bytes if thumbnail_bytes else None,
                        force_document=True
                    )
                    if thumbnail_bytes:
                        thumbnail_bytes.seek(0)
                except Exception as e:
                    logger.error(f"Ошибка отправки файла {pdf_path}: {e}")
                    # Пробуем отправить без thumbnail
                    await client.send_file(
                        chat_id,
                        pdf_path,
                        caption=filename.replace(".pdf", ""),
                        attributes=[DocumentAttributeFilename(filename)],
                        force_document=True
                    )

        finally:
            # Удаляем временные файлы
            try:
                os.remove(audio_path)
            except:
                pass

            for pdf_path, _ in pdf_files:
                try:
                    os.remove(pdf_path)
                except:
                    pass

        await progress_message.edit(
            f"{EMOJI['success']} Обработка завершена!\n"
            f"Все файлы успешно сгенерированы и отправлены"
        )

    except Exception as e:
        logger.exception("Ошибка обработки сообщения")
        error_text = f"{EMOJI['error']} Произошла ошибка:\n{str(e)}"
        try:
            await progress_message.edit(error_text)
        except:
            await client.send_message(chat_id, error_text)


async def main():
    """Основная функция"""
    client = TelegramClient(
        TELEGRAM_SESSION_NAME,
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH
    )

    await client.start(
        phone=lambda: "+79254499550",
        code_callback=lambda: input("Please enter the code you received: "),
        password=lambda: getpass("Two-factor password: ") if input("Is 2FA enabled? (y/n): ").lower() == 'y' else None
    )

    print("Запуск клиента...")
    print("Userbot успешно запущен!")

    @client.on(events.NewMessage())
    async def universal_handler(event):
        message = event.message

        # Игнорируем служебные сообщения и команды
        if message.text and message.text.startswith('/'):
            return

        # Обрабатываем только подходящие сообщения
        if (message.text and message.text.startswith(('http://', 'https://'))) or message.media:
            await handle_message(event, client)

    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        welcome_text = (
            "🎙️ *Добро пожаловать в Transcribe To!*\n\n"
            "Я помогу вам преобразовать аудио и видео в текст:\n\n"
            "• 🎵 Аудиофайлы любого формата\n"
            "• 📺 YouTube видео по ссылке\n"
            "• 👥 Распознавание разных спикеров\n"
            "• ⏱️ Тайм-коды и структурирование\n\n"
            "Просто отправьте мне аудиофайл или ссылку на YouTube!"
        )
        await event.reply(welcome_text, parse_mode='markdown')

    logger.info("Userbot запущен")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())