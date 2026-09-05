import os
import asyncio
import asyncpg
import instructor
from pydantic import BaseModel, Field
from typing import List
from anthropic import AsyncAnthropic
from src.models.search import SearchResult

DB_DSN = os.getenv("DATABASE_URL", "postgresql://app_user:apppassword@localhost:5433/postgres")
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

class RAGEvaluation(BaseModel):
    faithfulness_score: float = Field(
        ..., 
        description="Puntuación de 0.0 a 1.0 indicando si la respuesta es fiel al contexto (sin alucinaciones)."
    )
    relevance_score: float = Field(
        ..., 
        description="Puntuación de 0.0 a 1.0 indicando si la respuesta responde directamente a la pregunta."
    )
    context_precision_score: float = Field(
        ..., 
        description="Puntuación de 0.0 a 1.0 indicando si el contexto provisto contenía la información necesaria o si había basura irrelevante."
    )
    reasoning: str = Field(
        ..., 
        description="Breve explicación de las puntuaciones otorgadas."
    )

async def evaluate_rag_response(tenant_id: str, query: str, answer: str, context: List[SearchResult]):
    """
    Se ejecuta en background. Evalúa la calidad del ciclo RAG y lo guarda en la BD.
    """
    print("📊 [Evaluator] Ejecutando evaluación RAGAS-style en background...")
    
    context_text = "\n\n".join([f"Doc {i+1}:\n{doc.content}" for i, doc in enumerate(context)])
    
    prompt = f"""
    Eres un juez imparcial evaluando un sistema RAG. 
    Tu trabajo es evaluar 3 métricas de 0.0 a 1.0 basándote estrictamente en los datos provistos.
    
    1. Faithfulness (Fidelidad): ¿La Respuesta se deriva puramente del Contexto? Si menciona cosas que no están en el contexto (alucina), baja la nota.
    2. Answer Relevance (Relevancia): ¿La Respuesta aborda la Pregunta original?
    3. Context Precision (Precisión del Contexto): ¿El Contexto era útil para responder a la Pregunta?
    
    Pregunta: {query}
    
    Contexto: 
    {context_text}
    
    Respuesta:
    {answer}
    """
    
    try:
        evaluation = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            response_model=RAGEvaluation,
        )
        
        # Guardar en PostgreSQL
        conn = await asyncpg.connect(DB_DSN)
        try:
            await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
            sql = """
            INSERT INTO rag_evaluations (tenant_id, query, faithfulness_score, relevance_score, context_precision_score, reasoning)
            VALUES ($1, $2, $3, $4, $5, $6)
            """
            await conn.execute(
                sql, 
                tenant_id, 
                query, 
                evaluation.faithfulness_score, 
                evaluation.relevance_score, 
                evaluation.context_precision_score, 
                evaluation.reasoning
            )
            print(f"✅ [Evaluator] Evaluación guardada: Fidelidad={evaluation.faithfulness_score} | Relevancia={evaluation.relevance_score} | Contexto={evaluation.context_precision_score}")
        finally:
            await conn.close()
            
    except Exception as e:
        print(f"⚠️ [Evaluator] Error durante la evaluación: {e}")
