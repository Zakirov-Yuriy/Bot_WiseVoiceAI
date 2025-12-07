import logging
import httpx
import uuid
import time
from typing import List, Dict, Optional, Callable, Any, Tuple

from ..config import (
    YOOMONEY_WALLET, YOOMONEY_BASE_URL, SUBSCRIPTION_AMOUNT
)
from ..exceptions import PaymentError
from ..circuit_breaker import CircuitBreaker
from ..database import activate_subscription

logger = logging.getLogger(__name__)


# =============================
#     YooMoney Payment
# =============================
async def create_yoomoney_payment(user_id: int, amount: int, description: str) -> Tuple[Optional[str], Optional[str]]:
    """Создает ссылку на оплату YooMoney."""
    payment_label = f"sub_{user_id}_{uuid.uuid4()}"
    quickpay_url = f"{YOOMONEY_BASE_URL}/quickpay/confirm.xml"
    params = {
        "receiver": YOOMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": description,
        "paymentType": "SB",
        "sum": amount,
        "label": payment_label,
    }

    async def _make_request():
        async with httpx.AsyncClient() as client:
            response = await client.post(quickpay_url, data=params, follow_redirects=False)
            if response.status_code == 302:
                # Для YooMoney редирект 302 - это успешный ответ
                redirect_url = response.headers.get('Location', '')
                if redirect_url:
                    return redirect_url, payment_label
                else:
                    raise PaymentError("YooMoney не вернул URL для оплаты")
            else:
                response.raise_for_status()
                from urllib.parse import urlencode
                encoded_params = urlencode(params)
                payment_url = f"{YOOMONEY_BASE_URL}/quickpay/confirm.xml?{encoded_params}"
                return payment_url, payment_label

    circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30, expected_exception=(httpx.RequestError,))

    for attempt in range(3):
        try:
            result = await circuit_breaker.call(_make_request)
            logger.info(f"Создана ссылка на оплату для user_id {user_id}: {payment_label}")
            return result
        except (httpx.RequestError,) as e:
            logger.warning(f"Попытка {attempt + 1}/3 создания платежа YooMoney не удалась: {e}")
            if attempt == 2:
                raise PaymentError(f"Не удалось создать платеж YooMoney: {e}") from e
            time.sleep(2 ** attempt)
    return None, None


async def confirm_payment_and_activate_subscription(payment_label: str, username: Optional[str] = None) -> bool:
    """
    Manually confirm payment and activate subscription.
    This function parses the payment label to extract user_id and activates the subscription.
    """
    try:
        # Parse payment label format: sub_{user_id}_{uuid}
        if not payment_label.startswith("sub_"):
            logger.error(f"Invalid payment label format: {payment_label}")
            return False

        parts = payment_label.split("_")
        if len(parts) < 2:
            logger.error(f"Invalid payment label format: {payment_label}")
            return False

        user_id_str = parts[1]
        try:
            user_id = int(user_id_str)
        except ValueError:
            logger.error(f"Invalid user_id in payment label: {payment_label}")
            return False

        # Activate subscription for the user
        expiry_time = await activate_subscription(user_id, username=username)
        logger.info(f"Подписка активирована для user_id {user_id} по платежу {payment_label}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при подтверждении платежа {payment_label}: {e}")
        return False
