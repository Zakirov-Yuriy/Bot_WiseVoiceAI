#!/usr/bin/env python3
"""
Script to add a new user to local SQLite database (users.db)
"""
import sqlite3
from datetime import datetime

def add_user_to_local_db(user_id: int, trials_used: int = 0, is_paid: bool = False,
                        subscription_expiry: int = 0, referrer_id: int = None,
                        referral_code: str = None, free_weeks: int = 0):
    """Add a new user to local SQLite database"""

    print("ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ В ЛОКАЛЬНУЮ БАЗУ ДАННЫХ")
    print("="*60)
    print(f"База данных: users.db")
    print(f"Добавляемый пользователь ID: {user_id}")

    try:
        # Connect to database
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        # Check if user already exists
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()

        if existing:
            print(f"❌ Пользователь с ID {user_id} уже существует в базе данных")
            conn.close()
            return False

        # Insert new user
        cursor.execute('''
            INSERT INTO users (user_id, trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, trials_used, is_paid, subscription_expiry, referrer_id, referral_code, free_weeks))

        conn.commit()
        print("✅ Пользователь успешно добавлен!")

        # Show user data
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()

        if user:
            print("\nДобавленный пользователь:")
            print("-" * 80)
            print(f"ID: {user[0]}")
            print(f"Попытки: {user[1]}")
            print(f"Оплачен: {'Да' if user[2] else 'Нет'}")
            expiry = user[3]
            if expiry and expiry > 0:
                expiry_str = datetime.fromtimestamp(expiry).strftime('%d.%m.%Y %H:%M:%S')
            else:
                expiry_str = "Нет"
            print(f"Истечение подписки: {expiry_str}")
            print(f"Реферер ID: {user[4] if user[4] else 'Нет'}")
            print(f"Реферальный код: {user[5] if user[5] else 'Нет'}")
            print(f"Бесплатные недели: {user[6]}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Ошибка при добавлении пользователя: {e}")
        return False

def main():
    """Main function to add user with ID 987654321"""
    user_id = 987654321

    # Default values for new user
    success = add_user_to_local_db(
        user_id=user_id,
        trials_used=0,        # No trials used yet
        is_paid=False,        # Not paid
        subscription_expiry=0, # No subscription
        referrer_id=None,     # No referrer
        referral_code=None,   # No referral code yet
        free_weeks=0          # No free weeks
    )

    if success:
        print("\n" + "="*60)
        print("✅ ОПЕРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print(f"Пользователь {user_id} добавлен в локальную базу данных")
        print("="*60)

        # Show updated database
        print("\nОБНОВЛЕННАЯ БАЗА ДАННЫХ:")
        import subprocess
        try:
            subprocess.run(['python', 'view_local_database.py'], check=True)
        except subprocess.CalledProcessError:
            print("Не удалось автоматически показать обновленную базу данных")
            print("Запустите: python view_local_database.py")

if __name__ == "__main__":
    main()
