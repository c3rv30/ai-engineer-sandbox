# 🛠️ Architecture and Troubleshooting Guide

This document records the architecture decisions, the problems found while building Phases 2 and 3 of the AI Engineer Sandbox, and the solutions implemented. It serves as a reference or post-mortem for future work.

---

## 1. Problem: the agent blocks valid questions (Agentic Router)

**Symptom:** 
Asking *"Who is Bryan Bobadilla?"*, the system answered: *"I am an AI Sandbox focused on technical matters... The question about a person is outside my scope"*.

**Cause:**
The intent router (`src/services/router.py`) was told to classify as `out_of_scope` any question that was not strictly technical (code, architecture, cloud). It had no context that "Bryan Bobadilla" was the author of the résumé being analyzed.

**Solution:**
The router agent's system prompt was updated to state the current context explicitly:
> *"You are the Router of a Sandbox that is currently analyzing Bryan Bobadilla's résumé. If it is a question about his experience or profile, classify it as `knowledge_search`."*

---

## 2. Problem: the re-ranker drops vital information (Top-K and duplicates)

**Symptom:**
Even though the system routed the question correctly, the LLM answered: *"I have no information available about Bryan Bobadilla"*, even when the DB did contain his name.

**Causes:**
1. **Data poisoning (duplicates):** Testing the upload of the same PDF several times filled the database with identical copies. The vector search got the 5 best results (`top_k=5`), and all 5 were clones of the same chunk.
2. **Cross-encoder bias:** We used `FlashRank` with the `ms-marco-TinyBERT` model (optimized for English). Scoring a short chunk in Spanish (only the name and email), it gave it a very low score, pushing it out of the Top 3 that was finally sent to Claude.

**Solution:**
1. **In-memory deduplication:** In `src/api/routers/chat.py`, the initial search was raised to `15` chunks, and an iterative step removes identical chunks (`content not in seen`) before passing them to the re-ranker.
2. **Wider context window:** `src/models/requests.py` was changed to raise `top_k_rerank` from 3 to 7. Modern models support huge context windows, so it is better to err on the side of too much context than too little.
   *Note (2026-09-14): after the migration to LangGraph this parameter stopped being applied; the researcher used a fixed 10. Today the default is 10 and `researcher_node` honors whatever the client sends. See `BUG-06` in [`TECHNICAL_AUDIT.md`](TECHNICAL_AUDIT.md).*
3. **DB cleanup:** A `DELETE FROM documents;` was run to purge the flood of clones.

---

## 3. Problem: backend connection drops ("the backend is down")

**Symptom:**
The user gets a red error in Streamlit: *`Max retries exceeded with url: /chat/... Connection refused`* or *`405 Method Not Allowed`*.

**Causes:**
1. **Uvicorn hot reloading:** With Uvicorn running with the `--reload` flag, any file edit (such as `README.md` or a `.py`) restarted the server on the fly. During those 10 seconds, Uvicorn loads the heavy machine learning models (`SentenceTransformers` and `FlashRank`) into RAM. A request made in that exact window was refused.
2. **Zombie processes:** Using the `wait` command, or the lack of `nohup` in background terminals, made the Python subprocesses die when the terminal detached.

**Solution:**
- Robust port handling, killing zombies first (`lsof -t -i:8000 | xargs kill -9`).
- Explaining to the user the temporary latency of the ML models' cold starts.

---

## 4. Problem: the Streamlit frontend freezes while streaming (SSE)

**Symptom:**
When **real-time streaming (SSE)** was implemented with `instructor.Partial`, the Streamlit web interface collapsed, flickered erratically or hit a timeout error.

**Cause:**
The `instructor` library emits one network event for every single *token* the LLM generates, sending the **complete** JSON object (which keeps growing). For a 500-word answer, it sent 500 JSON objects per second (more than 150 KB of traffic). The Streamlit script tried to `json.loads` and redraw the interface (`st.markdown`) 500 times per second, choking the UI thread.

**Solution (native streaming wrapper):**
Instead of forcing manual updates with `st.markdown`, the consumer was rewritten as a native Python generator that computes the "diff" (the new characters) of each JSON chunk, and rendering is delegated to Streamlit's official `st.write_stream()` function. 
```python
def stream_parser():
    global final_sources, final_confidence
    last_yielded_length = 0
    # ...
```

*Note:* If the UI code is not wrapped in a `main()` function, the variables initialized in the `if` block live in the module's global _scope_. Therefore, inside `stream_parser()` you cannot use `nonlocal final_sources` (it raises `SyntaxError`); you must use `global final_sources` to modify the variable that feeds the expanders afterwards.

This lets Streamlit's internal WebSocket engine (`Tornado`) handle *backpressure* and render the tokens one by one at the right speed, producing the familiar ChatGPT-style typing effect.

*Note (Phase 4):* with the migration to LangGraph the producer changed, not the consumer. The tokens no longer go straight from `generate_answer_stream` to the endpoint: `generator_node` writes them to the graph's `custom` channel (`get_stream_writer()`), and `/chat/stream/` consumes them together with the per-node progress through `astream(stream_mode=["updates", "custom"])`. The `stream_parser()` described above still works as is, because the SSE format did not change: every event still carries the full accumulated `answer`.

---

## 5. Problem: type error from partial objects ("NoneType and str")

**Symptom:**
When streaming started, Streamlit crashed immediately: `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'`.

**Cause:**
With `instructor.Partial[StructuredAnswer]`, before the LLM starts predicting the first letters of the answer, the emitted JSON object has the structure of the keys but with null values: `{"answer": null}`.
The Python line:
`final_answer = data.get("answer", "")` 
returned `None` (because the `"answer"` key does exist in the JSON, and its value is literally null). When the code tried to concatenate `final_answer + "▌"`, it crashed trying to add `None` to a string.

**Solution:**
It was fixed with a logical OR (`or`) that falls back to an empty string if the value is `None` or falsy:
`final_answer = data.get("answer") or ""`

---

## 6. Problem: Pydantic validation failures when asking for long essays

**Symptom:**
Asking the bot for a complex, long analysis (e.g. "Analyze in detail..."), the backend raised: `3 validation errors for StructuredAnswer answer Field required [type=missing, input_value={}, input_type=dict]`.

**Cause:**
When fast models like Claude Haiku 3.5 get prompts asking them to "write a long report", they occasionally decide to ignore `instructor`'s strict tool-calling wrapper (which requires generating a JSON) and return raw text instead, so the `instructor` engine reads a completely empty `{}` object at the end of the stream and Pydantic raises a validation error for the missing fields.

**Solution:**
The prompt in `extractor.py` was adjusted to strongly instruct the model to pack its whole long analysis inside the JSON:
> *"VERY IMPORTANT: You must return your answer structured. If you are going to write a long analysis, put all the text, formatted in Markdown, inside the 'answer' field. Do not answer with plain text outside the JSON schema."*
In addition, `max_tokens` was raised from 1024 to 2048 so the output is not cut off by the limit and breaks the validation of the final JSON.
