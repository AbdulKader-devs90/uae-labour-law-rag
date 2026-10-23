"""Streamed graph execution and plain UI data, without Streamlit dependencies."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from time import perf_counter
from typing import Any, Generator
from uuid import uuid4

# Set these before importing any of the model libraries.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Shared by all Streamlit sessions: model inference always uses the same thread.
_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag")


def load_graph():
    """Import once through Python's module cache; suitable for st.cache_resource."""
    from src.graph import graph

    return graph


def run_question(question: str) -> Generator[dict[str, Any], None, None]:
    """Yield completed nodes, then the merged final state and tracing metadata."""
    events = Queue()
    sentinel = object()

    def run():
        try:
            graph = load_graph()
            run_id = uuid4()
            started = perf_counter()
            state = {"question": question}
            for batch in graph.stream(
                {"question": question},
                stream_mode="updates",
                config={"run_id": run_id, "run_name": "uae_labour_rag_ui"},
            ):
                for node, update in batch.items():
                    state.update(update)
                    events.put({"node": node, "update": dict(update)})
            seconds = perf_counter() - started
            state["seconds"] = seconds
            events.put({"done": True, "state": state, "run_id": str(run_id), "seconds": seconds})
        finally:
            events.put(sentinel)

    future = _WORKER.submit(run)
    while True:
        event = events.get()
        if event is sentinel:
            future.result()  # Propagate failures to the caller instead of hanging.
            break
        yield event


def to_view_model(state: dict) -> dict:
    """Convert Documents and scores into JSON-friendly presentation data."""
    answer = str(state.get("answer", ""))
    path = str(state.get("path", ""))
    top_score = float(state.get("top_score", 0.0))
    short_titles = {
        "labour_law": "Labour Law",
        "exec_regs": "Executive Regulation",
        "labour_law_amendment_2022": "2022 Amendment",
        "pdpl": "PDPL",
    }
    sources = []
    for n, (document, score) in enumerate(state.get("results", []), 1):
        metadata = document.metadata
        title = str(metadata.get("title", ""))
        short_title = short_titles.get(metadata.get("source"), title.split(" (")[0])
        article = metadata.get("article")
        article_label = "Preamble" if article == 0 else f"Art. {article}"
        text = document.page_content
        first_line, separator, rest = text.partition("\n")
        if first_line.strip().startswith("[") and first_line.strip().endswith("]"):
            text = rest if separator else ""
        sources.append({
            "n": n,
            "label": f"{short_title} · {article_label}",
            "law_title": title,
            "article": article,
            "part": metadata.get("part"),
            "score": max(0.0, min(1.0, float(score))),
            "text": text.strip(),
            "cited": f"[S{n}]" in answer,
        })
    confidence = "High" if top_score >= 0.8 else "Medium" if top_score >= 0.3 else "Low"
    return {
        "answer": answer,
        "path": path,
        "top_score": top_score,
        "rewritten": str(state.get("rewritten", "")),
        "seconds": float(state.get("seconds", 0.0)),
        "sources": sources,
        "confidence": "—" if path.startswith("refused") else confidence,
    }


if __name__ == "__main__":
    import json

    for event in run_question("How many days of annual leave do I get?"):
        if event.get("done"):
            print(json.dumps(to_view_model(event["state"]), indent=2, ensure_ascii=False))
