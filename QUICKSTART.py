#!/usr/bin/env python
"""
pocketSearch Quick Start - Copy/paste commands for deployment
"""

DOCKER_QUICK_START = """
# Docker (Recommended - Easiest)
cd pocketSearch
docker-compose up -d
# Access: http://localhost:5000
# View logs: docker-compose logs -f
# Stop: docker-compose down
"""

MANUAL_QUICK_START = """
# Manual Installation
cd pocketSearch
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
pip install -r requirements.txt
./start.sh
"""

GENERATE_SECRET_KEY = """
# Generate SECRET_KEY (required!)
python -c "import secrets; print(secrets.token_hex(32))"
# Then add to .env:
# SECRET_KEY=<generated-value>
"""

VERIFY_SETUP = """
# Verify Everything Works
python -c "
from app import app, get_db, init_db
print('✓ App initialized')
init_db()
print('✓ Database ready')
print('✓ All checks passed - ready to deploy!')
"
"""

TEST_ENDPOINTS = """
# Test Key Endpoints
curl http://localhost:5000/              # Home page
curl http://localhost:5000/history       # History page
curl http://localhost:5000/workspace     # Workspace
curl http://localhost:5000/saved         # Saved items
"""

SYSTEMD_SETUP = """
# See DEPLOYMENT.md for complete setup
# Quick summary:
# 1. Create /etc/systemd/system/pocketsearch.service (see DEPLOYMENT.md)
# 2. systemctl daemon-reload
# 3. systemctl enable pocketsearch
# 4. systemctl start pocketsearch
"""

TROUBLESHOOTING = """
# Common Issues

# Port 5000 already in use?
PORT=5001 ./start.sh

# Database locked?
rm -f *.db-shm *.db-wal

# Python dependencies missing?
pip install -r requirements.txt

# Missing SECRET_KEY?
# Run: python -c "import secrets; print(secrets.token_hex(32))"
# Add to .env

# Not loading styling?
# Check static/ folder exists with CSS files
# Verify templates/ folder with HTML files
"""

if __name__ == "__main__":
    print("=" * 70)
    print("pocketSearch - QUICK START GUIDE")
    print("=" * 70)
    print()
    
    print("🚀 OPTION 1: Docker (Recommended)")
    print("-" * 70)
    print(DOCKER_QUICK_START)
    
    print("🚀 OPTION 2: Manual Installation")
    print("-" * 70)
    print(MANUAL_QUICK_START)
    
    print("🔑 REQUIRED: Generate SECRET_KEY")
    print("-" * 70)
    print(GENERATE_SECRET_KEY)
    
    print("✅ VERIFY Setup")
    print("-" * 70)
    print(VERIFY_SETUP)
    
    print("🧪 TEST Endpoints")
    print("-" * 70)
    print(TEST_ENDPOINTS)
    
    print("📋 MORE INFO")
    print("-" * 70)
    print("• Deployment: See DEPLOYMENT.md")
    print("• Docker: See docker-compose.yml")
    print("• Configuration: See .env.example")
    print("• Cleanup: See PRODUCTION_READY.md")
    print("• Details: See CLEANUP_SUMMARY.md")
    print()
