import asyncio
import logging
import os
import tempfile
import subprocess
from getpass import getpass

import yt_dlp
import httpx
import uuid
import time
import json
import requests
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from langdetect import detect, LangDetectException
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

# Глобальный словарь для хранения времени последнего обновления прогресса
LAST_UPDATE_TIMES = {}


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


async def update_progress(progress, message, lang: str):
    """Обновляет сообщение с прогресс-баром"""
    try:
        if isinstance(progress, str):
            await message.edit(progress)
            LAST_UPDATE_TIMES[message.id] = time.time()
            return

        if not isinstance(progress, (int, float)):
            return

        current_time = time.time()
        last_update = LAST_UPDATE_TIMES.get(message.id, 0)
        if current_time - last_update < 3.5 and progress < 1.0:
            return

        progress = max(0.0, min(1.0, float(progress)))
        bar_length = 10
        filled = int(progress * bar_length)
        bar = '🟪' * filled + '⬜' * (bar_length - filled)
        percent = int(progress * 100)

        text = f"⚙️ *Обработка аудио...*\n{bar} {percent}%"
        await message.edit(text)
        LAST_UPDATE_TIMES[message.id] = current_time

    except Exception as e:
        logger.warning(f"Не удалось обновить прогресс: {str(e)}")


async def download_youtube_audio(url: str, progress_callback: callable = None) -> str:
    """Скачивает аудио с YouTube"""
    loop = asyncio.get_running_loop()
    progress_queue = asyncio.Queue()

    def progress_hook(data):
        if data['status'] == 'downloading' and progress_callback:
            loop.call_soon_threadsafe(progress_queue.put_nowait, data)

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
    await process_progress()
    return await download_task


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
        "model": "openai/gpt-oss-20b:free",
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
            await progress_callback(0.01)
            await progress_callback("Загружаю файл в Bot AI...")

        audio_url = await upload_to_assemblyai(file_path)

        if progress_callback:
            await progress_callback(0.30)
            await progress_callback("Запускаю транскрибацию...")

        result = await transcribe_with_assemblyai(audio_url)

        if progress_callback:
            await progress_callback(0.90)

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
            await progress_callback(1.0)

        return segments
    except Exception as e:
        logger.error(f"Ошибка в process_audio_file: {e}")
        return []


async def handle_message(event, client):
    """Обработчик входящих сообщений"""
    try:
        lang = 'ru'
        message = event.message
        chat_id = message.chat_id

        # Красивые эмодзи для статусов
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

        if message.text and message.text.startswith(('http://', 'https://')):
            # Обработка YouTube ссылки
            url = message.text.strip()
            progress_message = await client.send_message(chat_id,
                                                         f"{EMOJI['downloading']} Скачивание видео...\n"
                                                         f"⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%"
                                                         )

            async def download_progress(data):
                if data.get('status') == 'downloading':
                    percent = data.get('_percent_str', '0%')
                    try:
                        percent_value = float(percent.strip().replace('%', ''))
                        filled = min(10, int(percent_value / 10))
                        bar = '🟪' * filled + '⬜' * (10 - filled)
                        text = f"{EMOJI['downloading']} Скачивание видео...\n{bar} {percent}"
                        await progress_message.edit(text)
                    except:
                        text = f"{EMOJI['downloading']} Скачивание видео...\n{percent}"
                        await progress_message.edit(text)

            audio_path = await download_youtube_audio(url, progress_callback=download_progress)
            await progress_message.edit(f"{EMOJI['processing']} Обработка аудио...\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%")

        elif message.media:
            # Обработка медиафайла
            progress_message = await client.send_message(chat_id,
                                                         f"{EMOJI['processing']} Обработка аудио...\n"
                                                         f"⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%"
                                                         )

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
            await client.send_message(chat_id, f"{EMOJI['error']} {get_string('invalid_link', lang)}")
            return

        # Обработка аудио
        results = await process_audio_file(
            audio_path,
            progress_callback=lambda p: update_progress(p, progress_message, lang))

        if not results:
            await progress_message.edit(f"{EMOJI['error']} {get_string('no_speech', lang)}")
            return

        # Создаем PDF файлы
        text_with_speakers = format_results_with_speakers(results)
        text_plain = format_results_plain(results)
        timecodes_text = generate_summary_timecodes(results)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf1, \
                tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf2, \
                tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf3:

            save_text_to_pdf(text_with_speakers, pdf1.name)
            save_text_to_pdf(text_plain, pdf2.name)
            save_text_to_pdf(timecodes_text, pdf3.name)

            # Отправляем файлы с красивыми подписями
            await client.send_file(chat_id, pdf1.name,
                                   caption=f"{EMOJI['speakers']} Транскрипция с распознаванием спикеров\n"
                                           f"Разделение по говорящим с указанием спикеров")

            await client.send_file(chat_id, pdf2.name,
                                   caption=f"{EMOJI['text']} Транскрипция (текст без спикеров)\n"
                                           f"Полный текст без разделения по спикерам")

            await client.send_file(chat_id, pdf3.name,
                                   caption=f"{EMOJI['timecodes']} Транскрипт с тайм-кодами\n"
                                           f"Структурированное оглавление с временными метками")

        # Удаляем временные файлы
        for path in [audio_path, pdf1.name, pdf2.name, pdf3.name]:
            try:
                os.remove(path)
            except:
                pass

        await client.send_message(chat_id,
                                  f"{EMOJI['success']} Обработка завершена!\n"
                                  f"Все файлы успешно сгенерированы и отправлены"
                                  )

    except Exception as e:
        error_text = f"{EMOJI['error']} Произошла ошибка:\n{str(e)}"
        await client.send_message(chat_id, error_text)
        logger.exception("Ошибка обработки сообщения")


async def main():
    """Основная функция"""
    client = TelegramClient(
        TELEGRAM_SESSION_NAME,
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH
    )

    # Правильная обработка аутентификации
    await client.start(
        phone=lambda: "+79254499550",  # Ваш номер телефона
        code_callback=lambda: input("Please enter the code you received: "),
        password=lambda: getpass("Two-factor password: ") if input("Is 2FA enabled? (y/n): ").lower() == 'y' else None
    )

    print("Запуск клиента...")
    print("Userbot успешно запущен!")

    # Единый обработчик для всех типов сообщений
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
        lang = 'ru'
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