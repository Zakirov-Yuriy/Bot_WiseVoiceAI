#!/bin/bash

# Script to update SSL certificates and reload nginx
# Run this script after certificate renewal

echo "Updating SSL certificates..."

# Copy certificates to a location accessible by the container (if needed)
# Since we're mounting /root/.acme.sh directly, this might not be necessary

# Reload nginx in the running container
echo "Reloading nginx configuration..."
docker-compose exec bot nginx -s reload

if [ $? -eq 0 ]; then
    echo "✅ Nginx reloaded successfully"
    echo "✅ SSL certificates updated"
else
    echo "❌ Failed to reload nginx"
    exit 1
fi

echo "Testing HTTPS connection..."
curl -I https://transcribe-to.work.gd/health

echo "SSL update completed."
