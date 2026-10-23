"""
Retrieval layer for the UAE Labour Law RAG bot.

Everything we built in notebooks 03-04, moved into one reusable module:
  - load the saved chunks (data/chunks/*.jsonl)
  - open the Chroma vector store from disk (no re-embedding)
  - build BM25 keyword indexes
  - hybrid search = dense + BM25 merged with Reciprocal Rank Fusion (RRF)
  - re-rank the candidates with a cross-encoder (FlashRank)

Usage (from a notebook in notebooks/):
    import sys; sys.path.insert(0, "..")
    from src.retrieval import retrieve, hybrid_search, label
"""
import os

# macOS stability: torch (embeddings) and onnxruntime (re-ranker) both load OpenMP.
# Running them from several threads at once can crash the Python process.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import json
import re
from pathlib import Path

from flashrank import Ranker, RerankRequest
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

ROOT = Path(__file__).resolve().parent.parent          # project folder
DATA = ROOT / "data"
CHROMA_DIR = str(DATA / "chroma")


# ── 1. Chunks ───────────────────────────────────────────────────────────────
def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        return [Document(page_content=r["text"], metadata=r["metadata"]) for r in map(json.loads, f)]


CHUNKS = {
    "article": load_chunks(DATA / "chunks" / "article_chunks.jsonl"),
    "fixed":   load_chunks(DATA / "chunks" / "fixed_chunks.jsonl"),
}

# ── 2. Dense search: embeddings + Chroma (loaded from disk) ─────────────────
EMB = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    encode_kwargs={"normalize_embeddings": True},
)
STORES = {
    name: Chroma(collection_name=f"uae_{name}", embedding_function=EMB, persist_directory=CHROMA_DIR)
    for name in CHUNKS
}


# ── 3. Keyword search: BM25 ────────────────────────────────────────────────
def tokenize(text):
    """Lowercase and split on non-letters: 'Leave,' -> 'leave'."""
    return re.findall(r"\w+", text.lower())


BM25 = {name: BM25Retriever.from_documents(ch, k=10, preprocess_func=tokenize) for name, ch in CHUNKS.items()}


# ── Helpers ────────────────────────────────────────────────────────────────
def label(d):
    """Short readable ID, e.g. 'labour_law:29'."""
    return f"{d.metadata['source']}:{d.metadata['article']}"


def dense_search(query, name="article", k=10):
    return STORES[name].similarity_search(query, k=k)


def bm25_search(query, name="article", k=10):
    retriever = BM25[name]
    retriever.k = k
    return retriever.invoke(query)


# ── 4. Hybrid search with Reciprocal Rank Fusion ───────────────────────────
def rrf(result_lists, k=60, top_n=10):
    """Each chunk gets 1/(k + rank) from every list it appears in. Rank-based, so score scales don't matter."""
    scores, docs = {}, {}
    for results in result_lists:
        for rank, d in enumerate(results, 1):
            cid = d.metadata["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1 / (k + rank)
            docs[cid] = d
    best = sorted(scores, key=scores.get, reverse=True)[:top_n]
    return [docs[c] for c in best]


def hybrid_search(query, name="article", k=10, top_n=10):
    """Top-k from dense + top-k from BM25, merged with RRF -> top_n candidates."""
    return rrf([dense_search(query, name, k), bm25_search(query, name, k)], top_n=top_n)


# ── 5. Re-ranking with a cross-encoder ─────────────────────────────────────
RANKER = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir=str(DATA / "models"))


def rerank(query, docs, top_n=5):
    """Score each (question, chunk) pair TOGETHER. Returns [(doc, score)], best first. Score ~0..1."""
    if not docs:
        return []
    passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
    results = RANKER.rerank(RerankRequest(query=query, passages=passages))
    return [(docs[r["id"]], float(r["score"])) for r in results[:top_n]]


def retrieve(query, name="article", candidates=10, top_n=5):
    """Full retrieval: hybrid search for `candidates` chunks, then re-rank and keep `top_n`."""
    return rerank(query, hybrid_search(query, name, top_n=candidates), top_n=top_n)