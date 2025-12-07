import logging
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart

from .. import database as db
from .. import services
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
from ..services.payment import confirm_payment_and_activate_subscription

logger = logging.getLogger(__name__)


async def subscription_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    description = f"Подписка на Transcribe To на {SUBSCRIPTION_DURATION_DAYS} дней"

    payment_url, payment_label = await services.create_yoomoney_payment(
        user_id=user_id,
        amount=SUBSCRIPTION_AMOUNT,
        description=description
    )

    if payment_url:
        # Log payment creation
        await audit_logger.log_payment_event(
            user_id=user_id,
            event_type="created",
            amount=SUBSCRIPTION_AMOUNT,
            payment_id=payment_label,
            status="pending",
            metadata={
                "description": description,
                "payment_url": payment_url,
                "subscription_days": SUBSCRIPTION_DURATION_DAYS
            }
        )

        await message.answer(
            f"💳 Для оформления подписки перейдите по ссылке:\n[Оплатить подписку]({payment_url})\n"
            f"Стоимость: {SUBSCRIPTION_AMOUNT} руб. на {SUBSCRIPTION_DURATION_DAYS} дней.\n"
            "После оплаты подписка активируется автоматически.",
            reply_markup=create_menu_keyboard(),
            parse_mode='Markdown'
        )
        logger.info(f"Ссылка на оплату отправлена для user_id {user_id}: {payment_label}")

        # --- Логика реферальной программы при покупке подписки ---
        user_data = await db.get_user_data(user_id)
        if user_data and user_data.referrer_id:
            referrer_id = user_data.referrer_id
            # Начисляем рефереру неделю бесплатного пользования
            await db.add_free_weeks_to_referrer(referrer_id, weeks_to_add=1)

            # Log referral bonus
            await audit_logger.log_referral_event(
                user_id=user_id,
                event_type="bonus_awarded",
                referrer_id=referrer_id,
                metadata={
                    "bonus_weeks": 1,
                    "reason": "subscription_purchase"
                }
            )

            logger.info(f"Рефереру {referrer_id} добавлена 1 неделя подписки за приглашение пользователя {user_id}")
            # Опционально: уведомить реферера о начислении бонуса
            # try:
            #     await bot.send_message(referrer_id, f"Пользователь {user_id} оформил подписку! Вам начислена 1 неделя бесплатного пользования.")
            # except Exception as e:
            #     logger.warning(f"Не удалось уведомить реферера {referrer_id}: {e}")

    else:
        await message.answer(
            "❌ Не удалось создать ссылку на оплату. Пожалуйста, попробуйте позже.",
            reply_markup=create_menu_keyboard()
        )


async def confirm_payment_handler(message: types.Message) -> None:
    """Admin command to manually confirm payment and activate subscription"""
    user_id = message.from_user.id

    # Check if user is admin
    if user_id not in settings.admin_user_ids:
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    # Parse command arguments
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /confirm_payment <payment_label>\n"
            "Пример: /confirm_payment sub_123456789_abc123..."
        )
        return

    payment_label = args[1]

    # Confirm payment and activate subscription
    success = await confirm_payment_and_activate_subscription(payment_label)

    if success:
        await message.answer(
            f"✅ Платеж {payment_label} подтвержден и подписка активирована!",
            reply_markup=create_menu_keyboard()
        )

        # Log admin action
        await audit_logger.log_admin_event(
            admin_id=user_id,
            action="confirm_payment",
            target_id=None,  # Could extract user_id from label if needed
            metadata={
                "payment_label": payment_label,
                "result": "success"
            }
        )
    else:
        await message.answer(
            f"❌ Не удалось подтвердить платеж {payment_label}. Проверьте правильность метки платежа.",
            reply_markup=create_menu_keyboard()
        )


async def user_info_handler(message: types.Message) -> None:
    """Admin command to get user information"""
    user_id = message.from_user.id

    # Check if user is admin
    if user_id not in settings.admin_user_ids:
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    # Parse command arguments
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /user_info <user_id>\n"
            "Пример: /user_info 123456789"
        )
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return

    # Get user data
    user_data = await db.get_user_data(target_user_id)

    if user_data:
        expiry_str = "Не активна"
        if user_data.subscription_expiry and user_data.subscription_expiry > 0:
            import time
            expiry_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(user_data.subscription_expiry))

        await message.answer(
            f"👤 Информация о пользователе {target_user_id}:\n"
            f"Имя пользователя: {user_data.username or 'Не указано'}\n"
            f"Количество транскрибаций: {user_data.transcription_count}\n"
            f"Использовано попыток: {user_data.trials_used}\n"
            f"Статус подписки: {'Активна' if user_data.is_paid else 'Не активна'}\n"
            f"Окончание подписки: {expiry_str}\n"
            f"Бесплатных недель: {user_data.free_weeks}\n"
            f"Реферальный код: {user_data.referral_code or 'Не установлен'}\n"
            f"Приглашен реферрером: {user_data.referrer_id or 'Нет'}",
            reply_markup=create_menu_keyboard()
        )
    else:
        await message.answer(
            f"❌ Пользователь {target_user_id} не найден в базе данных.",
            reply_markup=create_menu_keyboard()
        )
