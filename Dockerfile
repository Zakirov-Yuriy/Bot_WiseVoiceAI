FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    redis-server \
    supervisor \
    nginx \
 && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app /var/log/supervisor /var/run/redis

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY images/ /app/images/

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy nginx configuration
COPY nginx.conf /etc/nginx/sites-available/default

# Expose ports
EXPOSE 80 443 8000 8001 6379

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
