import os
import json
from typing import List, Dict
from pydantic import BaseModel
import instructor
from anthropic import AsyncAnthropic
import asyncpg
from dotenv import load_dotenv

load_dotenv()
DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")

class Triplet(BaseModel):
    source_node: str
    relation: str
    target_node: str

class KnowledgeGraphExtraction(BaseModel):
    triplets: List[Triplet]

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

async def extract_knowledge_graph(chunk_text: str) -> List[Triplet]:
    """Extrae entidades y relaciones de un texto usando un LLM."""
    prompt = f"""
    Eres un experto en GraphRAG. Extrae un grafo de conocimiento del siguiente texto.
    Identifica las entidades principales (personas, tecnologías, empresas, conceptos) y sus relaciones.
    Devuelve los resultados en formato de tripletas (NODO ORIGEN, RELACIÓN, NODO DESTINO).
    Si no hay relaciones claras, devuelve una lista vacía.
    
    Texto: {chunk_text}
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
        print(f"Error extrayendo grafo: {e}")
        return []

async def insert_knowledge_graph(tenant_id: str, chunk_id: str, triplets: List[Triplet]):
    """Guarda las tripletas extraídas en la BDD bajo el tenant actual."""
    if not triplets:
        return
        
    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
        insert_query = """
        INSERT INTO knowledge_graph (tenant_id, source_node, relation, target_node, source_chunk_id)
        VALUES ($1, $2, $3, $4, $5)
        """
        records = [(tenant_id, t.source_node.lower(), t.relation.lower(), t.target_node.lower(), chunk_id) for t in triplets]
        await conn.executemany(insert_query, records)
    finally:
        await conn.close()

async def retrieve_subgraph(tenant_id: str, query: str) -> str:
    """Busca en el grafo de conocimiento nodos relevantes a la query de forma difusa."""
    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
        
        # Extraemos palabras clave de la query para buscar nodos en el grafo
        # Esto es un naive approach, idealmente usaríamos el LLM para extraer las entidades de la pregunta.
        import re
        words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 3]
        if not words:
            return ""
            
        # Buscar relaciones donde el origen o destino coincida con alguna palabra de la pregunta
        # Usamos ILIKE para coincidencia parcial
        conditions = []
        for word in words:
            conditions.append(f"source_node ILIKE '%{word}%' OR target_node ILIKE '%{word}%'")
            
        sql_query = f"""
        SELECT source_node, relation, target_node
        FROM knowledge_graph
        WHERE {' OR '.join(conditions)}
        LIMIT 10
        """
        
        rows = await conn.fetch(sql_query)
        if not rows:
            return ""
            
        graph_text = "Contexto Estructural (GraphRAG):\n"
        for r in rows:
            graph_text += f"- [{r['source_node']}] --({r['relation']})--> [{r['target_node']}]\n"
            
        return graph_text
    finally:
        await conn.close()
