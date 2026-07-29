# Document Metadata Schema

Purpose: provide rich, consistent metadata for each knowledge article to support intent-aware ranking, filtering, and query expansion.

Fields:
- id: string (unique)
- title: string
- description: string (short summary)
- category: string (e.g., Programming, Security, UI/UX, Networking)
- tags: array[string] (granular topics)
- aliases: array[string] (alternative query phrases)
- difficulty: string (Beginner | Intermediate | Advanced)
- type: string (Documentation | Tutorial | Reference | Example | Template | Video | Article)
- authors: array[string]
- updated: ISO8601 date
- popularity: number (e.g., views or score)
- content_hash: string (for freshness checks)
- related: array[id] (related documents)

Example (YAML):

id: doc-code-gen-001
title: Python Code Generation Guide
description: Guide to generating Python code using LLMs with examples and best practices.
category: Programming
tags: [python, code-generation, llm, examples]
aliases: ["generate code", "write python"]
difficulty: Intermediate
type: Tutorial
authors: ["Jane Doe"]
updated: 2026-07-30T00:00:00Z
popularity: 1245
content_hash: 9f86d081884c7d659a2feaa0c55ad015
related: [doc-llm-best-practices]

Notes:
- Keep tags and aliases curated to improve query expansion.
- Record difficulty and type to aid search-mode ranking (tutorial vs reference).
- Ensure updated and popularity are refreshed by ingestion pipeline.