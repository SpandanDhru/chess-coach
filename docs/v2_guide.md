# Chess Coach — v2 Guide

v2 evolves the v1 `sync → analyze → coach` pipeline (Chess.com → Stockfish → OpenAI)
into three new capabilities: **multi-platform incremental sync**, a **persistent
mistake-pattern model**, and a **semantic-embeddings RAG** coaching mode.

All four phases are built, tested (46 passing unit tests), and verified live end-to-end.

---

## What shipped

### Phase 1 — Multi-platform incremental sync
- New `LichessIngester` (Lichess NDJSON export API, optional `LICHESS_TOKEN`), normalized
  into the same `GameMetadata` shape as Chess.com — one unified format.
- `sync` routes per-platform, supports `--all-platforms`, and is **incremental** via the
  stored `last_synced_at` (a re-sync pulls only new games). `--full` walks the entire
  history; `speed_bucket()` normalizes each platform's time control into one scale.

### Phase 2 — Aggregation + persistent patterns
- `aggregate_by_opening / phase / time_control` in `database.py`.
- `save_pattern` is now an **upsert**; `Coach.detect_and_persist_patterns` writes the
  `patterns` table idempotently (re-runs only add newly analyzed games, never double-count).

### Phase 3 — Semantic RAG (the learning centerpiece)
- `src/coaching/knowledge.py`, with every stage explicit:
  build docs → embed (OpenAI `text-embedding-3-small`, one batched call) →
  store vectors in a **SQLite `embeddings` table** → retrieve by hand-written
  **numpy cosine similarity** → augment + generate.
- Commands: `index` (build the knowledge base) and `ask "…" --show-sources` (answer a
  natural-language question and print the retrieved chunks + similarity scores).

### Phase 4 — Two-tier explanations
- `Coach.explain_critical_mistakes` (capped at `CRITICAL_EXPLANATIONS`, cached in
  `Position.explanation`), wired to `coach --game-id --explain`.
- Stockfish does *all* per-position evaluation; the LLM is spent only on the few most
  costly mistakes and on coaching prose/answers.

**SQLite stays the single system of record** — the vector store is just a derived table
inside it.

---

## Command reference by platform

The pipeline is the same for both platforms; only the `--platform` flag (and which
`.env` default handle is used) changes. `--username` overrides the default and can be
**any** public account on that platform.

### Chess.com

```bash
# Sync recent games (incremental after the first run)
python -m src.cli sync --platform chesscom --username hikaru

# Pull the full history the first time (needed to reach 500+ games)
python -m src.cli sync --platform chesscom --username hikaru --full

# Analyze just that player's games with Stockfish (no OpenAI cost)
python -m src.cli analyze --username hikaru

# Detect + persist recurring mistake patterns (no OpenAI cost)
python -m src.cli coach --patterns --username hikaru

# Build the RAG knowledge base, then ask questions
python -m src.cli index --username hikaru
python -m src.cli ask "what openings do I struggle with?" --username hikaru --show-sources

# Coaching writeup for one game, with per-move explanations of the worst mistakes
python -m src.cli coach --game-id <game-id> --explain
```

> `--platform chesscom` is the default, so you can drop it: `sync --username hikaru`.
> If `CHESS_COM_USERNAME` is set in `.env`, `--username` is optional too.

### Lichess

```bash
# Sync recent games (incremental after the first run)
python -m src.cli sync --platform lichess --username DrNykterstein

# Pull the full history the first time
python -m src.cli sync --platform lichess --username DrNykterstein --full

# Everything downstream is identical — scope by the same handle
python -m src.cli analyze --username DrNykterstein
python -m src.cli coach --patterns --username DrNykterstein
python -m src.cli index --username DrNykterstein
python -m src.cli ask "which time control do I play worst in?" --username DrNykterstein --show-sources
python -m src.cli coach --game-id <game-id> --explain
```

> `--platform lichess` is required (chesscom is the default). Reads work anonymously;
> set `LICHESS_TOKEN` in `.env` (a free personal access token) to raise rate limits for
> large `--full` syncs.

### Both platforms at once

```bash
# Sync Chess.com AND Lichess in one run.
# Uses CHESS_COM_USERNAME / LICHESS_USERNAME from .env for each platform...
python -m src.cli sync --all-platforms

# ...or force the same handle on both (e.g. you use the same name everywhere)
python -m src.cli sync --all-platforms --username magnus

# Games from both sources land in the same database and aggregate together.
python -m src.cli stats --username magnus
```

---

## Notes on flags

| Flag | Applies to | Meaning |
|------|-----------|---------|
| `--platform {chesscom,lichess}` | `sync` | Source platform (default `chesscom`). |
| `--all-platforms` | `sync` | Sync both platforms in one run. |
| `--full` | `sync` | Ignore the incremental bound and fetch entire history. |
| `--limit N` | `sync` | Max games per platform (default 20, or all with `--full`). |
| `--username <handle>` | most commands | Scope to one player (any public account). |
| `--show-sources` | `ask` | Print retrieved chunks + cosine scores. |
| `--explain` | `coach --game-id` | Add per-move explanations of the worst mistakes. |

## Cost discipline
- `sync`, `analyze`, and `coach --patterns` make **no OpenAI calls** (Stockfish + SQL only).
- `index` = one batched embedding call (bounded by document count, not game count).
- Each `ask` = one embedding + one completion.
- `coach --game-id` = one completion; `--explain` adds up to `CRITICAL_EXPLANATIONS`
  (default 3), cached so re-runs cost nothing for already-explained moves.

---

## Quickstart with your own account

**No code changes are needed** if your `.env` already has `OPENAI_API_KEY`,
`STOCKFISH_PATH` (or a Stockfish binary on PATH), and — optionally —
`CHESS_COM_USERNAME`. Just pass `--username <your handle>` to point any command at your
account (it overrides the `.env` default for that run).

Full run-through, in order (example handle: `sinkhulz`):

```bash
# 1. Pull your recent games (incremental after the first run). Chess.com is the
#    default, so no --platform needed.
python -m src.cli sync --username sinkhulz

#    First time, to pull your full history (toward a bigger corpus):
python -m src.cli sync --username sinkhulz --full

# 2. Analyze your games with Stockfish (no OpenAI cost)
python -m src.cli analyze --username sinkhulz

# 3. See your record / openings / how many are analyzed
python -m src.cli stats --username sinkhulz

# 4. Detect + save your recurring mistake patterns (no OpenAI cost)
python -m src.cli coach --patterns --username sinkhulz

# 5. Build the RAG knowledge base, then ask it questions
python -m src.cli index --username sinkhulz
python -m src.cli ask "what openings do I struggle with?" --username sinkhulz --show-sources
python -m src.cli ask "which time control do I play worst in?" --username sinkhulz --show-sources

# 6. Deep-dive one game: coaching writeup + explanations of the worst moments.
#    Grab a <game-id> from step 3's output.
python -m src.cli coach --game-id <game-id> --explain
```

Notes:
- **Order matters**: `ask` needs `index` first, and `index` only has useful content after
  `analyze` (and ideally `coach --patterns`). So the flow is
  sync → analyze → patterns → index → ask.
- Since `CHESS_COM_USERNAME` is set in `.env`, if you set it to your handle you can drop
  `--username` entirely (`python -m src.cli sync`). Passing `--username sinkhulz` explicitly
  works regardless of the default.
- Only steps 5 and 6 spend OpenAI credits (fractions of a cent each); steps 1–4 are free.
