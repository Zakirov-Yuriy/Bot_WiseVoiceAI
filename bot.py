import asyncio
import logging
import os
import tempfile
import subprocess
import yt_dlp
import httpx
import uuid
import time
import telegram.error
from telegram import Message, Update, InputFile
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from langdetect import detect, LangDetectException
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

# Конфигурация AssemblyAI
ASSEMBLYAI_API_KEY = "74f0dded2b1949a7be47a3adc3473194"
ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
HEADERS = {"authorization": ASSEMBLYAI_API_KEY}

# Конфигурация FFMPEG
FFMPEG_DIR = r"D:\Programming\ffmpeg-7.1.1-essentials_build\bin"
os.environ["PATH"] += os.pathsep + FFMPEG_DIR

# Настройки обработки
SEGMENT_DURATION = 60  # seconds
MESSAGE_CHUNK_SIZE = 4000  # characters
API_TIMEOUT = 300  # seconds

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
        'try_again': "Попробуйте еще раз или обратитесь в поддержку",
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
        'try_again': "Please try again or contact support",
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
    font_path = r"C:\Users\zakco\PycharmProjects\WiseVoiceAI\DejaVuSans.ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", font_path))
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
        "speaker_labels": True,          # включаем спикеров
        "language_detection": True,      # пусть определяет язык
        "punctuate": True,               # расставит точки/запятые
        "format_text": True              # сделает читабельным
    }

    async with httpx.AsyncClient() as client:
        # создаём задачу
        resp = await client.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers, json=payload
        )
        resp.raise_for_status()
        transcript_id = resp.json()["id"]

        # ждём результат
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



async def update_progress(progress, message: Message, lang: str):
    """Обновляет сообщение с прогресс-баром.
       Принимает либо float 0..1, либо строку статуса."""
    try:
        # Если пришла строка — просто показать статусный текст
        if isinstance(progress, str):
            await message.edit_text(progress)
            LAST_UPDATE_TIMES[message.message_id] = time.time()
            return

        # Если пришло что-то не число и не строка — игнорируем
        if not isinstance(progress, (int, float)):
            return

        # Троттлинг для числового прогресса
        current_time = time.time()
        last_update = LAST_UPDATE_TIMES.get(message.message_id, 0)
        if current_time - last_update < 2.0 and progress < 1.0:
            return

        # Нормализация и отрисовка бара
        progress = max(0.0, min(1.0, float(progress)))
        bar_length = 10
        filled = int(progress * bar_length)
        filled_char = '🟪'
        empty_char = '⬜'
        bar = filled_char * filled + empty_char * (bar_length - filled)
        percent = int(progress * 100)

        base_text = get_string('processing_audio', lang)
        text = base_text.format(bar=bar, percent=percent)

        await message.edit_text(text)
        LAST_UPDATE_TIMES[message.message_id] = current_time

    except telegram.error.BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Ошибка обновления прогресса: {str(e)}")
    except Exception as e:
        logger.warning(f"Не удалось обновить прогресс: {str(e)}")



async def download_youtube_audio(url: str, progress_callback: callable = None) -> str:
    """Скачивает аудио с YouTube"""
    loop = asyncio.get_running_loop()
    progress_queue = asyncio.Queue()

    def progress_hook(data):
        """Хук для прогресса"""
        if data['status'] == 'downloading' and progress_callback:
            loop.call_soon_threadsafe(progress_queue.put_nowait, data)

    def sync_download():
        """Синхронное скачивание через yt-dlp"""
        temp_dir = tempfile.gettempdir()
        unique_id = str(uuid.uuid4())
        outtmpl = os.path.join(temp_dir, f"{unique_id}.%(ext)s")

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
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        except Exception as e:
            logger.error(f"Ошибка скачивания YouTube: {str(e)}")
            raise RuntimeError(f"Ошибка скачивания видео: {str(e)}") from e

    async def process_progress():
        """Обрабатывает обновления прогресса"""
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    lang = user.language_code if user and user.language_code in locales else 'ru'
    context.user_data['lang'] = lang
    await update.message.reply_text(get_string('welcome', lang))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (YouTube ссылок)"""
    url = update.message.text.strip()

    # Определяем язык
    try:
        lang = detect(url)
        if lang not in locales:
            lang = context.user_data.get('lang', 'ru')
    except LangDetectException:
        lang = context.user_data.get('lang', 'ru')
    context.user_data['lang'] = lang

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(get_string('invalid_link', lang))
        return

    progress_message = await update.message.reply_text(
        get_string('downloading_video', lang).format(bar='', percent='0%'))

    try:
        # Функция для обновления прогресса скачивания
        async def download_progress(data):
            if data.get('status') == 'downloading':
                percent = data.get('_percent_str', '0%')
                filled_char = '🟪'
                empty_char = '⬜'

                try:
                    percent_value = float(percent.strip().replace('%', ''))
                    filled = int(percent_value / 10)
                    bar = filled_char * filled + empty_char * (10 - filled)
                    text = get_string('downloading_video', lang).format(bar=bar, percent=percent)
                    await progress_message.edit_text(text)
                except:
                    text = get_string('downloading_video', lang).format(bar='', percent=percent)
                    await progress_message.edit_text(text)

        # Скачивание видео
        audio_path = await download_youtube_audio(url, progress_callback=download_progress)

        # Обработка аудио
        await progress_message.edit_text(
            get_string('processing_audio', lang).format(bar='', percent='0'))

        results = await process_audio_file(
            audio_path,
            progress_callback=lambda p: update_progress(p, progress_message, lang))

        if not results:
            await progress_message.edit_text(get_string('no_speech', lang))
            return

        # Формируем тексты
        text_with_speakers = format_results_with_speakers(results)
        text_plain = format_results_plain(results)

        # Создаем временные PDF файлы
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file1, \
                tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file2:

            pdf_path_with_speakers = pdf_file1.name
            pdf_path_plain = pdf_file2.name

            save_text_to_pdf(text_with_speakers, pdf_path_with_speakers)
            save_text_to_pdf(text_plain, pdf_path_plain)

        # Отправляем PDF файлы
        with open(pdf_path_with_speakers, 'rb') as f1, open(pdf_path_plain, 'rb') as f2:
            await update.message.reply_document(
                document=InputFile(f1, filename="transcription_with_speakers.pdf"),
                caption=get_string('caption_with_speakers', lang)
            )
            await update.message.reply_document(
                document=InputFile(f2, filename="transcription_plain.pdf"),
                caption=get_string('caption_plain', lang)
            )

        # Удаляем временные файлы
        os.remove(pdf_path_with_speakers)
        os.remove(pdf_path_plain)

        # Финальное сообщение
        await update.message.reply_text(get_string('done', lang))

    except asyncio.TimeoutError:
        await progress_message.edit_text(get_string('timeout_error', lang))
        logger.error("Таймаут обработки запроса")
    except telegram.error.TimedOut:
        await update.message.reply_text(get_string('telegram_timeout', lang))
        logger.error("Таймаут Telegram API")
    except Exception as e:
        error_text = get_string('error', lang).format(error=str(e))
        try:
            await progress_message.edit_text(error_text)
        except:
            await update.message.reply_text(error_text)
        logger.exception("Ошибка обработки ссылки")
    finally:
        # Предложение попробовать снова
        await update.message.reply_text(get_string('try_again', lang))


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик медиа-файлов"""
    # Определяем язык
    lang = context.user_data.get('lang', 'ru')
    if update.message.caption:
        try:
            caption_lang = detect(update.message.caption)
            if caption_lang in locales:
                lang = caption_lang
        except LangDetectException:
            pass
    context.user_data['lang'] = lang

    # Определяем тип файла
    file_types = {
        update.message.audio: "audio",
        update.message.voice: "voice",
        update.message.video: "video",
        update.message.document: "document"
    }

    for file_source, file_type in file_types.items():
        if file_source:
            file = file_source
            break
    else:
        await update.message.reply_text(get_string('unsupported_format', lang))
        return

    # Создаем временный файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        temp_path = temp_file.name

    progress_message = await update.message.reply_text(
        get_string('processing_audio', lang).format(bar='', percent='0%'))

    try:
        # Скачиваем файл из Telegram
        tg_file = await file.get_file()
        await tg_file.download_to_drive(temp_path)
        await update.message.reply_text(get_string('uploading_file', lang))

        # Обрабатываем аудио
        results = await process_audio_file(
            temp_path,
            progress_callback=lambda p: update_progress(p, progress_message, lang))

        if not results:
            await progress_message.edit_text(get_string('no_speech', lang))
            return

        # Формируем тексты
        text_with_speakers = format_results_with_speakers(results)
        text_plain = format_results_plain(results)

        # Создаем временные PDF файлы
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file1, \
                tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file2:

            pdf_path_with_speakers = pdf_file1.name
            pdf_path_plain = pdf_file2.name

            save_text_to_pdf(text_with_speakers, pdf_path_with_speakers)
            save_text_to_pdf(text_plain, pdf_path_plain)

        # Отправляем PDF файлы
        with open(pdf_path_with_speakers, 'rb') as f1, open(pdf_path_plain, 'rb') as f2:
            await update.message.reply_document(
                document=InputFile(f1, filename="transcription_with_speakers.pdf"),
                caption=get_string('caption_with_speakers', lang)
            )
            await update.message.reply_document(
                document=InputFile(f2, filename="transcription_plain.pdf"),
                caption=get_string('caption_plain', lang)
            )

        # Удаляем временные файлы
        os.remove(pdf_path_with_speakers)
        os.remove(pdf_path_plain)

        # Финальное сообщение
        await update.message.reply_text(get_string('done', lang))

    except Exception as e:
        error_text = get_string('error', lang).format(error=str(e))
        await progress_message.edit_text(error_text)
        logger.exception("Ошибка обработки файла")
    finally:
        # Удаляем временный аудиофайл
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Ошибка удаления временного файла: {e}")


async def process_audio_file(file_path: str, progress_callback=None) -> list[dict]:
    """Загружает файл в AssemblyAI, ждёт транскрипт и возвращает список сегментов"""
    try:
        if progress_callback:
            await progress_callback(0.01)
            await progress_callback("Загружаю файл в AssemblyAI...")

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
            await progress_callback(1.0)  # дорисовать 100%

        return segments
    except Exception as e:
        logger.error(f"Ошибка в process_audio_file: {e}")
        return []





def main():
    """Запуск бота"""
    app = ApplicationBuilder() \
        .token("7295836546:AAGWYalfQ6pkkCRPIK6LcegMDBFFM5SjAN0") \
        .read_timeout(60) \
        .write_timeout(60) \
        .pool_timeout(60) \
        .build()

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.AUDIO | filters.VOICE | filters.VIDEO | filters.Document.AUDIO | filters.Document.VIDEO,
        handle_file
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()