#!/usr/bin/env python3
"""Lightweight intent classifier prototype.

Behavior: load seed intents (JSON), build keyword->intent index, and score a query
by keyword overlap. Returns ranked intents, inferred tags, and expanded query terms.

This is dependency-free and suitable as a starting point for an ML-backed classifier.
"""
import json
import sys
import os
import re
from collections import Counter, defaultdict

BASE = os.path.dirname(__file__)
SEED = os.path.join(BASE, 'seed_intents.json')

WORD_RE = re.compile(r"\w+")

class IntentClassifier:
    def __init__(self, seed_path=SEED):
        with open(seed_path, 'r', encoding='utf-8') as f:
            self.intents = json.load(f)
        # build inverted keyword index
        self.keyword_index = defaultdict(set)
        for intent, data in self.intents.items():
            for kw in data.get('keywords', []):
                self.keyword_index[kw.lower()].add(intent)

    def _tokens(self, text):
        return [t.lower() for t in WORD_RE.findall(text)]

    def predict(self, query):
        tokens = self._tokens(query)
        token_counts = Counter(tokens)
        intent_scores = defaultdict(float)
        # keyword overlap scoring
        for token, count in token_counts.items():
            if token in self.keyword_index:
                intents = self.keyword_index[token]
                for intent in intents:
                    # simple additive score; later replace with TF-IDF or learned weights
                    intent_scores[intent] += 1.0 * count
        # normalize by intent keyword set size
        norm_scores = {}
        for intent, raw in intent_scores.items():
            kws = self.intents[intent].get('keywords', [])
            denom = max(len(kws), 1)
            norm_scores[intent] = raw / denom
        # fallback: if no keyword hits, use example token overlap
        if not norm_scores:
            for intent, data in self.intents.items():
                score = 0.0
                for ex in data.get('examples', []):
                    for t in self._tokens(ex):
                        if t in token_counts:
                            score += 0.5
                if score > 0:
                    norm_scores[intent] = score
        # sort
        ranked = sorted(norm_scores.items(), key=lambda x: x[1], reverse=True)
        # derive tags and expanded terms: union of top intent keywords + aliases
        expanded = []
        inferred_tags = []
        for intent, score in ranked:
            data = self.intents[intent]
            inferred_tags.extend(data.get('tags', []))
            expanded.extend(data.get('keywords', [])[:10])
            expanded.extend(data.get('aliases', [])[:5])
        # dedupe while preserving order
        def dedupe(seq):
            seen = set()
            out = []
            for s in seq:
                if s not in seen:
                    seen.add(s)
                    out.append(s)
            return out
        return {
            'query': query,
            'tokens': tokens,
            'ranked_intents': [{'intent': i, 'score': s} for i, s in ranked],
            'inferred_tags': dedupe(inferred_tags),
            'expanded_query_terms': dedupe(expanded)[:50]
        }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: classifier.py "your query here"')
        sys.exit(1)
    q = ' '.join(sys.argv[1:])
    c = IntentClassifier()
    out = c.predict(q)
    print(json.dumps(out, indent=2))
