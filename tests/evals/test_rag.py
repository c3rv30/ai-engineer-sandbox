import os
import pytest
from dotenv import load_dotenv
load_dotenv()

from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, ContextualRelevancyMetric

from src.services.retriever import retrieve_documents
from src.services.reranker import rerank_documents
from src.services.extractor import generate_answer

# Para DeepEval, el modelo evaluador ("juez") usa OpenAI por defecto, 
# pero podemos configurarlo para usar Anthropic seteando la variable correcta si quisieramos,
# o podemos dejar que falle de la misma forma hasta que tengas tu API Key funcional.

@pytest.mark.asyncio
async def test_rag_contextual_relevancy_and_faithfulness():
    """
    Evalúa que:
    1. El contexto recuperado sea relevante a la pregunta (Contextual Relevancy).
    2. La respuesta generada no alucine y se base estrictamente en el contexto (Faithfulness).
    """
    query = "¿Para qué sirve el archivo pyproject.toml?"
    
    # 1. Recuperar contexto (Vectorial + FlashRank)
    vector_candidates = await retrieve_documents(query, top_k=5)
    best_results = await rerank_documents(query, vector_candidates, top_k=3)
    
    # 2. Generar respuesta
    structured_response = await generate_answer(query, best_results)
    
    # 3. Formatear para DeepEval
    retrieval_context = [doc.content for doc in best_results]
    actual_output = structured_response.answer
    
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=retrieval_context
    )
    
    # 4. Definir Métricas
    # Faithfulness: ¿La respuesta alucina? (Threshold 0.7 = 70% de confianza mínimo)
    faithfulness_metric = FaithfulnessMetric(threshold=0.7)
    
    # Contextual Relevancy: ¿Los chunks recuperados son relevantes para la pregunta?
    context_relevancy_metric = ContextualRelevancyMetric(threshold=0.5)
    
    # 5. Ejecutar Asserts
    # DeepEval llamará al LLM "Juez" para puntuar la salida de nuestro pipeline
    assert_test(test_case, [faithfulness_metric, context_relevancy_metric])
