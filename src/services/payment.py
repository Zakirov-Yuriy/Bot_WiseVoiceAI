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
