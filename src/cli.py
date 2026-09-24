"""Command-line interface for chess coach.

End-to-end pipeline (Chess.com -> Stockfish -> OpenAI), CLI only:

    python -m src.cli sync    --username <handle>
    python -m src.cli analyze --game-id <id>   # or --all
    python -m src.cli coach   --game-id <id>

All three credentials are validated up front (see src/config.py) so
misconfiguration fails fast with a clear message.
"""

from collections import Counter
from dataclasses import asdict

import click

from .analysis import StockfishAnalyzer
from .analysis.llm_explainer import LLMError, LLMExplainer
from .coaching.coach import Coach, CoachError, build_game_summary
from .config import Config, ConfigError
from .ingestion.chesscom import ChessComIngester
from .ingestion.chesscom import IngestionError as ChessComIngestionError
from .ingestion.lichess import IngestionError as LichessIngestionError
from .ingestion.lichess import LichessIngester
from .storage.database import Database

# Both ingesters raise their own IngestionError; catch either as one type.
_INGESTION_ERRORS = (ChessComIngestionError, LichessIngestionError)


@click.group()
@click.pass_context
def cli(ctx):
    """Chess AI Coach - Improve your game with AI-powered analysis."""
    try:
        config = Config.load_and_validate()
    except ConfigError as exc:
        raise click.ClickException(str(exc))

    ctx.obj = {
        "config": config,
        "db": Database(config.db_path),
    }


@cli.command()
@click.option("--username", default=None,
              help="Handle to sync (defaults to the per-platform value in .env)")
@click.option(
    "--platform",
    type=click.Choice(["chesscom", "lichess"]),
    default="chesscom",
    show_default=True,
    help="Source platform (ignored when --all-platforms is set)",
)
@click.option("--all-platforms", is_flag=True,
              help="Sync both Chess.com and Lichess in one run")
@click.option("--limit", type=int, default=None,
              help="Max games to fetch per platform (default: 20, or all with --full)")
@click.option("--full", is_flag=True,
              help="Fetch full history, ignoring the incremental last-synced bound")
@click.pass_context
def sync(ctx, username, platform, all_platforms, limit, full):
    """Sync games from Chess.com and/or Lichess into the local database.

    Re-syncs are incremental: only games newer than the last sync are fetched,
    unless --full is given (which walks the entire history).
    """
    config: Config = ctx.obj["config"]
    db: Database = ctx.obj["db"]

    platforms = ["chesscom", "lichess"] if all_platforms else [platform]

    total_new = 0
    for plat in platforms:
        handle = username or _default_username(plat, config)
        if not handle:
            msg = (
                f"No {plat} handle given. Pass --username <handle>, or set a "
                f"default {_ENV_VAR[plat]} in .env."
            )
            if all_platforms:
                click.echo(f"Skipping {plat}: {msg}")
                continue
            raise click.ClickException(msg)

        total_new += _sync_platform(config, db, plat, handle, limit, full)

    if total_new:
        click.echo("Next: `analyze --all` then `coach --game-id <id>`.")


def _sync_platform(config, db, platform, handle, limit, full) -> int:
    """Sync one platform for one handle. Returns the number of new games saved."""
    ingester = _ingester_for(platform, config, db)

    # Incremental bound: skip games we've already pulled unless --full.
    since = None if full else ingester.get_last_synced(handle)
    # Default to a small recent batch when incremental; --full means "everything".
    effective_limit = limit if limit is not None else (None if full else 20)

    scope = "full history" if full else (
        f"new games since {since:%Y-%m-%d}" if since else "recent games"
    )
    cap = f"up to {effective_limit} " if effective_limit is not None else "all "
    click.echo(f"Syncing {cap}{scope} from {platform} for '{handle}'...")

    try:
        games = ingester.fetch_games(handle, since=since, limit=effective_limit)
    except _INGESTION_ERRORS as exc:
        raise click.ClickException(str(exc))

    new_count = 0
    skipped = 0
    newest = since
    for game in games:
        if db.game_exists(game.game_id):
            skipped += 1
            continue
        db.save_game(asdict(game))
        new_count += 1
        if newest is None or game.played_at > newest:
            newest = game.played_at
        click.echo(
            f"  + [{platform}] {game.game_id}  {game.played_at:%Y-%m-%d}  "
            f"{game.color} vs {game.opponent_username}  {game.result}"
        )

    if newest is not None:
        ingester.update_last_synced(handle, newest)

    click.echo(
        f"  {platform}: {len(games)} fetched, {new_count} new, "
        f"{skipped} already stored."
    )
    return new_count


# Per-platform default handle + the .env var name used in error messages.
_ENV_VAR = {"chesscom": "CHESS_COM_USERNAME", "lichess": "LICHESS_USERNAME"}


def _default_username(platform, config):
    """Resolve the configured default handle for a platform."""
    if platform == "chesscom":
        return config.chesscom_username
    return config.lichess_username


def _ingester_for(platform, config, db):
    """Construct the ingester for a platform."""
    if platform == "chesscom":
        return ChessComIngester(db)
    return LichessIngester(db, token=config.lichess_token)


def _build_explainer(config) -> LLMExplainer:
    """Construct the OpenAI-backed explainer from config."""
    return LLMExplainer(
        config.openai_api_key,
        model=config.openai_model,
        user_rating=config.user_rating,
        embedding_model=config.embedding_model,
    )


@cli.command()
@click.option("--game-id", help="Analyze a specific game by ID")
@click.option("--username", help="Only analyze this player's games (any handle)")
@click.option("--last", type=int, help="Analyze the last N games")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all unanalyzed games")
@click.option("--force", is_flag=True, help="Re-analyze even if already analyzed")
@click.pass_context
def analyze(ctx, game_id, username, last, analyze_all, force):
    """Analyze games with Stockfish (no OpenAI cost).

    Scope with --game-id for one game, or a batch via --all / --last / --username.
    Passing --username alone analyzes all of that player's games.
    """
    config: Config = ctx.obj["config"]
    db: Database = ctx.obj["db"]

    # Resolve target games (as dicts).
    if game_id:
        game = db.get_game(game_id)
        if game is None:
            raise click.ClickException(
                f"No game with id '{game_id}'. Run `sync` first or check `stats`."
            )
        targets = [game]
    elif last:
        targets = db.get_recent_games(limit=last, username=username)
    elif analyze_all or username:
        targets = db.get_recent_games(limit=10_000_000, username=username)
    else:
        raise click.ClickException(
            "Specify one of --game-id, --username, --last N, or --all."
        )

    if not targets and username:
        raise click.ClickException(
            f"No games stored for '{username}'. Run `sync --username {username}` first."
        )

    if not force:
        pending = [g for g in targets if g["analyzed_at"] is None]
        skipped = len(targets) - len(pending)
        if skipped:
            click.echo(f"Skipping {skipped} already-analyzed game(s) (use --force).")
        targets = pending

    if not targets:
        click.echo("Nothing to analyze.")
        return

    # Large batches use the faster bulk depth; a single game keeps full depth.
    depth = config.bulk_stockfish_depth if len(targets) > 1 else config.stockfish_depth

    click.echo(
        f"Analyzing {len(targets)} game(s) with Stockfish (depth {depth})..."
    )

    try:
        with StockfishAnalyzer(
            config.stockfish_path,
            depth=depth,
            threads=config.stockfish_threads,
        ) as analyzer:
            for game in targets:
                gid = game["game_id"]
                click.echo(f"  Analyzing {gid}...")
                analyses = analyzer.analyze_game(game["pgn"], gid)
                db.save_analysis(gid, [_analysis_to_dict(a) for a in analyses])
                summary = build_game_summary(gid, analyses)
                click.echo(
                    f"    {summary.total_moves} moves | "
                    f"blunders {summary.blunders}, mistakes {summary.mistakes}, "
                    f"inaccuracies {summary.inaccuracies} | "
                    f"avg cp loss {summary.avg_centipawn_loss:.0f}"
                )
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"Could not start Stockfish at '{config.stockfish_path}': {exc}"
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc))

    click.echo("Analysis complete.")


@cli.command()
@click.option("--game-id", help="Coaching writeup for a specific game (1 OpenAI call)")
@click.option("--recent", type=int, help="LLM-free review of the last N games")
@click.option("--username", help="Scope --recent to this player's games (any handle)")
@click.option("--opening", help="Coaching report for an opening (1 OpenAI call)")
@click.option("--patterns", is_flag=True, help="Detect & persist recurring mistake patterns")
@click.option("--explain", is_flag=True,
              help="With --game-id: add per-move explanations for the worst mistakes")
@click.pass_context
def coach(ctx, game_id, recent, username, opening, patterns, explain):
    """Get coaching insights."""
    config: Config = ctx.obj["config"]
    db: Database = ctx.obj["db"]

    explainer = _build_explainer(config)
    coach_obj = Coach(db, explainer)

    try:
        if game_id:
            click.echo(coach_obj.coach_game(game_id))
            if explain:
                click.echo(
                    f"\n--- Worst moments (up to {config.critical_explanations}) ---"
                )
                for item in coach_obj.explain_critical_mistakes(
                    game_id, max_explanations=config.critical_explanations
                ):
                    click.echo(
                        f"\nMove {item['move_number']} "
                        f"(played {item['move_played']}, best {item['best_move']}, "
                        f"lost ~{item['centipawn_loss']:.0f}cp):"
                    )
                    click.echo(f"  {item['explanation']}")
        elif recent:
            reviews = coach_obj.review_recent_games(recent, username=username)
            if not reviews:
                where = f" for '{username}'" if username else ""
                click.echo(f"No games found{where}. Run `sync` first.")
            for r in reviews:
                status = (
                    f"blunders {r['blunders']}, avg cp {r['avg_cp_loss']:.0f}"
                    if r["analyzed"]
                    else "not analyzed"
                )
                click.echo(
                    f"{r['game_id']}  {r['color']} vs {r['opponent']}  "
                    f"{r['result']}  [{status}]"
                )
        elif opening:
            click.echo(coach_obj.analyze_opening(opening_name=opening))
        elif patterns:
            found = coach_obj.detect_and_persist_patterns(username=username)
            if not found:
                click.echo(
                    "No recurring patterns detected yet. Analyze more games first "
                    "(patterns need repeated blunders/mistakes to surface)."
                )
            else:
                click.echo(f"Detected & saved {len(found)} pattern(s):")
                for p in sorted(
                    found, key=lambda r: r["occurrence_count"], reverse=True
                ):
                    click.echo(
                        f"  [{p['severity']}] {p['description']} "
                        f"— {p['occurrence_count']}x "
                        f"({len(p['example_game_ids'] or [])} games)"
                    )
        else:
            raise click.ClickException(
                "Specify one of --game-id, --recent N, --opening, or --patterns."
            )
    except (CoachError, LLMError) as exc:
        raise click.ClickException(str(exc))


@cli.command()
@click.option("--username", help="Scope the knowledge base to one player's games")
@click.pass_context
def index(ctx, username):
    """Build the RAG knowledge base from aggregates + patterns (for `ask`).

    Run after `sync` + `analyze` (and optionally `coach --patterns`). Cost is a
    few batched embedding calls, bounded by document count — not game count.
    """
    from .coaching.knowledge import Knowledge

    config: Config = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    explainer = _build_explainer(config)
    knowledge = Knowledge(db, explainer)

    click.echo("Building knowledge base (embedding aggregate + pattern documents)...")
    try:
        count = knowledge.index(username=username)
    except LLMError as exc:
        raise click.ClickException(str(exc))

    if count == 0:
        raise click.ClickException(
            "No documents to index. Sync and analyze some games first (and run "
            "`coach --patterns` to add pattern documents)."
        )
    click.echo(f"Indexed {count} documents. Try: ask \"what openings do I struggle with?\"")


@cli.command()
@click.argument("question")
@click.option("--username", help="Scope the answer to one player's knowledge base")
@click.option("--show-sources", is_flag=True,
              help="Print the retrieved documents + similarity scores")
@click.pass_context
def ask(ctx, question, username, show_sources):
    """Ask a natural-language question about the player's game data (RAG).

    Retrieves the most relevant aggregate/pattern documents and answers grounded
    in them. One embedding + one completion per question.
    """
    from .coaching.knowledge import Knowledge, KnowledgeError

    config: Config = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    explainer = _build_explainer(config)
    knowledge = Knowledge(db, explainer)

    try:
        answer, docs = knowledge.answer(
            question, k=config.rag_top_k, username=username
        )
    except (KnowledgeError, LLMError) as exc:
        raise click.ClickException(str(exc))

    click.echo(answer)

    if show_sources:
        click.echo("\n--- Retrieved context (most similar first) ---")
        for doc in docs:
            click.echo(f"  [{doc['score']:.3f}] ({doc['source_type']}) {doc['text']}")


@cli.command()
@click.option("--username", help="Only show stats for this player's games")
@click.pass_context
def stats(ctx, username):
    """Display statistics about stored games (optionally for one player)."""
    db: Database = ctx.obj["db"]
    games = db.get_recent_games(limit=10_000_000, username=username)

    if not games:
        if username:
            click.echo(f"No games stored for '{username}'. Run `sync --username {username}`.")
        else:
            click.echo("No games stored yet. Run `sync` first.")
        stored = db.list_usernames()
        if stored:
            click.echo("Players with stored games: " + ", ".join(stored))
        return

    scope = f" for '{username}'" if username else ""
    click.echo(f"Stats{scope}:")

    wins = draws = losses = analyzed = 0
    openings: Counter = Counter()
    for g in games:
        result, color = g["result"], g["color"]
        if result == "1/2-1/2":
            draws += 1
        elif (result == "1-0" and color == "white") or (
            result == "0-1" and color == "black"
        ):
            wins += 1
        else:
            losses += 1
        if g["analyzed_at"] is not None:
            analyzed += 1
        if g["opening_name"]:
            openings[g["opening_name"]] += 1

    click.echo(f"Total games: {len(games)}  (analyzed: {analyzed})")
    click.echo(f"Record: {wins}W / {draws}D / {losses}L")
    if openings:
        click.echo("Most common openings:")
        for name, count in openings.most_common(5):
            click.echo(f"  {count:>3}  {name}")

    click.echo("\nRecent games:")
    for g in games[:10]:
        flag = "✓" if g["analyzed_at"] is not None else " "
        click.echo(
            f"  [{flag}] {g['game_id']}  {g['played_at']:%Y-%m-%d}  "
            f"{g['color']} vs {g['opponent_username']}  {g['result']}"
        )


def _analysis_to_dict(analysis) -> dict:
    """Convert a PositionAnalysis into the dict shape save_analysis expects."""
    return {
        "move_number": analysis.move_number,
        "fen": analysis.fen,
        "move_played": analysis.move_played,
        "eval_before": analysis.eval_before,
        "eval_after": analysis.eval_after,
        "centipawn_loss": analysis.centipawn_loss,
        "depth": analysis.depth,
        "best_move": analysis.best_move,
        "best_move_eval": analysis.best_move_eval,
        # Stored as JSON; list-of-lists is fine.
        "top_3_moves": [list(m) for m in analysis.top_3_moves],
        "classification": analysis.classification.value,
        "is_blunder": analysis.is_blunder,
        "is_missed_tactic": analysis.is_missed_tactic,
        "mate_in": analysis.mate_in,
        "explanation": analysis.explanation,
    }


if __name__ == "__main__":
    cli()
