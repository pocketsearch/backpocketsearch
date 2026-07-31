# pocketSearch — Decisions Log

Format: `YYYY-MM-DD: what changed / what was decided, and why`

## 2026-07-31
- Removed run.py, app/__init__.py, app/routes.py — dead Blueprint skeleton, never
  wired in, actually broken (app/ package shadowed app.py in imports).
- Removed src/intent/ (classifier.py, safety.py, seed_intents.json) and
  src/retrieval/orchestrator.py — prototype intent classifier + safety layer,
  never imported by app.py or knowledge/. Not resurrected as-is if intent
  classification is wanted later — needs proper design + wiring into /go.
- Removed static/style.css.bak — stale, diverged from live style.css.
- Confirmed app.py is the sole entry point. run.py pattern will not be revisited
  unless there's a specific reason to split into Blueprints.

## 2026-07-31 (cont.)
- Removed docs/metadata_schema.md — described metadata fields (content_hash, aliases,
  popularity) for "intent-aware ranking," but grep confirmed zero usage anywhere in
  knowledge/, app.py, or recon.py. Written for the already-removed intent classifier,
  never consumed by anything live.
- webscope.db filename is a holdover, not naming drift: WebScope was a separate project
  being built in parallel, later merged into pocketSearch to avoid duplicating work.
  Never renamed post-merge. Not a bug, not inconsistency to fix.
