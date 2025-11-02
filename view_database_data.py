#!/usr/bin/env python3
"""
Script to view data in local SQLite database and remote MySQL database
"""
import asyncio
import sqlite3
import logging
from datetime import datetime
from src.database import get_user_data, async_session, User
from src.config import DATABASE_URL
from sqlalchemy import select, func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def view_sqlite_data():
    """View data in local SQLite database (users.db.backup)"""
    print("\n" + "="*60)
    print("ЛОКАЛЬНАЯ БАЗА ДАННЫХ (SQLite - users.db.backup)")
    print("="*60)

    try:
        conn = sqlite3.connect('users.db.backup')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get total count
        cursor.execute('SELECT COUNT(*) as count FROM users')
        total_count = cursor.fetchone()['count']
        print(f"Всего пользователей: {total_count}")

        if total_count > 0:
            # Get all users
            cursor.execute('SELECT * FROM users ORDER BY user_id')
            users = cursor.fetchall()

            print("\nПользователи:")
            print("-" * 100)
            print(f"{'ID':<12} {'Попытки':<8} {'Оплачен':<8} {'Истечение':<12} {'Реферер':<10} {'Код':<12} {'Недели':<8}")
            print("-" * 100)

            for user in users:
                expiry = user['subscription_expiry']
                if expiry and expiry > 0:
                    expiry_str = datetime.fromtimestamp(expiry).strftime('%d.%m.%Y')
                else:
                    expiry_str = "Нет"

                paid_str = "Да" if user['is_paid'] else "Нет"
                referrer = str(user['referrer_id']) if user['referrer_id'] else "-"

                print(f"{user['user_id']:<12} {user['trials_used']:<8} {paid_str:<8} {expiry_str:<12} {referrer:<10} {str(user['referral_code'] or '-'):<12} {user['free_weeks']:<8}")

        conn.close()

    except Exception as e:
        print(f"Ошибка при чтении SQLite базы данных: {e}")

async def view_mysql_data():
    """View data in remote MySQL database"""
    print("\n" + "="*60)
    print("УДАЛЕННАЯ БАЗА ДАННЫХ (MySQL - Railway)")
    print("="*60)
    print(f"URL: {DATABASE_URL}")

    try:
        async with async_session() as session:
            # Get total count
            stmt = select(func.count(User.user_id))
            result = await session.execute(stmt)
            total_count = result.scalar()
            print(f"Всего пользователей: {total_count}")

            if total_count > 0:
                # Get all users
                stmt = select(User).order_by(User.user_id)
                result = await session.execute(stmt)
                users = result.scalars().all()

                print("\nПользователи:")
                print("-" * 100)
                print(f"{'ID':<12} {'Попытки':<8} {'Оплачен':<8} {'Истечение':<12} {'Реферер':<10} {'Код':<12} {'Недели':<8}")
                print("-" * 100)

                for user in users:
                    expiry = user.subscription_expiry
                    if expiry and expiry > 0:
                        expiry_str = datetime.fromtimestamp(expiry).strftime('%d.%m.%Y')
                    else:
                        expiry_str = "Нет"

                    paid_str = "Да" if user.is_paid else "Нет"
                    referrer = str(user.referrer_id) if user.referrer_id else "-"

                    print(f"{user.user_id:<12} {user.trials_used:<8} {paid_str:<8} {expiry_str:<12} {referrer:<10} {str(user.referral_code or '-'):<12} {user.free_weeks:<8}")

    except Exception as e:
        print(f"Ошибка при чтении MySQL базы данных: {e}")
        print("Возможно, нет подключения к интернету или проблемы с конфигурацией базы данных.")

async def main():
    """Main function to view both databases"""
    print("ПРОСМОТР ДАННЫХ В БАЗАХ ДАННЫХ")
    print("Бот WiseVoiceAI - управление пользователями")

    # View SQLite data
    view_sqlite_data()

    # View MySQL data
    await view_mysql_data()

    print("\n" + "="*60)
    print("Пояснения к столбцам:")
    print("- ID: Telegram user ID")
    print("- Попытки: Количество использованных бесплатных попыток")
    print("- Оплачен: Есть ли активная подписка")
    print("- Истечение: Дата окончания подписки")
    print("- Реферер: ID пользователя, который пригласил этого пользователя")
    print("- Код: Реферальный код для приглашения других пользователей")
    print("- Недели: Количество бесплатных недель от рефералов")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
