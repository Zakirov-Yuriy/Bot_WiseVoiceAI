import logging
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart

from .. import database as db
from ..ui import UserSelections
from ..config import (
    settings,
    YOOMONEY_WALLET, YOOMONEY_REDIRECT_URI, SUBSCRIPTION_AMOUNT,
    SUBSCRIPTION_DURATION_DAYS, PAID_USER_FILE_LIMIT, FREE_USER_FILE_LIMIT,
    SUPPORTED_FORMATS, CUSTOM_THUMBNAIL_PATH, BASE_DIR, SUPPORT_USERNAME,
    SUPPORTED_AUDIO_FORMATS, SUPPORTED_VIDEO_FORMATS
)
from ..localization import get_string
from ..ui import create_menu_keyboard, create_settings_keyboard, create_referral_keyboard
from ..services.security import audit_logger

logger = logging.getLogger(__name__)


async def start_handler(message: types.Message, bot: Bot) -> None:
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

                        # Log referral link usage
                        await audit_logger.log_referral_event(
                            user_id=user_id,
                            event_type="link_used",
                            referrer_id=referrer_id,
                            metadata={"source": "telegram_start_command"}
                        )

                        logger.info(f"Пользователь {user_id} пришел по реферальной ссылке от {referrer_id}")
                        # Генерируем реферальный код для нового пользователя, если он еще не создан
                        user_data = await db.get_user_data(user_id)
                        if not user_data or not user_data.referral_code:
                            await db.generate_and_set_referral_code(user_id)
                        break
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Не удалось обработать реферальную ссылку: {param}. Ошибка: {e}")

    welcome_text = (
        "🎉 *Привет!*\n\n"
        f"У вас есть *{settings.free_trials_count} бесплатные попытки* попробовать сервис.\n\n"
        f"⚡️ Если ваш файл весит больше *{settings.max_file_size_mb} МБ* — загрузите его в одно из популярных облачных хранилищ и отправьте мне ссылку:\n\n"
        "• [Dropbox](https://www.dropbox.com/)\n"
        "• [Google Drive](https://drive.google.com/)\n"
        "• [OneDrive](https://onedrive.live.com/)\n\n"
        "👉 Важно:\n"
        "• Файл должен быть *доступен по ссылке для всех*.\n"
        "• Размер не больше *5 ГБ*.\n\n"
        "После этого просто пришлите мне ссылку, и я все сделаю за вас 🙌"
    )
    await message.answer(
    welcome_text,
    parse_mode="Markdown",
    disable_web_page_preview=True  # ✅ убирает предпросмотр ссылок (рекламу)
)


async def menu_handler(message: types.Message) -> None:
    await message.answer(get_string('menu', 'ru'), reply_markup=create_menu_keyboard(), parse_mode='Markdown')
    logger.info(f"Меню отправлено для user_id {message.from_user.id}")


async def settings_cmd(message: types.Message) -> None:
    await message.answer(
        get_string('settings_choose', 'ru'),
        reply_markup=create_settings_keyboard(message.from_user.id)
    )


async def referral_cmd(message: types.Message) -> None:
    user_id = message.from_user.id
    user_data = await db.get_user_data(user_id)

    if not user_data:
        await message.answer("❌ Произошла ошибка при получении данных пользователя.")
        return

    referral_code = user_data.referral_code
    if not referral_code:
        referral_code = await db.generate_and_set_referral_code(user_id)
        if not referral_code:
            await message.answer("❌ Не удалось сгенерировать реферальный код.")
            return

    # Формируем реферальную ссылку
    bot_username = f"@{settings.bot_username}"
    referral_link = f"https://t.me/{settings.bot_username}?start=ref_{user_id}"

    # Пример текста для реферального сообщения
    referral_message_template = (
        "✨ Вы приглашены в Transcribe To — бота для удобного и точного преобразования аудио и видео в текст!\n\n"
        f"🎁 Забирайте {settings.free_trials_count} бесплатные попытки прямо сейчас 👇\n\n"
        f"Telegram: @{settings.bot_username}\n\n"
        "Просто отправьте аудио или видео — и получите готовый текст с тайм-кодами и поддержкой разных спикеров 🙌\n\n"
        "--- Ваш реферальный код: {referral_code} ---\n"
        "--- Ваша реферальная ссылка: {referral_link} ---"
    )

    await message.answer(
        referral_message_template.format(referral_code=referral_code, referral_link=referral_link),
        reply_markup=create_referral_keyboard(referral_link), # Предполагаем, что такая кнопка есть в ui.py
        parse_mode='Markdown'
    )
    logger.info(f"Реферальная информация отправлена для user_id {user_id}")


async def support_cmd(message: types.Message) -> None:
    await message.answer(f"Напишите нам: {SUPPORT_USERNAME}")
