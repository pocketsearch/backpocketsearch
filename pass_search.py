import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import knowledge as knowledge

logger = logging.getLogger("webscope.intent")

DOMAIN_RE = re.compile(
    r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.I,
)

OWNER_REPO_RE = re.compile(r"^[\w-]+/[\w.-]+$")

CODE_EXT_RE = re.compile(
    r"\.(?:js|ts|py|go|rs|java|rb|php|c|cpp|cs)$",
    re.I,
)

CODE_KEYWORDS = (
    "npm",
    "pypi",
    "package",
    "library",
    "sdk",
    "api",
    "repo",
    "github",
    "framework",
    "dependency",
)

PERSON_TOKEN_RE = re.compile(r"^[A-Z][a-z]+$")

PERSON_DENYLIST = {
    "Best Coffee Shops",
    "New York City",
    "United States",
    "United Kingdom",
    "South Australia",
    "Western Australia",
    "New South Wales",
    "Search Engine Optimization",
    "Artificial Intelligence",
    "Machine Learning",
    "Computer Science",
    "Open Source Software",
}

VALID_MODES = {"auto", "domain", "person", "code"}


def normalized_domain_candidate(query):
    raw = (query or "").strip()

    raw = re.sub(r"^https?://", "", raw, flags=re.I)
    raw = raw.split("/", 1)[0]
    raw = raw.split("?", 1)[0]
    raw = raw.split("#", 1)[0]

    if ":" in raw:
        host, maybe_port = raw.rsplit(":", 1)
        if maybe_port.isdigit():
            raw = host

    return raw.lower().rstrip(".")


def classify_intent(query, requested_mode="auto"):
    """
    PASS ordered classifier.

    auto:
      1. domain
      2. code
      3. person
      4. general

    Explicit UI modes override auto classification.
    """

    query = (query or "").strip()
    requested_mode = (requested_mode or "auto").lower()

    if requested_mode not in VALID_MODES:
        requested_mode = "auto"

    if requested_mode != "auto":
        intent = requested_mode
        logger.info(
            "intent query=%r assigned=%s reason=explicit-mode",
            query,
            intent,
        )
        return intent

    # STEP 1 — DOMAIN
    candidate = normalized_domain_candidate(query)

    if DOMAIN_RE.fullmatch(candidate):
        intent = "domain"
        logger.info(
            "intent query=%r assigned=%s reason=domain-regex",
            query,
            intent,
        )
        return intent

    # STEP 2 — CODE
    lower = query.lower()

    owner_repo = (
        " " not in query
        and "/" in query
        and OWNER_REPO_RE.fullmatch(query) is not None
    )

    extension_match = CODE_EXT_RE.search(query) is not None

    keyword_match = any(
        re.search(rf"\b{re.escape(keyword)}\b", lower, re.I)
        for keyword in CODE_KEYWORDS
    )

    if owner_repo or extension_match or keyword_match:
        intent = "code"
        logger.info(
            "intent query=%r assigned=%s reason=code-heuristic",
            query,
            intent,
        )
        return intent

    # STEP 3 — PERSON
    tokens = query.split()

    person_shape = (
        2 <= len(tokens) <= 4
        and all(PERSON_TOKEN_RE.fullmatch(token) for token in tokens)
        and query not in PERSON_DENYLIST
    )

    if person_shape:
        intent = "person"
        logger.info(
            "intent query=%r assigned=%s reason=person-shape",
            query,
            intent,
        )
        return intent

    # STEP 4 — GENERAL
    intent = "general"

    logger.info(
        "intent query=%r assigned=%s reason=default",
        query,
        intent,
    )

    return intent


def _unique(items):
    output = []
    seen = set()

    for item in items or []:
        if not item:
            continue

        url = item.get("url", "")
        title = item.get("title", "").strip().lower()

        key = url or title

        if not key or key in seen:
            continue

        seen.add(key)
        output.append(item)

    return output


def _source_count(results):
    return len(
        {
            item.get("source")
            for item in results
            if item.get("source")
        }
    )


def _analysis_allowed(results):
    return _source_count(results) >= 3


def _entity_match_count(query, results):
    """
    Basic entity matching for person intent.

    At least two distinct sources must contain enough of the
    person's name in title/snippet text.
    """

    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z]+", query)
        if len(token) > 1
    ]

    if not tokens:
        return 0

    matching_sources = set()

    for item in results:
        text = (
            str(item.get("title", ""))
            + " "
            + str(item.get("snippet", ""))
        ).lower()

        matched = sum(token in text for token in tokens)

        # Require surname + at least one other name token where possible.
        needed = 2 if len(tokens) >= 2 else 1

        if matched >= needed and item.get("source"):
            matching_sources.add(item["source"])

    return len(matching_sources)


def build_analysis(query, results, intent):
    source_count = _source_count(results)

    analysis = {
        "intent": intent,
        "source_count": source_count,
        "show_analysis": False,
        "contradictions": [],
        "consensus": None,
        "bias": [],
        "overlooked": [],
        "fallback_label": None,
    }

    if intent == "domain":
        return analysis

    if source_count < 3:
        return analysis

    if intent == "person" and _entity_match_count(query, results) < 2:
        return analysis

    analysis["show_analysis"] = True

    contradictions = knowledge.detect_contradictions(results)
    consensus = knowledge.calculate_consensus(results)
    bias = [knowledge.detect_bias(item) for item in results]
    overlooked = knowledge.extract_overlooked_facts(results)

    # Cross-cutting PASS rule:
    # modules with <= 1 meaningful data point disappear.
    if len(contradictions) >= 2:
        analysis["contradictions"] = contradictions

    if consensus and consensus.get("total_sources", 0) >= 3:
        analysis["consensus"] = consensus

    if len(bias) >= 2:
        analysis["bias"] = bias

    if len(overlooked) >= 2:
        analysis["overlooked"] = overlooked

    return analysis


def search_code(query, web_search):
    """
    CODE allowlist:
      GitHub repositories
      npm
      PyPI

    General web search runs ONLY when all code-specific sources
    return zero results.
    """

    tasks = {
        "github": lambda: knowledge.github_search(query, limit=8),
        "npm": lambda: knowledge.npm_search(query, limit=8),
        "pypi": lambda: knowledge.pypi_search(query, limit=8),
    }

    collected = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fn): name
            for name, fn in tasks.items()
        }

        for future in as_completed(futures):
            name = futures[future]

            try:
                collected.extend(future.result() or [])
            except Exception as exc:
                logger.warning(
                    "code source=%s query=%r failed=%s",
                    name,
                    query,
                    exc,
                )

    collected = _unique(collected)

    if collected:
        # GitHub API is already star-sorted.
        # npm registry is relevance-ranked.
        # PyPI retains registry ordering.
        priority = {
            "GitHub": 0,
            "NPM": 1,
            "PyPI": 2,
        }

        collected.sort(
            key=lambda item: priority.get(
                item.get("source", ""),
                99,
            )
        )

        return collected[:12], False, 0

    started = time.perf_counter()

    try:
        fallback, web_ms = web_search(query)
    except Exception:
        fallback = []
        web_ms = int((time.perf_counter() - started) * 1000)

    for item in fallback:
        item.setdefault("source", "Web")
        item["code_fallback"] = True

    return _unique(fallback)[:8], True, web_ms


def search_person(query, web_search):
    """
    PERSON allowlist.

    The current application has no dedicated authenticated social/
    professional APIs. Therefore this uses its existing web-result
    provider for attributable public mentions rather than calling
    Wikipedia/GitHub/HN/etc.
    """

    try:
        results, elapsed = web_search(query)
    except Exception:
        results, elapsed = [], 0

    for item in results:
        item.setdefault("source", "Web")

    return _unique(results)[:10], elapsed


def search_general(query, web_search, rank_results):
    """
    GENERAL:
      existing web ranking + existing knowledge sources
      final rendered result set capped at eight.
    """

    started = time.perf_counter()

    try:
        web_results, web_ms = web_search(query)
    except Exception:
        web_results, web_ms = [], 0

    try:
        enriched = knowledge.enrich_query(query).get("results", [])
    except Exception:
        enriched = []

    combined = _unique((enriched or []) + (web_results or []))

    try:
        combined = rank_results(combined, query)
    except Exception:
        pass

    elapsed = web_ms or int((time.perf_counter() - started) * 1000)

    return combined[:8], elapsed


def run_search(query, intent, web_search, rank_results):
    if intent == "code":
        results, fallback, elapsed = search_code(
            query,
            web_search,
        )

        analysis = build_analysis(
            query,
            results,
            intent,
        )

        if fallback:
            analysis["fallback_label"] = (
                "No code-specific results — showing general results."
            )

        return results, analysis, elapsed

    if intent == "person":
        results, elapsed = search_person(
            query,
            web_search,
        )

        return (
            results,
            build_analysis(query, results, intent),
            elapsed,
        )

    results, elapsed = search_general(
        query,
        web_search,
        rank_results,
    )

    return (
        results,
        build_analysis(query, results, intent),
        elapsed,
    )
