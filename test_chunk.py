import re
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def cosine_distance(a, b):
    return 1 - (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def semantic_chunking_dynamic(text: str):
    sentences = re.split(r'(?<=[.?!])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 3: return [text]
    
    embeddings = model.encode(sentences)
    distances = [cosine_distance(embeddings[i], embeddings[i+1]) for i in range(len(sentences)-1)]
    
    # Threshold dinámico: media + desviación estándar
    threshold = np.mean(distances) + 1.25 * np.std(distances)
    
    chunks = []
    current_chunk = [sentences[0]]
    for i in range(1, len(sentences)):
        if distances[i-1] > threshold:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentences[i]]
        else:
            current_chunk.append(sentences[i])
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

text = "PostgreSQL es una base de datos muy robusta. Ofrece soporte avanzado para vectores. Además soporta FTS de manera nativa. Docker permite desplegar contenedores rápidamente. Aisla el entorno de la aplicación. Kubernetes orquesta estos contenedores en producción. Mi perro se llama Firulais. Es un golden retriever muy amigable. Le encanta salir a pasear por el parque."
print(semantic_chunking_dynamic(text))
