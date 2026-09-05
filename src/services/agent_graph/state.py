from typing import Annotated, Sequence, TypedDict, List, Dict, Any, Optional
import operator
from langchain_core.messages import BaseMessage
from src.models.search import SearchResult
from src.models.structured import StructuredAnswer

class AgentState(TypedDict):
    # El historial de la conversación y mensajes del sistema
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Contexto del Tenant
    tenant_id: str
    user_profile: str
    
    # Datos en crudo originales
    query: str
    
    # Decisiones del supervisor
    intent_type: str
    
    # Artefactos generados por los nodos
    search_queries: List[str]
    documents: List[SearchResult]
    final_answer: Optional[StructuredAnswer]
    
    # Estado cíclico
    iterations: int
    needs_more_info: bool
