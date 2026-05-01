"""LLM-powered explanations for chess positions using OpenAI API."""

from typing import List, Optional
import openai

from .models import PositionAnalysis, GameAnalysisSummary


class LLMExplainer:
    """Generate natural language explanations for chess positions."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        user_rating: Optional[int] = None,
    ):
        """
        Initialize LLM explainer.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (gpt-4o-mini recommended for cost)
            user_rating: User's rating for explanation calibration
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.user_rating = user_rating or 1200  # Default to beginner
    
    def explain_position(
        self,
        analysis: PositionAnalysis,
    ) -> str:
        """
        Generate natural language explanation for why a move was good/bad.
        
        Args:
            analysis: Position analysis from Stockfish
            
        Returns:
            Plain English explanation tailored to user's level
        """
        # TODO: Implement
        # 1. Construct prompt with FEN, move played, best move, evaluation
        # 2. Include user rating for appropriate explanation level
        # 3. Call OpenAI API
        # 4. Return explanation
        
        raise NotImplementedError("Position explanation not yet implemented")
    
    def summarize_game(
        self,
        summary: GameAnalysisSummary,
        all_analyses: List[PositionAnalysis],
    ) -> str:
        """
        Generate a coaching summary for an entire game.
        
        Args:
            summary: Game analysis statistics
            all_analyses: Full list of position analyses
            
        Returns:
            One-paragraph coaching summary with key themes
        """
        # TODO: Implement
        # 1. Extract key patterns (blunders, missed tactics, phase weaknesses)
        # 2. Construct prompt with game statistics
        # 3. Call OpenAI API
        # 4. Return summary
        
        raise NotImplementedError("Game summary not yet implemented")
    
    def generate_coaching_report(
        self,
        opening: Optional[str] = None,
        pattern_type: Optional[str] = None,
        games_data: Optional[dict] = None,
    ) -> str:
        """
        Generate a coaching report on specific aspects of play.
        
        Args:
            opening: Specific opening to analyze (e.g., "French Defense")
            pattern_type: Type of pattern to focus on (e.g., "tactics", "endgame")
            games_data: Aggregate statistics from database
            
        Returns:
            Coaching advice based on aggregate patterns
        """
        # TODO: Implement
        # 1. Query relevant game data from database
        # 2. Identify patterns and weaknesses
        # 3. Construct prompt with aggregate statistics
        # 4. Call OpenAI API with coaching context
        # 5. Return personalized recommendations
        
        raise NotImplementedError("Coaching report not yet implemented")
    
    def _build_position_prompt(
        self,
        analysis: PositionAnalysis,
    ) -> str:
        """Build prompt for position explanation."""
        # TODO: Create effective prompt template
        # Should include: FEN, move played, best move, eval change, user rating
        raise NotImplementedError()
