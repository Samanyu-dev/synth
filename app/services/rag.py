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

_embeddings_cache = None

def get_history_embeddings(client):
    global _embeddings_cache
    if _embeddings_cache is not None:
        return _embeddings_cache
    
    # Generate embeddings for our mock DB
    response = client.models.embed_content(
        model="text-embedding-004",
        contents=HISTORY_DB
    )
    _embeddings_cache = [emb.values for emb in response.embeddings]
    return _embeddings_cache

def query_historical_context(query: str, top_k: int = 2) -> str:
    """Query the vector database for relevant historical coaching context."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return ""
        
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        
        # Get query embedding
        query_response = client.models.embed_content(
            model="text-embedding-004",
            contents=query
        )
        query_embedding = np.array(query_response.embeddings[0].values)
        
        # Get DB embeddings
        db_embeddings = np.array(get_history_embeddings(client))
        
        # Calculate cosine similarity
        similarities = np.dot(db_embeddings, query_embedding) / (
            np.linalg.norm(db_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Get top k indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = [HISTORY_DB[i] for i in top_indices if similarities[i] > 0.4]
        
        if not results:
            return ""
            
        return "\n".join(f"- {res}" for res in results)
        
    except Exception as e:
        logger.warning(f"RAG query failed: {e}")
        return ""
