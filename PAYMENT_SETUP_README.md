# Настройка платежей YooMoney

## Проблема
Webhook сервер не был запущен, поэтому YooMoney не мог отправлять уведомления о платежах, и подписки не активировались автоматически.

## Исправления

### 1. Добавлен webhook_server в supervisord
- Webhook сервер теперь запускается автоматически вместе с ботом
- Логи webhook сервера: `/var/log/supervisor/webhook_server.log`

### 2. Настроен nginx для проксирования webhook запросов
- Nginx слушает порт 80 и проксирует `/yoomoney/webhook` на `localhost:8001`
- Для тестирования используется HTTP (без SSL)

### 3. Обновлен Dockerfile
- Добавлен nginx
- Открыты порты 80, 443, 8000, 8001, 6379

## Настройка на сервере

### 1. Пересборка и перезапуск контейнера
```bash
# На сервере
cd /path/to/your/project
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 2. Проверка работы сервисов
```bash
# Проверить запущенные процессы
docker-compose ps

# Проверить логи webhook сервера
docker-compose logs webhook_server

# Проверить логи nginx
docker-compose logs nginx
```

### 3. Тестирование webhook endpoint
```bash
# Тест health check
curl http://transcribe-to.work.gd/health

# Тест webhook endpoint (должен вернуть "OK")
curl -X POST http://transcribe-to.work.gd/test/webhook -d "test=data"
```

### 4. Настройка YooMoney
Войдите в свой аккаунт YooMoney (кошелек 4100111325360739) и настройте HTTP уведомления:

1. Перейдите в "Инструменты для разработчиков" → "HTTP-уведомления"
2. Добавьте URL для уведомлений: `http://transcribe-to.work.gd/yoomoney/webhook`
3. Выберите события для уведомления (платежи на кошелек)

### 5. Переменные окружения
Убедитесь, что в `.env` файле установлены:
```
YOOMONEY_WALLET=4100111325360739
YOOMONEY_WEBHOOK_URL=http://transcribe-to.work.gd/yoomoney/webhook
ENABLE_PAYMENTS=true
```

## Тестирование платежей

### 1. Ручное тестирование webhook
```bash
# Симулировать платеж YooMoney (замените параметры)
curl -X POST http://transcribe-to.work.gd/yoomoney/webhook \
  -d "notification_type=p2p-incoming&operation_id=test123&amount=300.00&currency=643&datetime=2023-12-01T12:00:00Z&sender=test&codepro=false&label=sub_123456789_test&unaccepted=false"
```

### 2. Проверка логов
```bash
# Логи webhook сервера
tail -f /var/log/supervisor/webhook_server.log

# Логи бота
tail -f /var/log/supervisor/bot.log
```

### 3. Проверка базы данных
```bash
# Подключитесь к MySQL и проверьте таблицу users
SELECT user_id, is_paid, subscription_expiry FROM users WHERE user_id = 123456789;
```

## Производственная настройка SSL

Для продакшена настройте HTTPS:

1. Получите SSL сертификат (Let's Encrypt):
```bash
sudo apt install certbot
sudo certbot certonly --standalone -d transcribe-to.work.gd
```

2. Обновите nginx.conf:
```nginx
server {
    listen 443 ssl http2;
    server_name transcribe-to.work.gd;

    ssl_certificate /etc/letsencrypt/live/transcribe-to.work.gd/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/transcribe-to.work.gd/privkey.pem;

    # ... остальная конфигурация
}
```

3. Обновите YOOMONEY_WEBHOOK_URL на HTTPS в .env файле

4. Добавьте редирект с HTTP на HTTPS в nginx.conf

## Мониторинг

- Следите за логами webhook сервера на наличие ошибок
- Проверяйте, что YooMoney отправляет уведомления
- Тестируйте процесс оплаты регулярно
