# Chess AI Coach

Note: GitHub repo in progress; Will be updated soon.



A personal chess coaching agent that analyzes your games from Chess.com and Lichess using Stockfish and OpenAI's API to help you improve.

## Features

- Import games from Chess.com and Lichess
- Deep position analysis with Stockfish
- AI-powered coaching insights via OpenAI API
- Track patterns, openings, and improvement areas
- Personalized recommendations based on your play style

## Project Structure

```
chess-coach/
├── src/               # Main application code
├── tests/             # Test suite
├── data/              # Local data storage (gitignored)
├── config/            # Configuration files
├── scripts/           # Utility scripts
└── notebooks/         # Analysis notebooks (optional)
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up configuration
cp config/config.example.yaml config/config.yaml
# Edit config.yaml with your API keys

# Sync your games
python -m src.cli sync --platform lichess --username your_username

# Analyze recent games
python -m src.cli analyze --last 10

# Get coaching insights
python -m src.cli coach --opening "French Defense"
```

## Setup

See [docs/setup.md](docs/setup.md) for detailed installation instructions.

## Architecture

See [docs/architecture.md](docs/architecture.md) for system design overview.
