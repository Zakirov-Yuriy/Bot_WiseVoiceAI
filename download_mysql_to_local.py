#!/usr/bin/env python3
"""
Script to download all data from remote MySQL database and save to local SQLite database
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

def init_local_sqlite():
    """Initialize local SQLite database with users table"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Create users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            trials_used INTEGER DEFAULT 0,
            is_paid BOOLEAN DEFAULT FALSE,
            subscription_expiry INTEGER DEFAULT 0,
            referrer_id INTEGER,
            referral_code VARCHAR(255) UNIQUE,
            free_weeks INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    return conn

def save_user_to_sqlite(conn, user):
    """Save a single user to local SQLite database"""
    cursor = conn.cursor()

    # Check if user already exists
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user.user_id,))
    existing = cursor.fetchone()

    if existing:
        # Update existing user
        cursor.execute('''
            UPDATE users SET
                trials_used = ?,
                is_paid = ?,
                subscription_expiry = ?,
                referrer_id = ?,
                referral_code = ?,
                free_weeks = ?
            WHERE user_id = ?
        ''', (
            user.trials_used,
            user.is_paid,
            user.subscription_expiry,
            user.referrer_id,
            user.referral_code,
            user.free_weeks,
            user.user_id
        ))
        logger.info(f"Обновлен пользователь {user.user_id}")
    else:
        # Insert new user
        cursor.execute('''
            INSERT INTO users (user_id, trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user.user_id,
            user.trials_used,
            user.is_paid,
            user.subscription_expiry,
            user.referrer_id,
            user.referral_code,
            user.free_weeks
        ))
        logger.info(f"Добавлен пользователь {user.user_id}")

    conn.commit()

async def download_and_save_data():
    """Download all data from MySQL and save to local SQLite"""
    print("СКАЧИВАНИЕ ДАННЫХ С УДАЛЕННОЙ БАЗЫ ДАННЫХ")
    print("="*60)
    print(f"Источник: MySQL (Railway) - {DATABASE_URL}")
    print("Назначение: SQLite (локальная) - users.db")

    # Initialize local SQLite database
    print("\n1. Инициализация локальной базы данных...")
    local_conn = init_local_sqlite()
    print("✅ Локальная база данных готова")

    try:
        # Connect to remote MySQL database
        print("\n2. Подключение к удаленной базе данных...")
        async with async_session() as session:
            print("✅ Подключение установлено")

            # Get all users from MySQL
            print("\n3. Получение данных пользователей...")
            stmt = select(User).order_by(User.user_id)
            result = await session.execute(stmt)
            mysql_users = result.scalars().all()

            total_users = len(mysql_users)
            print(f"Найдено пользователей: {total_users}")

            if total_users > 0:
                print("\n4. Сохранение данных в локальную базу...")

                saved_count = 0
                for user in mysql_users:
                    save_user_to_sqlite(local_conn, user)
                    saved_count += 1

                    if saved_count % 10 == 0:
                        print(f"   Сохранено {saved_count}/{total_users} пользователей...")

                print(f"✅ Все данные сохранены! Обработано пользователей: {saved_count}")

                # Show summary
                print("\n5. Проверка сохраненных данных...")
                cursor = local_conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM users')
                result = cursor.fetchone()
                local_count = result[0] if result else 0
                print(f"Всего пользователей в локальной базе: {local_count}")

            else:
                print("❌ В удаленной базе данных нет пользователей")

    except Exception as e:
        print(f"❌ Ошибка при работе с базами данных: {e}")
        print("Возможно, нет подключения к интернету или проблемы с конфигурацией.")
        return False

    finally:
        local_conn.close()

    print("\n" + "="*60)
    print("✅ ОПЕРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
    print("Все данные из удаленной MySQL базы сохранены в локальную SQLite базу (users.db)")
    print("="*60)

    return True

def show_local_data():
    """Show data from local SQLite database"""
    print("\nЛОКАЛЬНАЯ БАЗА ДАННЫХ (users.db) - ПРОВЕРКА:")
    print("-" * 60)

    try:
        conn = sqlite3.connect('users.db')
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
        print(f"Ошибка при чтении локальной базы данных: {e}")

async def main():
    """Main function"""
    success = await download_and_save_data()

    if success:
        show_local_data()

    print("\n" + "="*60)
    print("ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ:")
    print("- Локальная база данных: users.db")
    print("- Для просмотра данных запустите: python view_database_data.py")
    print("- Файл users.db можно использовать для резервного копирования")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
