"""
entities.py — extract structured entities from search queries and results.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Optional

from knowledge.storage import MemoryStorage


class EntityExtractor:
    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    def extract_from_query(self, query: str) -> list[dict]:
        entities: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for kind, value in self._extract_domains(query):
            key = (kind, value)
            if key not in seen:
                seen.add(key)
                entities.append({"kind": kind, "value": value, "context": query})
        for kind, value in self._extract_github_repos(query):
            key = (kind, value)
            if key not in seen:
                seen.add(key)
                entities.append({"kind": kind, "value": value, "context": query})
        for kind, value in self._extract_technologies(query):
            key = (kind, value)
            if key not in seen:
                seen.add(key)
                entities.append({"kind": kind, "value": value, "context": query})

        return entities

    def extract_and_store(self, query: str) -> list[dict]:
        entities = self.extract_from_query(query)
        for ent in entities:
            self.storage.upsert_entity(ent["kind"], ent["value"], ent.get("context", ""))
        return entities

    def _extract_domains(self, text: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        domain_pattern = re.compile(
            r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
        )
        for match in domain_pattern.finditer(text):
            domain = match.group(0).lower()
            if domain in ("example.com", "test.com"):
                continue
            if domain.endswith(".png") or domain.endswith(".jpg") or domain.endswith(".gif"):
                continue
            try:
                ipaddress.ip_address(domain)
                continue
            except ValueError:
                pass
            results.append(("domain", domain))

        ip_pattern = re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b'
        )
        for match in ip_pattern.finditer(text):
            ip = match.group(0)
            try:
                ipaddress.ip_address(ip)
                if not ipaddress.ip_address(ip).is_private:
                    results.append(("ip", ip))
            except ValueError:
                pass

        return results

    def _extract_github_repos(self, text: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        github_pattern = re.compile(r'github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)')
        for match in github_pattern.finditer(text):
            owner, repo = match.group(1), match.group(2)
            if owner in ("topics", "trending", "search", "settings", "notifications"):
                continue
            results.append(("github_repo", f"{owner}/{repo}"))
        return results

    def _extract_technologies(self, text: str) -> list[tuple[str, str]]:
        text_lower = text.lower()
        results: list[tuple[str, str]] = []

        tech_keywords = {
            "linux": ["linux", "ubuntu", "debian", "fedora", "arch", "centos", "rhel", "kali"],
            "windows": ["windows", "microsoft", "win32", "win64", "powershell"],
            "macos": ["macos", "mac os", "os x", "apple"],
            "android": ["android", "apk", "adb"],
            "ios": ["ios", "iphone", "ipad", "xcode"],
            "python": ["python", "pip", "pypi", "django", "flask", "fastapi"],
            "javascript": ["javascript", "js", "node.js", "npm", "react", "vue", "angular"],
            "rust": ["rust", "cargo", "rustc"],
            "go": ["golang", "go lang"],
            "java": ["java", "jvm", "spring"],
            "docker": ["docker", "container", "dockerfile", "kubernetes", "k8s"],
            "git": ["git", "github", "gitlab", "bitbucket"],
            "database": ["sql", "mysql", "postgres", "mongodb", "redis", "sqlite"],
            "cloud": ["aws", "azure", "gcp", "cloud"],
            "security": ["cve", "vulnerability", "exploit", "security", "hacker", "pentest"],
            "networking": ["dns", "http", "https", "ssh", "tcp", "udp", "vpn", "firewall"],
            "ai": ["ai", "ml", "machine learning", "deep learning", "neural", "openai", "llm"],
        }

        for category, keywords in tech_keywords.items():
            if any(kw in text_lower for kw in keywords):
                results.append(("technology", category))

        return results
