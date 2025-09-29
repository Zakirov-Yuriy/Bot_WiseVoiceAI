import sqlite3
import time
import logging
from asyncio import Lock
from .config import SUBSCRIPTION_DURATION_DAYS, ADMIN_USER_IDS

logger = logging.getLogger(__name__)
db_lock = Lock()

async def init_db():
    async with db_lock:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                trials_used INTEGER DEFAULT 0,
                is_paid BOOLEAN DEFAULT FALSE,
                subscription_expiry INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")


async def check_user_trials(user_id: int) -> tuple[bool, bool]:
    if user_id in ADMIN_USER_IDS:
        logger.info(f"User {user_id} is an admin, granting full access.")
        return True, True

    async with db_lock:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT trials_used, is_paid, subscription_expiry FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute('INSERT INTO users (user_id, trials_used, is_paid, subscription_expiry) VALUES (?, 0, FALSE, 0)', (user_id,))
            conn.commit()
            trials_used = 0
            is_paid = False
        else:
            trials_used, is_paid, subscription_expiry = row
            if is_paid and subscription_expiry > 0 and time.time() > subscription_expiry:
                is_paid = False
                cursor.execute('UPDATE users SET is_paid = FALSE, subscription_expiry = 0 WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"Подписка для user_id {user_id} истекла")
        conn.close()
        can_use = is_paid or trials_used < 2
        logger.info(f"User {user_id}: can_use={can_use}, is_paid={is_paid}, trials_used={trials_used}")
        return can_use, is_paid


async def increment_trials(user_id: int):
    async with db_lock:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET trials_used = trials_used + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"Попытки для user {user_id} обновлены")


async def activate_subscription(user_id: int):
    async with db_lock:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        expiry_time = int(time.time()) + SUBSCRIPTION_DURATION_DAYS * 24 * 60 * 60
        cursor.execute('UPDATE users SET is_paid = TRUE, subscription_expiry = ? WHERE user_id = ?', (expiry_time, user_id))
        conn.commit()
        conn.close()
        logger.info(f"Подписка активирована для user_id {user_id} до {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry_time))}")
        return expiry_time
