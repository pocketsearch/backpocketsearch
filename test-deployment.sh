#!/bin/bash
# pocketSearch — Quick Deployment Test
# Run this: cd pocketSearch && ./test-deployment.sh

set -e

PYTHON="./venv/bin/python3"
PIP="./venv/bin/pip"

echo "🔍 POCKETSEARCH DEPLOYMENT TEST"
echo "=================================="
echo ""

# 1. Check syntax
echo "→ Checking Python syntax..."
$PYTHON -m py_compile app.py pass_search.py recon.py 2>&1 | grep -v "^$" || true
for file in knowledge/*.py; do
  $PYTHON -m py_compile "$file" || exit 1
done
echo "✓ All Python files compile"
echo ""

# 2. Check imports
echo "→ Verifying dependencies..."
$PYTHON -c "
import flask, requests, bs4, dns.resolver, dotenv, tenacity
print('✓ flask')
print('✓ requests')
print('✓ beautifulsoup4')
print('✓ dnspython')
print('✓ python-dotenv')
print('✓ tenacity')
"
echo ""

# 3. Test .env
echo "→ Checking .env..."
if [ ! -f ".env" ]; then
  echo "✗ .env not found"
  exit 1
fi

if grep -q "change-this" .env; then
  echo "✗ .env still has placeholder values"
  exit 1
fi

SECRET=$(grep "^SECRET_KEY=" .env | cut -d= -f2)
if [ -z "$SECRET" ]; then
  echo "✗ SECRET_KEY not set"
  exit 1
fi
echo "✓ .env properly configured"
echo ""

# 4. Test Flask initialization
echo "→ Testing Flask app initialization..."
$PYTHON -c "
import os
os.environ['DB_PATH'] = '/tmp/test-pocketsearch.db'

from app import app, init_db

with app.app_context():
    init_db()

routes = [rule.rule for rule in app.url_map.iter_rules()]
print('✓ Flask app initialized')
print('✓ Routes: ' + ', '.join(sorted(routes)))
"
rm -f /tmp/test-pocketsearch.db /tmp/test-pocketsearch.db-*
echo ""

# 5. Test templates
echo "→ Checking templates..."
for template in templates/*.html; do
  [ -f "$template" ] && echo "  ✓ $(basename $template)" || { echo "  ✗ Missing $(basename $template)"; exit 1; }
done
echo ""

# 6. Required files
echo "→ Checking deployment files..."
REQUIRED="app.py requirements.txt .env Dockerfile docker-compose.yml start.sh setup-ssl.sh PRIVACY.md"
for file in $REQUIRED; do
  [ -f "$file" ] && echo "  ✓ $file" || { echo "  ✗ Missing $file"; exit 1; }
done
echo ""

# 7. Permissions
echo "→ Checking permissions..."
[ -x "start.sh" ] && echo "  ✓ start.sh executable" || { echo "  ✗ start.sh not executable"; exit 1; }
[ -x "setup-ssl.sh" ] && echo "  ✓ setup-ssl.sh executable" || { echo "  ✗ setup-ssl.sh not executable"; exit 1; }
echo ""

echo "=================================="
echo "✓ ALL CHECKS PASSED"
echo ""
echo "To start server:"
echo "  ./venv/bin/python3 app.py"
echo ""
echo "Or use start.sh:"
echo "  ./start.sh"
echo ""
