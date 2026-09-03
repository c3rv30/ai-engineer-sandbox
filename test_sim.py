from sentence_transformers import SentenceTransformer
import torch
import torch.nn.functional as F

model = SentenceTransformer("all-MiniLM-L6-v2")

q1 = "¿Qué tecnologías de base de datos sabe usar Bryan?"
q2 = "¿Bryan conoce alguna tecnología de base de datos?"

e1 = model.encode(q1, convert_to_tensor=True)
e2 = model.encode(q2, convert_to_tensor=True)

sim = F.cosine_similarity(e1.unsqueeze(0), e2.unsqueeze(0))
print(f"Similitud: {sim.item()}")
