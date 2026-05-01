"""Command-line interface for chess coach."""

import click
from pathlib import Path
import yaml

from .storage.database import Database
from .ingestion import ChessComIngester, LichessIngester
from .analysis import StockfishAnalyzer, LLMExplainer
from .coaching import Coach


@click.group()
@click.pass_context
def cli(ctx):
    """Chess AI Coach - Improve your game with AI-powered analysis."""
    # Load configuration
    config_path = Path("config/config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}
    
    # Initialize database
    db = Database(config.get("database", {}).get("path", "data/chess_coach.db"))
    
    # Store in context for subcommands
    ctx.obj = {
        "config": config,
        "db": db,
    }


@cli.command()
@click.option("--platform", type=click.Choice(["lichess", "chesscom"]), required=True)
@click.option("--username", required=True)
@click.option("--limit", type=int, help="Maximum games to fetch")
@click.pass_context
def sync(ctx, platform, username, limit):
    """Sync games from a platform."""
    click.echo(f"Syncing games from {platform} for {username}...")
    
    # TODO: Implement
    # 1. Initialize appropriate ingester
    # 2. Fetch games
    # 3. Save to database
    # 4. Display summary
    
    click.echo("Not yet implemented!")


@cli.command()
@click.option("--game-id", help="Analyze specific game by ID")
@click.option("--last", type=int, help="Analyze last N games")
@click.pass_context
def analyze(ctx, game_id, last):
    """Analyze games with Stockfish."""
    
    if game_id:
        click.echo(f"Analyzing game {game_id}...")
    elif last:
        click.echo(f"Analyzing last {last} games...")
    else:
        click.echo("Please specify --game-id or --last N")
        return
    
    # TODO: Implement
    # 1. Initialize Stockfish analyzer
    # 2. Get games from database
    # 3. Analyze each game
    # 4. Save analysis to database
    # 5. Display summary
    
    click.echo("Not yet implemented!")


@cli.command()
@click.option("--opening", help="Get advice for specific opening")
@click.option("--recent", type=int, help="Review last N games")
@click.option("--patterns", is_flag=True, help="Detect recurring patterns")
@click.pass_context
def coach(ctx, opening, recent, patterns):
    """Get coaching insights."""
    
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    
    # Initialize explainer
    openai_key = config.get("openai", {}).get("api_key")
    if not openai_key:
        click.echo("Error: OpenAI API key not configured")
        return
    
    # TODO: Implement
    # 1. Initialize Coach
    # 2. Call appropriate method based on flags
    # 3. Display insights
    
    click.echo("Not yet implemented!")


@cli.command()
@click.pass_context
def stats(ctx):
    """Display statistics about your games."""
    db = ctx.obj["db"]
    
    # TODO: Implement
    # 1. Query database for statistics
    # 2. Display total games, win rate, common openings, etc.
    
    click.echo("Not yet implemented!")


if __name__ == "__main__":
    cli()
