# Chess AI Coach - Repository Structure

```
chess-coach/
│
├── README.md                       # Project overview and quick start
├── LICENSE                         # MIT License
├── requirements.txt                # Python dependencies
├── .gitignore                      # Git ignore patterns
│
├── config/                         # Configuration files
│   └── config.example.yaml         # Example configuration (copy to config.yaml)
│
├── docs/                           # Documentation
│   ├── setup.md                    # Installation and setup guide
│   ├── architecture.md             # System design and architecture
│   └── development.md              # Development notes and roadmap
│
├── src/                            # Main application code
│   ├── __init__.py
│   ├── cli.py                      # Command-line interface entry point
│   │
│   ├── ingestion/                  # Game ingestion from platforms
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract base ingester
│   │   ├── chesscom.py             # Chess.com API client
│   │   └── lichess.py              # Lichess API client
│   │
│   ├── analysis/                   # Position and game analysis
│   │   ├── __init__.py
│   │   ├── models.py               # Data models for analysis
│   │   ├── stockfish_analyzer.py   # Stockfish engine wrapper
│   │   └── llm_explainer.py        # OpenAI API for explanations
│   │
│   ├── storage/                    # Database layer
│   │   ├── __init__.py
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   └── database.py             # Database operations
│   │
│   └── coaching/                   # Coaching insights and recommendations
│       ├── __init__.py
│       └── coach.py                # High-level coaching interface
│
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── unit/                       # Unit tests
│   │   └── test_stockfish_analyzer.py
│   └── integration/                # Integration tests
│
├── scripts/                        # Utility scripts
│   └── init_db.py                  # Initialize database schema
│
├── data/                           # Local data storage (gitignored)
│   ├── games/                      # Raw game data cache
│   ├── analysis/                   # Analysis results
│   └── cache/                      # Temporary cache files
│
└── notebooks/                      # Jupyter notebooks (optional)
    └── (exploratory analysis)
```

## Quick Reference

### Main Commands

```bash
# Sync games
python -m src.cli sync --platform lichess --username YOUR_USERNAME

# Analyze games
python -m src.cli analyze --last 10

# Get coaching insights
python -m src.cli coach --opening "French Defense"
python -m src.cli coach --recent 5
python -m src.cli coach --patterns

# View statistics
python -m src.cli stats
```

### Key Files to Implement First

1. `src/storage/database.py` - Complete database operations
2. `src/analysis/stockfish_analyzer.py` - Stockfish integration
3. `src/ingestion/lichess.py` - Lichess API implementation
4. `src/analysis/llm_explainer.py` - OpenAI integration
5. `src/coaching/coach.py` - Coaching logic

### Configuration

Copy `config/config.example.yaml` to `config/config.yaml` and update:
- OpenAI API key
- Stockfish path
- Your usernames on chess platforms
- Your rating for explanation calibration

### Database Schema

See `src/storage/models.py` for the complete schema:
- `games` - Game metadata and PGN
- `positions` - Position-by-position analysis
- `openings` - Opening statistics
- `patterns` - Recurring mistake patterns
- `sync_state` - Sync status tracking

## Development Workflow

1. Set up environment (see `docs/setup.md`)
2. Configure application (copy example config)
3. Initialize database (`python scripts/init_db.py`)
4. Implement ingestion layer
5. Implement analysis layer
6. Implement coaching layer
7. Add tests as you go
8. Iterate on prompts and insights

See `docs/development.md` for detailed implementation roadmap.
