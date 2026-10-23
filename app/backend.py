"""Streamed graph execution and plain UI data, without Streamlit dependencies."""

import os
import html
import json
import re
import sys
from functools import lru_cache
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

SUGGESTIONS = [
    ("Leave", "How many days of annual leave do I get?"),
    ("End of service", "How is end-of-service gratuity calculated?"),
    ("Contracts", "How much notice must be given to end a contract?"),
    ("Rights", "Can my employer keep my passport?"),
    ("Personal data", "Can my company send my personal data abroad?"),
    ("Article lookup", "What does Article 51 say?"),
]

PIPELINE_LABELS = {
    "rewrite": "Understanding your question",
    "retrieve": "Searching 4 laws",
    "generate": "Writing the answer",
    "finalize": "Checking citations",
    "refuse": "No reliable source found",
}

PIPELINE_NEXT_LABELS = {
    "rewrite": "Searching 4 laws",
    "retrieve": "Writing the answer",
    "generate": "Checking citations",
    "finalize": "Answer ready",
    "refuse": "No reliable source found",
}


@lru_cache(maxsize=1)
def article_parts():
    """Read actual part counts from the corpus, rather than retrieved subsets."""
    counts = {}
    path = Path(__file__).resolve().parents[1] / "data/chunks/article_chunks.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        metadata = json.loads(line)["metadata"]
        key = (metadata["source"], metadata["article"])
        counts[key] = max(counts.get(key, 1), int(metadata.get("part", 1)))
    return counts


def answer_markdown(answer: str, message_id: str) -> str:
    """Keep Markdown while escaping raw HTML and making citation anchor chips."""
    safe = html.escape(answer)
    return re.sub(
        r"\[S(\d+)\]",
        lambda m: f'<sup><a class="citation-chip" href="#source-{message_id}-{m[1]}" '
                  f'title="Read source {m[1]}">S{m[1]}</a></sup>',
        safe,
    )


def highlighted_text(text: str, question: str, rewritten: str = "") -> str:
    """Highlight complete query words; preserve the exact source text."""
    stopwords = {"what", "does", "this", "that", "with", "from", "have", "many", "much",
                 "must", "about", "tell", "your", "which", "under", "there", "their", "given"}
    words = {w.lower() for w in re.findall(r"\b\w{4,}\b", question + " " + rewritten)} - stopwords
    if not words:
        return html.escape(text)
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(words)) + r")\b", re.I)
    pieces, position = [], 0
    for match in pattern.finditer(text):
        pieces.extend((html.escape(text[position:match.start()]), "<mark>" + html.escape(match[0]) + "</mark>"))
        position = match.end()
    pieces.append(html.escape(text[position:]))
    return "".join(pieces)


def clipboard_html(answer: str, appearance: str = "System") -> str:
    """Self-contained copy control with a fallback for clipboard-restricted browsers."""
    payload = json.dumps(answer).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    color = {"Light": "#637084", "Dark": "#a5b3c7"}.get(appearance)
    override = f"button{{color:{color}}}" if color else ""
    return '''<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@500&display=swap');
    body{margin:0}button{font:500 13px Inter,system-ui,sans-serif;
    background:transparent;color:#637084;border:1px solid #8795a655;border-radius:10px;
    padding:9px 12px;cursor:pointer;width:100%;height:38px}button:hover{background:#b99a5420}
    button:focus-visible{outline:2px solid #b99a54}
    @media(prefers-color-scheme:dark){button{color:#a5b3c7}}''' + override + '''</style>
    <button id="copy" aria-label="Copy answer">Copy answer</button><script>
    const text = ''' + payload + ''';
    document.getElementById('copy').onclick = async function(){try{
      try{await navigator.clipboard.writeText(text)}catch(e){
        const el=document.createElement('textarea');el.value=text;document.body.appendChild(el);
        el.select();if(!document.execCommand('copy'))throw e;el.remove();}
      this.textContent='Copied ✓';setTimeout(()=>this.textContent='Copy answer',2000);
    }catch(e){this.textContent='Select text to copy';}};</script>'''


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
            "total_parts": article_parts().get((metadata.get("source"), article), 1),
            "score": max(0.0, min(1.0, float(score))),
            "text": text.strip(),
            "cited": f"[S{n}]" in answer,
        })
    confidence = "High" if top_score >= 0.8 else "Medium" if top_score >= 0.3 else "Low"
    return {
        "answer": answer,
        "question": str(state.get("question", "")),
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
