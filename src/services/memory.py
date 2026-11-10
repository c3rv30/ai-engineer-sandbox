import os
import uuid
import instructor
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from src.config import ANTHROPIC_MODEL
from src.services.db import tenant_connection
from src.services.embeddings import embed, to_pgvector


client = instructor.from_anthropic(AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")))

class ExtractedFacts(BaseModel):
    new_facts: list[str] = Field(
        description="List of new facts, preferences or persistent personal information about the user (max. 3). Empty if there is no new long-term information.",
        default_factory=list
    )

async def extract_and_save_facts(tenant_id: uuid.UUID, user_message: str):
    """
    Runs in the background. Checks whether the user revealed new information about
    themselves. If so, it embeds it and stores it.
    """
    prompt = f"""
    You are a long-term memory extractor. Analyze the following user message and decide whether it revealed any important fact about the user, their preferences, their tech stack or their company.
    Only extract facts that are useful to remember in future sessions. Write them concisely, in the third person and in the same language as the message (e.g. "The user prefers programming in Python", "The user works at company X").
    
    User message: "{user_message}"
    """
    
    try:
        extraction: ExtractedFacts = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
            response_model=ExtractedFacts,
        )
        
        if not extraction.new_facts:
            return
            
        print(f"🧠 [Memory] New facts detected: {extraction.new_facts}")
        
        # The embeddings are computed before taking a connection: it is CPU work and
        # would hold a pooled connection without using it.
        embeddings = [await embed(fact) for fact in extraction.new_facts]
        async with tenant_connection(tenant_id) as conn:
            
            for fact, fact_embedding in zip(extraction.new_facts, embeddings):
                emb_str = to_pgvector(fact_embedding)
                
                sql = """
                INSERT INTO user_memory (tenant_id, fact, fact_embedding)
                VALUES ($1, $2, $3::vector)
                """
                await conn.execute(sql, tenant_id, fact, emb_str)
    except Exception as e:
        print(f"Error extracting memory: {e}")

async def retrieve_user_facts(tenant_id: uuid.UUID, query: str, top_k: int = 3) -> str:
    """
    Finds the user's most relevant facts for their current question.
    """
    # The embedding is computed before taking a connection: it is CPU work and would
    # hold a pooled connection without using it.
    emb_str = to_pgvector(await embed(query))
    async with tenant_connection(tenant_id) as conn:
        
        
        sql = """
        SELECT fact, 1 - (fact_embedding <=> $1::vector) AS similarity
        FROM user_memory
        ORDER BY fact_embedding <=> $1::vector
        LIMIT $2
        """
        rows = await conn.fetch(sql, emb_str, top_k)
        
        if not rows:
            return ""
            
        # Filter facts by a minimum similarity so no noise comes back
        relevant_facts = [row['fact'] for row in rows if row['similarity'] > 0.3]
        
        if not relevant_facts:
            return ""
            
        facts_str = "\n".join(f"- {f}" for f in relevant_facts)
        return f"<USER_PROFILE>\nKnown information about the user from previous sessions:\n{facts_str}\n</USER_PROFILE>\n\n"
