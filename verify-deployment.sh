#!/bin/bash
# pocketSearch — Comprehensive Deployment Verification
# Runs all checks before production deployment

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() { echo -e "${GREEN}✓${NC} $1"; }
log_fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
log_info() { echo -e "${YELLOW}→${NC} $1"; }

cd "$(dirname "$0")"

log_info "POCKETSEARCH DEPLOYMENT VERIFICATION"
echo "======================================"
echo ""

# 1. Python version
log_info "Checking Python version..."
PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
if [[ "$PYTHON_VER" == 3.* ]]; then
  log_pass "Python $PYTHON_VER"
else
  log_fail "Python 3 required (found: $PYTHON_VER)"
fi

# 2. Dependencies
log_info "Checking dependencies..."
MISSING=0
for pkg in flask requests bs4 dnspython python-dotenv tenacity; do
  python3 -c "import ${pkg}" 2>/dev/null && log_pass "$pkg" || { log_fail "$pkg not installed"; MISSING=1; }
done

# 3. Syntax
log_info "Checking Python syntax..."
for file in app.py pass_search.py recon.py; do
  python3 -m py_compile "$file" 2>/dev/null && log_pass "$file" || log_fail "$file has syntax errors"
done

for file in knowledge/*.py; do
  python3 -m py_compile "$file" 2>/dev/null || log_fail "$file has syntax errors"
done
log_pass "All knowledge modules"

# 4. .env configuration
log_info "Checking .env configuration..."
if [ ! -f ".env" ]; then
  log_fail ".env file not found"
fi

if grep -q "change-this" .env; then
  log_fail ".env contains placeholder values"
fi

log_pass ".env properly configured"

# 5. Required files
log_info "Checking required files..."
REQUIRED_FILES=(
  "app.py"
  "pass_search.py"
  "recon.py"
  "requirements.txt"
  ".env"
  "templates/index.html"
  "templates/base.html"
  "templates/error.html"
  "Dockerfile"
  "docker-compose.yml"
  "start.sh"
  "setup-ssl.sh"
  "PRIVACY.md"
  "DEPLOYMENT.md"
)

for file in "${REQUIRED_FILES[@]}"; do
  [ -f "$file" ] && log_pass "$file" || log_fail "Missing: $file"
done

# 6. SSL certificates
log_info "Checking SSL certificates..."
if [ -f "cert.pem" ] && [ -f "key.pem" ]; then
  log_pass "Self-signed certificates present"
else
  log_info "No SSL certificates (will use HTTP or generate on first run)"
fi

# 7. Database initialization
log_info "Testing database initialization..."
export FLASK_ENV=testing
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Minimal test
python3 -c "
import os
import sys
os.environ['DB_PATH'] = '/tmp/test-pocketsearch.db'
os.environ['SECRET_KEY'] = '$SECRET_KEY'
os.environ['FLASK_ENV'] = 'testing'

from app import app, init_db
with app.app_context():
  init_db()
print('Database initialized')
" && log_pass "Database initialization" || log_fail "Database init failed"

rm -f /tmp/test-pocketsearch.db

# 8. Flask routes
log_info "Checking Flask routes..."
python3 -c "
import os
os.environ['SECRET_KEY'] = '$SECRET_KEY'
os.environ['FLASK_ENV'] = 'testing'

from app import app

routes = [rule.rule for rule in app.url_map.iter_rules()]
required_routes = ['/', '/go', '/privacy', '/results']

for route in required_routes:
  if route in routes:
    print(f'✓ {route}')
  else:
    print(f'✗ {route} missing')
    sys.exit(1)
" && log_pass "All required routes registered" || log_fail "Missing routes"

# 9. Templates
log_info "Checking templates..."
for template in templates/*.html; do
  [ -f "$template" ] && log_pass "$(basename $template)" || log_fail "Missing template"
done

# 10. Docker setup
log_info "Checking Docker configuration..."
if command -v docker &> /dev/null; then
  [ -f "Dockerfile" ] && log_pass "Dockerfile present" || log_fail "Dockerfile missing"
  [ -f "docker-compose.yml" ] && log_pass "docker-compose.yml present" || log_fail "docker-compose.yml missing"
  docker build -t pocketsearch-test . > /tmp/docker-build.log 2>&1 && log_pass "Docker image builds" || {
    log_fail "Docker build failed (see /tmp/docker-build.log)"
  }
  docker rmi pocketsearch-test > /dev/null 2>&1
else
  log_info "Docker not installed (optional for non-containerized deployment)"
fi

# 11. Port availability
log_info "Checking ports..."
PORT=5000
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
  log_info "Port $PORT already in use (app may be running)"
else
  log_pass "Port $PORT available"
fi

# 12. Permissions
log_info "Checking file permissions..."
[ -x "start.sh" ] && log_pass "start.sh executable" || log_fail "start.sh not executable"
[ -x "setup-ssl.sh" ] && log_pass "setup-ssl.sh executable" || log_fail "setup-ssl.sh not executable"

# 13. Documentation
log_info "Checking documentation..."
[ -f "DEPLOYMENT.md" ] && log_pass "DEPLOYMENT.md" || log_fail "DEPLOYMENT.md missing"
[ -f "PRODUCTION_READY.md" ] && log_pass "PRODUCTION_READY.md" || log_fail "PRODUCTION_READY.md missing"
[ -f "PRIVACY.md" ] && log_pass "PRIVACY.md" || log_fail "PRIVACY.md missing"

echo ""
echo "======================================"
log_pass "ALL CHECKS PASSED - READY FOR DEPLOYMENT"
echo ""
echo "Next steps:"
echo "  1. Review .env configuration"
echo "  2. Start server: ./start.sh"
echo "  3. Visit: http://localhost:5000 (or https://localhost:5000 for SSL)"
echo "  4. Run tests in browser or via curl"
echo "  5. For production: Follow DEPLOYMENT.md"
echo ""
