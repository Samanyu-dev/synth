import numpy as np
from google import genai
from app.config import get_settings
import logging

logger = logging.getLogger("synth.services.rag")

# Mock historical database of coaching logs spanning 5 years
HISTORY_DB = [
    "Athletes who show a sharp decline in 2k splits in February often bounce back in March if given 3 days of complete rest.",
    "When HR drift exceeds 5% during base phase, historically 60% of athletes develop an overuse injury within 3 weeks.",
    "The rowing team's fastest 2k times historically occur when the preceding 4x1k average split is within 2 seconds of their goal pace.",
    "Ella Wheeler historically struggles with 2x6k pacing, but excels in short sprints. Her endurance baseline drops if she misses more than 2 sessions a month.",
    "Athletes tapering for May races typically perform best when their peak volume is hit in the second week of April, followed by a 30% volume reduction."
]

import re

def _tokenize(text: str) -> set:
    # simple lowercase alphanumeric tokenization
    return set(re.findall(r'\b\w+\b', text.lower()))

def query_historical_context(query: str, top_k: int = 2) -> str:
    """Query the vector database for relevant historical coaching context using local keyword matching."""
    try:
        query_tokens = _tokenize(query)
        
        # Calculate overlap score
        scores = []
        for i, doc in enumerate(HISTORY_DB):
            doc_tokens = _tokenize(doc)
            overlap = len(query_tokens.intersection(doc_tokens))
            scores.append((overlap, i))
            
        # Sort descending by score
        scores.sort(reverse=True)
        
        # Filter top_k with at least 1 keyword match
        results = [HISTORY_DB[i] for score, i in scores[:top_k] if score > 0]
        
        if not results:
            return ""
            
        return "\n".join(f"- {res}" for res in results)
        
    except Exception as e:
        logger.warning(f"RAG query failed: {e}")
        return ""
