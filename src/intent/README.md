Intent classifier prototype

Files:
- seed_intents.json: seed examples, keywords, tags, aliases for each intent.
- classifier.py: dependency-free rule-based prototype. Run:

  python src/intent/classifier.py "code generation"

Output: JSON with ranked_intents, inferred_tags, and expanded_query_terms.

Next steps:
- Replace rule-based logic with a trained ML classifier (fine-tune on labeled queries).
- Add a small training harness and evaluation dataset.
- Wire classifier output into query expansion and retrieval pipeline.
