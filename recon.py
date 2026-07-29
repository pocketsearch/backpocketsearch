"""
Passive recon functions. Everything here reads from public sources only:
WHOIS servers, DNS, TLS certs the server hands out to anyone, crt.sh
(certificate transparency, public), and robots.txt/sitemap.xml (files
sites publish for crawlers). No port scanning, no auth bypass, no probing
for vulnerabilities.
"""
import json
import logging
import re
import shutil
import socket
import ssl
import subprocess
import xml.etree.ElementTree as ET

import dns.resolver
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; WebScope/1.0)"
TIMEOUT = 8
NAMESERVERS = ["1.1.1.1", "8.8.8.8"]

SECURITY_HEADERS = [
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
]

TECH_SIGNATURES = [
    ("WordPress", ["wp-content", "wp-includes", "/wp-json/"]),
    ("Shopify", ["cdn.shopify.com", "Shopify.theme"]),
    ("Wix", ["wix.com", "wixstatic.com"]),
    ("Squarespace", ["squarespace.com", "static1.squarespace.com"]),
    ("React", ["__REACT_DEVTOOLS", "data-reactroot", "react-dom"]),
    ("Vue.js", ["__VUE__", "data-v-", "vue.js"]),
    ("jQuery", ["jquery.min.js", "jquery.js"]),
    ("Bootstrap", ["bootstrap.min.css", "bootstrap.bundle"]),
    ("Cloudflare", ["cf-ray", "__cf_bm", "cloudflare"]),
    ("Google Analytics", ["google-analytics.com", "gtag(", "ga('create'"]),
    ("Google Tag Manager", ["googletagmanager.com"]),
    ("reCAPTCHA", ["recaptcha"]),
    ("PHP", ["X-Powered-By: PHP", ".php"]),
    ("ASP.NET", ["X-Powered-By: ASP.NET", "X-AspNet-Version", ".aspx"]),
    ("Nginx", ["nginx"]),
    ("Apache", ["apache"]),
]


def domain_from_url(url_or_domain):
    """Accepts a bare domain or a full URL and returns just the hostname."""
    raw = url_or_domain.strip()
    if "://" in raw:
        from urllib.parse import urlparse
        raw = urlparse(raw).netloc
    return raw.split("/")[0].split(":")[0].lower()


def run_whois(domain):
    """Shell out to the system `whois` binary. Kali ships it by default."""
    if not shutil.which("whois"):
        return {"available": False, "raw": "", "fields": {}}

    try:
        proc = subprocess.run(
            ["whois", domain], capture_output=True, text=True, timeout=15
        )
        raw = proc.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"available": True, "raw": f"whois lookup failed: {e}", "fields": {}}

    fields = {}
    patterns = {
        "registrar": r"(?i)^Registrar:\s*(.+)",
        "created": r"(?i)^Creation Date:\s*(.+)",
        "expires": r"(?i)^Registry Expiry Date:\s*(.+)",
        "updated": r"(?i)^Updated Date:\s*(.+)",
        "status": r"(?i)^Domain Status:\s*(.+)",
        "name_servers": r"(?i)^Name Server:\s*(.+)",
        "registrant_org": r"(?i)^Registrant Organization:\s*(.+)",
        "registrant_country": r"(?i)^Registrant Country:\s*(.+)",
        "dnssec": r"(?i)^DNSSEC:\s*(.+)",
        "registrar_iana": r"(?i)^Registrar IANA ID:\s*(.+)",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, raw, re.MULTILINE)
        if not matches:
            continue
        cleaned = [m.strip() for m in matches]
        fields[key] = cleaned if key in ("status", "name_servers") else cleaned[0]

    return {"available": True, "raw": raw, "fields": fields}


def get_dns_records(domain):
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = NAMESERVERS
    resolver.timeout = 5
    resolver.lifetime = 5

    record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
    records = {}
    for rtype in record_types:
        try:
            answer = resolver.resolve(domain, rtype)
            records[rtype] = [rdata.to_text() for rdata in answer]
        except dns.resolver.NoAnswer:
            records[rtype] = []
        except dns.resolver.NXDOMAIN:
            records[rtype] = None
            break
        except dns.resolver.Timeout:
            records[rtype] = ["timeout"]
        except dns.resolver.NoNameservers:
            records[rtype] = ["no nameservers"]
        except dns.exception.DNSException as e:
            records[rtype] = [f"dns error: {e}"]

    spf = [t for t in records.get("TXT", []) or [] if "v=spf1" in t.lower()]
    dmarc = []
    try:
        answer = resolver.resolve(f"_dmarc.{domain}", "TXT")
        dmarc = [rdata.to_text() for rdata in answer]
    except dns.resolver.NoAnswer:
        pass
    except dns.resolver.NXDOMAIN:
        pass
    except dns.resolver.Timeout:
        pass
    except dns.exception.DNSException:
        pass

    records["SPF"] = spf
    records["DMARC"] = dmarc
    return records


def get_ssl_info(domain, port=443):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
                cipher = tls.cipher()
                version = tls.version()
    except Exception as e:
        return {"available": False, "error": str(e)}

    def dn(pairs):
        return ", ".join(f"{k}={v}" for tup in pairs for k, v in tup)

    sans = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]

    return {
        "available": True,
        "subject": dn(cert.get("subject", [])),
        "issuer": dn(cert.get("issuer", [])),
        "not_before": cert.get("notBefore"),
        "not_after": cert.get("notAfter"),
        "san": sans,
        "tls_version": version,
        "cipher": cipher[0] if cipher else None,
    }


def get_security_headers(headers):
    present = {}
    for h in SECURITY_HEADERS:
        present[h] = headers.get(h)

    found = sum(1 for v in present.values() if v)
    total = len(SECURITY_HEADERS)
    if found == total:
        grade = "A"
    elif found >= total * 0.66:
        grade = "B"
    elif found >= total * 0.33:
        grade = "C"
    else:
        grade = "D"

    return {"headers": present, "grade": grade, "found": found, "total": total}


def get_robots_and_sitemap(base_url):
    result = {"robots_found": False, "disallow": [], "sitemaps": [], "sitemap_url_count": None}
    try:
        r = requests.get(f"{base_url.rstrip('/')}/robots.txt",
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code == 200:
            result["robots_found"] = True
            for line in r.text.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path:
                        result["disallow"].append(path)
                elif line.lower().startswith("sitemap:"):
                    result["sitemaps"].append(line.split(":", 1)[1].strip())
    except requests.exceptions.RequestException:
        pass

    sitemap_url = result["sitemaps"][0] if result["sitemaps"] else f"{base_url.rstrip('/')}/sitemap.xml"
    try:
        r = requests.get(sitemap_url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code == 200 and "<" in r.text:
            root = ET.fromstring(r.text)
            urls = [e for e in root.iter() if e.tag.endswith("url")]
            sitemaps = [e for e in root.iter() if e.tag.endswith("sitemap")]
            count = len(urls) + len(sitemaps)
            result["sitemap_url_count"] = count
            if sitemap_url not in result["sitemaps"]:
                result["sitemaps"].append(sitemap_url)
    except (requests.exceptions.RequestException, ET.ParseError):
        pass

    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)
def _get_crtsh_json(domain):
    r = requests.get(
        f"https://crt.sh/?q=%.{domain}&output=json",
        headers={"User-Agent": UA}, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_subdomains_crtsh(domain, limit=200):
    try:
        entries = _get_crtsh_json(domain)
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return {"available": False, "subdomains": []}

    found = set()
    for entry in entries:
        for name in entry.get("name_value", "").split("\n"):
            name = name.strip().lower()
            if name and not name.startswith("*.") and name.endswith(domain):
                found.add(name)

    return {"available": True, "subdomains": sorted(found)[:limit], "total_found": len(found)}


def fingerprint_tech(headers, html):
    detected = set()
    header_blob = " ".join(f"{k}: {v}" for k, v in headers.items())
    haystack = (header_blob + " " + html).lower()

    for name, signatures in TECH_SIGNATURES:
        for sig in signatures:
            if sig.lower() in haystack:
                detected.add(name)
                break

    try:
        soup = BeautifulSoup(html, "html.parser")
        gen = soup.find("meta", attrs={"name": "generator"})
        if gen and gen.get("content"):
            detected.add(gen["content"].strip())
    except Exception:
        pass

    return sorted(detected)


def run_full_recon(url, domain, page_headers=None, page_html=""):
    """Runs every passive check and returns one combined dict."""
    return {
        "domain": domain,
        "whois": run_whois(domain),
        "dns": get_dns_records(domain),
        "ssl": get_ssl_info(domain),
        "security_headers": get_security_headers(page_headers or {}),
        "robots": get_robots_and_sitemap(url),
        "subdomains": get_subdomains_crtsh(domain),
        "tech": fingerprint_tech(page_headers or {}, page_html),
    }
