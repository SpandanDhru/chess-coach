# Architecture Overview

## System Design

The Chess AI Coach follows a layered architecture with four main components:

```
┌─────────────────────────────────────────────────┐
│              User Interface (CLI)               │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│           Coaching Layer (Coach)                │
│  - Aggregate insights                           │
│  - Pattern detection                            │
│  - Recommendations                              │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────┴───────────────────────────────┐
│                                                  │
│  ┌─────────────────┐      ┌──────────────────┐ │
│  │  Analysis Layer │      │  Ingestion Layer │ │
│  ├─────────────────┤      ├──────────────────┤ │
│  │ - Stockfish     │      │ - Chess.com API  │ │
│  │ - LLM Explainer │      │ - Lichess API    │ │
│  │ - Classification│      │ - PGN parsing    │ │
│  └─────────────────┘      └──────────────────┘ │
│                                                  │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│              Storage Layer (Database)            │
│  - Games, Positions, Openings, Patterns         │
└──────────────────────────────────────────────────┘
```

## Components

### 1. Ingestion Layer (`src/ingestion/`)

**Responsibility**: Fetch games from external platforms and normalize them.

**Key classes**:
- `GameIngester` (abstract base)
- `ChessComIngester` - Chess.com public API
- `LichessIngester` - Lichess API

**Data flow**:
1. Fetch games via platform API
2. Parse PGN and extract metadata
3. Normalize to `GameMetadata` format
4. Check for duplicates
5. Save to database

**Rate limiting**: Respects platform rate limits. Chess.com has no auth; Lichess supports API tokens for higher limits.

### 2. Analysis Layer (`src/analysis/`)

**Responsibility**: Analyze positions and generate explanations.

**Components**:

#### StockfishAnalyzer
- Runs Stockfish engine at configurable depth
- Evaluates positions before/after each move
- Calculates centipawn loss
- Classifies moves (best/good/inaccuracy/mistake/blunder)
- Detects missed tactics (mate-in-N)

#### LLMExplainer
- Generates natural language explanations
- Tailored to user's rating level
- Three modes:
  - Position explanations (why was this move bad?)
  - Game summaries (key themes and takeaways)
  - Coaching reports (aggregate insights)

**Data flow**:
1. Parse PGN with `python-chess`
2. For each position:
   - Run Stockfish analysis
   - Get top 3 moves + evaluations
   - Calculate centipawn loss
   - Classify move quality
3. Identify critical moments (blunders, missed tactics)
4. Generate LLM explanations for critical positions
5. Save analysis to database

**Cost optimization**: Only call LLM for:
- Blunders and major mistakes
- Game summaries
- Coaching reports
NOT for every move (would be expensive).

### 3. Storage Layer (`src/storage/`)

**Responsibility**: Persist and query game data.

**Schema**:

```sql
games
  - game_id (unique)
  - platform, username, color
  - opponent info
  - result, time_control, played_at
  - opening (ECO code + name)
  - pgn (full game text)

positions
  - game_id (FK)
  - move_number, fen, move_played
  - evaluations (before, after, loss)
  - best_move, top_3_moves
  - classification, is_blunder
  - explanation (LLM-generated)

openings
  - eco_code (unique)
  - name
  - games played (as white/black)
  - win/draw/loss counts
  - average centipawn loss

patterns
  - pattern_type (tactical, positional, etc.)
  - description
  - occurrence_count, severity
  - phase (opening/middlegame/endgame)
  - example games
  - coaching advice

sync_state
  - platform, username
  - last_synced_at
```

**Queries**:
- Recent games
- Blunders for review
- Opening statistics
- Pattern detection
- Aggregate metrics

### 4. Coaching Layer (`src/coaching/`)

**Responsibility**: Transform raw analysis into actionable insights.

**Coach class methods**:
- `get_improvement_areas()` - Top 3-5 weaknesses
- `analyze_opening()` - Opening-specific advice
- `review_recent_games()` - Quick summaries
- `detect_patterns()` - Recurring mistakes

**Pattern detection**:
Identifies recurring themes like:
- "Hangs pieces in middlegame under time pressure"
- "Plays too passively in French Defense"
- "Misses back-rank tactics"
- "Poor endgame technique with rooks"

## Data Flow: Complete Analysis Cycle

1. **User runs**: `python -m src.cli sync --platform lichess --username alice`
   - Lichess API fetches games since last sync
   - Games normalized and saved to DB

2. **User runs**: `python -m src.cli analyze --last 10`
   - Fetch 10 most recent games from DB
   - For each game:
     - Stockfish analyzes every position
     - Move classifications stored
     - Critical moments identified
   - LLM generates explanations for blunders
   - Analysis saved to DB

3. **User runs**: `python -m src.cli coach --opening "French Defense"`
   - Query all French Defense games
   - Aggregate statistics (win rate, avg CP loss)
   - Find common mistakes in first 15 moves
   - LLM generates coaching report with:
     - Strengths/weaknesses
     - Specific recommendations
     - Example positions

## Technology Choices

**Why SQLite?**
- No server setup needed
- Good enough for personal use (1000s of games)
- Simple file-based backup
- Can migrate to PostgreSQL if needed

**Why Stockfish locally?**
- Free, fast, strong
- No API costs
- Consistent evaluation
- Full control over depth

**Why LLM for coaching?**
- Converts raw evals into human language
- Contextual advice based on rating
- Identifies strategic/tactical themes
- Personalizes recommendations

**Why separate analysis from explanation?**
- Stockfish is deterministic and cheap
- LLM is expensive and variable
- Can run bulk Stockfish analysis, then selectively explain
- Can regenerate explanations without re-analyzing

## Performance Characteristics

**Ingestion**: ~1-2 seconds per game (network dependent)

**Analysis**: 
- Stockfish: ~0.5-2 seconds per position at depth 20
- Full game (40 moves): ~30-60 seconds
- Batch 100 games: ~1 hour

**LLM calls**:
- Position explanation: ~2-5 seconds, ~$0.001-0.01
- Game summary: ~5-10 seconds, ~$0.01-0.05
- Coaching report: ~10-30 seconds, ~$0.05-0.20

**Costs** (rough estimate):
- Analyzing 100 games with GPT-4o-mini explanations: ~$2-5
- Monthly with 50 games: ~$1-3

## Extension Points

This architecture makes it easy to add:
- Web UI (FastAPI frontend)
- More platforms (chess24, ICC)
- Better pattern detection (ML clustering)
- Interactive training mode
- Spaced repetition for tactics
- Opening repertoire builder
