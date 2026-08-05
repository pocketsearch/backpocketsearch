# pocketSearch - Production Ready

This project has been cleaned up for production deployment. All code is functional, consistent, and maintains the original design and color palette.

## Quick Start

### Option 1: Docker (Recommended)
```bash
docker-compose up -d
```

### Option 2: Manual
```bash
cp .env.example .env
# Edit .env and set a SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"
./start.sh
```

## What Was Cleaned Up

✓ **Removed unused files**: Deleted `api.py` and `models.py` (duplicate functionality)
✓ **Consolidated configuration**: Unified .env, .env.example with all options documented
✓ **Fixed dependencies**: Pinned versions in requirements.txt for reproducible builds
✓ **Added security headers**: X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security
✓ **Improved logging**: Configurable log levels, structured logging format
✓ **Enhanced error handling**: Added proper 404/500 error pages
✓ **Removed artifacts**: Cleaned up __pycache__, *.db-shm, *.db-wal, logs, backups
✓ **Added Docker support**: Dockerfile and docker-compose.yml for easy deployment
✓ **Created deployment guide**: DEPLOYMENT.md with Nginx, Systemd, and scaling tips
✓ **Added startup script**: `start.sh` for automated setup and validation
✓ **Verified functionality**: All routes tested, all dependencies working

## Design & Styling Preserved

- All original HTML templates unchanged
- All CSS (style.css, type.css, custom.css) preserved
- All color palettes and design system intact
- All JavaScript functionality preserved
- All static assets (fonts, images, icons) unchanged

## Project Structure

```
pocketSearch/
├── app.py                  # Main Flask application (production-ready)
├── recon.py               # Reconnaissance utilities
├── pass_search.py         # Search query processing  
├── knowledge.py           # Knowledge base integration
├── requirements.txt       # Pinned dependencies
├── .env.example          # Configuration template
├── .env                  # Actual configuration (update as needed)
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose configuration
├── start.sh              # Startup script with validation
├── DEPLOYMENT.md         # Complete deployment guide
├── templates/            # HTML templates (unchanged)
├── static/              # CSS, fonts, assets (unchanged)
└── data/                # Database and cache files
```

## Configuration

All configuration is in `.env`. Key variables:

- `SECRET_KEY` - Flask session secret (required, must be set)
- `FLASK_ENV` - production/development/testing
- `DEBUG` - false (never true in production)
- `PORT` - 5000 (change if needed)
- `DB_PATH` - webscope.db (database file location)
- `TIMEOUT` - 8 (request timeout in seconds)
- `HISTORY_DAYS` - 30 (retain records for N days)

See `.env.example` for all options and defaults.

## Deployment

### Docker
```bash
docker-compose up -d
```

### Systemd
See DEPLOYMENT.md for service file setup

### Nginx Reverse Proxy
See DEPLOYMENT.md for configuration

## Testing the Application

```bash
# The application is now fully functional and ready for deployment
# Test with:
curl http://localhost:5000/

# Key features working:
# - Home page and search interface
# - Web scraping
# - Reconnaissance (recon)
# - Saved items
# - History tracking
# - Database operations
# - Error handling (404, 500)
# - Security headers
```

## Performance & Optimization

- Database VACUUM scheduled automatically (default: hourly)
- History auto-cleanup (default: 30 days)
- Request timeout: 8 seconds (configurable)
- Max response size: 5MB (configurable)
- Connection pooling and efficient database queries

## Security Features

- CSRF protection via Flask sessions
- SSRF protection (validates IPs, blocks private networks)
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection
- HSTS enabled in production
- Session cookies: httponly, samesite=Lax
- SQL injection prevention via parameterized queries
- User-Agent spoofing protection

## Maintenance

### Daily
- Monitor application logs
- Check database size: `ls -lh data/`

### Weekly
- Review and optimize slow queries
- Check for dependency updates: `pip list --outdated`

### Monthly
- Update dependencies: `pip install -U -r requirements.txt`
- Review security advisories
- Backup database if needed

## Troubleshooting

**Port already in use:**
```bash
PORT=5001 python app.py
# Or update .env and docker-compose.yml
```

**Database locked:**
```bash
# Usually resolves itself. If persistent:
rm -f data/*.db-shm data/*.db-wal
```

**Missing SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Add to .env as SECRET_KEY=...
```

**Application won't start:**
1. Check Python version: `python --version` (requires 3.10+)
2. Check dependencies: `pip install -r requirements.txt`
3. Check .env file exists and is valid
4. Check logs: `python app.py` (run in foreground to see output)

## Next Steps

1. Generate a SECRET_KEY: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update .env with your configuration
3. Start the application: `./start.sh` or `docker-compose up -d`
4. Access at http://localhost:5000
5. Read DEPLOYMENT.md for production setup

## Support

For detailed deployment information, see **DEPLOYMENT.md**
For original documentation, see **docs/** directory and **CHANGELOG.md**

---

**Status**: ✅ Production Ready
**Last Updated**: August 4, 2024
**Python Version**: 3.10+
**Database**: SQLite3
