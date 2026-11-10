"""Doubles for the agent graph and scripts with the real shape of what it emits.

The shape of the data lives only here: the tests describe the case (a greeting the
supervisor resolves, an answer from the generator…) and not LangGraph's protocol.
If `src/services/agent_graph/nodes.py` changes what it emits, this is the only file
that needs updating.

Contract reproduced (see nodes.py and chat.py):
- `ainvoke(state)` returns the final state; the endpoint reads `final_answer`,
  `intent_type`, `answer_language` and `documents`.
- `astream(state, stream_mode=["updates", "custom"])` yields `(mode, chunk)` tuples:
  with `"custom"`, `chunk` is `{"delta": str}` (the generator's text as it is produced);
  with `"updates"`, `chunk` is `{node_name: state_update}`. The supervisor's update
  always carries `intent_type` and `answer_language`.
"""
from dataclasses import dataclass, field
from typing import Any

from src.models.search import SearchResult
from src.models.structured import AnswerSource, StructuredAnswer

# The prefix generator_node emits before the generator's text.
GENERATOR_PREFIX = "✍️ *Generator writing the final answer...*\n\n---\n\n"
# The progress messages chat.py adds per node (BUG-01: they must not be stored).
SUPERVISOR_PROGRESS = "🤖 *Supervisor choosing a strategy...*\n\n"
RESEARCHER_PROGRESS = "🔍 *Researcher searching pgvector and GraphRAG...*\n\n"


def answer(text: str, *, confidence: float = 0.9, needs_more: bool = False,
           sources: list[tuple[str, str]] | None = None) -> StructuredAnswer:
    return StructuredAnswer(
        answer=text,
        sources=[AnswerSource(document_id=d, quote=q) for d, q in (sources or [])],
        confidence_score=confidence,
        requires_more_info=needs_more,
    )


def document(content: str = "test content", *, id_: str = "doc-1") -> SearchResult:
    return SearchResult(id=id_, content=content, metadata={"source": "test.md"}, score=0.9)


@dataclass
class Script:
    """What the graph would emit for a case.

    `emissions` are the stream's `(mode, chunk)` tuples, and `final_state` what
    `ainvoke` would return.
    """
    emissions: list[tuple[str, dict[str, Any]]]
    final_state: dict[str, Any]


def supervisor_script(text: str, *, intent_type: str = "casual_greeting", language: str = "en") -> Script:
    """The supervisor resolves on its own: greeting, out-of-scope topic or tool.

    The graph ends there, without going through the researcher or the generator, so
    nobody emits the text on the 'custom' channel (BUG-09).
    """
    final = answer(text, confidence=1.0)
    return Script(
        emissions=[("updates", {"supervisor": {"intent_type": intent_type, "answer_language": language,
                                               "final_answer": final}})],
        final_state={"intent_type": intent_type, "answer_language": language, "final_answer": final,
                     "documents": []},
    )


def generator_script(text: str, *, intent_type: str = "knowledge_search",
                     documents: list[SearchResult] | None = None,
                     chunks: list[str] | None = None,
                     confidence: float = 0.9, needs_more: bool = False,
                     language: str = "en") -> Script:
    """Full path: supervisor, researcher and generator emitting token by token."""
    docs = documents if documents is not None else [document()]
    final = answer(text, confidence=confidence, needs_more=needs_more)
    parts = chunks if chunks is not None else [text]
    emissions: list[tuple[str, dict[str, Any]]] = [
        ("updates", {"supervisor": {"intent_type": intent_type, "answer_language": language,
                                    "search_queries": [text[:20]]}}),
        ("updates", {"researcher": {"documents": docs, "iterations": 1, "retrieval_exhausted": False}}),
        ("custom", {"delta": GENERATOR_PREFIX}),
    ]
    emissions += [("custom", {"delta": part}) for part in parts]
    emissions.append(("updates", {"generator": {"final_answer": final, "needs_more_info": needs_more}}))
    return Script(
        emissions=emissions,
        final_state={"intent_type": intent_type, "answer_language": language, "final_answer": final,
                     "documents": docs},
    )


@dataclass
class GraphDouble:
    """Replaces `chat.agent_graph`. Records the initial states it receives."""
    script: Script | None = None
    error: Exception | None = None
    error_after: int = 0  # emissions before failing, in the stream
    invocations: list[dict[str, Any]] = field(default_factory=list)

    async def ainvoke(self, state, *args, **kwargs):
        self.invocations.append(state)
        if self.error is not None:
            raise self.error
        return {**state, **self.script.final_state}

    def astream(self, state, *args, stream_mode=None, **kwargs):
        self.invocations.append(state)

        async def generator():
            emitted = 0
            for emission in (self.script.emissions if self.script else []):
                if self.error is not None and emitted == self.error_after:
                    raise self.error
                yield emission
                emitted += 1
            if self.error is not None and emitted == self.error_after:
                raise self.error

        return generator()
