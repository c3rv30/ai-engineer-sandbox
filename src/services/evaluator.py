import os
import uuid
import asyncio
import instructor
from typing import List
from anthropic import AsyncAnthropic
from src.models.evaluation import RAGEvaluation
from src.models.search import SearchResult
from src.services.db import tenant_connection
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

async def evaluate_rag_response(tenant_id: uuid.UUID, query: str, answer: str, context: List[SearchResult]):
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
            # Con 300, la respuesta del juez se cortaba a mitad del JSON y la evaluación se
            # perdía (PERF-04). El razonamiento queda acotado en el esquema.
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            response_model=RAGEvaluation,
            # Si una puntuación sale de rango o el razonamiento se alarga, Instructor reintenta
            # devolviendo el error de validación. 3 es su valor por defecto en 1.16; se fija
            # para no depender de lo que traiga otra versión.
            max_retries=3,
        )
        
        # Guardar en PostgreSQL
        async with tenant_connection(tenant_id) as conn:
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
            
    except Exception as e:
        print(f"⚠️ [Evaluator] Error durante la evaluación: {e}")
