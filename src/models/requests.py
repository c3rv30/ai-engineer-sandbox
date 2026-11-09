from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# The only retrieval defaults: the researcher and the chat router import them. The
# contract used to say 7 while the code used 10 (BUG-06).
DEFAULT_TOP_K_RETRIEVE = 15
DEFAULT_TOP_K_RERANK = 10
# Maximums the API accepts. They also bound the widening of the self-correction loop.
MAX_TOP_K_RETRIEVE = 50
MAX_TOP_K_RERANK = 20

class ChatRequest(BaseModel):
    query: str
    history: List[Dict[str, str]] = Field(default_factory=list, description="Previous messages of the conversation")
    # The limits prevent a negative LIMIT in Postgres and bound the cost: the search is
    # repeated for each query variant (original, Multi-Query and HyDE) and every
    # candidate goes through the cross-encoder.
    top_k_retrieve: int = Field(DEFAULT_TOP_K_RETRIEVE, ge=1, le=MAX_TOP_K_RETRIEVE,
                                description="Hybrid search candidates for each query variant")
    top_k_rerank: int = Field(DEFAULT_TOP_K_RERANK, ge=1, le=MAX_TOP_K_RERANK,
                              description="Documents that survive re-ranking and reach the generator")

class IngestRequest(BaseModel):
    file_path: str
