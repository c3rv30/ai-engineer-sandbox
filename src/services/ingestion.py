import asyncio
import uuid
import json
import os
import argparse
import base64
from typing import List, Dict, Any

from pydantic import BaseModel, Field
import tiktoken
import fitz  # PyMuPDF
from anthropic import AsyncAnthropic
from langfuse import observe
from dotenv import load_dotenv

from src.services.embeddings import EMBEDDING_MODEL, encode, to_pgvector

load_dotenv()


class DocumentChunk(BaseModel):
    text: str = Field(..., description="The text content of the chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata attached to the chunk")
    embedding: List[float] | None = Field(default=None, description="Embedding vector")

class IngestionResult(BaseModel):
    total_chunks: int
    inserted_chunks: int

import re
import numpy as np

def cosine_distance(a, b):
    # Avoids division by 0 on empty vectors
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1 - (np.dot(a, b) / (norm_a * norm_b))

@observe(name="semantic_chunk_text")
def chunk_text(content: str, source_type: str, max_tokens: int = 400, overlap: int = 0) -> List[DocumentChunk]:
    """
    Phase 4: Semantic Chunking.
    Splits the text on sentence boundaries and groups the sentences mathematically
    by the similarity of their embeddings (all-MiniLM-L6-v2), with a size limit (max_tokens).
    """
    encoder = tiktoken.get_encoding("cl100k_base")
    
    # 1. Split into sentences, respecting acronyms and periods (simple regex)
    sentences = re.split(r'(?<=[.?!])\s+', content)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return []
    
    # If it is very short, the embedding math is not worth it
    if len(sentences) == 1:
        return [DocumentChunk(
            text=sentences[0],
            metadata={"source_type": source_type, "chunk_size_tokens": len(encoder.encode(sentences[0]))}
        )]
        
    # 2. Embed the sentences to compare similarity
    # It is CPU work (~1.2 s for 400 sentences): from async code, chunk_text must be
    # called with asyncio.to_thread or the server stops serving while it runs (PERF-03).
    sentence_embeddings = encode(sentences)
    
    distances = [cosine_distance(sentence_embeddings[i], sentence_embeddings[i+1]) for i in range(len(sentences)-1)]
    
    # Dynamic threshold: cut when the current sentence diverges significantly from the
    # document's norm, or when the token limit is exceeded
    threshold = np.mean(distances) + 1.25 * np.std(distances)
    
    chunks = []
    current_chunk_sentences = [sentences[0]]
    current_chunk_tokens = len(encoder.encode(sentences[0]))
    
    for i in range(1, len(sentences)):
        sentence = sentences[i]
        tokens_count = len(encoder.encode(sentence))
        
        dist = distances[i-1]
        
        # Break if the topic changed drastically OR if the limit is exceeded
        if dist > threshold or (current_chunk_tokens + tokens_count) > max_tokens:
            chunks.append(DocumentChunk(
                text=" ".join(current_chunk_sentences),
                metadata={"source_type": source_type, "chunk_size_tokens": current_chunk_tokens}
            ))
            current_chunk_sentences = [sentence]
            current_chunk_tokens = tokens_count
        else:
            current_chunk_sentences.append(sentence)
            current_chunk_tokens += tokens_count
            
    if current_chunk_sentences:
        chunks.append(DocumentChunk(
            text=" ".join(current_chunk_sentences),
            metadata={"source_type": source_type, "chunk_size_tokens": current_chunk_tokens}
        ))
        
    return chunks

@observe(name="describe_image_with_claude")
async def describe_image_with_claude(image_bytes: bytes, media_type: str = "image/png") -> str:
    """Uses Claude to describe the content of an image so it can be embedded."""
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    b64_img = base64.b64encode(image_bytes).decode('utf-8')
    # In Spanish, the language of the corpus: full-text search uses the 'spanish'
    # configuration (sql/01_init.sql), so a description in another language would only
    # be found by the vector search.
    prompt = "You are an expert analyst extracting information for RAG. Describe this image in great detail. Extract all visible text verbatim. If it is a chart or a table, describe its axes, metrics and relations. Write the description in Spanish."
    
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_img}},
                    {"type": "text", "text": prompt}
                ]
            }
        ],
    )
    return response.content[0].text

@observe(name="process_pdf")
async def process_pdf(file_path: str) -> List[DocumentChunk]:
    doc = fitz.open(file_path)
    chunks = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Extract text
        text = page.get_text()
        if text.strip():
            page_chunks = await asyncio.to_thread(chunk_text, text, source_type=f"pdf_page_{page_num+1}")
            chunks.extend(page_chunks)
            
        # Extract images (simple)
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            media_type = f"image/{ext}" if ext in ["jpeg", "png", "gif", "webp"] else "image/png"
            
            print(f"-> Analyzing image {img_index+1} on page {page_num+1} with Claude Vision...")
            try:
                description = await describe_image_with_claude(image_bytes, media_type)
                chunks.append(DocumentChunk(
                    text=f"[Image on page {page_num+1}]: {description}",
                    metadata={"source_type": "pdf_image", "page": page_num+1}
                ))
            except Exception as e:
                print(f"Error analyzing image: {e}")
                
    return chunks

@observe(name="generate_embeddings_local")
async def generate_embeddings(chunks: List[DocumentChunk]) -> List[DocumentChunk]:
    if not chunks:
        return chunks
    texts = [chunk.text for chunk in chunks]
    embeddings_np = await asyncio.to_thread(encode, texts)
    for chunk, emb in zip(chunks, embeddings_np):
        chunk.embedding = emb.tolist()
    return chunks

from src.services.graphrag import extract_knowledge_graph, insert_knowledge_graph
from src.services.db import close_pool, tenant_connection

@observe(name="insert_documents_db")
async def insert_documents(chunks: List[DocumentChunk], source: str, tenant_id: uuid.UUID) -> List[str]:
    """Inserts chunks and returns the generated IDs."""
    if not chunks:
        return []
    async with tenant_connection(tenant_id) as conn:
        insert_query = """
        INSERT INTO documents (tenant_id, content, embedding, metadata)
        VALUES ($1, $2, $3::vector, $4)
        RETURNING id
        """
        records = []
        for chunk in chunks:
            emb_str = to_pgvector(chunk.embedding)
            chunk.metadata["source"] = source
            records.append((tenant_id, chunk.text, emb_str, json.dumps(chunk.metadata)))
            
        # executemany does not support RETURNING easily, so we use a loop with execute or executemany without ids
        # To get the IDs we use prepared statements
        stmt = await conn.prepare(insert_query)
        ids = []
        for rec in records:
            row_id = await stmt.fetchval(*rec)
            ids.append(str(row_id))
            
        return ids

@observe(name="ingestion_pipeline")
async def ingest_file(file_path: str, tenant_id: uuid.UUID, source: str | None = None) -> IngestionResult:
    # Name that identifies the document in metadata["source"]. It is separate from
    # file_path because the API ingests from a temporary file with a random name.
    source = source or os.path.basename(file_path)
    print(f"Processing {source}...")
    chunks = []
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".md" or ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = await asyncio.to_thread(chunk_text, content, source_type="markdown")
    elif ext == ".pdf":
        chunks = await process_pdf(file_path)
    elif ext in [".png", ".jpg", ".jpeg"]:
        print("-> Analyzing standalone image with Claude Vision...")
        with open(file_path, "rb") as f:
            img_bytes = f.read()
        media_type = f"image/{ext[1:]}"
        desc = await describe_image_with_claude(img_bytes, media_type)
        chunks.append(DocumentChunk(
            text=f"[Image {source}]: {desc}",
            metadata={"source_type": "standalone_image"}
        ))
    else:
        raise ValueError(f"Unsupported format: {ext}")
        
    print(f"-> {len(chunks)} chunks generated in total.")
    
    print(f"Computing embeddings with {EMBEDDING_MODEL} (local)...")
    chunks_with_embeddings = await generate_embeddings(chunks)
    
    print("Inserting into PostgreSQL...")
    inserted_ids = await insert_documents(chunks_with_embeddings, source, tenant_id)
    print(f"-> {len(inserted_ids)} rows inserted.")
    
    print("Running the GraphRAG pipeline in parallel...")
    async def process_graphrag(chunk, chunk_id):
        triplets = await extract_knowledge_graph(chunk.text)
        await insert_knowledge_graph(tenant_id, chunk_id, triplets)
        
    tasks = [process_graphrag(c, cid) for c, cid in zip(chunks_with_embeddings, inserted_ids)]
    await asyncio.gather(*tasks)
    print("-> GraphRAG extraction completed.")
    
    return IngestionResult(total_chunks=len(chunks), inserted_chunks=len(inserted_ids))

async def main():
    parser = argparse.ArgumentParser(description="Multimodal ingestion (MD, PDF, images) into PostgreSQL")
    parser.add_argument("file", help="Path to the file to ingest")
    # type=uuid.UUID makes argparse validate and reject a malformed tenant.
    parser.add_argument("--tenant", help="Tenant ID for RLS (UUID)", type=uuid.UUID,
                        default=uuid.UUID("00000000-0000-0000-0000-000000000000"))
    args = parser.parse_args()
    if not os.path.exists(args.file):
        print(f"Error: the file '{args.file}' does not exist.")
        return
    try:
        await ingest_file(args.file, args.tenant)
    finally:
        # Close the pool's connections before asyncio.run closes the loop; otherwise
        # the process ends by cutting them off without saying goodbye to the server.
        await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
