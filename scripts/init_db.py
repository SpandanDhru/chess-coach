#!/usr/bin/env python3
"""Utility script to initialize the database schema."""

from pathlib import Path
from src.storage.database import Database


def main():
    """Initialize the database with schema."""
    db_path = Path("data/chess_coach.db")
    
    print(f"Initializing database at {db_path}")
    
    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create database (this will create all tables)
    db = Database(str(db_path))
    
    print("✓ Database initialized successfully")
    print(f"  Location: {db_path.absolute()}")


if __name__ == "__main__":
    main()
