#!/usr/bin/env python3
"""
Script to view data in local SQLite database (users.db)
"""
import sqlite3
from datetime import datetime

def view_local_data():
    """Show data from local SQLite database (users.db)"""
    print("ПРОСМОТР ЛОКАЛЬНОЙ БАЗЫ ДАННЫХ")
    print("Бот WiseVoiceAI - users.db")
    print("="*60)

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

        else:
            print("❌ В локальной базе данных нет пользователей")

        conn.close()

    except Exception as e:
        print(f"❌ Ошибка при чтении локальной базы данных: {e}")
        print("Возможно, файл users.db не существует или поврежден.")

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
    view_local_data()
