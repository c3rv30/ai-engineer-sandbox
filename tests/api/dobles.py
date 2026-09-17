"""Dobles del grafo de agentes y guiones con la forma real de lo que emite.

La forma de los datos vive solo aquí: los tests describen el caso (un saludo que
resuelve el supervisor, una respuesta del redactor…) y no el protocolo de LangGraph.
Si `src/services/agent_graph/nodes.py` cambia lo que emite, este es el único archivo
que hay que actualizar.

Contrato reproducido (ver nodes.py y chat.py):
- `ainvoke(state)` devuelve el estado final; el endpoint lee `final_answer`,
  `intent_type` y `documents`.
- `astream(state, stream_mode=["updates", "custom"])` entrega tuplas `(mode, chunk)`:
  con `"custom"`, `chunk` es `{"delta": str}` (el texto del redactor según se genera);
  con `"updates"`, `chunk` es `{nombre_nodo: actualización_de_estado}`.
"""
from dataclasses import dataclass, field
from typing import Any

from src.models.search import SearchResult
from src.models.structured import AnswerSource, StructuredAnswer

# El prefijo que emite generator_node antes del texto del redactor.
PREFIJO_REDACTOR = "✍️ *Redactor estructurando respuesta final...*\n\n---\n\n"
# Los mensajes de progreso que chat.py añade por nodo (BUG-01: no deben persistirse).
PROGRESO_SUPERVISOR = "🤖 *Supervisor evaluando estrategia...*\n\n"
PROGRESO_INVESTIGADOR = "🔍 *Investigador buscando en Postgres Vector y GraphRAG...*\n\n"


def respuesta(answer: str, *, confianza: float = 0.9, requiere_mas: bool = False,
              fuentes: list[tuple[str, str]] | None = None) -> StructuredAnswer:
    return StructuredAnswer(
        answer=answer,
        sources=[AnswerSource(document_id=d, quote=q) for d, q in (fuentes or [])],
        confidence_score=confianza,
        requires_more_info=requiere_mas,
    )


def documento(contenido: str = "contenido de prueba", *, id_: str = "doc-1") -> SearchResult:
    return SearchResult(id=id_, content=contenido, metadata={"source": "prueba.md"}, score=0.9)


@dataclass
class Guion:
    """Lo que emitiría el grafo para un caso.

    `emisiones` son las tuplas `(mode, chunk)` del stream, y `estado_final` lo que
    devolvería `ainvoke`.
    """
    emisiones: list[tuple[str, dict[str, Any]]]
    estado_final: dict[str, Any]


def guion_supervisor(texto: str, *, intent_type: str = "casual_greeting") -> Guion:
    """El supervisor resuelve solo: saludo, tema fuera de alcance o herramienta.

    El grafo termina ahí, sin pasar por el investigador ni por el redactor, así que
    nadie emite el texto por el canal 'custom' (BUG-09).
    """
    final = respuesta(texto, confianza=1.0)
    return Guion(
        emisiones=[("updates", {"supervisor": {"intent_type": intent_type, "final_answer": final}})],
        estado_final={"intent_type": intent_type, "final_answer": final, "documents": []},
    )


def guion_redactor(texto: str, *, intent_type: str = "knowledge_search",
                   documentos: list[SearchResult] | None = None,
                   trozos: list[str] | None = None,
                   confianza: float = 0.9, requiere_mas: bool = False) -> Guion:
    """Camino completo: supervisor, investigador y redactor emitiendo token a token."""
    docs = documentos if documentos is not None else [documento()]
    final = respuesta(texto, confianza=confianza, requiere_mas=requiere_mas)
    partes = trozos if trozos is not None else [texto]
    emisiones: list[tuple[str, dict[str, Any]]] = [
        ("updates", {"supervisor": {"intent_type": intent_type, "search_queries": [texto[:20]]}}),
        ("updates", {"researcher": {"documents": docs, "iterations": 1, "retrieval_exhausted": False}}),
        ("custom", {"delta": PREFIJO_REDACTOR}),
    ]
    emisiones += [("custom", {"delta": parte}) for parte in partes]
    emisiones.append(("updates", {"generator": {"final_answer": final, "needs_more_info": requiere_mas}}))
    return Guion(
        emisiones=emisiones,
        estado_final={"intent_type": intent_type, "final_answer": final, "documents": docs},
    )


@dataclass
class GrafoDoble:
    """Sustituye a `chat.agent_graph`. Registra los estados iniciales que recibe."""
    guion: Guion | None = None
    error: Exception | None = None
    error_tras: int = 0  # emisiones antes de fallar, en el stream
    invocaciones: list[dict[str, Any]] = field(default_factory=list)

    async def ainvoke(self, state, *args, **kwargs):
        self.invocaciones.append(state)
        if self.error is not None:
            raise self.error
        return {**state, **self.guion.estado_final}

    def astream(self, state, *args, stream_mode=None, **kwargs):
        self.invocaciones.append(state)

        async def generador():
            emitidas = 0
            for emision in (self.guion.emisiones if self.guion else []):
                if self.error is not None and emitidas == self.error_tras:
                    raise self.error
                yield emision
                emitidas += 1
            if self.error is not None and emitidas == self.error_tras:
                raise self.error

        return generador()
