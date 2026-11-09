import os
import instructor
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from langfuse import observe

from src.services.history import format_history

# Patch the Anthropic client with Instructor
client = instructor.from_anthropic(AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")))

class QueryIntent(BaseModel):
    intent_type: str = Field(
        description="Must be 'casual_greeting', 'knowledge_search', 'tool_execution' or 'out_of_scope'."
    )
    search_queries: list[str] = Field(
        description="If 'knowledge_search', 3 variations of the question optimized for search (full-text and vector similarity), written in Spanish. Otherwise, empty.",
        default_factory=list
    )
    hypothetical_document: str = Field(
        description="If 'knowledge_search', a hypothetical paragraph showing what the ideal document answering the question would look like (HyDE technique), written in Spanish. Otherwise, empty.",
        default=""
    )
    direct_answer: str = Field(
        description="If 'casual_greeting' or 'out_of_scope', your final answer, in the language of the user's input. Otherwise, empty.",
        default=""
    )
    tool_name: str = Field(
        description="If 'tool_execution', the exact name of the tool to run: 'get_current_time', 'get_crypto_price', 'get_github_profile'.",
        default=""
    )
    tool_args: dict = Field(
        description="If 'tool_execution', a JSON dictionary with the function's parameters (e.g. {'symbol': 'bitcoin'} or {'username': 'torvalds'}).",
        default_factory=dict
    )

@observe(name="agentic_query_router")
async def analyze_query(query: str, history: list = None) -> QueryIntent:
    """
    Router agent: analyzes the user's intent and resolves coreferences using the history.
    """
    history_str = format_history(history)

    # The search queries and the HyDE paragraph go in Spanish whatever language the user
    # writes in: the corpus is in Spanish and full-text search uses the 'spanish'
    # configuration (sql/01_init.sql, retriever.py). The direct answer, in the user's language.
    prompt = f"""
    You are the "Router" of an AI Engineer Sandbox that is currently analyzing the résumé and professional profile of the engineer Bryan Bobadilla.
    
    Your task is to analyze the following user input:
    "{query}"
    
    {history_str}
    
    Decide the intent of the input using these rules:
    - `casual_greeting`: If it is a simple greeting (Hi, how are you).
    - `knowledge_search`: If it is a question about the résumé, Bryan Bobadilla's experience, technologies, software architecture, cloud, or the project's technical context.
    - `tool_execution`: If the user asks something that can be answered with the available tools (current time, cryptocurrency prices, or GitHub profiles).
    - `out_of_scope`: ONLY if it is a question about politics, religion or other unrelated topics that CANNOT be answered with the tools.
    
    Available tools (ONLY for 'tool_execution'):
    1. get_current_time: Takes no arguments.
    2. get_crypto_price: Takes the argument 'symbol' (e.g. bitcoin, ethereum).
    3. get_github_profile: Takes the argument 'username'.
    
    LANGUAGE: The user may write in Spanish or English. Write `direct_answer` in the user's language. Write `search_queries` and `hypothetical_document` in Spanish in every case, because the indexed documents are in Spanish.
    
    IMPORTANT: If the intent is 'knowledge_search':
    1. Generate 3 different variations of the question in `search_queries` to cover synonyms and different wordings (Multi-Query). If the question depends on the history (e.g. "And what did he do there?"), resolve the coreference in every variation.
    2. Write a `hypothetical_document` of 2-3 sentences pretending to be the ideal résumé or documentation fragment that would answer the question, using exact technical terminology (HyDE).
    """
    
    # claude-haiku-4-5-20251001, which we found works perfectly on this account
    # Haiku is very fast and cheap, ideal for routing
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
        response_model=QueryIntent,
    )
    
    return response
