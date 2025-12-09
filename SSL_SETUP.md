# Настройка SSL сертификата Let's Encrypt для продакшена

## Важность HTTPS для YooMoney
YooMoney требует HTTPS URL для webhook уведомлений в продакшене. HTTP работает только для тестирования.

## Шаг 1: Установка Certbot

```bash
# Обновите систему
sudo apt update && sudo apt upgrade -y

# Установите certbot
sudo apt install certbot -y

# Установите certbot для nginx (если планируете использовать nginx напрямую)
sudo apt install python3-certbot-nginx -y
```

## Шаг 2: Получение SSL сертификата

### Вариант 1: Standalone (рекомендуется для Docker)

```bash
# Остановите nginx в контейнере, если он работает
docker-compose exec nginx nginx -s stop

# Или остановите весь контейнер
docker-compose down

# Получите сертификат (standalone режим)
sudo certbot certonly --standalone -d transcribe-to.work.gd

# Следуйте инструкциям на экране
# Введите ваш email для уведомлений
# Примите условия использования
# Сертификаты будут сохранены в /etc/letsencrypt/live/transcribe-to.work.gd/
```

### Вариант 2: С помощью nginx плагина (если nginx не в контейнере)

```bash
# Если nginx работает на хосте, используйте плагин
sudo certbot --nginx -d transcribe-to.work.gd
```

## Шаг 3: Обновление nginx конфигурации

После получения сертификата обновите `nginx.conf`:

```nginx
server {
    listen 80;
    server_name transcribe-to.work.gd 155.212.168.210;

    # Редирект всех HTTP запросов на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name transcribe-to.work.gd 155.212.168.210;

    # SSL конфигурация
    ssl_certificate /etc/letsencrypt/live/transcribe-to.work.gd/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/transcribe-to.work.gd/privkey.pem;

    # Современные настройки безопасности
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # Proxy webhook запросов
    location /yoomoney/webhook {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Health check
    location /health {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Test endpoint
    location /test/webhook {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Шаг 4: Монтирование сертификатов в Docker

Обновите `docker-compose.yml` для монтирования сертификатов:

```yaml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/sites-available/default
      - /etc/letsencrypt:/etc/letsencrypt:ro  # Монтируем сертификаты
    depends_on:
      - app
    networks:
      - app-network

  app:
    build: .
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      # ... другие переменные
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

## Шаг 5: Обновление .env файла

Измените webhook URL на HTTPS:

```
YOOMONEY_WEBHOOK_URL=https://transcribe-to.work.gd/yoomoney/webhook
```

## Шаг 6: Перезапуск сервисов

```bash
# Пересоберите и запустите
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Проверьте работу HTTPS
curl -I https://transcribe-to.work.gd/health
```

## Шаг 7: Настройка автоматического обновления сертификатов

Поскольку вы используете acme.sh, настройте автоматическое обновление:

```bash
# Настройте cron job для acme.sh (уже может быть настроено)
crontab -l

# Если нет, добавьте:
# 0 3 * * * "/root/.acme.sh"/acme.sh --cron --home "/root/.acme.sh" > /dev/null

# После обновления сертификатов нужно перезагрузить nginx
# Создайте post-renewal hook
mkdir -p /root/.acme.sh/transcribe-to.work.gd

# Создайте скрипт для перезагрузки nginx после обновления
cat > /root/.acme.sh/transcribe-to.work.gd/post-renewal.sh << 'EOF'
#!/bin/bash
echo "Reloading nginx after SSL certificate renewal..."
cd /path/to/your/project  # Укажите путь к проекту
docker-compose exec bot nginx -s reload
EOF

chmod +x /root/.acme.sh/transcribe-to.work.gd/post-renewal.sh
```

Или настройте cron job для запуска скрипта обновления:

```bash
# Добавьте в crontab (crontab -e):
# Каждый день в 3:00 проверять и обновлять сертификаты
0 3 * * * /path/to/project/update_ssl.sh
# Тест webhook
curl -k https://transcribe-to.work.gd/health

# Тест платежного webhook (замените параметры)
curl -X POST https://transcribe-to.work.gd/yoomoney/webhook \
  -d "notification_type=p2p-incoming&operation_id=test123&amount=300.00&currency=643&datetime=2023-12-01T12:00:00Z&sender=test&codepro=false&label=sub_123456789_test&unaccepted=false"
```

## Troubleshooting

### Проблема: Certbot не может получить сертификат
```bash
# Проверьте DNS
nslookup transcribe-to.work.gd

# Проверьте firewall
sudo ufw status
sudo ufw allow 80
sudo ufw allow 443

# Проверьте, что порт 80 доступен
curl -I http://transcribe-to.work.gd
```

### Проблема: Сертификаты не монтируются в контейнер
```bash
# Проверьте права доступа
ls -la /etc/letsencrypt/live/transcribe-to.work.gd/

# Измените права если нужно
sudo chmod 755 /etc/letsencrypt/archive
sudo chmod 755 /etc/letsencrypt/live
```

### Проблема: Nginx не перезапускается после обновления сертификатов
```bash
# Проверьте логи certbot
sudo journalctl -u certbot

# Ручной тест перезапуска
docker-compose exec nginx nginx -s reload
```

## Безопасность

- Регулярно обновляйте сертификаты (автоматически каждые 90 дней)
- Мониторьте срок действия сертификатов
- Используйте strong ciphers
- Настройте HSTS заголовки при необходимости
