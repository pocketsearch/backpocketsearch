#!/bin/bash
# pocketSearch startup script for production deployments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}pocketSearch Startup Script${NC}"
echo "=================================="

# Check Python version
echo "Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo -e "Python version: ${YELLOW}${python_version}${NC}"

# Check for .env file
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please copy .env.example to .env and configure it:"
    echo "  cp .env.example .env"
    exit 1
fi

# Check for SECRET_KEY
if ! grep -q "^SECRET_KEY=" .env || grep "^SECRET_KEY=change-this" .env > /dev/null; then
    echo -e "${RED}Error: SECRET_KEY not configured!${NC}"
    echo "Generate a new key with:"
    echo "  python -c \"import secrets; print(secrets.token_hex(32))\""
    echo "Then update .env with the generated value"
    exit 1
fi

echo -e "${GREEN}✓${NC} .env configuration found"

# Create data directory if it doesn't exist
mkdir -p data
echo -e "${GREEN}✓${NC} Data directory ready"

# Install/upgrade dependencies
echo "Checking dependencies..."
pip install --quiet -r requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

# Initialize database
echo "Initializing database..."
python -c "from app import init_db; init_db(); print('✓ Database initialized')"

# Run the application
echo -e "${GREEN}✓${NC} Starting application..."
echo "Access the application at: http://localhost:5000"
echo ""
python app.py
