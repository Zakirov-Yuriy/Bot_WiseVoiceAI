import logging
import os
import tempfile
import time
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest

from . import database as db
from . import services
from . import ui
from .config import (
    YOOMONEY_WALLET, YOOMONEY_REDIRECT_URI, SUBSCRIPTION_AMOUNT,
    SUBSCRIPTION_DURATION_DAYS, PAID_USER_FILE_LIMIT, FREE_USER_FILE_LIMIT,
    SUPPORTED_FORMATS, CUSTOM_THUMBNAIL_PATH, BASE_DIR
)
from .localization import get_string

logger = logging.getLogger(__name__)

# --- Handler Functions ---

async def start_handler(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    text = message.text
    referrer_id = None

    # Обработка реферальной ссылки
    if text and '?' in text:
        parts = text.split('?')
        if len(parts) > 1:
            query_params = parts[1].split('&')
            for param in query_params:
                if param.startswith('start=ref_'):
                    try:
                        referrer_id = int(param.split('_')[1])
                        await db.update_user_referrer(user_id, referrer_id)
                        logger.info(f"Пользователь {user_id} пришел по реферальной ссылке от {referrer_id}")
                        # Генерируем реферальный код для нового пользователя, если он еще не создан
                        user_data = await db.get_user_data(user_id)
                        if not user_data or not user_data.get("referral_code"):
                            await db.generate_and_set_referral_code(user_id)
                        break
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Не удалось обработать реферальную ссылку: {param}. Ошибка: {e}")

    welcome_text = (
        "🎉 *Привет!*\n\n"
        "У вас есть *2 бесплатные попытки* попробовать сервис.\n\n"
        "⚡️ Если ваш файл весит больше *20 МБ* — загрузите его в одно из популярных облачных хранилищ и отправьте мне ссылку:\n\n"
        "• [Dropbox](https://www.dropbox.com/)\n"
        "• [Google Drive](https://drive.google.com/)\n"
        "• [OneDrive](https://onedrive.live.com/)\n\n"
        "👉 Важно:\n"
        "• Файл должен быть *доступен по ссылке для всех*.\n"
        "• Размер не больше *5 ГБ*.\n\n"
        "После этого просто пришлите мне ссылку, и я все сделаю за вас 🙌"
    )
    await message.answer(welcome_text, reply_markup=ui.create_menu_keyboard(), parse_mode='Markdown')
    logger.info(f"Команда /start выполнена для user_id {user_id}")

async def subscription_handler(message: types.Message):
    user_id = message.from_user.id
    description = f"Подписка на Transcribe To на {SUBSCRIPTION_DURATION_DAYS} дней"
    
    payment_url, payment_label = await services.create_yoomoney_payment(
        user_id=user_id,
        amount=SUBSCRIPTION_AMOUNT,
        description=description
    )

    if payment_url:
        await message.answer(
            f"💳 Для оформления подписки перейдите по ссылке:\n[Оплатить подписку]({payment_url})\n"
            f"Стоимость: {SUBSCRIPTION_AMOUNT} руб. на {SUBSCRIPTION_DURATION_DAYS} дней.\n"
            "После оплаты подписка активируется автоматически.",
            reply_markup=ui.create_menu_keyboard(),
            parse_mode='Markdown'
        )
        logger.info(f"Ссылка на оплату отправлена для user_id {user_id}: {payment_label}")
        
        # --- Логика реферальной программы при покупке подписки ---
        user_data = await db.get_user_data(user_id)
        if user_data and user_data.get("referrer_id"):
            referrer_id = user_data["referrer_id"]
            # Начисляем рефереру неделю бесплатного пользования
            await db.add_free_weeks_to_referrer(referrer_id, weeks_to_add=1)
            logger.info(f"Рефереру {referrer_id} добавлена 1 неделя подписки за приглашение пользователя {user_id}")
            # Опционально: уведомить реферера о начислении бонуса
            # try:
            #     await bot.send_message(referrer_id, f"Пользователь {user_id} оформил подписку! Вам начислена 1 неделя бесплатного пользования.")
            # except Exception as e:
            #     logger.warning(f"Не удалось уведомить реферера {referrer_id}: {e}")

    else:
        await message.answer(
            "❌ Не удалось создать ссылку на оплату. Пожалуйста, попробуйте позже.",
            reply_markup=ui.create_menu_keyboard()
        )

async def menu_handler(message: types.Message):
    await message.answer(get_string('menu', 'ru'), reply_markup=ui.create_menu_keyboard(), parse_mode='Markdown')
    logger.info(f"Меню отправлено для user_id {message.from_user.id}")

async def settings_cmd(message: types.Message):
    await message.answer(
        get_string('settings_choose', 'ru'),
        reply_markup=ui.create_settings_keyboard(message.from_user.id)
    )

async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    user_data = await db.get_user_data(user_id)

    if not user_data:
        await message.answer("❌ Произошла ошибка при получении данных пользователя.")
        return

    referral_code = user_data.get("referral_code")
    if not referral_code:
        referral_code = await db.generate_and_set_referral_code(user_id)
        if not referral_code:
            await message.answer("❌ Не удалось сгенерировать реферальный код.")
            return

    # Формируем реферальную ссылку
    bot_username = "@Transcribe_to_bot" # Замените на реальное имя вашего бота
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    # Пример текста для реферального сообщения
    referral_message_template = (
        "✨ Вы приглашены в Transcribe To — бота для удобного и точного преобразования аудио и видео в текст!\n\n"
        "🎁 Забирайте 2 бесплатные попытки прямо сейчас 👇\n\n"
        f"Telegram: {bot_username}\n\n"
        "Просто отправьте аудио или видео — и получите готовый текст с тайм-кодами и поддержкой разных спикеров 🙌\n\n"
        "--- Ваш реферальный код: {referral_code} ---\n"
        "--- Ваша реферальная ссылка: {referral_link} ---"
    )
    
    await message.answer(
        referral_message_template.format(referral_code=referral_code, referral_link=referral_link),
        reply_markup=ui.create_referral_keyboard(referral_link), # Предполагаем, что такая кнопка есть в ui.py
        parse_mode='Markdown'
    )
    logger.info(f"Реферальная информация отправлена для user_id {user_id}")


async def support_cmd(message: types.Message):
    await message.answer("Напишите нам: @Zak_Yuri")

async def callback_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    data = callback.data
    logger.info(f"Callback от user_id {user_id}: {data}")

    if data == 'subscribe':
        await subscription_handler(callback.message)
        await callback.answer()

    elif data == 'settings':
        ui.ensure_user_settings(user_id)
        await callback.message.answer(get_string('settings_choose', 'ru'), reply_markup=ui.create_settings_keyboard(user_id))

    elif data in ['set_format_google', 'set_format_word', 'set_format_pdf', 'set_format_txt', 'set_format_md']:
        ui.ensure_user_settings(user_id)
        new_fmt = {
            'set_format_google': 'google',
            'set_format_word': 'word',
            'set_format_pdf': 'pdf',
            'set_format_txt': 'txt',
            'set_format_md': 'md'
        }[data]
        ui.user_settings[user_id]['format'] = new_fmt
        try:
            await callback.message.edit_text(get_string('settings_choose', 'ru'), reply_markup=ui.create_settings_keyboard(user_id))
        except Exception:
            await callback.message.answer(get_string('settings_choose', 'ru'), reply_markup=ui.create_settings_keyboard(user_id))

    elif data == 'settings_back':
        try:
            await callback.message.edit_text(get_string('menu', 'ru'), reply_markup=ui.create_menu_keyboard())
        except Exception:
            await callback.message.answer(get_string('menu', 'ru'), reply_markup=ui.create_menu_keyboard())

    elif data in ['select_speakers', 'select_plain', 'select_timecodes']:
        if user_id not in ui.user_selections:
            await callback.answer("Сначала отправьте аудиофайл или ссылку на YouTube.")
            return
        selections = ui.user_selections[user_id]
        if data == 'select_speakers':
            selections['speakers'] = not selections['speakers']
        elif data == 'select_plain':
            selections['plain'] = not selections['plain']
        elif data == 'select_timecodes':
            selections['timecodes'] = not selections['timecodes']
        try:
            await callback.message.edit_text(
                get_string('select_transcription', 'ru'),
                reply_markup=ui.create_transcription_selection_keyboard(user_id)
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Не удалось обновить сообщение: {str(e)}")

    elif data == 'confirm_selection':
        if user_id not in ui.user_selections:
            await callback.answer("Сначала отправьте аудиофайл или ссылку на YouTube.")
            return
        selections = ui.user_selections[user_id]
        if not any([selections['speakers'], selections['plain'], selections['timecodes']]):
            await callback.message.edit_text(
                f"❌ {get_string('no_selection', 'ru')}",
                reply_markup=ui.create_transcription_selection_keyboard(user_id)
            )
            return
        audio_path = selections.get('file_path')
        if not audio_path:
            await callback.message.edit_text(
                f"❌ Ошибка: файл не найден. Попробуйте отправить файл или ссылку снова.",
                reply_markup=ui.create_menu_keyboard()
            )
            if user_id in ui.user_selections:
                del ui.user_selections[user_id]
            return
        try:
            await callback.message.delete()
            await process_audio_file_for_user(bot, callback.message, user_id, selections, audio_path)
        except Exception as e:
            logger.error(f"Ошибка обработки после подтверждения для user_id {user_id}: {str(e)}")
            await callback.message.edit_text(f"❌ {get_string('error', 'ru', error=str(e))}")

    # Обработка callback для реферальной программы (например, кнопка "Отправить приглашение")
    elif data == 'send_referral_invitation':
        user_data = await db.get_user_data(user_id)
        if not user_data:
            await callback.message.answer("❌ Произошла ошибка при получении данных пользователя.")
            await callback.answer()
            return

        referral_code = user_data.get("referral_code")
        if not referral_code:
            referral_code = await db.generate_and_set_referral_code(user_id)
            if not referral_code:
                await callback.message.answer("❌ Не удалось сгенерировать реферальный код.")
                await callback.answer()
                return
        
        bot_username = "@Transcribe_to_bot" # Замените на реальное имя вашего бота
        referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        # Сохраняем ссылку, если она была сгенерирована только что
        # Предполагаем, что в db.py есть функция update_user_referral_link(user_id, referral_link)
        # Если нет, то нужно ее добавить. Пока просто используем сгенерированную ссылку.
        # await db.update_user_referral_link(user_id, referral_link) 

        if referral_link:
            await callback.message.answer(
                f"✨ Вот ваше реферальное приглашение:\n\n"
                f"🎁 Забирайте 2 бесплатные попытки прямо сейчас 👇\n\n"
                f"Telegram: @Transcribe_to_bot\n\n"
                f"Просто отправьте аудио или видео — и получите готовый текст с тайм-кодами и поддержкой разных спикеров 🙌\n\n"
                f"Ваша реферальная ссылка: {referral_link}",
                reply_markup=ui.create_menu_keyboard(), # Или другая клавиатура, если нужно
                parse_mode='Markdown'
            )
        else:
            await callback.message.answer("❌ Не удалось сгенерировать реферальную ссылку.")
        await callback.answer()


    try:
        await callback.answer()
    except TelegramBadRequest:
        pass

async def universal_handler(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    if message.text and message.text.startswith('/'):
        return

    if not ((message.text and message.text.startswith(('http://', 'https://'))) or message.audio or message.document):
        return

    can_use, is_paid = await db.check_user_trials(user_id)
    if not can_use:
        await message.answer(f"❌ {get_string('no_trials', 'ru')}", reply_markup=ui.create_menu_keyboard())
        return

    file_limit = PAID_USER_FILE_LIMIT if is_paid else FREE_USER_FILE_LIMIT
    if message.audio or message.document:
        file_size = (message.audio.file_size if message.audio else message.document.file_size)
        if file_size > file_limit:
            await message.answer(f"❌ {get_string('file_too_large', 'ru', size=file_size, limit=file_limit)}", reply_markup=ui.create_menu_keyboard())
            return

    audio_path = None
    try:
        ui.ensure_user_settings(user_id)

        if message.text and message.text.startswith(('http://', 'https://')):
            url = message.text.strip()
            logger.info(f"Скачивание YouTube: {url}")

            async def download_progress(percent_value):
                try:
                    progress = percent_value / 100.0
                    await ui.progress_manager.update_progress(progress, temp_message, 'ru')
                except Exception as e:
                    logger.warning(f"Ошибка обработки прогресса загрузки: {e}")

            temp_message = await message.answer(f"📥 Начинаю скачивание...\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%")
            audio_path = await services.download_youtube_audio(url, progress_callback=download_progress)
            await temp_message.delete()
        else:
            file = message.audio or message.document
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".temp").name
            await bot.download(file, destination=temp_path)
            audio_path = await services.convert_to_mp3(temp_path)
            try:
                os.remove(temp_path)
            except:
                logger.warning(f"Не удалось удалить временный файл {temp_path}")

        ui.user_selections[user_id] = {
            'speakers': False,
            'plain': False,
            'timecodes': False,
            'file_path': audio_path,
            'message_id': None
        }
        selection_message = await message.answer(
            get_string('select_transcription', 'ru'),
            reply_markup=ui.create_transcription_selection_keyboard(user_id)
        )
        ui.user_selections[user_id]['message_id'] = selection_message.message_id

    except Exception as e:
        logger.error(f"Ошибка предварительной обработки для user_id {user_id}: {str(e)}")
        await message.answer(f"❌ {get_string('error', 'ru', error=str(e))}")
        if audio_path:
            try:
                os.remove(audio_path)
            except:
                pass
        if user_id in ui.user_selections:
            del ui.user_selections[user_id]

async def process_audio_file_for_user(bot: Bot, message: types.Message, user_id: int, selections: dict, audio_path: str):
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

    ui.ensure_user_settings(user_id)
    chosen_format = ui.user_settings[user_id]['format']
    chosen_ext = SUPPORTED_FORMATS[chosen_format]['ext']

    logger.info(f"Обработка файла для user_id {user_id} с выбором: {selections}, формат: {chosen_format}")

    progress_message = await message.answer(f"{EMOJI['processing']} Начинаю обработку...\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%")

    out_files = []
    try:
        async def update_audio_progress(progress, status_text=None):
            if isinstance(progress, (int, float)):
                if progress < 0.99:
                    await asyncio.sleep(5)
                await ui.progress_manager.update_progress(progress, progress_message, lang)
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
            timecodes_text = services.generate_summary_timecodes(results)
            path, name = _save_with_format(timecodes_text, f"{EMOJI['timecodes']} Транскрипт с тайм-кодами")
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
            except Exception as e:
                logger.error(f"Ошибка отправки файла {file_path}: {e}")
                await bot.send_document(
                    chat_id,
                    document=FSInputFile(file_path, filename=filename),
                    caption=filename.replace(chosen_ext, "")
                )

        await progress_message.edit_text(
            f"{EMOJI['success']} {get_string('done')}\nВсе файлы успешно сформированы и отправлены",
            reply_markup=ui.create_menu_keyboard()
        )

        if not (await db.check_user_trials(user_id))[1]:
            await db.increment_trials(user_id)

    except Exception as e:
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
        if user_id in ui.user_selections:
            del ui.user_selections[user_id]

# --- Registration Function ---

def register_handlers(dp: Dispatcher, bot: Bot):
    dp.message.register(start_handler, CommandStart())
    dp.message.register(subscription_handler, Command("subscription", "subscribe"))
    dp.message.register(menu_handler, Command("menu"))
    dp.message.register(settings_cmd, Command("settings"))
    dp.message.register(referral_cmd, Command("referral"))
    dp.message.register(support_cmd, Command("support"))
    dp.callback_query.register(callback_handler)
    dp.message.register(universal_handler)
