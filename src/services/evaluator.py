import os
import uuid
import asyncio
import instructor
from typing import List, Optional
from anthropic import AsyncAnthropic

from src.config import ANTHROPIC_MODEL
from src.models.evaluation import RAGEvaluation
from src.models.search import SearchResult
from src.services.db import tenant_connection
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

async def evaluate_rag_response(tenant_id: uuid.UUID, query: str, answer: str, context: List[SearchResult],
                                expected_language: Optional[str] = None, detected_language: Optional[str] = None):
    """
    Runs in the background. Evaluates the quality of the RAG cycle and stores it in the DB.

    The two languages come from the endpoint, which already checked the answer (BUG-11):
    they are stored with the scores so the mismatch rate can be read next to them.
    None means unknown.
    """
    print("📊 [Evaluator] Running RAGAS-style evaluation in the background...")
    
    context_text = "\n\n".join([f"Doc {i+1}:\n{doc.content}" for i, doc in enumerate(context)])
    
    prompt = f"""
    You are an impartial judge evaluating a RAG system.
    Your job is to score 3 metrics from 0.0 to 1.0 based strictly on the data provided.
    The question, the context and the answer may be in Spanish or English; judge the content, not the language.
    
    1. Faithfulness: Is the Answer derived purely from the Context? If it mentions things that are not in the context (hallucinates), lower the score.
    2. Answer Relevance: Does the Answer address the original Question?
    3. Context Precision: Was the Context useful for answering the Question?
    
    Question: {query}
    
    Context: 
    {context_text}
    
    Answer:
    {answer}
    """
    
    try:
        evaluation = await client.messages.create(
            model=ANTHROPIC_MODEL,
            # With 300, the judge's answer was cut off in the middle of the JSON and the
            # evaluation was lost (PERF-04). The reasoning is bounded in the schema.
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            response_model=RAGEvaluation,
            # If a score is out of range or the reasoning runs long, Instructor retries by
            # sending back the validation error. 3 is its default in 1.16; it is pinned so
            # as not to depend on what another version ships.
            max_retries=3,
        )
        
        # Store in PostgreSQL
        async with tenant_connection(tenant_id) as conn:
            sql = """
            INSERT INTO rag_evaluations (tenant_id, query, faithfulness_score, relevance_score, context_precision_score, reasoning,
                                         expected_language, detected_language)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """
            await conn.execute(
                sql, 
                tenant_id, 
                query, 
                evaluation.faithfulness_score, 
                evaluation.relevance_score, 
                evaluation.context_precision_score, 
                evaluation.reasoning,
                expected_language,
                detected_language
            )
            print(f"✅ [Evaluator] Evaluation stored: Faithfulness={evaluation.faithfulness_score} | Relevance={evaluation.relevance_score} | Context={evaluation.context_precision_score}")
            
    except Exception as e:
        print(f"⚠️ [Evaluator] Error during the evaluation: {e}")
