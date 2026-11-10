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

# DeepEval's evaluator model ("judge") uses OpenAI by default,
# but it could be configured to use Anthropic by setting the right variable,
# or left to fail the same way until there is a working API key.

@pytest.mark.asyncio
async def test_rag_contextual_relevancy_and_faithfulness():
    """
    Evaluates that:
    1. The retrieved context is relevant to the question (Contextual Relevancy).
    2. The generated answer does not hallucinate and sticks strictly to the context (Faithfulness).
    """
    query = "What is the pyproject.toml file for?"
    
    # 1. Retrieve context (vector + FlashRank)
    vector_candidates = await retrieve_documents(query, top_k=5)
    best_results = await rerank_documents(query, vector_candidates, top_k=3)
    
    # 2. Generate the answer
    structured_response = await generate_answer(query, best_results)
    
    # 3. Format for DeepEval
    retrieval_context = [doc.content for doc in best_results]
    actual_output = structured_response.answer
    
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=retrieval_context
    )
    
    # 4. Define the metrics
    # Faithfulness: does the answer hallucinate? (threshold 0.7 = at least 70% confidence)
    faithfulness_metric = FaithfulnessMetric(threshold=0.7)
    
    # Contextual Relevancy: are the retrieved chunks relevant to the question?
    context_relevancy_metric = ContextualRelevancyMetric(threshold=0.5)
    
    # 5. Run the asserts
    # DeepEval will call the "judge" LLM to score our pipeline's output
    assert_test(test_case, [faithfulness_metric, context_relevancy_metric])
