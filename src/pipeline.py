import asyncio
import argparse
import json
from src.services.retriever import retrieve_documents
from src.services.reranker import rerank_documents
from src.services.extractor import generate_answer
from langfuse import observe

@observe(name="rag_pipeline")
async def run_search_pipeline(query: str, answer_language: str):
    print(f"\n[1] Question: '{query}'")
    
    print("\n[2] Stage 1: Vector retrieval (Retriever)...")
    candidates = await retrieve_documents(query, top_k=5)
    
    for i, c in enumerate(candidates, 1):
        print(f"  -> {i}. Score: {c.score:.4f} | Text: {c.content[:60].replace(chr(10), ' ')}...")
        
    print("\n[3] Stage 2: Re-ranking with a cross-encoder (FlashRank)...")
    best_results = await rerank_documents(query, candidates, top_k=3)
    
    for i, r in enumerate(best_results, 1):
        print(f"  -> {i}. Re-Rank Score: {r.rerank_score:.4f} | Vector Score: {r.score:.4f} | Text: {r.content[:60].replace(chr(10), ' ')}...")
        
    print("\n[4] Stage 3: Structured generation (Anthropic + Instructor)...")
    if not best_results:
        print("No documents found.")
        return
        
    answer = await generate_answer(query, best_results, answer_language)
    
    print("\n================ STRUCTURED ANSWER ================")
    # Pretty-print the Pydantic model
    print(json.dumps(answer.model_dump(), indent=2, ensure_ascii=False))
    print("===================================================\n")
    
    print("\n[Done!]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full RAG pipeline")
    parser.add_argument("query", help="Question to search for and answer")
    # Without the graph there is no supervisor to decide it (BUG-11).
    parser.add_argument("--language", choices=["es", "en"], required=True, help="Language of the answer")
    args = parser.parse_args()
    
    asyncio.run(run_search_pipeline(args.query, args.language))
