import asyncio
import uuid
import json
import os
import argparse
import base64
from typing import List, Dict, Any

from pydantic import BaseModel, Field
import tiktoken
import asyncpg
import fitz  # PyMuPDF
from anthropic import AsyncAnthropic
from langfuse import observe
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# Configuración
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DB_DSN = os.getenv("DATABASE_URL", "postgresql://postgres:postgrespassword@localhost:5433/postgres")

print(f"Cargando modelo local {EMBEDDING_MODEL} (esto puede tomar un momento la primera vez)...")
model = SentenceTransformer(EMBEDDING_MODEL)
print("Modelo cargado.")

class DocumentChunk(BaseModel):
    text: str = Field(..., description="El contenido de texto del chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos asociados al chunk")
    embedding: List[float] | None = Field(default=None, description="Vector de embedding")

class IngestionResult(BaseModel):
    total_chunks: int
    inserted_chunks: int

import re
import numpy as np

def cosine_distance(a, b):
    # Previene division por 0 en vectores vacíos
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1 - (np.dot(a, b) / (norm_a * norm_b))

@observe(name="semantic_chunk_text")
def chunk_text(content: str, source_type: str, max_tokens: int = 400, overlap: int = 0) -> List[DocumentChunk]:
    """
    Fase 4: Semantic Chunking Inteligente.
    Divide el texto respetando los límites de las oraciones y agrupándolas matemáticamente 
    según la similitud de sus embeddings (all-MiniLM-L6-v2) con un límite de tamaño (max_tokens).
    """
    encoder = tiktoken.get_encoding("cl100k_base")
    
    # 1. Separar por oraciones respetando acrónimos y puntos (Regex simple)
    sentences = re.split(r'(?<=[.?!])\s+', content)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return []
    
    # Si es muy corto, no vale la pena hacer la matemática de embeddings
    if len(sentences) == 1:
        return [DocumentChunk(
            text=sentences[0],
            metadata={"source_type": source_type, "chunk_size_tokens": len(encoder.encode(sentences[0]))}
        )]
        
    # 2. Vectorizar oraciones para comparar similitud
    # Al estar corriendo en la ingestión, esto es instantáneo localmente
    sentence_embeddings = model.encode(sentences)
    
    distances = [cosine_distance(sentence_embeddings[i], sentence_embeddings[i+1]) for i in range(len(sentences)-1)]
    
    # Umbral Dinámico: Cortar cuando la oración actual diverja significativamente de la norma del documento
    # O si superamos el límite matemático de tokens
    threshold = np.mean(distances) + 1.25 * np.std(distances)
    
    chunks = []
    current_chunk_sentences = [sentences[0]]
    current_chunk_tokens = len(encoder.encode(sentences[0]))
    
    for i in range(1, len(sentences)):
        sentence = sentences[i]
        tokens_count = len(encoder.encode(sentence))
        
        dist = distances[i-1]
        
        # Romper si cambió el tema drásticamente O si nos pasamos del límite
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
    """Usa Claude para describir el contenido de una imagen y poder vectorizarlo."""
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    b64_img = base64.b64encode(image_bytes).decode('utf-8')
    prompt = "Eres un experto analista extrayendo información para RAG. Describe en sumo detalle esta imagen. Extrae todo el texto visible. Si es un gráfico o tabla, describe sus ejes, métricas y relaciones."
    
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
        
        # Extraer Texto
        text = page.get_text()
        if text.strip():
            page_chunks = chunk_text(text, source_type=f"pdf_page_{page_num+1}")
            chunks.extend(page_chunks)
            
        # Extraer Imágenes (Simple)
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            media_type = f"image/{ext}" if ext in ["jpeg", "png", "gif", "webp"] else "image/png"
            
            print(f"-> Analizando imagen {img_index+1} de la página {page_num+1} con Claude Vision...")
            try:
                description = await describe_image_with_claude(image_bytes, media_type)
                chunks.append(DocumentChunk(
                    text=f"[Imagen en página {page_num+1}]: {description}",
                    metadata={"source_type": "pdf_image", "page": page_num+1}
                ))
            except Exception as e:
                print(f"Error analizando imagen: {e}")
                
    return chunks

@observe(name="generate_embeddings_local")
async def generate_embeddings(chunks: List[DocumentChunk]) -> List[DocumentChunk]:
    if not chunks:
        return chunks
    texts = [chunk.text for chunk in chunks]
    embeddings_np = await asyncio.to_thread(model.encode, texts)
    for chunk, emb in zip(chunks, embeddings_np):
        chunk.embedding = emb.tolist()
    return chunks

from src.services.graphrag import extract_knowledge_graph, insert_knowledge_graph

@observe(name="insert_documents_db")
async def insert_documents(chunks: List[DocumentChunk], source: str, tenant_id: uuid.UUID) -> List[str]:
    """Inserta chunks y devuelve los IDs generados."""
    if not chunks:
        return []
    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
        insert_query = """
        INSERT INTO documents (tenant_id, content, embedding, metadata)
        VALUES ($1, $2, $3::vector, $4)
        RETURNING id
        """
        records = []
        for chunk in chunks:
            emb_str = f"[{','.join(str(x) for x in chunk.embedding)}]"
            chunk.metadata["source"] = source
            records.append((tenant_id, chunk.text, emb_str, json.dumps(chunk.metadata)))
            
        # executemany no soporta RETURNING fácilmente, así que usamos un bucle con execute o executemany sin ids
        # Para obtener IDs usaremos prepared statements
        stmt = await conn.prepare(insert_query)
        ids = []
        for rec in records:
            row_id = await stmt.fetchval(*rec)
            ids.append(str(row_id))
            
        return ids
    finally:
        await conn.close()

@observe(name="ingestion_pipeline")
async def ingest_file(file_path: str, tenant_id: uuid.UUID) -> IngestionResult:
    print(f"Procesando {file_path}...")
    chunks = []
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".md" or ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = chunk_text(content, source_type="markdown")
    elif ext == ".pdf":
        chunks = await process_pdf(file_path)
    elif ext in [".png", ".jpg", ".jpeg"]:
        print("-> Analizando imagen individual con Claude Vision...")
        with open(file_path, "rb") as f:
            img_bytes = f.read()
        media_type = f"image/{ext[1:]}"
        desc = await describe_image_with_claude(img_bytes, media_type)
        chunks.append(DocumentChunk(
            text=f"[Imagen {os.path.basename(file_path)}]: {desc}",
            metadata={"source_type": "standalone_image"}
        ))
    else:
        raise ValueError(f"Formato no soportado: {ext}")
        
    print(f"-> {len(chunks)} chunks generados en total.")
    
    print(f"Calculando embeddings con {EMBEDDING_MODEL} (Local)...")
    chunks_with_embeddings = await generate_embeddings(chunks)
    
    print("Insertando en PostgreSQL...")
    inserted_ids = await insert_documents(chunks_with_embeddings, file_path, tenant_id)
    print(f"-> {len(inserted_ids)} registros insertados.")
    
    print("Ejecutando Pipeline GraphRAG en paralelo...")
    async def process_graphrag(chunk, chunk_id):
        triplets = await extract_knowledge_graph(chunk.text)
        await insert_knowledge_graph(tenant_id, chunk_id, triplets)
        
    tasks = [process_graphrag(c, cid) for c, cid in zip(chunks_with_embeddings, inserted_ids)]
    await asyncio.gather(*tasks)
    print("-> GraphRAG Extracción Completada.")
    
    return IngestionResult(total_chunks=len(chunks), inserted_chunks=len(inserted_ids))

async def main():
    parser = argparse.ArgumentParser(description="Ingesta Multimodal (MD, PDF, Imágenes) a PostgreSQL")
    parser.add_argument("file", help="Ruta al archivo a ingestar")
    # type=uuid.UUID hace que argparse valide y rechace un tenant mal formado.
    parser.add_argument("--tenant", help="ID del Tenant para RLS (UUID)", type=uuid.UUID,
                        default=uuid.UUID("00000000-0000-0000-0000-000000000000"))
    args = parser.parse_args()
    if not os.path.exists(args.file):
        print(f"Error: El archivo '{args.file}' no existe.")
        return
    await ingest_file(args.file, args.tenant)

if __name__ == "__main__":
    asyncio.run(main())
