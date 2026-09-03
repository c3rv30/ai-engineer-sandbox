import requests
import time

start = time.time()
r = requests.post(
    "http://127.0.0.1:8000/chat/stream/",
    json={"query": "Analiza la evolucion tecnica de Bryan Bobadilla", "history": []},
    stream=True
)

for line in r.iter_lines():
    if line:
        elapsed = time.time() - start
        print(f"[{elapsed:.2f}s] length: {len(line)}")
