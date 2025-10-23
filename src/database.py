import aiosqlite
import time
import logging
import random
import string
from typing import Optional
from .models import UserData
from .config import SUBSCRIPTION_DURATION_DAYS, ADMIN_USER_IDS

logger = logging.getLogger(__name__)

async def init_db() -> None:
    async with aiosqlite.connect('users.db') as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                trials_used INTEGER DEFAULT 0,
                is_paid BOOLEAN DEFAULT FALSE,
                subscription_expiry INTEGER DEFAULT 0,
                referrer_id INTEGER NULL,
                referral_code TEXT UNIQUE NULL,
                free_weeks INTEGER DEFAULT 0
            )
        ''')
        await conn.commit()
        logger.info("База данных инициализирована")

async def check_user_trials(user_id: int) -> tuple[bool, bool]:
    if user_id in ADMIN_USER_IDS:
        logger.info(f"User {user_id} is an admin, granting full access.")
        return True, True

    async with aiosqlite.connect('users.db') as conn:
        cursor = await conn.execute('SELECT trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        if row is None:
            await conn.execute('INSERT INTO users (user_id, trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks) VALUES (?, 0, FALSE, 0, NULL, NULL, 0)', (user_id,))
            await conn.commit()
            trials_used = 0
            is_paid = False
        else:
            trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks = row
            if is_paid and subscription_expiry > 0 and time.time() > subscription_expiry:
                is_paid = False
                await conn.execute('UPDATE users SET is_paid = FALSE, subscription_expiry = 0 WHERE user_id = ?', (user_id,))
                await conn.commit()
                logger.info(f"Подписка для user_id {user_id} истекла")
        can_use = is_paid or trials_used < 2
        logger.info(f"User {user_id}: can_use={can_use}, is_paid={is_paid}, trials_used={trials_used}")
        return can_use, is_paid

async def increment_trials(user_id: int) -> None:
    async with aiosqlite.connect('users.db') as conn:
        await conn.execute('UPDATE users SET trials_used = trials_used + 1 WHERE user_id = ?', (user_id,))
        await conn.commit()
        logger.info(f"Попытки для user {user_id} обновлены")

async def activate_subscription(user_id: int, weeks: int = SUBSCRIPTION_DURATION_DAYS) -> int:
    async with aiosqlite.connect('users.db') as conn:
        cursor = await conn.execute('SELECT is_paid, subscription_expiry FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        current_expiry = 0
        if row and row[0]:
            current_expiry = row[1]

        start_time = max(int(time.time()), current_expiry) if current_expiry > int(time.time()) else int(time.time())
        expiry_time = start_time + weeks * 24 * 60 * 60

        await conn.execute('UPDATE users SET is_paid = TRUE, subscription_expiry = ? WHERE user_id = ?', (expiry_time, user_id))
        await conn.commit()
        logger.info(f"Подписка активирована/продлена для user_id {user_id} до {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry_time))}")
        return expiry_time

async def get_user_data(user_id: int) -> Optional[UserData]:
    async with aiosqlite.connect('users.db') as conn:
        cursor = await conn.execute('SELECT user_id, trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            data = UserData(
                user_id=row[0],
                trials_used=row[1],
                is_paid=row[2],
                subscription_expiry=row[3],
                referrer_id=row[4],
                referral_code=row[5],
                free_weeks=row[6]
            )
            return data
        return None

async def update_user_referral_code(user_id: int, referral_code: str) -> None:
    async with aiosqlite.connect('users.db') as conn:
        await conn.execute('UPDATE users SET referral_code = ? WHERE user_id = ?', (referral_code, user_id))
        await conn.commit()
        logger.info(f"Реферальный код {referral_code} обновлен для user_id {user_id}")

async def update_user_referrer(user_id: int, referrer_id: int) -> None:
    async with aiosqlite.connect('users.db') as conn:
        await conn.execute('UPDATE users SET referrer_id = ? WHERE user_id = ?', (referrer_id, user_id))
        await conn.commit()
        logger.info(f"Реферер {referrer_id} установлен для user_id {user_id}")

async def add_free_weeks_to_referrer(referrer_id: int, weeks_to_add: int) -> None:
    async with aiosqlite.connect('users.db') as conn:
        cursor = await conn.execute('SELECT free_weeks, subscription_expiry FROM users WHERE user_id = ?', (referrer_id,))
        row = await cursor.fetchone()
        if row:
            current_free_weeks = row[0]
            current_expiry = row[1]

            new_free_weeks = current_free_weeks + weeks_to_add
            
            start_time = max(int(time.time()), current_expiry) if current_expiry > int(time.time()) else int(time.time())
            new_expiry_time = start_time + new_free_weeks * 24 * 60 * 60

            await conn.execute('UPDATE users SET free_weeks = ?, subscription_expiry = ?, is_paid = TRUE WHERE user_id = ?', (new_free_weeks, new_expiry_time, referrer_id))
            await conn.commit()
            logger.info(f"Рефереру {referrer_id} добавлено {weeks_to_add} бесплатных недель. Новая подписка до {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_expiry_time))}")

async def consume_free_week(user_id: int) -> bool:
    async with aiosqlite.connect('users.db') as conn:
        cursor = await conn.execute('SELECT free_weeks FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        if row and row[0] > 0:
            new_free_weeks = row[0] - 1
            await conn.execute('UPDATE users SET free_weeks = ? WHERE user_id = ?', (new_free_weeks, user_id))
            await conn.commit()
            logger.info(f"У пользователя {user_id} использована одна бесплатная неделя. Осталось: {new_free_weeks}")
            return True
        return False

async def generate_and_set_referral_code(user_id: int) -> Optional[str]:
    user_data = await get_user_data(user_id)
    if user_data and user_data.referral_code:
        logger.info(f"У пользователя {user_id} уже есть реферальный код.")
        return user_data.referral_code

    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        async with aiosqlite.connect('users.db') as conn:
            cursor = await conn.execute('SELECT user_id FROM users WHERE referral_code = ?', (code,))
            existing_code = await cursor.fetchone()
            if existing_code is None:
                await update_user_referral_code(user_id, code)
                logger.info(f"Сгенерирован и установлен реферальный код {code} для user_id {user_id}")
                return code
