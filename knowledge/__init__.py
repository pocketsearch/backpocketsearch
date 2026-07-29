"""
Multi-source open knowledge retrieval.
Philosophy: no query is ever blocked or rejected.
If one source fails, try another. Always return insight.
All sources are free/open APIs that require no authentication or keys.
Prioritizes production-ready code, cross-platform compatibility, and architectural precision.
"""
import json
import logging
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, timedelta
from functools import lru_cache
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("webscope.knowledge")

UA = "Mozilla/5.0 (compatible; WebScope/1.0)"
TIMEOUT = 8
_session = requests.Session()
_session.headers.update({"User-Agent": UA})

CACHE_DB = os.environ.get("KNOWLEDGE_CACHE_DB", "knowledge_cache.db")

# In-memory cache: (source_name, query) -> (results, timestamp)
_cache = {}
_CACHE_TTL = 1800  # 30 minutes

# Source trust scores (1-5). Higher = more authoritative for factual claims.
SOURCE_TRUST = {
    "NVD": 5.0,
    "CISA KEV": 5.0,
    "GitHub GHSA": 4.8,
    "OSV.dev": 4.8,
    "OWASP": 4.7,
    "Wikipedia": 4.5,
    "Wikidata": 4.3,
    "Stack Overflow": 4.2,
    "OpenAlex": 4.5,
    "DuckDuckGo": 4.0,
    "GitHub": 4.0,
    "GitHub Issues": 3.8,
    "Hacker News": 3.5,
    "NPM": 4.0,
    "PyPI": 4.0,
    "Wayback Machine": 3.5,
    "OpenStreetMap": 4.0,
    "WebScope": 3.0,
}

# Topics that get visual answer cards
CARD_TOPICS = {
    "dog": ["dog", "dogs", "puppy", "puppies", "canine", "breed", "breeds"],
    "cat": ["cat", "cats", "kitten", "kittens", "feline"],
    "car": ["car", "cars", "vehicle", "vehicles", "automobile", "truck", "suv"],
    "phone": ["phone", "phones", "smartphone", "smartphones", "iphone", "android", "mobile"],
    "laptop": ["laptop", "laptops", "notebook", "notebooks", "computer", "pc"],
    "cpu": ["cpu", "processor", "processors", "intel", "amd", "ryzen", "core i"],
    "gpu": ["gpu", "graphics card", "graphics cards", "nvidia", "amd", "radeon", "geforce"],
    "country": ["country", "countries", "nation", "capital", "population"],
    "city": ["city", "cities", "town", "towns", "population"],
    "disease": ["disease", "diseases", "symptom", "symptoms", "medical", "condition"],
    "drug": ["drug", "drugs", "medication", "medications", "pharmaceutical"],
    "food": ["food", "foods", "recipe", "recipes", "nutrition", "calories"],
    "drink": ["drink", "drinks", "beverage", "beverages", "water", "coffee", "tea"],
    "movie": ["movie", "movies", "film", "films", "cinema", "director", "actor"],
    "book": ["book", "books", "novel", "novels", "author", "literature"],
    "game": ["game", "games", "video game", "gaming", "playstation", "xbox", "nintendo"],
    "sport": ["sport", "sports", "athlete", "athletes", "olympics", "team"],
    "planet": ["planet", "planets", "solar system", "moon", "stars", "astronomy"],
    "element": ["element", "elements", "periodic table", "chemistry", "atom"],
    "language": ["language", "languages", "programming language", "spoken"],
}


def _get_cache_conn():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_cache (
            source TEXT NOT NULL,
            query TEXT NOT NULL,
            results TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (source, query)
        )
    """)
    return conn


def _cached(name):
    def decorator(fn):
        def wrapper(query, *args, **kwargs):
            q = query.lower().strip()
            key = (name, q)
            if key in _cache:
                result, ts = _cache[key]
                if time.time() - ts < _CACHE_TTL:
                    return result

            # Try persistent cache
            try:
                conn = _get_cache_conn()
                row = conn.execute(
                    "SELECT results, created_at FROM knowledge_cache WHERE source=? AND query=?",
                    (name, q),
                ).fetchone()
                conn.close()
                if row and time.time() - row[1] < _CACHE_TTL:
                    result = json.loads(row[0])
                    _cache[key] = (result, time.time())
                    return result
            except Exception:
                pass

            result = fn(query, *args, **kwargs)
            _cache[key] = (result, time.time())
            try:
                conn = _get_cache_conn()
                conn.execute(
                    "INSERT OR REPLACE INTO knowledge_cache (source, query, results, created_at) VALUES (?,?,?,?)",
                    (name, q, json.dumps(result), time.time()),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return result
        return wrapper
    return decorator


def _get_json(url, params=None, timeout=TIMEOUT):
    try:
        r = _session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("Knowledge GET %s failed: %s", url, e)
        return None


def _post_json(url, data=None, timeout=TIMEOUT):
    try:
        r = _session.post(url, json=data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("Knowledge POST %s failed: %s", url, e)
        return None


def _get_text(url, timeout=TIMEOUT):
    try:
        r = _session.get(url, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.debug("Knowledge GET text %s failed: %s", url, e)
        return None


# ---- Wikipedia / MediaWiki ----

@_cached("wiki")
def wiki_search(query, limit=8):
    results = []
    data = _get_json("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "srprop": "snippet|titlesnippet|wordcount|timestamp",
    })
    if not data or "query" not in data:
        return results
    for item in data["query"].get("search", []):
        title = item.get("title", "")
        snippet = re.sub(r'<span class="searchmatch">', "", item.get("snippet", ""))
        snippet = re.sub(r'</span>', "", snippet)
        results.append({
            "source": "Wikipedia",
            "type": "article",
            "title": title,
            "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
            "snippet": snippet,
            "meta": f"{item.get('wordcount', 0)} words · {item.get('timestamp', '')[:10]}",
        })
    return results


@_cached("wiki_extract")
def wiki_extract(title):
    data = _get_json("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "titles": title,
        "format": "json",
    })
    if not data or "query" not in data:
        return None
    pages = data["query"].get("pages", {})
    for page_id, page in pages.items():
        if page_id != "-1":
            return page.get("extract", "")
    return None


# ---- Wikidata ----

@_cached("wikidata")
def wikidata_search(query, limit=5):
    results = []
    data = _get_json("https://www.wikidata.org/w/api.php", {
        "action": "wbsearchentities",
        "search": query,
        "language": "en",
        "limit": limit,
        "format": "json",
    })
    if not data or "search" not in data:
        return results
    for item in data["search"]:
        desc = item.get("description", "")
        results.append({
            "source": "Wikidata",
            "type": "entity",
            "title": item.get("label", query),
            "url": f"https://www.wikidata.org/wiki/{item.get('id', '')}",
            "snippet": desc,
            "meta": item.get("id", ""),
        })
    return results


# ---- GitHub ----

@_cached("github")
def github_search(query, limit=8):
    results = []
    data = _get_json("https://api.github.com/search/repositories", {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": limit,
    })
    if not data or "items" not in data:
        return results
    for item in data["items"]:
        results.append({
            "source": "GitHub",
            "type": "repo",
            "title": item.get("full_name", ""),
            "url": item.get("html_url", ""),
            "snippet": item.get("description", "") or "",
            "meta": f"★ {item.get('stargazers_count', 0)} · {item.get('language', '') or 'unknown'} · {item.get('updated_at', '')[:10]}",
        })
    return results


@_cached("github_code")
def github_code_search(query, limit=6):
    results = []
    data = _get_json("https://api.github.com/search/code", {
        "q": query,
        "per_page": limit,
    })
    if not data or "items" not in data:
        return results
    for item in data["items"]:
        results.append({
            "source": "GitHub Code",
            "type": "code",
            "title": item.get("name", ""),
            "url": item.get("html_url", ""),
            "snippet": item.get("repository", {}).get("description", "") or "",
            "meta": item.get("repository", {}).get("full_name", ""),
        })
    return results


# ---- Stack Exchange ----

@_cached("stackexchange")
def stackexchange_search(query, limit=6):
    results = []
    data = _get_json("https://api.stackexchange.com/2.3/search/advanced", {
        "order": "desc",
        "sort": "relevance",
        "q": query,
        "pagesize": limit,
        "site": "stackoverflow",
    })
    if not data or "items" not in data:
        return results
    for item in data["items"]:
        tags = ", ".join(item.get("tags", [])[:5])
        results.append({
            "source": "Stack Overflow",
            "type": "question",
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": f"Score: {item.get('score', 0)} · {item.get('answer_count', 0)} answers · Tags: {tags}",
            "meta": f"asked {time.strftime('%Y-%m-%d', time.gmtime(item.get('creation_date', 0)))}",
        })
    return results


# ---- Hacker News ----

@_cached("hackernews")
def hackernews_search(query, limit=6):
    results = []
    data = _get_json("https://hn.algolia.com/api/v1/search", params={
        "query": query,
        "hitsPerPage": limit,
        "tags": "story",
    })
    if not data or "hits" not in data:
        return results
    for hit in data["hits"]:
        title = hit.get("title", "")
        url = hit.get("url", f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}")
        points = hit.get("points", 0)
        comments = hit.get("num_comments", 0)
        date = hit.get("created_at", "")[:10]
        results.append({
            "source": "Hacker News",
            "type": "discussion",
            "title": title,
            "url": url,
            "snippet": f"{points} points · {comments} comments · {date}",
            "meta": "tech discussion",
        })
    return results


@_cached("github_issues")
def github_issues_search(query, limit=6):
    results = []
    data = _get_json("https://api.github.com/search/issues", {
        "q": query,
        "per_page": limit,
        "sort": "reactions",
        "order": "desc",
    })
    if not data or "items" not in data:
        return results
    for item in data["items"]:
        results.append({
            "source": "GitHub Issues",
            "type": "issue",
            "title": item.get("title", ""),
            "url": item.get("html_url", ""),
            "snippet": f"State: {item.get('state', '')} · Reactions: {item.get('reactions', {}).get('total_count', 0)} · {item.get('updated_at', '')[:10]}",
            "meta": item.get("user", {}).get("login", ""),
        })
    return results


# ---- Reddit (disabled - Reddit blocks datacenter IPs) ----
# Kept as a stub so the module structure remains stable.
def reddit_search(query, limit=6):
    return []


# ---- OpenAlex (Academic Papers) ----

@_cached("openalex")
def openalex_search(query, limit=6):
    results = []
    mailto = os.environ.get("OPENALEX_MAILTO", "webscope@example.com")
    data = _get_json("https://api.openalex.org/works", {
        "search": query,
        "per-page": limit,
        "mailto": mailto,
    })
    if not data or "results" not in data:
        return results
    for item in data["results"]:
        title = item.get("title", "")
        doi = item.get("doi", "")
        url = doi if doi and doi.startswith("http") else item.get("id", "")
        year = item.get("publication_year", "")
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in item.get("authorships", [])[:3]
        )
        venue = item.get("host_venue", {}).get("display_name", "")
        results.append({
            "source": "OpenAlex",
            "type": "paper",
            "title": title,
            "url": url,
            "snippet": f"{venue} · {authors}" if venue or authors else "",
            "meta": str(year) if year else "",
        })
    return results


# ---- NPM ----

@_cached("npm")
def npm_search(query, limit=6):
    results = []
    data = _get_json("https://registry.npmjs.org/-/v1/search", {
        "text": query,
        "size": limit,
    })
    if not data or "objects" not in data:
        return results
    for obj in data["objects"]:
        pkg = obj.get("package", {})
        results.append({
            "source": "NPM",
            "type": "package",
            "title": pkg.get("name", ""),
            "url": f"https://www.npmjs.com/package/{pkg.get('name', '')}",
            "snippet": pkg.get("description", "") or "",
            "meta": f"v{pkg.get('version', '')} · {pkg.get('date', '')[:10] if pkg.get('date') else ''}",
        })
    return results


@_cached("npm_stats")
def npm_stats(query):
    try:
        r = _session.get(f"https://api.npmjs.org/downloads/point/last-week/{quote_plus(query)}", timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            downloads = data.get("downloads", 0)
            return f"{downloads:,} downloads/week"
    except Exception as e:
        logger.debug("npm stats failed: %s", e)
    return None


# ---- PyPI ----

@_cached("pypi")
def pypi_search(query, limit=6):
    results = []
    try:
        r = _session.get(
            "https://pypi.org/search/",
            params={"q": query},
            timeout=TIMEOUT,
            headers={"User-Agent": UA},
        )
        if r.status_code == 200:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                snippets = soup.select(".package-snippet")
                for snippet in snippets[:limit]:
                    name_tag = snippet.select_one(".package-snippet__name")
                    version_tag = snippet.select_one(".package-snippet__version")
                    desc_tag = snippet.select_one(".package-snippet__description")
                    if name_tag:
                        name = name_tag.get_text(strip=True)
                        results.append({
                            "source": "PyPI",
                            "type": "package",
                            "title": name,
                            "url": f"https://pypi.org/project/{name}/",
                            "snippet": desc_tag.get_text(strip=True) if desc_tag else "",
                            "meta": f"v{version_tag.get_text(strip=True) if version_tag else ''}",
                        })
            except ImportError:
                pass
    except Exception as e:
        logger.debug("PyPI search failed: %s", e)
    return results


# ---- DuckDuckGo Instant Answer ----

@_cached("ddg_instant")
def ddg_instant_answer(query):
    data = _get_json("https://api.duckduckgo.com/", {
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    })
    if not data:
        return None
    abstract = data.get("AbstractText", "")
    if abstract:
        return {
            "source": "DuckDuckGo",
            "type": "instant_answer",
            "title": data.get("Heading", query),
            "url": data.get("AbstractURL", ""),
            "snippet": abstract,
            "meta": "instant answer",
        }
    related = data.get("RelatedTopics", [])
    if related and isinstance(related, list):
        for topic in related[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                return {
                    "source": "DuckDuckGo",
                    "type": "instant_answer",
                    "title": topic.get("Text", query)[:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                    "meta": "related topic",
                }
    return None


# ---- Wayback Machine (archive.org) ----

@_cached("wayback")
def wayback_search(query, limit=6):
    results = []
    try:
        cdx_url = "https://web.archive.org/cdx/search/cdx"
        params = {
            "url": query,
            "output": "json",
            "limit": limit,
            "fl": "timestamp,statuscode,mimetype,length",
            "collapse": "timestamp:8",
            "filter": "statuscode:200",
        }
        data = _get_json(cdx_url, params=params, timeout=TIMEOUT)
        if not data or len(data) < 2:
            return results
        for row in data[1:]:
            ts, status, mime, length = row[0], row[1], row[2], row[3]
            year = ts[:4]
            month = ts[4:6]
            snapshot_url = f"https://web.archive.org/web/{ts}/{query}"
            results.append({
                "source": "Wayback Machine",
                "type": "archive",
                "title": f"Snapshot {year}-{month}",
                "url": snapshot_url,
                "snippet": f"Archived on {ts[:8]} · {status} · {mime} · {int(length):,} bytes",
                "meta": "historical snapshot",
            })
    except Exception as e:
        logger.debug("Wayback search failed: %s", e)
    return results


# ---- NVD (National Vulnerability Database) ----

@_cached("nvd")
def nvd_search(query, limit=6):
    results = []
    try:
        data = _get_json("https://services.nvd.nist.gov/rest/json/cves/2.0", {
            "keywordSearch": query,
            "resultsPerPage": limit,
        })
        if not data or "vulnerabilities" not in data:
            return results
        for vuln in data["vulnerabilities"]:
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "")
            desc = ""
            for desc_entry in cve.get("descriptions", []):
                if desc_entry.get("lang") == "en":
                    desc = desc_entry.get("value", "")
                    break
            metrics = cve.get("metrics", {})
            severity = "N/A"
            score = "N/A"
            for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                if key in metrics:
                    m = metrics[key][0]
                    cvss = m.get("cvssData", {})
                    score = cvss.get("baseScore", "N/A")
                    severity = cvss.get("baseSeverity", "N/A")
                    break
            results.append({
                "source": "NVD",
                "type": "cve",
                "title": cve_id,
                "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "snippet": desc[:200] + ("..." if len(desc) > 200 else ""),
                "meta": f"CVSS {score} · {severity}",
            })
    except Exception as e:
        logger.debug("NVD search failed: %s", e)
    return results


# ---- CISA Known Exploited Vulnerabilities (KEV) ----

@_cached("cisa_kev")
def cisa_kev_search(query, limit=6):
    results = []
    try:
        data = _get_json("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json")
        if not data or "vulnerabilities" not in data:
            return results
        q = query.lower()
        for vuln in data["vulnerabilities"]:
            cve_id = vuln.get("cveID", "")
            name = vuln.get("vulnerabilityName", "")
            if q not in cve_id.lower() and q not in name.lower():
                continue
            results.append({
                "source": "CISA KEV",
                "type": "cve",
                "title": f"{cve_id}: {name}",
                "url": f"https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                "snippet": vuln.get("shortDescription", ""),
                "meta": f"Added {vuln.get('dateAdded', '')[:10]} · {vuln.get('vendorProject', '')} {vuln.get('product', '')}",
            })
            if len(results) >= limit:
                break
    except Exception as e:
        logger.debug("CISA KEV search failed: %s", e)
    return results


# ---- GitHub Security Advisories (GHSA) ----

@_cached("ghsa")
def ghsa_search(query, limit=6):
    results = []
    data = _get_json("https://api.github.com/advisories", {
        "query": query,
        "per_page": limit,
    })
    if not data or not isinstance(data, list):
        return results
    for adv in data:
        ghsa_id = adv.get("ghsa_id", "")
        results.append({
            "source": "GitHub GHSA",
            "type": "advisory",
            "title": adv.get("summary", ghsa_id),
            "url": adv.get("html_url", f"https://github.com/advisories/{ghsa_id}"),
            "snippet": adv.get("description", "")[:200],
            "meta": f"Severity: {adv.get('severity', 'N/A')} · {adv.get('published_at', '')[:10]}",
        })
    return results


# ---- OSV.dev (Open Source Vulnerabilities) ----

@_cached("osv")
def osv_search(query, limit=6):
    results = []
    ecosystems = ["PyPI", "npm", "Go", "Maven", "RubyGems", "crates.io", "NuGet", "Packagist", "Pub", "Hex"]
    for ecosystem in ecosystems:
        try:
            data = _post_json("https://api.osv.dev/v1/query", {
                "package": {"name": query, "ecosystem": ecosystem},
                "page_size": limit,
            })
            if not data or "vulns" not in data:
                continue
            for vuln in data["vulns"][:limit]:
                osv_id = vuln.get("id", "")
                summary = vuln.get("summary", "")
                if not summary:
                    summary = vuln.get("details", "")[:100]
                aliases = ", ".join(vuln.get("aliases", [])[:3])
                results.append({
                    "source": "OSV.dev",
                    "type": "vuln",
                    "title": f"{osv_id}: {summary}",
                    "url": f"https://osv.dev/vulnerability/{osv_id}",
                    "snippet": vuln.get("details", "")[:200] + ("..." if len(vuln.get("details", "")) > 200 else ""),
                    "meta": f"Aliases: {aliases}" if aliases else f"{ecosystem}",
                })
            if results:
                break
        except Exception as e:
            logger.debug("OSV search failed for %s: %s", ecosystem, e)
    return results[:limit]


# ---- OWASP / Security Research (via DuckDuckGo site: searches) ----

@_cached("owasp")
def owasp_search(query, limit=6):
    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        data = {"q": f"site:owasp.org {query}"}
        r = _session.post(url, data=data, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for block in soup.select(".result"):
                a = block.select_one(".result__a")
                if not a or not a.get("href"):
                    continue
                href = a["href"]
                real_url = href
                if "uddg=" in href:
                    from urllib.parse import parse_qs, urlparse
                    qs = parse_qs(urlparse(href).query)
                    if "uddg" in qs:
                        real_url = qs["uddg"][0]
                title = a.get_text(strip=True)
                snippet_tag = block.select_one(".result__snippet")
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                if title and real_url and "owasp.org" in real_url:
                    results.append({
                        "source": "OWASP",
                        "type": "article",
                        "title": title,
                        "url": real_url,
                        "snippet": snippet,
                        "meta": "owasp.org",
                    })
                if len(results) >= limit:
                    break
    except Exception as e:
        logger.debug("OWASP search failed: %s", e)
    return results


# ---- OpenStreetMap Nominatim (Geocoding) ----

@_cached("nominatim")
def nominatim_search(query, limit=4):
    results = []
    try:
        cleaned = re.sub(r'^(where is|where\'s|location of|map of|show me)\s+', '', query, flags=re.IGNORECASE).strip()
        if not cleaned:
            cleaned = query
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": cleaned,
            "format": "json",
            "limit": limit,
            "addressdetails": 1,
        }
        data = _get_json(url, params=params, timeout=TIMEOUT)
        if not data:
            return results
        for item in data:
            display = item.get("display_name", "")
            lat = item.get("lat", "")
            lon = item.get("lon", "")
            osm_type = item.get("osm_type", "")
            osm_id = item.get("osm_id", "")
            results.append({
                "source": "OpenStreetMap",
                "type": "place",
                "title": display.split(",")[0],
                "url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                "snippet": display,
                "meta": f"{lat}, {lon}",
            })
    except Exception as e:
        logger.debug("Nominatim search failed: %s", e)
    return results


# ---- Analysis: Contradictions, Consensus, Bias, Missed Facts ----

def _tokenize(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def _similarity(a, b):
    set_a = set(_tokenize(a))
    set_b = set(_tokenize(b))
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    return len(intersection) / min(len(set_a), len(set_b))


def detect_contradictions(results):
    contradictions = []
    texts = []
    for item in results:
        snippet = item.get("snippet", "")
        title = item.get("title", "")
        if snippet and len(snippet) > 20:
            texts.append((item, snippet))
    
    for i, (item_a, text_a) in enumerate(texts):
        for j, (item_b, text_b) in enumerate(texts):
            if j <= i:
                continue
            sim = _similarity(text_a, text_b)
            if sim < 0.3 or sim > 0.8:
                continue
            
            a_lower = text_a.lower()
            b_lower = text_b.lower()
            has_negation = any(w in a_lower for w in ["not", "no", "never", "don't", "doesn't", "isn't", "aren't", "can't", "cannot", "unlike", "however", "but", "although"]) or \
                          any(w in b_lower for w in ["not", "no", "never", "don't", "doesn't", "isn't", "aren't", "can't", "cannot", "unlike", "however", "but", "although"])
            if not has_negation:
                continue
            
            contradictions.append({
                "source_a": item_a.get("source", ""),
                "title_a": item_a.get("title", "")[:80],
                "url_a": item_a.get("url", ""),
                "snippet_a": text_a[:200],
                "source_b": item_b.get("source", ""),
                "title_b": item_b.get("title", "")[:80],
                "url_b": item_b.get("url", ""),
                "snippet_b": text_b[:200],
                "confidence": round(sim * 100, 1),
            })
            if len(contradictions) >= 3:
                return contradictions
    return contradictions


def calculate_consensus(results):
    if not results:
        return {"agreement_pct": 0, "disagreement_pct": 0, "total_sources": 0}
    
    sources = [item.get("source", "") for item in results if item.get("source")]
    unique_sources = list(dict.fromkeys(sources))
    total = len(unique_sources)
    
    if total <= 1:
        return {"agreement_pct": 100, "disagreement_pct": 0, "total_sources": total}
    
    texts = [item.get("snippet", "") + " " + item.get("title", "") for item in results[:min(8, len(results))]]
    sims = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sims.append(_similarity(texts[i], texts[j]))
    
    avg_sim = sum(sims) / len(sims) if sims else 0.5
    agreement = round(avg_sim * 100, 1)
    disagreement = round(100 - agreement, 1)
    
    return {
        "agreement_pct": agreement,
        "disagreement_pct": disagreement,
        "total_sources": total,
    }


def detect_bias(item):
    signals = []
    text = (item.get("snippet", "") + " " + item.get("title", "")).lower()
    source = item.get("source", "").lower()
    
    commercial_signals = ["buy", "price", "discount", "deal", "sale", "review", "best", "top", "recommended", "sponsored", "affiliate", "amazon"]
    opinion_signals = ["opinion", "think", "believe", "feel", "should", "must", "obviously", "clearly", "without doubt"]
    scientific_signals = ["study", "research", "published", "peer-reviewed", "journal", "doi", "clinical", "experiment", "data"]
    political_signals = ["left", "right", "liberal", "conservative", "progressive", "party", "election", "policy", "government"]
    
    detected = []
    if any(s in text for s in commercial_signals):
        detected.append("commercial")
    if any(s in text for s in opinion_signals):
        detected.append("opinion")
    if any(s in text for s in scientific_signals) or source in ["openalex", "nvd", "cisa kev", "github ghsa", "osv.dev"]:
        detected.append("scientific")
    if any(s in text for s in political_signals):
        detected.append("political")
    
    if not detected:
        detected.append("neutral")
    
    return {
        "signals": detected,
        "source": item.get("source", ""),
        "title": item.get("title", "")[:60],
    }


def extract_overlooked_facts(results):
    facts = []
    seen_phrases = set()
    
    for item in results:
        snippet = item.get("snippet", "")
        source = item.get("source", "")
        if len(snippet) < 30:
            continue
        
        sentences = re.split(r'(?<=[.!?])\s+', snippet)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 200:
                continue
            
            tokens = set(_tokenize(sentence))
            is_unique = True
            for phrase in seen_phrases:
                phrase_tokens = set(_tokenize(phrase))
                if not tokens.isdisjoint(phrase_tokens) and _similarity(sentence, phrase) > 0.4:
                    is_unique = False
                    break
            
            if is_unique:
                seen_phrases.add(sentence)
                facts.append({
                    "fact": sentence,
                    "source": source,
                    "url": item.get("url", ""),
                })
                if len(facts) >= 5:
                    return facts
    return facts


def adapt_difficulty(text, level="standard"):
    if not text:
        return text
    simplifications = {
        "child": [
            (r'\binstall\b', 'put in'), (r'\bconfigure\b', 'set up'),
            (r'\butilize\b', 'use'), (r'\binitialize\b', 'start'),
            (r'\bterminate\b', 'stop'), (r'\bexecute\b', 'run'),
            (r'\bdemonstrate\b', 'show'), (r'\bverify\b', 'check'),
            (r'\bfurthermore\b', 'also'), (r'\bhowever\b', 'but'),
            (r'\btherefore\b', 'so'), (r'\bapproximately\b', 'about'),
            (r'\bdocument\b', 'write down'), (r'\bdirectory\b', 'folder'),
            (r'\bcommence\b', 'begin'), (r'\bsubsequently\b', 'then'),
            (r'\badditionally\b', 'also'), (r'\bnavigate\b', 'go to'),
            (r'\bimplementation\b', 'building'), (r'\barchitecture\b', 'design'),
        ],
        "high_school": [
            (r'\butilize\b', 'use'), (r'\bdemonstrate\b', 'show'),
            (r'\bfurthermore\b', 'also'), (r'\btherefore\b', 'so'),
            (r'\bhowever\b', 'but'), (r'\badditionally\b', 'also'),
            (r'\bapproximately\b', 'about'), (r'\bimplement\b', 'build'),
            (r'\binitialize\b', 'start'), (r'\bterminate\b', 'stop'),
            (r'\bexecute\b', 'run'), (r'\bconfiguration\b', 'settings'),
            (r'\bdirectory\b', 'folder'), (r'\bnavigate\b', 'go to'),
        ],
        "college": [
            (r'\butilize\b', 'use'), (r'\bdemonstrate\b', 'show'),
            (r'\bfurthermore\b', 'also'), (r'\btherefore\b', 'so'),
            (r'\bhowever\b', 'but'), (r'\binitialize\b', 'start'),
            (r'\bterminate\b', 'stop'), (r'\bdirectory\b', 'folder'),
        ],
        "engineer": [
            (r'\butilize\b', 'use'), (r'\binitialize\b', 'start'),
            (r'\bterminate\b', 'stop'), (r'\bdemonstrate\b', 'show'),
        ],
        "researcher": [],
    }
    replacements = simplifications.get(level, simplifications["college"])
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ---- Visual Answer Cards ----

def _generate_answer_card(query, topic):
    cards = {
        "dog": {
            "title": "Dog Breed Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Intelligence", "value": "High", "icon": "🧠"},
                {"label": "Energy", "value": "Very High", "icon": "⚡"},
                {"label": "Trainability", "value": "Excellent", "icon": "🎓"},
                {"label": "Good with Kids", "value": "Yes", "icon": "👶"},
                {"label": "Size", "value": "Medium", "icon": "📏"},
                {"label": "Lifespan", "value": "12-15 years", "icon": "⏳"},
            ],
            "summary": f"{query.title()} are known for their intelligence, energy, and strong work ethic. They excel in obedience training and require significant mental stimulation.",
            "best_for": ["Active families", "Herding work", "Dog sports", "Experienced owners"],
            "not_ideal_for": ["Inactive households", "First-time owners", "Small apartments without exercise access"],
        },
        "cat": {
            "title": "Cat Breed Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Intelligence", "value": "High", "icon": "🧠"},
                {"label": "Energy", "value": "Moderate", "icon": "⚡"},
                {"label": "Trainability", "value": "Good", "icon": "🎓"},
                {"label": "Good with Kids", "value": "Varies", "icon": "👶"},
                {"label": "Size", "value": "Medium", "icon": "📏"},
                {"label": "Lifespan", "value": "12-18 years", "icon": "⏳"},
            ],
            "summary": f"{query.title()} are independent yet affectionate companions known for their agility and cleanliness.",
            "best_for": ["Apartment living", "Busy people", "Quiet homes"],
            "not_ideal_for": ["Very noisy households", "People wanting dog-like obedience"],
        },
        "car": {
            "title": "Vehicle Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Safety", "value": "High", "icon": "🛡️"},
                {"label": "Efficiency", "value": "Moderate", "icon": "⛽"},
                {"label": "Performance", "value": "Good", "icon": "🏎️"},
                {"label": "Reliability", "value": "High", "icon": "🔧"},
                {"label": "Comfort", "value": "High", "icon": "💺"},
                {"label": "Tech", "value": "Modern", "icon": "📱"},
            ],
            "summary": f"The {query.title()} is a well-rounded vehicle offering strong safety ratings, reliable performance, and modern technology features.",
            "best_for": ["Families", "Commuting", "Road trips"],
            "not_ideal_for": ["Off-roading", "Track racing", "Towing heavy loads"],
        },
        "phone": {
            "title": "Smartphone Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Camera", "value": "Excellent", "icon": "📷"},
                {"label": "Battery", "value": "Good", "icon": "🔋"},
                {"label": "Performance", "value": "Top-tier", "icon": "⚡"},
                {"label": "Display", "value": "OLED", "icon": "🖥️"},
                {"label": "Durability", "value": "High", "icon": "🛡️"},
                {"label": "Ecosystem", "value": "Strong", "icon": "🌐"},
            ],
            "summary": f"The {query.title()} offers premium build quality, excellent camera performance, and strong ecosystem integration.",
            "best_for": ["Photography", "Productivity", "Media consumption", "Gaming"],
            "not_ideal_for": ["Budget buyers", "Heavy customization", "Expandable storage"],
        },
        "laptop": {
            "title": "Laptop Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Performance", "value": "High", "icon": "⚡"},
                {"label": "Battery", "value": "Good", "icon": "🔋"},
                {"label": "Display", "value": "Retina", "icon": "🖥️"},
                {"label": "Build", "value": "Premium", "icon": "🛡️"},
                {"label": "Keyboard", "value": "Excellent", "icon": "⌨️"},
                {"label": "Portability", "value": "Good", "icon": "💼"},
            ],
            "summary": f"The {query.title()} is a premium laptop known for excellent build quality, strong performance, and long battery life.",
            "best_for": ["Professional work", "Creative tasks", "Development", "Students"],
            "not_ideal_for": ["Gaming", "Heavy 3D rendering", "Budget constraints"],
        },
        "cpu": {
            "title": "Processor Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Cores", "value": "8-16", "icon": "🔢"},
                {"label": "Clock", "value": "Up to 5.0 GHz", "icon": "⚡"},
                {"label": "Cache", "value": "Large", "icon": "📦"},
                {"label": "TDP", "value": "65-125W", "icon": "🌡️"},
                {"label": "Architecture", "value": "Modern", "icon": "🏗️"},
                {"label": "Efficiency", "value": "High", "icon": "💡"},
            ],
            "summary": f"The {query.title()} processor delivers strong multi-threaded performance with excellent power efficiency.",
            "best_for": ["Gaming", "Content creation", "Programming", "Multi-tasking"],
            "not_ideal_for": ["Budget builds", "Extreme overclocking", "Server racks"],
        },
        "gpu": {
            "title": "Graphics Card Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "VRAM", "value": "8-16 GB", "icon": "💾"},
                {"label": "Ray Tracing", "value": "Yes", "icon": "✨"},
                {"label": "DLSS/FSR", "value": "Supported", "icon": "🎮"},
                {"label": "Power", "value": "High", "icon": "⚡"},
                {"label": "Cooling", "value": "Triple-fan", "icon": "❄️"},
                {"label": "Price", "value": "Premium", "icon": "💰"},
            ],
            "summary": f"The {query.title()} graphics card delivers excellent gaming performance with strong ray tracing capabilities.",
            "best_for": ["4K gaming", "AI/ML", "Video editing", "3D rendering"],
            "not_ideal_for": ["Budget builds", "Small cases", "Low-power systems"],
        },
        "country": {
            "title": "Country Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Population", "value": "Large", "icon": "👥"},
                {"label": "Area", "value": "Varies", "icon": "🗺️"},
                {"label": "GDP", "value": "High", "icon": "💰"},
                {"label": "Language", "value": "Multiple", "icon": "🗣️"},
                {"label": "Currency", "value": "Local", "icon": "💱"},
                {"label": "Timezone", "value": "Multiple", "icon": "🕐"},
            ],
            "summary": f"{query.title()} is a diverse country with rich history, strong economy, and varied geography.",
            "best_for": ["Tourism", "Business", "Education", "Cultural exchange"],
            "not_ideal_for": ["Homogeneous experiences", "Single-language environments"],
        },
        "city": {
            "title": "City Profile",
            "image_url": f"https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}",
            "attributes": [
                {"label": "Population", "value": "Large", "icon": "👥"},
                {"label": "Transit", "value": "Good", "icon": "🚇"},
                {"label": "Cost of Living", "value": "High", "icon": "💰"},
                {"label": "Safety", "value": "Moderate", "icon": "🛡️"},
                {"label": "Climate", "value": "Temperate", "icon": "🌤️"},
                {"label": "Culture", "value": "Rich", "icon": "🎭"},
            ],
            "summary": f"{query.title()} is a vibrant urban center with diverse neighborhoods, strong transit, and abundant cultural attractions.",
            "best_for": ["Urban living", "Career opportunities", "Entertainment", "Diversity"],
            "not_ideal_for": ["Peaceful retreats", "Low-cost living", "Car-dependent lifestyles"],
        },
    }

    if topic in cards:
        card = cards[topic].copy()
        card["query"] = query
        return card

    return None


def detect_calculation_query(query):
    q = query.lower()
    patterns = [
        r"\$[\d,]+", r"\d+\s*(million|billion|thousand|k|m|b)", r"how much",
        r"how many", r"what is \d+", r"calculate", r"mortgage", r"loan",
        r"afford", r"budget", r"salary", r"income", r"tax", r"interest rate",
        r"apr", r"down payment", r"monthly payment", r"cost of", r"price of",
    ]
    return any(re.search(p, q) for p in patterns)


def perform_calculation(query):
    q = query.lower()
    
    if "mortgage" in q or "monthly payment" in q or "afford" in q:
        numbers = re.findall(r'[\d,]+', query)
        if len(numbers) >= 1:
            try:
                price = float(numbers[0].replace(',', ''))
                rate = 0.065
                years = 30
                if len(numbers) >= 2:
                    rate = float(numbers[1].replace(',', '')) / 100
                if len(numbers) >= 3:
                    years = int(numbers[2])
                
                monthly_rate = rate / 12
                n = years * 12
                monthly = price * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)
                total = monthly * n
                interest = total - price
                
                return {
                    "type": "mortgage",
                    "inputs": {"price": price, "rate_pct": round(rate * 100, 2), "years": years},
                    "results": {
                        "monthly_payment": round(monthly, 2),
                        "total_cost": round(total, 2),
                        "total_interest": round(interest, 2),
                    },
                }
            except Exception:
                pass
    
    if "salary" in q or "income" in q or "tax" in q:
        numbers = re.findall(r'[\d,]+', query)
        if len(numbers) >= 1:
            try:
                income = float(numbers[0].replace(',', ''))
                tax_rate = 0.22
                if len(numbers) >= 2:
                    tax_rate = float(numbers[1].replace(',', '')) / 100
                
                tax = income * tax_rate
                net = income - tax
                
                return {
                    "type": "tax_estimate",
                    "inputs": {"income": income, "tax_rate_pct": round(tax_rate * 100, 2)},
                    "results": {
                        "gross": income,
                        "estimated_tax": round(tax, 2),
                        "net_income": round(net, 2),
                    },
                }
            except Exception:
                pass
    
    return None


def _detect_card_topic(query):
    q = query.lower()
    for topic, keywords in CARD_TOPICS.items():
        if any(kw in q for kw in keywords):
            return topic
    return None


def _get_follow_up_queries(query, topic=None):
    base = [f"{query} review", f"{query} pros and cons", f"best {query}", f"{query} tutorial"]
    if topic:
        base.extend([
            f"{query} vs alternatives",
            f"{query} specifications",
            f"{topic} comparison",
        ])
    return base[:6]


def _is_comparison_query(query):
    q = query.lower()
    patterns = [
        r'\bvs\b', r'\bversus\b', r'\bcompare\b', r'\bcomparison\b',
        r'\bdifference\b', r'\bpros and cons\b', r'\bwhich is better\b',
        r'\bbetter than\b', r'\bor\b.*\bwhich\b', r'\bagainst\b',
    ]
    for pat in patterns:
        if re.search(pat, q):
            return True
    return False


def _extract_comparison_entities(query):
    q = query.lower()
    for sep in [" vs ", " versus ", " compare ", " comparison "]:
        if sep in q:
            parts = q.split(sep, 1)
            if len(parts) == 2:
                a = parts[0].strip()
                b = parts[1].strip()
                b = re.sub(r'\b(which is better|better|difference|pros and cons)\b', '', b).strip()
                return a, b
    return None, None


def _classify(query):
    q = query.lower()
    
    if _is_comparison_query(query):
        return ["comparison"]
    
    # Technical / code-centric queries
    tech_keywords = [
        "python", "javascript", "typescript", "rust", "go lang", "golang", "java", "kotlin",
        "swift", "c++", "c#", "f#", "ruby", "php", "perl", "scala", "haskell", "elixir",
        "clojure", "dart", "lua", "r ", "matlab", "sql", "nosql", "mongodb", "postgres",
        "mysql", "redis", "docker", "kubernetes", "k8s", "terraform", "ansible", "linux",
        "kernel", "windows", "macos", "ios", "android", "unix", "bsd", "compiler",
        "interpreter", "runtime", "jit", "assembler", "firmware", "driver", "malloc",
        "race condition", "deadlock", "mutex", "semaphore", "atomic", "profiling",
        "benchmark", "latency", "throughput", "optimization", "cmake", "makefile",
        "bazel", "gradle", "maven", "cargo", "npm", "pip", "apt", "yum", "systemd",
        "bash", "shell", "powershell", "zsh", "fish", "vim", "neovim", "emacs",
        "vscode", "intellij", "eclipse", "xcode", "android studio", "git", "github",
        "gitlab", "bitbucket", "jenkins", "github actions", "gitlab ci", "travis",
        "circleci", "aws", "amazon", "gcp", "google cloud", "azure", "cloudflare",
        "nginx", "apache", "caddy", "haproxy", "envoy", "istio", "linkerd",
        "react", "vue", "angular", "svelte", "next.js", "nuxt", "django", "flask",
        "fastapi", "spring", "express", "rails", "laravel", "symfony", "gin", "echo",
        "actix", "rocket", "axum", "bevy", "godot", "unity", "unreal", "opengl",
        "vulkan", "metal", "directx", "webgpu", "wasm", "webassembly", "flutter",
        "react native", "electron", "tauri", "pwa", "websocket", "grpc", "rest",
        "graphql", "opentelemetry", "prometheus", "grafana", "elasticsearch",
        "kibana", "logstash", "splunk", "datadog", "newrelic", "sentry", "oauth",
        "jwt", "saml", "ldap", "kerberos", "tls", "ssl", "ssh", "vpn", "wireguard",
        "openvpn", "ipsec", "firewall", "iptables", "nftables", "selinux", "apparmor",
        "seccomp", "namespace", "cgroup", "overlayfs", "btrfs", "zfs", "ext4",
        "xfs", "fat32", "ntfs", "apfs", "exfat", "uefi", "bios", "uefi secure boot",
        "tpm", "secure boot", "virtualization", "kvm", "qemu", "xen", "hypervisor",
        "docker", "podman", "containerd", "cri-o", "lxc", "lxd", "systemd-nspawn",
        "firecracker", "gvisor", "kata", "rust", "zig", "nim", "odin", "jai",
        "code snippet", "implementation", "how to implement", "source code",
        "api design", "microservice", "monolith", "serverless", "function as a service",
        "faaS", "container", "orchestration", "ci/cd", "devops", "sre", "platform engineer",
        "gitops", "infrastructure as code", "iac", "policy as code", "observability",
        "distributed systems", "consensus", "raft", "paxos", "cap theorem", "acid",
        "eventual consistency", "sharding", "replication", "load balancer", "reverse proxy",
        "cdn", "edge computing", "zero trust", "sase", "ssrf", "csrf", "xss", "sqli",
        "rce", "lfi", "rfi", "buffer overflow", "use-after-free", "double free",
        "integer overflow", "format string", "rop", "jop", "ret2libc", "aslr", "dep",
        "stack canary", "control flow guard", "cfi", "shadow stack", "pti", "kpti",
        "spectre", "meltdown", "foreshadow", "zombieload", "ridl", "fallout",
        "microcode", "rootkit", "bootkit", "uefi exploit", "smep", "smap", "kasan",
        "kmalloc", "slab allocator", "buddy allocator", "page table", "tlb", "mmu",
        "context switch", "syscall", "int 0x80", "sysenter", "sysret", "vmcall",
        "hypercall", "ept", "npt", "vpdi", "apic", "ioapic", "lapic", "msi", "msi-x",
        "pcie", "acpi", "smm", "me", "psp", "ec", "embedded controller", "hsp",
        "usb", "thunderbolt", "usb4", "pci", "agp", "isa", "eisa", "mca", "vlb",
        "bios", "uefi", "edk2", "coreboot", "seabios", "ovmf", "arm64", "aarch64",
        "riscv", "risc-v", "mips", "powerpc", "s390x", "ia64", "alpha", "sparc",
        "m68k", "vax", "avr", "arm", "thumb", "aarch32", "armel", "armhf",
        "assembly", "asm", "nasm", "gas", "llvm", "gcc", "clang", "msvc", "icc",
        "tcc", "tinycc", "pcc", "sdcc", "golang", "gc", "go compiler", "gccgo",
        "rustc", "rustup", "cargo", "rustfmt", "clippy", "miri", "borrow checker",
        "ownership", "lifetime", "trait", "macro", "proc macro", "derive",
        "async", "await", "future", "stream", "tokio", "async-std", "actix-web",
        "axum", "hyper", "reqwest", "serde", "serde_json", "toml", "yaml",
        "ini", "cfg", "config", "configuration", "secrets", "vault", "key management",
        "kms", "hsm", "tpm 2.0", "secure element", "yubikey", "nitrokey",
        "opaque pointer", "handle", "file descriptor", "socket", "epoll", "kqueue",
        "iocp", "select", "poll", "eventfd", "signalfd", "timerfd", "inotify",
        "fanotify", "audit", "auditd", "journald", "syslog", "rsyslog", "syslog-ng",
        "logrotate", "journalctl", "dmesg", "procfs", "sysfs", "debugfs", "tracefs",
        "configfs", "securityfs", "efivarfs", "pstore", "ramfs", "tmpfs", "devtmpfs",
        "devpts", "hugetlbfs", "mqueue", "cpuset", "cgroup", "cgroup2", "systemd",
        "init", "sysvinit", "upstart", "launchd", "smf", "systemd", "openrc",
        "runit", "s6", "dinit", "busybox", "toybox", "sbase", "ubase",
        "golang", "python", "node.js", "deno", "bun", "php", "ruby", "perl",
        "lua", "tcl", "expect", "guile", "racket", "scheme", "common lisp",
        "clisp", "sbcl", "ecl", "ccl", "allegro", "lispworks", "emacs lisp",
        "elisp", "org-mode", "gnu emacs", "xemacs", "gvim", "vim", "neovim",
        "kakoune", "helix", "zed", "vscode", "code", "github codespaces",
        "gitpod", "replit", "codesandbox", "stackblitz", "figma", "excalidraw",
        "notion", "obsidian", "logseq", "roam", "foam", "vscode",
    ]
    
    if any(w in q for w in tech_keywords):
        return ["stackexchange", "github", "github_issues", "ddg_instant", "wikipedia", "openalex", "npm", "pypi", "hackernews"]
    
    if any(w in q for w in ["npm", "pip install", "package ", "library ", "module ", "crate", "gem", "nuget"]):
        return ["npm", "pypi", "github", "ddg_instant"]
    if any(w in q for w in ["paper", "research", "journal", "academic", "study ", "arxiv", "publication"]):
        return ["openalex", "wikipedia", "ddg_instant"]
    if any(w in q for w in ["stackoverflow", "how to", "how do i", "error ", "exception ", "question ", "debug"]):
        return ["stackexchange", "github", "github_issues", "ddg_instant"]
    if any(w in q for w in ["where is ", "map", "location", "city", "country", "gps", "coordinates", "address"]):
        return ["nominatim", "wikipedia", "ddg_instant"]
    if any(w in q for w in ["who is", "what is", "when was", "why is", "how is", "biography", "born", "definition"]):
        return ["wikipedia", "wikidata", "ddg_instant"]
    if any(w in q for w in ["news", "discussion", "opinion", "forum", "thread"]):
        return ["hackernews", "github_issues", "ddg_instant"]
    
    # Security / vulnerability research — public authoritative sources only
    security_keywords = [
        "cve", "vulnerability", "exploit", "exploitation", "advisory", "security",
        "owasp", "penetration test", "pentest", "red team", "blue team", "incident response",
        "malware", "ransomware", "threat actor", "apt", "mitre", "attack pattern",
        "cvss", "severity", "patch", "disclosure", "bug bounty", "responsible disclosure",
        "zero-day", "0day", "n-day", "proof of concept", "poc", "mitigation",
        "hardening", "secure coding", "threat model", "attack surface", "reconnaissance",
        "recon", "osint", "footprinting", "enumeration", "lateral movement", "privilege escalation",
        "persistence", "command and control", "c2", "c&c", "exfiltration", "data breach",
        "siem", "soar", "edr", "xdr", "mdr", "threat intelligence", "threat feed",
        "yara", "sigma", "suricata", "snort", "wazuh", "osquery", "velociraptor",
        "bloodhound", "sharped", "mimikatz", "hashcat", "john", "johntheripper",
        "burp", "zaproxy", "owasp zap", "nessus", "qualys", "rapid7", "nmap",
        "metasploit", "exploit-db", "cve-", "ghsa-", "osv-", "security advisory",
        "vulnerability management", "patch management", "configuration management",
        "compliance", "gdpr", "hipaa", "pci dss", "soc 2", "iso 27001",
        "nist", "cybersecurity", "infosec", "information security",
    ]
    if any(w in q for w in security_keywords):
        return ["nvd", "cisa_kev", "ghsa", "osv", "owasp", "stackexchange", "github", "ddg_instant"]
    
    # Default broad coverage — never leave a query hanging
    return ["ddg_instant", "wikipedia", "github", "hackernews", "github_issues", "stackexchange", "openalex"]


def enrich_query(query, max_results=30):
    """
    Aggregate insight from multiple open sources in parallel.
    Never returns empty. Falls back across sources until something useful is found.
    """
    all_results = []
    seen_urls = set()

    def add_unique(items):
        for item in items or []:
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            all_results.append(item)

    sources = _classify(query)
    tasks = []

    if "ddg_instant" in sources:
        tasks.append(("ddg_instant", lambda: [ddg_instant_answer(query)]))
    if "wikipedia" in sources:
        tasks.append(("wikipedia", lambda: wiki_search(query)))
    if "wikidata" in sources:
        tasks.append(("wikidata", lambda: wikidata_search(query)))
    if "github" in sources:
        tasks.append(("github", lambda: github_search(query)))
    if "stackexchange" in sources:
        tasks.append(("stackexchange", lambda: stackexchange_search(query)))
    if "hackernews" in sources:
        tasks.append(("hackernews", lambda: hackernews_search(query)))
    if "github_issues" in sources:
        tasks.append(("github_issues", lambda: github_issues_search(query)))
    if "nvd" in sources:
        tasks.append(("nvd", lambda: nvd_search(query)))
    if "cisa_kev" in sources:
        tasks.append(("cisa_kev", lambda: cisa_kev_search(query)))
    if "ghsa" in sources:
        tasks.append(("ghsa", lambda: ghsa_search(query)))
    if "osv" in sources:
        tasks.append(("osv", lambda: osv_search(query)))
    if "owasp" in sources:
        tasks.append(("owasp", lambda: owasp_search(query)))
    if "openalex" in sources:
        tasks.append(("openalex", lambda: openalex_search(query)))
    if "npm" in sources:
        tasks.append(("npm", lambda: npm_search(query)))
    if "pypi" in sources:
        tasks.append(("pypi", lambda: pypi_search(query)))
    if "wayback" in sources:
        tasks.append(("wayback", lambda: wayback_search(query)))
    if "nominatim" in sources:
        tasks.append(("nominatim", lambda: nominatim_search(query)))

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {}
        for name, fn in tasks:
            future_map[executor.submit(fn)] = name

        try:
            for future in as_completed(future_map, timeout=15):
                name = future_map[future]
                try:
                    items = future.result()
                    add_unique(items)
                    if name == "wikipedia" and items and len(all_results) < max_results:
                        extract = wiki_extract(items[0]["title"])
                        if extract:
                            all_results.insert(0, {
                                "source": "Wikipedia",
                                "type": "summary",
                                "title": f"Summary: {items[0]['title']}",
                                "url": items[0]["url"],
                                "snippet": extract[:600] + ("..." if len(extract) > 600 else ""),
                                "meta": "auto-extracted intro",
                            })
                except Exception as e:
                    logger.debug("Knowledge source %s raised: %s", name, e)
        except TimeoutError:
            logger.debug("Some knowledge sources timed out after 15s")

    # Deduplicate by title
    unique = []
    seen_titles = set()
    for item in all_results:
        t = item.get("title", "").lower().strip()
        if t and t not in seen_titles:
            seen_titles.add(t)
            unique.append(item)

    final = unique[:max_results]

    # Analysis layer
    contradictions = detect_contradictions(final)
    consensus = calculate_consensus(final)
    bias_analyses = [detect_bias(item) for item in final[:6]]
    overlooked = extract_overlooked_facts(final)
    calculation = perform_calculation(query) if detect_calculation_query(query) else None
    card_topic = _detect_card_topic(query)
    answer_card = _generate_answer_card(query, card_topic) if card_topic else None
    follow_ups = _get_follow_up_queries(query, card_topic)

    # How-to step-by-step generation
    step_by_steps = None
    if _howto_processor.is_how_to_query(query):
        difficulty = _howto_processor.detect_difficulty(query, final)
        step_by_steps = _howto_processor.generate_steps(final, query, difficulty)
        step_by_steps = _howto_processor._simplify_language(step_by_steps, difficulty)
        step_by_steps = _howto_processor._add_prerequisites(step_by_steps, query, difficulty)
        step_by_steps = _howto_processor._add_tips(step_by_steps, query, difficulty)

    # Final fallback — never return empty
    if not final:
        final = [{
            "source": "WebScope",
            "type": "fallback",
            "title": f'No direct results for "{query}"',
            "url": f"https://www.google.com/search?q={quote_plus(query)}",
            "snippet": "Try broadening your query or checking spelling. External knowledge sources may be temporarily rate-limited, but your query is valid.",
            "meta": "fallback",
        }]

    return {
        "results": final,
        "analysis": {
            "contradictions": contradictions,
            "consensus": consensus,
            "bias": bias_analyses,
            "overlooked": overlooked,
            "calculation": calculation,
            "card_topic": card_topic,
            "answer_card": answer_card,
            "follow_ups": follow_ups,
            "query": query,
            "step_by_steps": step_by_steps,
            "how_to_summary": _howto_processor.generate_summary(query, step_by_steps) if step_by_steps else None,
        },
    }


# ---- Memory system ----

from knowledge.storage import MemoryStorage
from knowledge.entities import EntityExtractor
from knowledge.memory import SearchMemory
from knowledge.learning import InterestLearner
from knowledge.preferences import PreferenceLearner
from knowledge.ranking import PersonalRanker
from knowledge.rewriter import QueryRewriter
from knowledge.graph import KnowledgeGraph
from knowledge.collections import AutoCollections
from knowledge.recommendations import RecommendationEngine
from knowledge.tagger import AutoTagger
from knowledge.howto import HowToProcessor

_memory_storage = MemoryStorage()
_entity_extractor = EntityExtractor(_memory_storage)
_search_memory = SearchMemory(_memory_storage, _entity_extractor)
_interest_learner = InterestLearner(_memory_storage)
_preference_learner = PreferenceLearner(_memory_storage)
_personal_ranker = PersonalRanker(_preference_learner)
_query_rewriter = QueryRewriter(_search_memory, _interest_learner)
_knowledge_graph = KnowledgeGraph(_memory_storage)
_auto_collections = AutoCollections(_memory_storage, _interest_learner, _entity_extractor)
_recommendation_engine = RecommendationEngine(
    _memory_storage, _interest_learner, _preference_learner, _search_memory, _entity_extractor
)
_auto_tagger = AutoTagger(_interest_learner, _entity_extractor)
_howto_processor = HowToProcessor(_memory_storage, _entity_extractor)


def record_search(query: str, normalized_query: str = "") -> int:
    return _search_memory.record_search(query, normalized_query)


def get_recent_queries(limit: int = 10) -> list[str]:
    return _search_memory.get_recent_queries(limit)


def get_top_interests(min_score: float = 0.5, limit: int = 20) -> list[dict]:
    return _interest_learner.get_top_interests(min_score, limit)


def get_preferred_sources(limit: int = 5) -> list[str]:
    return _preference_learner.get_preferred_sources(limit)


def rank_results(results, query: str = ""):
    return _personal_ranker.rank(results, query)


def rewrite_query(query: str) -> str:
    return _query_rewriter.rewrite(query)


def get_recommendations(limit: int = 8) -> list[dict]:
    return _recommendation_engine.get_recommendations(limit)


def auto_tag(title: str, snippet: str, url: str = "") -> list[str]:
    return _auto_tagger.generate_tags(title, snippet, url)


def get_related_entities(entity: str) -> list[dict]:
    return _knowledge_graph.get_related(entity)


def build_collections() -> list[dict]:
    return _auto_collections.build_collections()


def decay_interests() -> None:
    _interest_learner.decay_all()
