import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest

from .. import database as db
from .. import services
from ..ui import UserSelections, user_selections, user_settings
from ..config import settings
from ..localization import get_string
from ..ui import create_menu_keyboard, create_settings_keyboard, create_transcription_selection_keyboard, ensure_user_settings
from .command_handlers import start_handler, menu_handler, settings_cmd, referral_cmd, support_cmd
from .payment_handlers import subscription_handler, confirm_payment_handler, user_info_handler


async def user_handler(message: types.Message) -> None:
    """Показать информацию о текущем пользователе"""
    user_id = message.from_user.id

    user_data = await db.get_user_data(user_id)
    if not user_data:
        await message.answer("❌ Не удалось получить данные пользователя.")
        return

    import time
    current_time = int(time.time())

    if user_data.is_paid and user_data.subscription_expiry > current_time:
        # Показать дни до окончания подписки
        days_left = (user_data.subscription_expiry - current_time) // (24 * 60 * 60)
        message_text = f"👤 *Информация о пользователе*\n\n✅ У вас активная подписка!\n📅 Дней до окончания: {days_left}"
    else:
        # Показать оставшиеся попытки
        remaining_attempts = max(0, 3 - user_data.trials_used)
        message_text = f"👤 *Информация о пользователе*\n\n🎯 Оставшихся бесплатных попыток: {remaining_attempts}\n💳 Для неограниченного использования оформите подписку!"

    await message.answer(message_text, parse_mode='Markdown', reply_markup=create_menu_keyboard())
from .file_handlers import universal_handler, process_audio_file_for_user

logger = logging.getLogger(__name__)


async def callback_handler(callback: types.CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    data = callback.data
    logger.info(f"Callback от user_id {user_id}: {data}")

    if data == 'user':
        user_data = await db.get_user_data(user_id)
        if not user_data:
            await callback.message.answer("❌ Не удалось получить данные пользователя.")
            await callback.answer()
            return

        import time
        current_time = int(time.time())

        if user_data.is_paid and user_data.subscription_expiry > current_time:
            # Показать дни до окончания подписки
            days_left = (user_data.subscription_expiry - current_time) // (24 * 60 * 60)
            message_text = f"👤 *Информация о пользователе*\n\n✅ У вас активная подписка!\n📅 Дней до окончания: {days_left}"
        else:
            # Показать оставшиеся попытки
            remaining_attempts = max(0, 3 - user_data.trials_used)
            message_text = f"👤 *Информация о пользователе*\n\n🎯 Оставшихся бесплатных попыток: {remaining_attempts}\n💳 Для неограниченного использования оформите подписку!"

        await callback.message.answer(message_text, parse_mode='Markdown', reply_markup=create_menu_keyboard())
        await callback.answer()

    elif data == 'subscribe':
        await subscription_handler(callback.message)
        await callback.answer()

    elif data == 'settings':
        ensure_user_settings(user_id)
        await callback.message.answer(get_string('settings_choose', 'ru'), reply_markup=create_settings_keyboard(user_id))

    elif data in ['set_format_google', 'set_format_word', 'set_format_pdf', 'set_format_txt', 'set_format_md']:
        ensure_user_settings(user_id)
        new_fmt = {
            'set_format_google': 'google',
            'set_format_word': 'word',
            'set_format_pdf': 'pdf',
            'set_format_txt': 'txt',
            'set_format_md': 'md'
        }[data]
        user_settings[user_id]['format'] = new_fmt
        try:
            await callback.message.edit_text(get_string('settings_choose', 'ru'), reply_markup=create_settings_keyboard(user_id))
        except TelegramBadRequest:
            await callback.message.answer(get_string('settings_choose', 'ru'), reply_markup=create_settings_keyboard(user_id))

    elif data == 'settings_back':
        try:
            await callback.message.edit_text(get_string('menu', 'ru'), reply_markup=create_menu_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(get_string('menu', 'ru'), reply_markup=create_menu_keyboard())

    elif data in ['select_speakers', 'select_plain', 'select_timecodes', 'select_summary']:
        if user_id not in user_selections:
            await callback.answer("Сначала отправьте аудиофайл, голосовое сообщение или ссылку на YouTube.")
            return
        selections = user_selections[user_id]
        if data == 'select_speakers':
            selections['speakers'] = not selections['speakers']
        elif data == 'select_plain':
            selections['plain'] = not selections['plain']
        elif data == 'select_timecodes':
            selections['timecodes'] = not selections['timecodes']
        elif data == 'select_summary':
            selections['summary'] = not selections['summary']
        try:
            await callback.message.edit_text(
                get_string('select_transcription', 'ru'),
                reply_markup=create_transcription_selection_keyboard(user_id)
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Не удалось обновить сообщение: {str(e)}")

    elif data == 'confirm_selection':
        if user_id not in user_selections:
            await callback.answer("Сначала отправьте аудиофайл, голосовое сообщение или ссылку на YouTube.")
            return
        selections = user_selections[user_id]
        if not any([selections['speakers'], selections['plain'], selections['timecodes'], selections['summary']]):
            await callback.message.edit_text(
                f"❌ {get_string('no_selection', 'ru')}",
                reply_markup=create_transcription_selection_keyboard(user_id)
            )
            return
        audio_path = selections.get('file_path')
        if not audio_path:
            await callback.message.edit_text(
                f"❌ Ошибка: файл не найден. Попробуйте отправить файл или ссылку снова.",
                reply_markup=create_menu_keyboard()
            )
            if user_id in user_selections:
                del user_selections[user_id]
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

        referral_code = user_data.referral_code
        if not referral_code:
            referral_code = await db.generate_and_set_referral_code(user_id)
            if not referral_code:
                await callback.message.answer("❌ Не удалось сгенерировать реферальный код.")
                await callback.answer()
                return

        bot_username = f"@{settings.bot_username}"
        referral_link = f"https://t.me/{settings.bot_username}?start=ref_{user_id}"

        # Сохраняем ссылку, если она была сгенерирована только что
        # Предполагаем, что в db.py есть функция update_user_referral_link(user_id, referral_link)
        # Если нет, то нужно ее добавить. Пока просто используем сгенерированную ссылку.
        # await db.update_user_referral_link(user_id, referral_link)

        if referral_link:
            await callback.message.answer(
                f"✨ Вот ваше реферальное приглашение:\n\n"
                f"🎁 Забирайте 2 бесплатные попытки прямо сейчас 👇\n\n"
                f"Telegram: @{settings.bot_username}\n\n"
                f"Просто отправьте аудио или видео — и получите готовый текст с тайм-кодами и поддержкой разных спикеров 🙌\n\n"
                f"Ваша реферальная ссылка: {referral_link}",
                reply_markup=create_menu_keyboard(), # Или другая клавиатура, если нужно
                parse_mode='Markdown'
            )
        else:
            await callback.message.answer("❌ Не удалось сгенерировать реферальную ссылку.")
        await callback.answer()


def register_handlers(dp: Dispatcher, bot: Bot):
    dp.message.register(start_handler, CommandStart())
    dp.message.register(subscription_handler, Command("subscription", "subscribe"))
    dp.message.register(confirm_payment_handler, Command("confirm_payment"))
    dp.message.register(user_handler, Command("user"))
    dp.message.register(user_info_handler, Command("user_info"))
    dp.message.register(menu_handler, Command("menu"))
    dp.message.register(settings_cmd, Command("settings"))
    dp.message.register(referral_cmd, Command("referral"))
    dp.message.register(support_cmd, Command("support"))
    dp.callback_query.register(callback_handler)
    dp.message.register(universal_handler)
