import logging
import os
import tempfile
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
import re

from .. import database as db
from .. import services
from ..ui import UserSelections, user_selections, user_settings, progress_manager
from ..config import (
    settings,
    YOOMONEY_WALLET, YOOMONEY_REDIRECT_URI, SUBSCRIPTION_AMOUNT,
    SUBSCRIPTION_DURATION_DAYS, PAID_USER_FILE_LIMIT, FREE_USER_FILE_LIMIT,
    SUPPORTED_FORMATS, CUSTOM_THUMBNAIL_PATH, BASE_DIR, SUPPORT_USERNAME,
    SUPPORTED_AUDIO_FORMATS, SUPPORTED_VIDEO_FORMATS
)
from ..localization import get_string
from ..exceptions import PaymentError, TranscriptionError, FileProcessingError, APIError
from ..ui import create_menu_keyboard, create_transcription_selection_keyboard, ensure_user_settings

logger = logging.getLogger(__name__)

# URL validation regex for safety
URL_PATTERN = re.compile(
    r"^https?://"  # http:// or https://
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)*"  # domain...
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"  # domain
    r"(?::[0-9]{1,5})?"  # optional port
    r"(?:/?|[/?]\S+)$", re.IGNORECASE)

def validate_url(url: str) -> bool:
    """Validate URL format and safety"""
    if not URL_PATTERN.match(url):
        return False
    # Additional checks can be added here (e.g., allowed domains)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    # Allow specific domains like youtube, dropbox, drive, onedrive, yandex
    allowed_domains = [
        'youtube.com', 'youtu.be', 'www.youtube.com',
        'dropbox.com', 'dl.dropboxusercontent.com',
        'drive.google.com', 'docs.google.com',
        'onedrive.live.com', '1drv.ms',
        'disk.yandex.ru', 'disk.yandex.com', 'yadi.sk'
    ]
    return parsed.netloc in allowed_domains


async def universal_handler(message: types.Message, bot: Bot) -> None:
    user_id = message.from_user.id
    if message.text and message.text.startswith('/'):
        return

    if not ((message.text and message.text.startswith(('http://', 'https://'))) or message.audio or message.document or message.voice):
        return

    can_use, is_paid = await db.check_user_trials(user_id)
    if not can_use:
        await message.answer(f"❌ {get_string('no_trials', 'ru')}", reply_markup=create_menu_keyboard())
        return

    file_limit = PAID_USER_FILE_LIMIT if is_paid else FREE_USER_FILE_LIMIT
    if message.audio or message.document or message.voice:
        file_size = (message.audio.file_size if message.audio else message.document.file_size if message.document else message.voice.file_size)
        if file_size > file_limit:
            await message.answer(f"❌ {get_string('file_too_large', 'ru', size=file_size, limit=file_limit)}", reply_markup=create_menu_keyboard())
            return

        # Проверка поддерживаемых форматов
        supported_audio_formats = set(f".{fmt}" for fmt in SUPPORTED_AUDIO_FORMATS)
        supported_video_formats = set(f".{fmt}" for fmt in SUPPORTED_VIDEO_FORMATS)

        if message.audio:
            # Для аудио проверяем mime_type или file_name
            file_name = getattr(message.audio, 'file_name', '') or ''
            mime_type = getattr(message.audio, 'mime_type', '') or ''
            file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
            if mime_type and 'audio' not in mime_type.lower():
                await message.answer("❌ Поддерживаются только аудиофайлы. Пожалуйста, отправьте аудиофайл в формате MP3, M4A, FLAC, WAV, OGG или OPUS.", reply_markup=create_menu_keyboard())
                return
        elif message.document:
            file_name = getattr(message.document, 'file_name', '') or ''
            mime_type = getattr(message.document, 'mime_type', '') or ''
            file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''

            # Проверяем расширение
            if file_ext and file_ext not in supported_audio_formats and file_ext not in supported_video_formats:
                audio_list = ", ".join(SUPPORTED_AUDIO_FORMATS)
                video_list = ", ".join(SUPPORTED_VIDEO_FORMATS)
                await message.answer(f"❌ Файл в формате .{file_ext} не поддерживается. Поддерживаемые форматы: {audio_list} (аудио) и {video_list} (видео).", reply_markup=create_menu_keyboard())
                return
        elif message.voice:
            # Для голосовых сообщений проверяем mime_type
            mime_type = getattr(message.voice, 'mime_type', '') or ''
            if mime_type and 'audio' not in mime_type.lower():
                await message.answer("❌ Поддерживаются только голосовые сообщения. Пожалуйста, запишите голосовое сообщение.", reply_markup=create_menu_keyboard())
                return

    audio_path = None
    try:
        ensure_user_settings(user_id)

        if message.text and message.text.startswith(('http://', 'https://')):
            url = message.text.strip()
            if not validate_url(url):
                await message.answer("❌ Указанная ссылка не поддерживается или имеет неправильный формат. Пожалуйста, проверьте ссылку и попробуйте еще раз.", reply_markup=create_menu_keyboard())
                return
            logger.info(f"Скачивание: {url}")

            async def download_progress(percent_value):
                try:
                    progress = percent_value / 100.0
                    await progress_manager.update_progress(progress, temp_message, 'ru')
                except Exception as e:
                    logger.warning(f"Ошибка обработки прогресса загрузки: {e}")

            temp_message = await message.answer(f"📥 Начинаю скачивание...\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%")
            audio_path = await services.download_youtube_audio(url, progress_callback=download_progress)
            await temp_message.delete()
        else:
            file = message.audio or message.document or message.voice
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".temp").name
            try:
                await bot.download(file, destination=temp_path)
                audio_path = await services.convert_to_mp3(temp_path)
                try:
                    os.remove(temp_path)
                except:
                    logger.warning(f"Не удалось удалить временный файл {temp_path}")
            except TelegramBadRequest as e:
                if "file is too big" in str(e):
                    await message.answer(
                        f'❌ Ваш файл превысил допустимый размер ({settings.max_file_size_mb} МБ).\n'
                        'Пожалуйста, загрузите его в одно из облачных сервисов:\n'
                        '• <a href="https://www.dropbox.com">Dropbox</a>\n'
                        '• <a href="https://drive.google.com">Google Drive</a>\n'
                        '• <a href="https://onedrive.live.com">OneDrive</a>\n'
                        '• <a href="https://disk.yandex.ru">Яндекс.Диск</a>\n\n'
                        'После этого пришлите мне ссылку.\n'
                        'Обязательно проверьте, что ссылка имеет <b>общий доступ</b> (доступ по ссылке).\n'
                        'После получения ссылки я сразу приступлю к работе.\n\n'
                        'Спасибо!',
                        parse_mode="HTML",
                        disable_web_page_preview=True  # ✅ Отключает предпросмотр (убирает "рекламу")
                    )
                else:
                    await message.answer(f"❌ {get_string('error', 'ru', error=str(e))}")
                return

        user_selections[user_id] = {
            'speakers': False,
            'plain': False,
            'timecodes': False,
            'file_path': audio_path,
            'message_id': None
        }
        selection_message = await message.answer(
            get_string('select_transcription', 'ru'),
            reply_markup=create_transcription_selection_keyboard(user_id)
        )
        user_selections[user_id]['message_id'] = selection_message.message_id

    except TelegramBadRequest as e:
        if "file is too big" in str(e):
            await message.answer(
                f'❌ Ваш файл превысил допустимый размер ({settings.max_file_size_mb} МБ).\n'
                'Пожалуйста, загрузите его в один из облачных сервисов:\n'
                '• <a href="https://www.dropbox.com">Dropbox</a>\n'
                '• <a href="https://drive.google.com">Google Drive</a>\n'
                '• <a href="https://onedrive.live.com">OneDrive</a>\n'
                '• <a href="https://disk.yandex.ru">Яндекс.Диск</a>\n\n'
                'После этого пришлите мне ссылку.\n'
                'Обязательно проверьте, что ссылка имеет <b>общий доступ</b> (доступ по ссылке).\n'
                'После получения ссылки я сразу приступлю к работе.\n\n'
                'Спасибо!',
                parse_mode="HTML",
                disable_web_page_preview=True  # ✅ Отключает предпросмотр (убирает "рекламу")
            )

        else:
            await message.answer(f"❌ {get_string('error', 'ru', error=str(e))}")
    except (FileProcessingError, APIError) as e:
        logger.error(f"Ошибка предварительной обработки для user_id {user_id}: {str(e)}")
        await message.answer(f"❌ {get_string('error', 'ru', error=str(e))}")
        if audio_path:
            try:
                os.remove(audio_path)
            except:
                pass
        if user_id in user_selections:
            del user_selections[user_id]


async def process_audio_file_for_user(bot: Bot, message: types.Message, user_id: int, selections: UserSelections, audio_path: str) -> None:
    lang = 'ru'
    chat_id = message.chat.id
    EMOJI = {
        'processing': '⚙️',
        'success': '✅',
        'error': '❌',
        'speakers': '👥',
        'text': '📝',
        'timecodes': '⏱️'
    }

    ensure_user_settings(user_id)
    chosen_format = user_settings[user_id]['format']
    chosen_ext = SUPPORTED_FORMATS[chosen_format]['ext']

    logger.info(f"Обработка файла для user_id {user_id} с выбором: {selections}, формат: {chosen_format}")

    progress_message = await message.answer(f"{EMOJI['processing']} Начинаю обработку...\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%")

    out_files = []
    try:
        async def update_audio_progress(progress, status_text=None):
            if isinstance(progress, (int, float)):
                if progress < 0.99:
                    await asyncio.sleep(5)
                await services.progress_manager.update_progress(progress, progress_message, lang)
            elif status_text:
                await progress_message.edit_text(f"{EMOJI['processing']} {status_text}")

        results = await services.process_audio_file(audio_path, user_id, progress_callback=update_audio_progress)

        if not results or not any(seg.get('text') for seg in results):
            await progress_message.edit_text(f"{EMOJI['error']} {get_string('no_speech', lang)}")
            return

        def _save_with_format(text_data: str, base_name: str):
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=chosen_ext).name
            if chosen_ext == ".pdf":
                services.save_text_to_pdf(text_data, temp_out)
            elif chosen_ext == ".docx":
                services.save_text_to_docx(text_data, temp_out)
            elif chosen_ext == ".txt":
                services.save_text_to_txt(text_data, temp_out)
            elif chosen_ext == ".md":
                services.save_text_to_md(text_data, temp_out)
            display_name = f"{base_name}{' (Google Docs)' if chosen_format=='google' else ''}{chosen_ext}"
            return temp_out, display_name

        if selections['speakers']:
            text_with_speakers = services.format_results_with_speakers(results)
            path, name = _save_with_format(text_with_speakers, f"{EMOJI['speakers']} Транскрипция со спикерами")
            out_files.append((path, name))

        if selections['plain']:
            text_plain = services.format_results_plain(results)
            path, name = _save_with_format(text_plain, f"{EMOJI['text']} Транскрипция без спикеров")
            out_files.append((path, name))

        if selections['timecodes']:
            timecodes_text = await services.generate_summary_timecodes(results)
            path, name = _save_with_format(timecodes_text, f"{EMOJI['timecodes']} Транскт с тайм-кодами")
            out_files.append((path, name))

        thumbnail_bytes = services.create_custom_thumbnail(CUSTOM_THUMBNAIL_PATH) if chosen_ext == '.pdf' else None
        thumbnail_file = BufferedInputFile(thumbnail_bytes.read(), filename="thumbnail.jpg") if thumbnail_bytes else None

        for file_path, filename in out_files:
            try:
                await bot.send_document(
                    chat_id,
                    document=FSInputFile(file_path, filename=filename),
                    caption=filename.replace(chosen_ext, ""),
                    thumbnail=thumbnail_file if chosen_ext == '.pdf' else None
                )
            except TelegramBadRequest as e:
                logger.error(f"Ошибка отправки файла {file_path}: {e}")
                await bot.send_document(
                    chat_id,
                    document=FSInputFile(file_path, filename=filename),
                    caption=filename.replace(chosen_ext, "")
                )

        await progress_message.edit_text(
            f"{EMOJI['success']} {get_string('done')}\nВсе файлы успешно сформированы и отправлены",
            reply_markup=create_menu_keyboard()
        )

        if not (await db.check_user_trials(user_id))[1]:
            await db.increment_trials(user_id)

    except (TranscriptionError, FileProcessingError) as e:
        logger.exception(f"Ошибка обработки для user_id {user_id}: {str(e)}")
        await progress_message.edit_text(f"{EMOJI['error']} {get_string('error', lang, error=str(e))}")
    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except:
                pass
        for file_path, _ in out_files:
            try:
                os.remove(file_path)
            except:
                pass
        if user_id in user_selections:
            del user_selections[user_id]
