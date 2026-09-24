#!/usr/bin/env python3
"""Utility script to initialize the database schema.

Idempotent and safe to re-run: ``Database.__init__`` calls
``Base.metadata.create_all`` which only creates missing tables.

The DB path comes from the ``DB_PATH`` env var (loaded from .env if present),
falling back to the same default the CLI uses. This script deliberately does not
require the OpenAI / Chess.com credentials — you can set up the schema first.
"""

import os
import sys
from pathlib import Path

# Make the project root importable when run as `python scripts/init_db.py`
# (Python otherwise puts scripts/ on sys.path, not the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.storage.database import Database


def main():
    """Initialize the database with schema."""
    load_dotenv()
    db_path = Path(os.getenv("DB_PATH", "data/chess_coach.db"))

    print(f"Initializing database at {db_path}")

    # Ensure data directory exists (Database also does this, kept for clarity).
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create database (this will create all tables if they don't exist).
    Database(str(db_path))

    print("✓ Database initialized successfully")
    print(f"  Location: {db_path.absolute()}")


if __name__ == "__main__":
    main()
