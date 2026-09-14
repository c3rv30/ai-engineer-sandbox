# 🛠️ Guía de Arquitectura y Troubleshooting

Este documento registra las decisiones arquitectónicas, los problemas encontrados durante el desarrollo de la Fase 2 y 3 del AI Engineer Sandbox, y las soluciones implementadas. Sirve como referencia o post-mortem para futuros desarrollos.

---

## 1. Problema: El Agente bloquea preguntas válidas (Agentic Router)

**Síntoma:** 
Al preguntar *"¿Quién es Bryan Bobadilla?"*, el sistema respondió: *"Soy un AI Sandbox enfocado en asuntos técnicos... La pregunta sobre una persona está fuera de mi alcance"*.

**Causa:**
El Router de intenciones (`src/services/router.py`) estaba instruido para clasificar como `out_of_scope` cualquier pregunta que no fuera estrictamente técnica (código, arquitectura, nube). No tenía contexto de que "Bryan Bobadilla" era el autor del currículum que estábamos analizando.

**Solución:**
Se actualizó el `System Prompt` del Agente Enrutador indicándole explícitamente el contexto actual:
> *"Eres el Router de un Sandbox que actualmente está analizando el currículum de Bryan Bobadilla. Si es una pregunta sobre su experiencia o perfil, clasifícalo como `knowledge_search`."*

---

## 2. Problema: El Re-ranker omite información vital (Top-K y Duplicados)

**Síntoma:**
A pesar de que el sistema enrutaba bien la pregunta, el LLM respondía: *"No tengo información disponible sobre Bryan Bobadilla"*, incluso cuando la DB sí tenía su nombre.

**Causas:**
1. **Data Poisoning (Duplicados):** Al probar la subida del mismo PDF varias veces, la base de datos se llenó de copias idénticas. El buscador vectorial obtenía los 5 mejores resultados (`top_k=5`), y los 5 eran clones del mismo fragmento.
2. **Sesgo del Cross-Encoder:** Usamos `FlashRank` con el modelo `ms-marco-TinyBERT` (optimizado para inglés). Al evaluar un fragmento corto en español (solo el nombre y email), le asignó un puntaje bajísimo, sacándolo del Top 3 que finalmente se le enviaba a Claude.

**Solución:**
1. **Deduplicación en memoria:** En `src/api/routers/chat.py`, se aumentó la búsqueda inicial a `15` fragmentos, y se inyectó un algoritmo iterativo que elimina fragmentos idénticos (`content not in seen`) antes de pasarlos al Re-ranker.
2. **Ampliación del Context Window:** Se modificó `src/models/requests.py` para aumentar `top_k_rerank` de 3 a 7. Los modelos modernos soportan ventanas de contexto gigantes, por lo que es preferible pecar de exceso de contexto que de falta del mismo.
   *Nota (2026-09-14): tras la migración a LangGraph este parámetro dejó de aplicarse; el investigador usaba un 10 fijo. Hoy el valor por defecto es 10 y `researcher_node` respeta lo que envíe el cliente. Ver `BUG-06` en [`AUDITORIA_TECNICA.md`](AUDITORIA_TECNICA.md).*
3. **Limpieza de DB:** Se ejecutó un `DELETE FROM documents;` para purgar la saturación de clones.

---

## 3. Problema: Caídas de Conexión del Backend ("El back está caído")

**Síntoma:**
El usuario recibe un error rojo en Streamlit: *`Max retries exceeded with url: /chat/... Connection refused`* o *`405 Method Not Allowed`*.

**Causas:**
1. **Uvicorn Hot-Reloading:** Al estar corriendo Uvicorn con la flag `--reload`, cualquier edición a archivos (como `README.md` o `.py`) reiniciaba el servidor en caliente. Durante esos 10 segundos, Uvicorn carga los modelos pesados de Machine Learning (`SentenceTransformers` y `FlashRank`) a la memoria RAM. Si se hacía una petición en ese lapso exacto, se rechazaba.
2. **Procesos Zombies:** El uso del comando `wait` o la falta de `nohup` en terminales de background causaba que al desvincularse la terminal, los subprocesos de Python murieran.

**Solución:**
- Manejo robusto de puertos matando zombies previamente (`lsof -t -i:8000 | xargs kill -9`).
- Explicar al usuario la latencia temporal de los arranques en frío de los modelos ML.

---

## 4. Problema: El Frontend de Streamlit se congela al hacer Streaming (SSE)

**Síntoma:**
Al implementar **Streaming Real-time (SSE)** con `instructor.Partial`, la interfaz web de Streamlit colapsaba, parpadeaba erráticamente o marcaba error de timeout.

**Causa:**
La librería `instructor` emite un evento de red por cada *token* individual que el LLM genera, enviando el objeto JSON **completo** (que va creciendo). Para una respuesta de 500 palabras, enviaba 500 JSONs por segundo (generando más de 150KB de red). El script de Streamlit intentaba hacer `json.loads` y re-dibujar la interfaz gráfica (`st.markdown`) 500 veces por segundo, ahogando el Thread de la UI.

**Solución (Native Streaming Wrapper):**
En lugar de forzar actualizaciones manuales con `st.markdown`, reescribimos el consumidor usando un generador nativo de Python que calcula el "diff" (los caracteres nuevos) de cada chunk JSON, y le delegamos el renderizado a la función oficial `st.write_stream()` de Streamlit. 
```python
def stream_parser():
    global final_sources, final_confidence
    last_yielded_length = 0
    # ...
```

*Nota:* Si el código de la UI no está envuelto en una función `main()`, las variables inicializadas en el bloque `if` viven en el _scope_ global del módulo. Por tanto, dentro de `stream_parser()` no se puede usar `nonlocal final_sources` (ya que arroja `SyntaxError`), sino que debe usarse `global final_sources` para poder modificar la variable que alimentará los expanders posteriores.

Esto permite que el motor interno de WebSockets de Streamlit (`Tornado`) maneje el *backpressure* y renderice visualmente los tokens uno a uno a la velocidad perfecta, creando el auténtico efecto visual de ChatGPT.

*Nota (Fase 4):* con la migración a LangGraph el emisor cambió, no el consumidor. Los tokens ya no salen directamente de `generate_answer_stream` hacia el endpoint: los escribe `generator_node` en el canal `custom` del grafo (`get_stream_writer()`), y `/chat/stream/` los consume junto al progreso por nodo con `astream(stream_mode=["updates", "custom"])`. El `stream_parser()` descrito arriba sigue siendo válido tal cual, porque el formato SSE no cambió: cada evento sigue llevando el `answer` acumulado completo.

---

## 5. Problema: Error de Tipos por Objetos Parciales ("NoneType and str")

**Síntoma:**
Al iniciar el streaming, Streamlit arrojaba un crash inmediato: `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'`.

**Causa:**
Al usar `instructor.Partial[StructuredAnswer]`, antes de que el LLM empiece a predecir las primeras letras de la respuesta, el objeto JSON emitido tiene la estructura de llaves pero con valores nulos: `{"answer": null}`.
La línea de código en Python:
`final_answer = data.get("answer", "")` 
Retornaba `None` (porque la llave `"answer"` sí existe en el JSON, y su valor es literalmente nulo). Cuando el código intentaba concatenar `final_answer + "▌"`, crasheaba por intentar sumar `None` con un String.

**Solución:**
Se corrigió usando un operador OR lógico (`or`) para que fuerce un fallback a string vacío si el valor es `None` o Falso:
`final_answer = data.get("answer") or ""`

---

## 6. Problema: Fallas de validación de Pydantic al pedir ensayos largos

**Síntoma:**
Al pedirle al bot que hiciera un análisis complejo y largo (ej. "Analiza detalladamente..."), el backend arrojaba: `3 validation errors for StructuredAnswer answer Field required [type=missing, input_value={}, input_type=dict]`.

**Causa:**
Cuando los modelos rápidos como Claude Haiku 3.5 reciben prompts que les piden "escribir un informe largo", ocasionalmente deciden ignorar el envoltorio estricto de Tool Calling de `instructor` (que requiere generar un JSON) y prefieren devolver texto en bruto directamente, lo que resulta en que el motor de `instructor` lea un objeto `{}` completamente vacío al finalizar el stream y Pydantic arroje error de validación por campos faltantes.

**Solución:**
Se ajustó el prompt del `extractor.py` para forzar e instruir fuertemente al modelo a empacar todo su análisis extenso dentro del JSON:
> *"MUY IMPORTANTE: Debes devolver tu respuesta estructurada. Si vas a escribir un análisis largo, pon todo el texto formateado en Markdown dentro del campo 'answer'. No respondas con texto plano fuera del esquema JSON."*
Además, se aumentó `max_tokens` de 1024 a 2048 para que no se corte por el límite y rompa la validación del JSON final.
