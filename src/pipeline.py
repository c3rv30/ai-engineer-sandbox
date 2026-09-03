import asyncio
import argparse
import json
from src.services.retriever import retrieve_documents
from src.services.reranker import rerank_documents
from src.services.extractor import generate_answer
from langfuse import observe

@observe(name="rag_pipeline")
async def run_search_pipeline(query: str):
    print(f"\n[1] Pregunta: '{query}'")
    
    print("\n[2] Etapa 1: Recuperación Vectorial (Retriever)...")
    candidates = await retrieve_documents(query, top_k=5)
    
    for i, c in enumerate(candidates, 1):
        print(f"  -> {i}. Score: {c.score:.4f} | Texto: {c.content[:60].replace(chr(10), ' ')}...")
        
    print("\n[3] Etapa 2: Re-ranking con Cross-Encoder (FlashRank)...")
    best_results = await rerank_documents(query, candidates, top_k=3)
    
    for i, r in enumerate(best_results, 1):
        print(f"  -> {i}. Re-Rank Score: {r.rerank_score:.4f} | Vector Score: {r.score:.4f} | Texto: {r.content[:60].replace(chr(10), ' ')}...")
        
    print("\n[4] Etapa 3: Generación Estructurada (Anthropic + Instructor)...")
    if not best_results:
        print("No se encontraron documentos.")
        return
        
    answer = await generate_answer(query, best_results)
    
    print("\n================ RESPUESTA ESTRUCTURADA ================")
    # Para imprimir el modelo pydantic de forma bonita
    print(json.dumps(answer.model_dump(), indent=2, ensure_ascii=False))
    print("========================================================\n")
    
    print("\n[¡Completado!]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba el pipeline completo de RAG")
    parser.add_argument("query", help="Pregunta a buscar y responder")
    args = parser.parse_args()
    
    asyncio.run(run_search_pipeline(args.query))
