# UAE Labour Law RAG Assistant

## What this is
A RAG chatbot that answers questions about 4 UAE laws with article-level citations:
UAE Labour Law (Federal Decree-Law 33/2021), its Executive Regulation (Cabinet Resolution 1/2022),
the 2022 Amendment (Decree-Law 14/2022) and the PDPL (Decree-Law 45/2021).
Built with LangChain + LangGraph, traced and evaluated with LangSmith. Course project (Week 2, RAG).

## Stack
- Python 3.12, venv in `.venv/` (activate: `source .venv/bin/activate`)
- LLM: Nebius Token Factory via `ChatOpenAI` (see `src/llm.py`, settings in `.env`)
- Embeddings: BAAI/bge-small-en-v1.5 (local), vector store: Chroma in `data/chroma/`
- Keyword search: BM25; fusion: RRF; re-ranker: FlashRank (local)
- UI: Streamlit (to be built in `app/`)

## The pipeline (DO NOT change its logic)
- `src/retrieval.py` — chunks, Chroma, BM25, hybrid search, re-rank
- `src/rewrite.py` — LLM query rewrite + dual re-rank (`retrieve_with_rewrite`)
- `src/graph.py` — LangGraph flow: rewrite → retrieve → (refuse | generate) → (refuse | generate retry | finalize)
  - `graph.stream(...)` / `graph.invoke(...)` with input `{"question": str}`
  - Final state keys: question, rewritten, results [(Document, score)], top_score, draft, attempts,
    answer, sources [str], path ("answered" | "answered_no_citation" | "refused_low_score" | "refused_by_llm")
  - Each Document has metadata: source, title, article, part, chunk_id; page_content starts with a
    header line like "[Labour Law — Article 29]"
  - `ask(question)` is a convenience wrapper; the answer text contains tags like [S1] that refer to
    `results[0]`, `results[1]`, ...
- `src/evaluation.py`, `scripts/run_eval.py` — LangSmith evaluation (15 questions, 3 versions)
- Evaluation results: `data/eval/v1/summary.csv` (A_naive, B_hybrid, C_full)

## Rules
- Do not edit `src/` logic. You may ADD small helper functions in a new file (e.g. `app/backend.py`).
- Never print or commit secrets from `.env`.
- macOS: torch + onnxruntime crash when called from several threads at once. Call the graph from ONE
  thread; set OMP_NUM_THREADS=1, KMP_DUPLICATE_LIB_OK=TRUE, TOKENIZERS_PARALLELISM=false before imports
  (already done at the top of `src/retrieval.py`; keep imports of `src` early in the app).
- Load the graph once with `st.cache_resource` (models take ~10 s to load).
- The bot explains the law; it is not legal advice. Keep a short disclaimer visible.