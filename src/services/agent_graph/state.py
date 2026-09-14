from typing import Annotated, Sequence, TypedDict, List, Dict, Any, Optional
import operator
import uuid
from langchain_core.messages import BaseMessage
from src.models.search import SearchResult
from src.models.structured import StructuredAnswer

class AgentState(TypedDict):
    # El historial de la conversación y mensajes del sistema
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Contexto del Tenant
    tenant_id: uuid.UUID
    user_profile: str
    
    # Datos en crudo originales
    query: str
    # Turnos previos de la conversación ([{'role','content'}, ...]). Lo consume el
    # supervisor para resolver correferencias ("¿y en qué años?").
    history: List[Dict[str, str]]
    # Parámetros de recuperación del ChatRequest. El investigador los aplica en cada
    # pasada, también en las que añade el ciclo de auto-corrección.
    top_k_retrieve: int
    top_k_rerank: int

    # Decisiones del supervisor
    intent_type: str
    
    # Artefactos generados por los nodos
    search_queries: List[str]
    documents: List[SearchResult]
    final_answer: Optional[StructuredAnswer]
    
    # Estado cíclico
    iterations: int
    needs_more_info: bool
    # Lo fija el investigador: True si ampliar la búsqueda no podría traer nada nuevo,
    # porque el corpus no dio más candidatos y el redactor ya los vio todos, o porque
    # la ventana ya está en los máximos. route_reviewer no reintenta en ese caso.
    retrieval_exhausted: bool
