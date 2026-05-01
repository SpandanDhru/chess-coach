# Development Notes

## Project Status

This is a starter repository structure. Core components have been scaffolded but not yet implemented.

## Implementation Priority

Recommended build order:

### Phase 1: Foundation (Week 1)
1. ✅ Repository structure
2. ⬜ Database layer implementation
   - Finish `Database` class methods
   - Test schema creation
3. ⬜ Basic PGN parsing
   - Test with sample games
4. ⬜ Stockfish integration
   - Implement `analyze_position()`
   - Test move classification

### Phase 2: Ingestion (Week 2)
5. ⬜ Lichess ingester
   - Implement API calls
   - Parse NDJSON response
   - Test with real account
6. ⬜ Chess.com ingester
   - Implement archive fetching
   - Parse PGN format
7. ⬜ Sync command
   - Wire up CLI to ingesters
   - Test incremental sync

### Phase 3: Analysis (Week 3)
8. ⬜ Complete Stockfish analyzer
   - Full game analysis pipeline
   - Save to database
9. ⬜ LLM explainer
   - Position explanation prompts
   - Test with GPT-4o-mini
10. ⬜ Analyze command
    - Wire up CLI
    - Test end-to-end

### Phase 4: Coaching (Week 4)
11. ⬜ Pattern detection
    - Group similar mistakes
    - Auto-classify patterns
12. ⬜ Coach implementation
    - Opening analysis
    - Improvement areas
13. ⬜ Coach command
    - Wire up CLI
    - Test coaching output

## Key Design Decisions

### Why not use a chess API for analysis?
- Stockfish locally is free and fast
- Full control over depth and parameters
- No rate limits or API costs
- Consistent evaluations

### Why separate Stockfish and LLM?
- Stockfish is deterministic and cheap
- Run bulk analysis overnight
- Selectively explain critical positions
- Can regenerate explanations without re-analyzing

### Why SQLite?
- Simple, no server needed
- Good for personal use (100s-1000s of games)
- Easy backups (just copy the file)
- Can migrate later if needed

## Testing Strategy

- Unit tests for each component in isolation
- Integration tests for end-to-end flows
- Use sample PGN files for testing
- Mock API calls in tests

## Future Enhancements

Ideas for v2+:
- Web UI with FastAPI + React
- Interactive position trainer
- Opening repertoire builder
- Spaced repetition for tactics
- Pattern recognition with clustering
- Export annotated PGNs
- Mobile app integration
- Multi-user support
- Cloud deployment

## Contributing

If expanding this project:
1. Keep the layered architecture
2. Write tests for new features
3. Update documentation
4. Use type hints
5. Follow existing code style
