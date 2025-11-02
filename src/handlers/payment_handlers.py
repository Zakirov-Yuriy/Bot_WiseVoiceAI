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
