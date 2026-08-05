# Privacy Policy

**pocketSearch** — Last Updated: August 5, 2026

---

## Overview

pocketSearch is a self-hosted search and reconnaissance tool. This privacy policy describes how data is handled when you operate this application.

## Data Collection

### What We Collect
- **Search queries**: Text entered into the search interface
- **Scrape requests**: URLs you request to scrape
- **Reconnaissance data**: Domains, IP addresses, or targets you investigate
- **Metadata**: Response times, HTTP status codes, result counts

### What We Do NOT Collect
- User identity, email, or personal information (unless you provide it)
- Browser cookies or tracking identifiers
- Third-party analytics or telemetry
- Location data
- Device fingerprints

## Data Storage

All data is stored **locally in your instance only**:
- Search history: SQLite database (`webscope.db`)
- Cached knowledge: SQLite database (`knowledge_cache.db`)
- No data leaves your server unless you explicitly query external sources

### Data Retention

- **Search records**: Retained for 30 days by default (configurable via `HISTORY_DAYS` environment variable)
- **Scrape results**: Same 30-day retention, then auto-deleted
- **Recon data**: Same 30-day retention, then auto-deleted
- **Manual cleanup**: Delete via `/history` interface anytime

## External Requests

pocketSearch may make requests to external services for:
- **DNS queries**: Resolve domain names
- **WHOIS lookups**: Query domain registration data
- **Web scraping**: Fetch and parse content from URLs you specify
- **Search APIs**: Query public search indexes (if configured)

**You control all external requests.** No data is sent automatically without your explicit search action.

## Third-Party Services

pocketSearch can integrate with optional third-party APIs:
- OpenAlex (requires email, configured in `.env`)
- Public DNS services
- Any API you configure

**You must explicitly configure** any third-party integration. Defaults use only local processing.

## Security

- **No authentication** by default (self-hosted = you control access)
- **HTTPS recommended** for production (configure via reverse proxy: Nginx, Caddy, etc.)
- **Database encryption**: Not built-in (use full-disk encryption on your server)
- **Secrets management**: Store API keys in `.env` (excluded from git)

## User Rights

You have full control:
- **Access**: View all stored data via the interface
- **Correction**: Edit or delete saved items
- **Deletion**: Clear history, purge databases anytime
- **Portability**: Export search results as JSON via API

## Children's Privacy

pocketSearch is a technical tool intended for adult users. If you're under 18, get parental permission before use.

## Changes to This Policy

We may update this policy. Changes take effect immediately upon posting here. Your continued use constitutes acceptance.

## Contact

pocketSearch is self-hosted. For questions about this policy or your instance, contact your system administrator.

---

## Self-Hosted Exception

Since this runs on **your infrastructure**:
- You are responsible for complying with data protection laws (GDPR, CCPA, etc.) in your jurisdiction
- You are the data controller — ensure users of your instance consent to data practices
- Review your deployment security and retention policies regularly
- This policy is a template; customize for your organization's needs

---

**pocketSearch Privacy Policy** — Open-source, self-hosted, privacy-first search tool.
