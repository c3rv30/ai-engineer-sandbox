import os
import uuid
import json
from typing import List, Dict
from pydantic import BaseModel
import instructor
from anthropic import AsyncAnthropic
import src.config  # noqa: F401  (loads .env before the client is built)
from src.services.db import tenant_connection


class Triplet(BaseModel):
    source_node: str
    relation: str
    target_node: str

class KnowledgeGraphExtraction(BaseModel):
    triplets: List[Triplet]

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

async def extract_knowledge_graph(chunk_text: str) -> List[Triplet]:
    """Extracts entities and relations from a text using an LLM."""
    # The nodes are later matched by keyword against the words of the question
    # (retrieve_subgraph), so they keep the language and spelling of the text.
    prompt = f"""
    You are a GraphRAG expert. Extract a knowledge graph from the following text.
    Identify the main entities (people, technologies, companies, concepts) and their relations.
    Return the results as triples (SOURCE NODE, RELATION, TARGET NODE).
    Write the nodes and relations in the same language as the text, keeping names exactly as they appear.
    If there are no clear relations, return an empty list.
    
    Text: {chunk_text}
    """
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            response_model=KnowledgeGraphExtraction
        )
        return response.triplets
    except Exception as e:
        print(f"Error extracting the graph: {e}")
        return []

async def insert_knowledge_graph(tenant_id: uuid.UUID, chunk_id: str, triplets: List[Triplet]):
    """Stores the extracted triples in the DB under the current tenant."""
    if not triplets:
        return
        
    async with tenant_connection(tenant_id) as conn:
        insert_query = """
        INSERT INTO knowledge_graph (tenant_id, source_node, relation, target_node, source_chunk_id)
        VALUES ($1, $2, $3, $4, $5)
        """
        records = [(tenant_id, t.source_node.lower(), t.relation.lower(), t.target_node.lower(), chunk_id) for t in triplets]
        await conn.executemany(insert_query, records)

async def retrieve_subgraph(tenant_id: uuid.UUID, query: str) -> str:
    """Fuzzy search of the knowledge graph for nodes relevant to the query."""
    async with tenant_connection(tenant_id) as conn:
        
        # Extract keywords from the query to look up nodes in the graph
        # This is a naive approach; ideally the LLM would extract the entities from the question.
        import re
        words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 3]
        if not words:
            return ""
            
        # Find relations whose source or target matches any word of the question
        # ILIKE gives a partial match. The words come from user text, so they travel as
        # a parameter and never inside the SQL: the safety of the query cannot depend
        # on what the regex above lets through.
        patterns = [f"%{word}%" for word in words]
        sql_query = """
        SELECT source_node, relation, target_node
        FROM knowledge_graph
        WHERE source_node ILIKE ANY($1::text[])
           OR target_node ILIKE ANY($1::text[])
        LIMIT 10
        """

        rows = await conn.fetch(sql_query, patterns)
        if not rows:
            return ""
            
        graph_text = "Structural context (GraphRAG):\n"
        for r in rows:
            graph_text += f"- [{r['source_node']}] --({r['relation']})--> [{r['target_node']}]\n"
            
        return graph_text
