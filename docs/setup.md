# Setup Guide

## Prerequisites

- Python 3.9 or higher
- Stockfish chess engine installed
- OpenAI API key

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd chess-coach
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Stockfish

**Ubuntu/Debian:**
```bash
sudo apt-get install stockfish
```

**macOS (Homebrew):**
```bash
brew install stockfish
```

**Windows:**
Download from [stockfishchess.org](https://stockfishchess.org/download/) and note the path to the executable.

### 5. Configure the application

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` and update:
- `openai.api_key` - Your OpenAI API key
- `stockfish.path` - Path to Stockfish binary
- `lichess.username` and/or `chesscom.username` - Your usernames
- `user.rating` - Your approximate rating

### 6. Verify installation

```bash
# Test Stockfish
stockfish

# Test the CLI
python -m src.cli --help
```

## Getting Started

### Sync your games

```bash
# From Lichess
python -m src.cli sync --platform lichess --username your_username

# From Chess.com
python -m src.cli sync --platform chesscom --username your_username
```

### Analyze games

```bash
# Analyze last 10 games
python -m src.cli analyze --last 10

# Analyze a specific game
python -m src.cli analyze --game-id abc123
```

### Get coaching insights

```bash
# Review recent games
python -m src.cli coach --recent 5

# Get advice for an opening
python -m src.cli coach --opening "French Defense"

# Detect patterns in your play
python -m src.cli coach --patterns
```

### View statistics

```bash
python -m src.cli stats
```

## Configuration Options

See `config/config.example.yaml` for all available configuration options.

### Key settings:

- **analysis.depth**: Stockfish analysis depth (18-22 recommended)
  - Lower = faster but less accurate
  - Higher = slower but catches more subtle mistakes
  
- **openai.model**: Choose between cost and quality
  - `gpt-4o-mini` - Cheaper, good for most explanations
  - `gpt-4o` - More expensive, better for complex positions

## Troubleshooting

### "Stockfish not found"
Update `stockfish.path` in your config to point to the correct binary location.

### "OpenAI API error"
Check that your API key is correct and you have credits available.

### "No games found"
Verify your username is correct and you have public games available.
