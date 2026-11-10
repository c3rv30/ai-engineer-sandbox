from typing import Annotated, Sequence, TypedDict, List, Dict, Any, Optional
import operator
import uuid
from langchain_core.messages import BaseMessage
from src.models.search import SearchResult
from src.models.structured import StructuredAnswer

class AgentState(TypedDict):
    # Conversation history and system messages
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Tenant context
    tenant_id: uuid.UUID
    user_profile: str
    
    # Original raw data
    query: str
    # Previous turns of the conversation ([{'role','content'}, ...]). The supervisor
    # uses it to resolve coreferences ("and in which years?").
    history: List[Dict[str, str]]
    # Retrieval parameters from the ChatRequest. The researcher applies them on every
    # pass, including the ones the self-correction loop adds.
    top_k_retrieve: int
    top_k_rerank: int

    # Supervisor decisions
    intent_type: str
    
    # Artifacts produced by the nodes
    search_queries: List[str]
    documents: List[SearchResult]
    final_answer: Optional[StructuredAnswer]
    
    # Loop state
    iterations: int
    needs_more_info: bool
    # Set by the researcher: True if widening the search could bring nothing new,
    # because the corpus gave no more candidates and the generator already saw them all,
    # or because the window is already at the maximums. route_reviewer does not retry then.
    retrieval_exhausted: bool
