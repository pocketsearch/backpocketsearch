import ipaddress
import json
import logging
import os
import re
import sqlite3
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, flash, g, session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import recon as reconlib
import knowledge as knowledgelib
import ipstack as ipstacklib
import assistant as assistantlib
from pass_search import classify_intent, run_search
from knowledge import record_search, get_recommendations, auto_tag, rank_results, rewrite_query, get_recent_queries

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
app.config["ENV"] = os.environ.get("FLASK_ENV", "production")
app.config["TESTING"] = app.config["ENV"] == "testing"

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable must be set. "
        "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
    )
app.secret_key = secret_key

DB_PATH = os.environ.get("DB_PATH", "webscope.db")
UA = "Mozilla/5.0 (compatible; WebScope/1.0)"
TIMEOUT = int(os.environ.get("TIMEOUT", "8"))
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(5 * 1024 * 1024)))
RECON_CACHE_TTL = timedelta(hours=int(os.environ.get("RECON_CACHE_HOURS", "24")))
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
PREFERRED_DOMAIN = os.environ.get("PREFERRED_DOMAIN", "kitpocket.it.com")

logger = logging.getLogger("webscope")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
log_level = os.environ.get("LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")
logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
logging.getLogger("werkzeug").setLevel(logging.WARNING)

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(ip_str):
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return True


def _resolve_and_validate(hostname):
    try:
        info = socket.getaddrinfo(hostname, None)
        for fam, _, _, _, sockaddr in info:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                logger.warning("Blocked SSRF to private/reserved IP: %s -> %s", hostname, ip)
                raise ValueError(f"Target resolves to private/reserved IP: {ip}")
    except socket.gaierror as e:
        logger.warning("DNS resolution failed for %s: %s", hostname, e)
        raise ValueError(f"Cannot resolve host: {hostname}") from e


def safe_get(url, **kwargs):
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")
    _resolve_and_validate(hostname)
    kwargs.setdefault("headers", {})
    kwargs["headers"]["User-Agent"] = UA
    kwargs.setdefault("timeout", TIMEOUT)
    kwargs.setdefault("stream", True)
    return requests.get(url, **kwargs)


# ---------------------------------------------------------------------------
# Assistant routes
# ---------------------------------------------------------------------------

@app.route("/assistant", methods=["GET", "POST"])
def assistant():
    """Simple chat interface powered by Groq."""
    enabled = assistantlib.is_enabled()
    answer = None
    error = None
    user_query = ""

    if request.method == "POST":
        user_query = (request.form.get("query") or "").strip()
        if not user_query:
            error = "Please enter a question."
        elif not enabled:
            error = "Assistant is not configured. Set GROQ_API_KEY to enable it."
        else:
            try:
                answer = assistantlib.get_response(user_query)
            except assistantlib.AssistantDisabledError:
                error = "Assistant is not configured. Set GROQ_API_KEY to enable it."
            except Exception as exc:  # noqa: BLE001
                logger.error("Assistant error: %s", exc)
                error = "Assistant request failed. Please try again later."

    return render_template(
        "assistant.html",
        enabled=enabled,
        answer=answer,
        error=error,
        user_query=user_query,
    )
