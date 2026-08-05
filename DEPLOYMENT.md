# pocketSearch

A powerful web search and reconnaissance tool with persistent storage and intelligent result ranking.

## Features

- **Web Scraping**: Extract and analyze website content with structured metadata
- **Advanced Search**: Intelligent query parsing with source-specific optimizations
- **Reconnaissance**: Domain analysis with header inspection and metadata extraction
- **Saved Items**: Bookmark and organize search results with notes
- **Workspace**: Visual workspace for managing multiple searches
- **History**: Track all searches, scrapes, and reconnaissance with retention policies
- **Database Optimization**: Automatic VACUUM scheduling and history cleanup

## Requirements

- Python 3.10+
- SQLite3
- Modern web browser

## Installation

### Using Docker (Recommended for Production)

```bash
# Clone or download the repository
cd pocketSearch

# Generate a SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Create a .env file with at minimum:
echo "SECRET_KEY=<generated-key-from-above>" > .env

# Start the application
docker-compose up -d

# Access at http://localhost:5000
```

### Manual Installation

```bash
# Clone or download the repository
cd pocketSearch

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Generate a SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Create .env file
cp .env.example .env
# Edit .env and add your SECRET_KEY

# Run the application
python app.py
```

Access the application at `http://localhost:5000` (or your configured HOST:PORT)

## Configuration

All configuration is done through environment variables. See `.env.example` for all available options:

| Variable | Default | Description |
|----------|---------|-------------|
| SECRET_KEY | *required* | Flask session secret key (generate with: `python -c 'import secrets; print(secrets.token_hex(32))'`) |
| FLASK_ENV | production | Application environment (production, development, testing) |
| HOST | 0.0.0.0 | Server listen address |
| PORT | 5000 | Server listen port |
| DEBUG | false | Enable Flask debug mode (never in production) |
| LOG_LEVEL | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| DB_PATH | webscope.db | Database file path |
| TIMEOUT | 8 | Request timeout in seconds |
| MAX_BODY_BYTES | 5242880 | Maximum response body size (5MB) |
| RECON_CACHE_HOURS | 24 | Recon result cache TTL |
| HISTORY_DAYS | 30 | Retain history records for N days |
| VACUUM_INTERVAL_HOURS | 1 | Database VACUUM optimization interval |

## Project Structure

```
pocketSearch/
├── app.py                 # Main Flask application
├── recon.py              # Reconnaissance utilities
├── pass_search.py        # Search query processing
├── knowledge.py          # Knowledge base integration
├── templates/            # HTML templates (Jinja2)
├── static/              # CSS, JavaScript, assets
├── data/                # Data directory (databases, cache)
├── Dockerfile           # Docker image definition
├── docker-compose.yml   # Docker Compose configuration
├── requirements.txt     # Python dependencies
└── .env.example        # Environment configuration template
```

## Routes

### Main Routes

- `GET /` - Home page
- `POST /search` - Perform a search
- `GET /result/<id>` - View search result
- `POST /scrape` - Scrape a URL
- `GET /scrape/<id>` - View scrape result
- `POST /recon` - Run reconnaissance on a domain
- `GET /recon/<id>` - View recon result
- `GET /history` - View search history
- `POST /save` - Save an item
- `GET /saved` - View saved items
- `GET /workspace` - Visual workspace

### API Routes

- `GET /api/search/suggestions?q=query` - Get search suggestions
- `POST /theme` - Toggle theme (light/dark)

## Deployment

### Systemd Service

Create `/etc/systemd/system/pocketsearch.service`:

```ini
[Unit]
Description=pocketSearch Web Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/pocketsearch
Environment="PATH=/var/www/pocketsearch/venv/bin"
ExecStart=/var/www/pocketsearch/venv/bin/python app.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable pocketsearch
sudo systemctl start pocketsearch
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name pocketsearch.example.com;
    client_max_body_size 5M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest flask-testing

# Run tests
pytest tests/
```

### Code Quality

```bash
# Lint with flake8
pip install flake8
flake8 app.py recon.py pass_search.py

# Format with black
pip install black
black app.py recon.py pass_search.py
```

## Security Notes

1. **Always** set a strong SECRET_KEY in production
2. **Never** run with DEBUG=true in production
3. Use HTTPS/TLS in production (via Nginx/Caddy)
4. Regularly update dependencies: `pip install -U -r requirements.txt`
5. Monitor database size and adjust VACUUM_INTERVAL_HOURS as needed
6. Set HISTORY_DAYS to limit data retention per your policy

## Performance Tuning

- Adjust TIMEOUT for slower networks (increase from 8)
- Increase MAX_BODY_BYTES for large responses
- Tune VACUUM_INTERVAL_HOURS based on database growth
- Monitor database size: `ls -lh *.db`

## Troubleshooting

### Port already in use
```bash
# Change PORT in .env or Docker config
PORT=5001 python app.py
```

### Database locked
```bash
# This usually resolves itself. If persistent:
rm -f *.db-shm *.db-wal
```

### Memory issues
Reduce MAX_BODY_BYTES or increase system memory allocation

### Slow performance
Check database size and adjust HISTORY_DAYS to clean older records

## License

See LICENSE file for details

## Support

For issues and questions, check the docs/ directory or review the application logs.
