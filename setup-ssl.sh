#!/bin/bash
# pocketSearch — SSL/TLS Setup Script
# Usage: ./setup-ssl.sh yourdomain.com

set -e

DOMAIN="${1:-yourdomain.com}"
EMAIL="${2:-admin@$DOMAIN}"

if [ -z "$DOMAIN" ]; then
  echo "Usage: $0 <domain> [email]"
  exit 1
fi

echo "Setting up SSL for $DOMAIN..."

# 1. Check if certbot available
if ! command -v certbot &> /dev/null; then
  echo "Installing certbot..."
  apt-get update && apt-get install -y certbot python3-certbot-nginx
fi

# 2. Get certificate
echo "Requesting Let's Encrypt certificate..."
certbot certonly --standalone --non-interactive --agree-tos -m "$EMAIL" -d "$DOMAIN" || {
  echo "Certificate generation failed. Manual steps:"
  echo "  1. Verify domain DNS points to this server"
  echo "  2. Ensure port 443 is open"
  echo "  3. Run: certbot certonly --standalone -d $DOMAIN"
  exit 1
}

CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

echo "✓ Certificate created: $CERT_PATH"

# 3. Create Nginx config
cat > /tmp/pocketsearch-nginx.conf <<EOF
upstream pocketsearch {
  server 127.0.0.1:5000;
}

# Redirect HTTP to HTTPS
server {
  listen 80;
  listen [::]:80;
  server_name $DOMAIN www.$DOMAIN;
  return 301 https://\$host\$request_uri;
}

# HTTPS
server {
  listen 443 ssl http2;
  listen [::]:443 ssl http2;
  server_name $DOMAIN www.$DOMAIN;

  # Certificates
  ssl_certificate $CERT_PATH;
  ssl_certificate_key $KEY_PATH;

  # Modern config (A+ rating)
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers HIGH:!aNULL:!MD5;
  ssl_prefer_server_ciphers on;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 10m;

  # HSTS (tell browsers: always HTTPS)
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-Frame-Options "SAMEORIGIN" always;

  client_max_body_size 5M;

  location / {
    proxy_pass http://pocketsearch;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_read_timeout 60s;
  }
}
EOF

echo "✓ Nginx config created: /tmp/pocketsearch-nginx.conf"
echo ""
echo "NEXT STEPS:"
echo "1. Copy config to Nginx:"
echo "   sudo cp /tmp/pocketsearch-nginx.conf /etc/nginx/sites-available/pocketsearch"
echo "   sudo ln -s /etc/nginx/sites-available/pocketsearch /etc/nginx/sites-enabled/"
echo "2. Test: sudo nginx -t"
echo "3. Reload: sudo systemctl reload nginx"
echo "4. Start pocketSearch backend: docker-compose up -d (or ./start.sh)"
echo "5. Visit: https://$DOMAIN"
echo ""
echo "Auto-renewal:"
echo "  certbot renew --dry-run  (test)"
echo "  (Runs via cron automatically)"
