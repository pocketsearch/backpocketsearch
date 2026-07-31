import ipaddress
import json
import logging
import os
import re
import sqlite3
import socket
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, flash, g, session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import recon as reconlib
import knowledge as knowledgelib
from knowledge import record_search, get_recommendations, auto_tag, rank_results, rewrite_query, get_recent_queries

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
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
logger.setLevel(logging.INFO)

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


URL_PATTERN = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+'
    r'(:\d+)?(/.*)?$'
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrapes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            title TEXT,
            description TEXT,
            status_code INTEGER,
            response_ms INTEGER,
            word_count INTEGER,
            link_count INTEGER,
            image_count INTEGER,
            headings TEXT,
            links TEXT,
            images TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            result_count INTEGER,
            response_ms INTEGER,
            results TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            data TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            item_json TEXT NOT NULL,
            note TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


_db_initialized = False

@app.before_request
def _ensure_db():
    global _db_initialized
    if not _db_initialized:
        init_db()
        _vacuum_if_needed()
        _db_initialized = True


# Workspace route (frontend only). Preserves all backend behavior; renders a visual workspace.
@app.route('/workspace')
def workspace():
    # For now, show saved items as workspace tiles if available
    db = get_db()
    cur = db.execute('SELECT id, query, item_json, created_at FROM saved_items ORDER BY created_at DESC LIMIT 50')
    rows = [dict(r) for r in cur.fetchall()]
    # parse item_json safely
    for r in rows:
        try:
            r['item'] = json.loads(r['item_json'])
        except Exception:
            r['item'] = {}
    return render_template('workspace.html', items=rows)


def _vacuum_if_needed():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT COUNT(*) FROM scrapes")
        scrapes = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM searches")
        searches = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM recons")
        recons = cur.fetchone()[0]
        total = scrapes + searches + recons
        if total > 5000:
            logger.info("Running VACUUM on %s (rows=%d)", DB_PATH, total)
            conn.execute("VACUUM")
            conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Vacuum check failed: %s", e)


def looks_like_url(raw):
    raw = raw.strip()
    if not raw or " " in raw:
        return False
    if raw.startswith(("http://", "https://")):
        return True
    if raw.startswith("localhost") and (raw == "localhost" or raw[9:10] in (":", "/")):
        return True
    if raw.startswith("[") and "]" in raw:
        return True
    return bool(URL_PATTERN.match(raw))


def normalize_url(raw):
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        return None
    return raw


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)
def _stream_body(resp):
    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                logger.warning("Response body capped at %d bytes for %s", MAX_BODY_BYTES, resp.url)
                break
            chunks.append(chunk)
    return b"".join(chunks)


def scrape(url):
    start = time.time()
    resp = safe_get(url)
    elapsed_ms = int((time.time() - start) * 1000)
    body = _stream_body(resp)
    text = body.decode(resp.encoding or "utf-8", errors="replace")
    resp.close()

    soup = BeautifulSoup(text, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

    headings = []
    for level in ("h1", "h2", "h3"):
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                headings.append(f"{level.upper()}: {text}")

    links = []
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if href not in seen_links:
            seen_links.add(href)
            links.append(href)

    images = []
    seen_images = set()
    for img in soup.find_all("img", src=True):
        src = urljoin(url, img["src"])
        if src not in seen_images:
            seen_images.add(src)
            images.append(src)

    body_text = soup.get_text(separator=" ", strip=True)
    word_count = len(body_text.split())

    return {
        "url": url,
        "title": title,
        "description": description,
        "status_code": resp.status_code,
        "response_ms": elapsed_ms,
        "word_count": word_count,
        "link_count": len(links),
        "image_count": len(images),
        "headings": headings[:50],
        "links": links[:100],
        "images": images[:50],
    }


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)
def web_search(query, max_results=15):
    """Real search results from DuckDuckGo's HTML endpoint. No API key, no mock data."""
    start = time.time()
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    elapsed_ms = int((time.time() - start) * 1000)
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for block in soup.select(".result"):
        a = block.select_one(".result__a")
        if not a or not a.get("href"):
            continue

        href = a["href"]
        real_url = href
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            if "uddg" in qs:
                real_url = qs["uddg"][0]
        elif href.startswith("//"):
            real_url = "https:" + href

        title = a.get_text(strip=True)
        snippet_tag = block.select_one(".result__snippet")
        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

        if title and real_url:
            results.append({"title": title, "url": real_url, "snippet": snippet})
        if len(results) >= max_results:
            break

    return results, elapsed_ms


@app.route("/")
def index():
    recommendations = get_recommendations(limit=6)
    recent = get_recent_queries(limit=5)
    return render_template("index.html", recommendations=recommendations, recent_queries=recent)


@app.route("/go", methods=["POST"])
def go():
    raw = request.form.get("query", "")
    if not raw.strip():
        flash("Type a URL or a search query.")
        return redirect(url_for("index"))

    if looks_like_url(raw):
        url = normalize_url(raw)
        if not url:
            flash("That doesn't look like a valid URL.")
            return redirect(url_for("index"))
        try:
            data = scrape(url)
        except requests.exceptions.RequestException as e:
            flash(f"Could not fetch that URL: {e}")
            return redirect(url_for("index"))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("index"))

        db = get_db()
        cur = db.execute(
            """INSERT INTO scrapes
               (url, title, description, status_code, response_ms, word_count,
                link_count, image_count, headings, links, images, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["url"], data["title"], data["description"], data["status_code"],
                data["response_ms"], data["word_count"], data["link_count"],
                data["image_count"], "\n".join(data["headings"]), "\n".join(data["links"]),
                "\n".join(data["images"]), datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        db.commit()
        return redirect(url_for("result", scrape_id=cur.lastrowid))

    query = raw.strip()
    record_search(query)
    knowledgelib._interest_learner.record_from_query(query)
    rewritten_query = rewrite_query(query)

    web_results = []
    web_ms = 0
    try:
        web_results, web_ms = web_search(rewritten_query)
    except requests.exceptions.RequestException as e:
        logger.warning("Web search failed for %r: %s", rewritten_query, e)

    enriched_data = knowledgelib.enrich_query(rewritten_query)
    enriched = enriched_data.get("results", [])
    analysis = enriched_data.get("analysis", {})
    enriched_map = {item["url"]: item for item in enriched if item.get("url")}

    web_map = {item["url"]: item for item in web_results if item.get("url")}
    seen = set()
    merged = []

    for item in enriched:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            merged.append(item)

    for item in web_results:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            merged.append(item)

    merged = rank_results(merged, rewritten_query)

    knowledgelib._knowledge_graph.link_query_entities(query)
    knowledgelib._auto_collections.build_collections()

    # Never allow empty results — fallback is already injected by enrich_query,
    # but if somehow merged is still empty, synthesize a final fallback.
    if not merged:
        merged = [{
            "source": "WebScope",
            "type": "fallback",
            "title": f'No direct results for "{query}"',
            "url": f"https://www.google.com/search?q={quote_plus(query)}",
            "snippet": "Try broadening your query or checking spelling. External knowledge sources may be temporarily unavailable.",
            "meta": "fallback",
        }]

    total_ms = web_ms

    db = get_db()
    cur = db.execute(
        "INSERT INTO searches (query, result_count, response_ms, results, created_at) VALUES (?,?,?,?,?)",
        (query, len(merged), total_ms, json.dumps(merged),
         datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()
    session["last_analysis"] = analysis
    session.modified = True
    return redirect(url_for("search_result", search_id=cur.lastrowid))


@app.route("/result/<int:scrape_id>")
def result(scrape_id):
    db = get_db()
    row = db.execute("SELECT * FROM scrapes WHERE id = ?", (scrape_id,)).fetchone()
    if row is None:
        flash("That result doesn't exist.")
        return redirect(url_for("index"))
    record = dict(row)
    record["headings"] = [h for h in record["headings"].split("\n") if h]
    record["links"] = [l for l in record["links"].split("\n") if l]
    record["images"] = [i for i in record["images"].split("\n") if i]
    return render_template("result.html", r=record)


@app.route("/search/<int:search_id>")
def search_result(search_id):
    db = get_db()
    row = db.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
    if row is None:
        flash("That search doesn't exist.")
        return redirect(url_for("index"))
    record = dict(row)
    results = json.loads(record["results"])

    grouped = {}
    order = []
    for item in results:
        src = item.get("source", "Other")
        if src not in grouped:
            grouped[src] = []
            order.append(src)
        grouped[src].append(item)

    record["results"] = results
    record["grouped"] = grouped
    record["group_order"] = order

    analysis = {}
    analysis_param = request.args.get("analysis")
    if analysis_param:
        try:
            analysis = json.loads(analysis_param)
        except Exception:
            pass
    if not analysis:
        analysis = session.get("last_analysis", {})
    record["analysis"] = analysis

    saved_count = 0
    try:
        saved_count = get_db().execute("SELECT COUNT(*) FROM saved_items").fetchone()[0]
    except Exception:
        pass
    record["saved_count"] = saved_count
    return render_template("search.html", s=record)


@app.route("/recon", methods=["POST"])
def recon():
    raw = request.form.get("target", "")
    if not raw.strip():
        flash("Enter a domain or URL for recon.")
        return redirect(url_for("index"))

    domain = reconlib.domain_from_url(raw)
    if not domain or "." not in domain:
        flash("That doesn't look like a valid domain.")
        return redirect(url_for("index"))

    url = raw.strip() if raw.strip().startswith(("http://", "https://")) else f"https://{domain}"

    db = get_db()
    now = datetime.utcnow()
    row = db.execute(
        "SELECT id, data, created_at FROM recons WHERE domain = ? ORDER BY id DESC LIMIT 1",
        (domain,),
    ).fetchone()
    if row and now - datetime.fromisoformat(row["created_at"]) < RECON_CACHE_TTL:
        logger.info("Serving cached recon for %s (id=%s)", domain, row["id"])
        return redirect(url_for("recon_result", recon_id=row["id"]))

    page_headers, page_html = {}, ""
    try:
        page = safe_get(url)
        body = _stream_body(page)
        page_headers = dict(page.headers)
        page_html = body.decode(page.encoding or "utf-8", errors="replace")
        page.close()
    except requests.exceptions.RequestException:
        pass
    except ValueError as e:
        flash(str(e))
        return redirect(url_for("index"))

    data = reconlib.run_full_recon(url, domain, page_headers, page_html)

    cur = db.execute(
        "INSERT INTO recons (domain, data, created_at) VALUES (?,?,?)",
        (domain, json.dumps(data), now.isoformat(timespec="seconds")),
    )
    db.commit()
    return redirect(url_for("recon_result", recon_id=cur.lastrowid))


@app.route("/recon/<int:recon_id>")
def recon_result(recon_id):
    db = get_db()
    row = db.execute("SELECT * FROM recons WHERE id = ?", (recon_id,)).fetchone()
    if row is None:
        flash("That recon report doesn't exist.")
        return redirect(url_for("index"))
    record = dict(row)
    record["data"] = json.loads(record["data"])
    return render_template("recon.html", rec=record)


@app.route("/history")
def history():
    db = get_db()
    scrapes = db.execute(
        "SELECT id, url AS label, status_code, created_at FROM scrapes ORDER BY id DESC LIMIT 50"
    ).fetchall()
    searches = db.execute(
        "SELECT id, query AS label, result_count, created_at FROM searches ORDER BY id DESC LIMIT 50"
    ).fetchall()
    recons = db.execute(
        "SELECT id, domain AS label, created_at FROM recons ORDER BY id DESC LIMIT 50"
    ).fetchall()

    rows = []
    for r in scrapes:
        rows.append({
            "kind": "page", "id": r["id"], "label": r["label"],
            "meta": f'status {r["status_code"]}', "created_at": r["created_at"],
        })
    for r in searches:
        rows.append({
            "kind": "search", "id": r["id"], "label": r["label"],
            "meta": f'{r["result_count"]} results', "created_at": r["created_at"],
        })
    for r in recons:
        rows.append({
            "kind": "recon", "id": r["id"], "label": r["label"],
            "meta": "recon report", "created_at": r["created_at"],
        })
    rows.sort(key=lambda x: x["created_at"], reverse=True)
    return render_template("history.html", rows=rows[:100])


@app.context_processor
def inject_theme():
    db = get_db()
    search_count = db.execute("SELECT COUNT(*) as c FROM searches").fetchone()["c"]
    saved_count = db.execute("SELECT COUNT(*) as c FROM saved_items").fetchone()["c"]
    entity_count = 0
    try:
        entity_count = knowledgelib._memory_storage.get_entities(limit=1)
        entity_count = len(knowledgelib._memory_storage.get_entities(limit=1000000))
    except Exception:
        pass
    return {
        "theme": request.cookies.get("theme", "light"),
        "statusbar": {
            "search_count": search_count,
            "saved_count": saved_count,
            "entity_count": entity_count,
        }
    }


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/export/<int:search_id>.<fmt>")
def export_search(search_id, fmt):
    db = get_db()
    row = db.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
    if row is None:
        flash("That search doesn't exist.")
        return redirect(url_for("index"))
    record = dict(row)
    results = json.loads(record["results"])
    query = record["query"]

    if fmt == "json":
        payload = json.dumps({"query": query, "results": results}, indent=2)
        return (payload, 200, {"Content-Type": "application/json",
                                "Content-Disposition": f'attachment; filename="search-{search_id}.json"'})
    elif fmt == "csv":
        import csv
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["source", "type", "title", "url", "snippet", "meta"])
        writer.writeheader()
        for item in results:
            writer.writerow({k: item.get(k, "") for k in writer.fieldnames})
        return (buf.getvalue(), 200, {"Content-Type": "text/csv",
                                       "Content-Disposition": f'attachment; filename="search-{search_id}.csv"'})
    else:
        flash("Unsupported export format.")
        return redirect(url_for("search_result", search_id=search_id))


@app.route("/save", methods=["POST"])
def save_item():
    query = request.form.get("query", "")
    item_json = request.form.get("item_json", "{}")
    note = request.form.get("note", "")
    if not query or not item_json:
        flash("Nothing to save.")
        return redirect(request.referrer or url_for("index"))
    db = get_db()
    cur = db.execute(
        "INSERT INTO saved_items (query, item_json, note, created_at) VALUES (?,?,?,?)",
        (query, item_json, note, datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()
    item_id = cur.lastrowid

    try:
        parsed = json.loads(item_json) if isinstance(item_json, str) else item_json
        title = parsed.get("title", "")
        snippet = parsed.get("snippet", "")
        url = parsed.get("url", "")
        tags = auto_tag(title, snippet, url)
        for tag in tags:
            knowledgelib._memory_storage.add_tag(item_id, tag)
        knowledgelib._preference_learner.record_from_query(query)
    except Exception:
        pass

    flash("Saved to your knowledge base.")
    return redirect(request.referrer or url_for("index"))


@app.route("/saved")
def saved_items():
    db = get_db()
    rows = db.execute("SELECT id, query, item_json, note, created_at FROM saved_items ORDER BY id DESC LIMIT 100").fetchall()
    items = []
    for row in rows:
        tags = knowledgelib._memory_storage.get_tags(row["id"])
        items.append({
            "id": row["id"],
            "query": row["query"],
            "item": json.loads(row["item_json"]),
            "note": row["note"],
            "created_at": row["created_at"],
            "tags": tags,
        })
    return render_template("saved.html", items=items)


@app.route("/api/typeahead")
def typeahead():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return json.dumps({"suggestions": []})
    
    suggestions = []
    suggestions.append(f"{q} definition")
    suggestions.append(f"{q} tutorial")
    suggestions.append(f"{q} pros and cons")
    suggestions.append(f"best {q}")
    suggestions.append(f"{q} vs alternatives")
    
    try:
        data = knowledgelib._get_json("https://en.wikipedia.org/w/api.php", {
            "action": "opensearch",
            "search": q,
            "limit": 5,
            "format": "json",
        })
        if data and len(data) >= 2:
            for title in data[1][:5]:
                if title.lower() not in [s.lower() for s in suggestions]:
                    suggestions.append(title)
    except Exception:
        pass
    
    return json.dumps({"suggestions": suggestions[:8]})


@app.route("/theme", methods=["POST"])
def theme():
    mode = request.form.get("mode", "light")
    resp = redirect(request.referrer or url_for("index"))
    resp.set_cookie("theme", mode, max_age=30 * 24 * 60 * 60, httponly=True, samesite="Lax")
    return resp


def _cleanup_old_records():
    try:
        cutoff = datetime.utcnow() - timedelta(days=int(os.environ.get("HISTORY_DAYS", "30")))
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM scrapes WHERE created_at < ?", (cutoff.isoformat(timespec="seconds"),))
        conn.execute("DELETE FROM searches WHERE created_at < ?", (cutoff.isoformat(timespec="seconds"),))
        conn.execute("DELETE FROM recons WHERE created_at < ?", (cutoff.isoformat(timespec="seconds"),))
        conn.commit()
        deleted = conn.total_changes
        conn.close()
        if deleted:
            logger.info("Cleaned up %d old records older than %s", deleted, cutoff.date())
    except Exception as e:
        logger.warning("Cleanup failed: %s", e)


if __name__ == "__main__":
    init_db()
    _cleanup_old_records()
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), debug=DEBUG)
