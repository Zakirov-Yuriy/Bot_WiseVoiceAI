#!/usr/bin/env python3
"""
Script to upload a user from local SQLite database to remote MySQL database
"""
import asyncio
import sqlite3
import logging
from datetime import datetime
from src.database import async_session, User
from src.config import DATABASE_URL
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def upload_user_to_mysql(user_id: int):
    """Upload a specific user from local SQLite to remote MySQL database"""

    print("ЗАГРУЗКА ПОЛЬЗОВАТЕЛЯ В УДАЛЕННУЮ БАЗУ ДАННЫХ")
    print("="*60)
    print(f"Пользователь ID: {user_id}")
    print(f"Из: SQLite (users.db)")
    print(f"В: MySQL (Railway) - {DATABASE_URL}")

    try:
        # First, get user data from local SQLite database
        print("\n1. Получение данных пользователя из локальной базы...")

        conn = sqlite3.connect('users.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        local_user = cursor.fetchone()

        if not local_user:
            print(f"❌ Пользователь с ID {user_id} не найден в локальной базе данных")
            conn.close()
            return False

        print("✅ Данные пользователя получены из локальной базы")

        # Show user data
        print("\nДанные пользователя:")
        print("-" * 50)
        print(f"ID: {local_user['user_id']}")
        print(f"Попытки: {local_user['trials_used']}")
        print(f"Оплачен: {'Да' if local_user['is_paid'] else 'Нет'}")
        expiry = local_user['subscription_expiry']
        if expiry and expiry > 0:
            expiry_str = datetime.fromtimestamp(expiry).strftime('%d.%m.%Y %H:%M:%S')
        else:
            expiry_str = "Нет"
        print(f"Истечение подписки: {expiry_str}")
        print(f"Реферер ID: {local_user['referrer_id'] if local_user['referrer_id'] else 'Нет'}")
        print(f"Реферальный код: {local_user['referral_code'] if local_user['referral_code'] else 'Нет'}")
        print(f"Бесплатные недели: {local_user['free_weeks']}")

        conn.close()

        # Now upload to MySQL database
        print("\n2. Загрузка в удаленную MySQL базу данных...")

        async with async_session() as session:
            # Check if user already exists in MySQL
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"⚠️  Пользователь с ID {user_id} уже существует в MySQL базе данных")
                print("Обновляем данные...")

                # Update existing user
                existing_user.trials_used = local_user['trials_used']
                existing_user.is_paid = local_user['is_paid']
                existing_user.subscription_expiry = local_user['subscription_expiry']
                existing_user.referrer_id = local_user['referrer_id']
                existing_user.referral_code = local_user['referral_code']
                existing_user.free_weeks = local_user['free_weeks']

                await session.commit()
                print("✅ Данные пользователя обновлены в MySQL")

            else:
                # Create new user in MySQL
                mysql_user = User(
                    user_id=local_user['user_id'],
                    trials_used=local_user['trials_used'],
                    is_paid=local_user['is_paid'],
                    subscription_expiry=local_user['subscription_expiry'],
                    referrer_id=local_user['referrer_id'],
                    referral_code=local_user['referral_code'],
                    free_weeks=local_user['free_weeks']
                )

                session.add(mysql_user)
                await session.commit()
                print("✅ Пользователь добавлен в MySQL базу данных")

        print("\n" + "="*60)
        print("✅ ОПЕРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print(f"Пользователь {user_id} загружен в удаленную MySQL базу данных")
        print("="*60)

        return True

    except Exception as e:
        print(f"❌ Ошибка при загрузке пользователя: {e}")
        print("Возможно, нет подключения к интернету или проблемы с конфигурацией.")
        return False

async def main():
    """Main function to upload user with ID 987654321"""
    user_id = 987654321

    success = await upload_user_to_mysql(user_id)

    if success:
        print("\nПРОВЕРКА РЕЗУЛЬТАТА:")
        print("Запустите 'python view_database_data.py' для просмотра обновленных данных")

if __name__ == "__main__":
    asyncio.run(main())
