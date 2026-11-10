import os
from typing import AsyncGenerator, Dict, List, Optional
import instructor
from anthropic import AsyncAnthropic
from instructor import Partial
from langfuse import observe

import src.config  # noqa: F401  (loads .env before the client is built)
from src.models.search import RerankedResult
from src.models.structured import StructuredAnswer
from src.services.history import format_history
from src.services.language import answer_instruction

# Initialize the Anthropic client and wrap it with instructor
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 8192


def _build_prompt(
    query: str,
    context: List[RerankedResult],
    answer_language: str,
    user_profile: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Builds the generator's prompt.

    The full and the streaming versions share it on purpose: having two copies of the
    prompt is exactly why the anti-plain-text instruction (documented in
    TROUBLESHOOTING.md §6) lived in only one of them.
    """
    context_text = ""
    for idx, c in enumerate(context, 1):
        context_text += f"\n--- Document {idx} (ID: {c.id}) ---\n{c.content}\n"

    history_str = format_history(history)

    # The language order goes after the Context on purpose: placed before a long
    # Spanish context, an English question was answered in Spanish. It names the
    # language the supervisor decided instead of asking the model to work it out
    # from the Question (BUG-11).
    return f"""
    You are an expert AI Engineering assistant. Your goal is to answer the user's question using ONLY the information provided in the Context.
    If the information is not enough, say so in 'requires_more_info'.
    Cite the sources using the document ID.

    VERY IMPORTANT: You must return your answer structured. If you are going to write a long analysis, put all the text, formatted in Markdown, inside the 'answer' field. Do not answer with plain text outside the JSON schema.

    {user_profile}

    {history_str}
    Question: {query}

    IMPORTANT: If the question depends on the history (e.g. "And in which years?"), first resolve what it refers to using the previous turn and answer ONLY about that referent. The Context may bring extra documents: do not dump all of it, answer only what you were asked.

    Context:
    {context_text}

    {answer_instruction(answer_language)}
    """


@observe(name="generate_structured_answer")
async def generate_answer(
    query: str,
    context: List[RerankedResult],
    answer_language: str,
    user_profile: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> StructuredAnswer:
    """
    Takes the question and the retrieved context and calls Anthropic (Claude) to
    generate a structured answer validated with Pydantic.

    It also receives the history: without it, a follow-up question like
    "And in which years?" has no referent, and the generator answers by dumping all
    the retrieved context instead of sticking to what it was asked.

    The normal path is `generate_answer_stream`; this version remains as the
    fallback when streaming does not manage to complete the structured object.
    """
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": _build_prompt(query, context, answer_language, user_profile, history)}
        ],
        response_model=StructuredAnswer
    )

    return response


@observe(name="generate_structured_answer_stream")
async def generate_answer_stream(
    query: str,
    context: List[RerankedResult],
    answer_language: str,
    user_profile: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[Partial[StructuredAnswer], None]:
    """
    Same as `generate_answer`, but emitting the object as it is built.

    It emits the partial model, not its serialized JSON, because the consumer needs
    both the incremental text (for SSE) and the final object (for the graph state).
    The first partials arrive with `answer` set to None: the model has not opened
    that field yet.
    """
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": _build_prompt(query, context, answer_language, user_profile, history)}
        ],
        response_model=Partial[StructuredAnswer],
        stream=True
    )

    async for partial_model in response:
        yield partial_model
