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
    
    # Decisiones del supervisor
    intent_type: str
    
    # Artefactos generados por los nodos
    search_queries: List[str]
    documents: List[SearchResult]
    final_answer: Optional[StructuredAnswer]
    
    # Estado cíclico
    iterations: int
    needs_more_info: bool
