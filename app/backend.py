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


# Keyword routes are ordered: immigration wins when a question mentions both.
AUTHORITY_ROUTES = {
    "immigration": {
        "keywords": ["visa", "golden visa", "residency", "residence permit", "emirates id", "entry permit", "family sponsorship"],
        "authorities": [
            {"name": "ICP (Federal Authority for Identity, Citizenship, Customs & Port Security)", "url": "https://icp.gov.ae", "note": ""},
            {"name": "GDRFA Dubai", "url": "https://gdrfad.gov.ae", "note": "For Dubai residents"},
        ],
    },
    "employment": {
        "keywords": ["work permit", "labour card", "employment contract", "establishment card", "wages", "wps", "labour complaint", "mohre"],
        "authorities": [{"name": "MOHRE (Ministry of Human Resources & Emiratisation)", "url": "https://www.mohre.gov.ae", "note": ""}],
    },
    "default": {
        "keywords": [],
        "authorities": [{"name": "UAE Government portal", "url": "https://u.ae", "note": ""}],
    },
}

RELATED_ARTICLES = {
    ("labour_law", 29): ["Can I carry forward unused annual leave?", "How is unused leave paid when I leave my job?"],
    ("labour_law", 51): ["Can my employer deduct from my gratuity?", "How is end-of-service gratuity calculated?"],
    ("labour_law", 30): ["Can I be dismissed during maternity leave?", "How long is maternity leave?"],
    ("labour_law", 43): ["What happens if notice is not given?", "How much notice must be given to end a contract?"],
    ("labour_law", 13): ["What are my employer’s obligations?", "What does the law say about paying wages on time?"],
    ("pdpl", 22): ["What are my rights over my personal data?", "When can personal data be transferred abroad?"],
    ("pdpl", 23): ["What are my rights over my personal data?", "When is consent needed to process personal data?"],
}

METRIC_DEFINITIONS = {
    "decision_correct": "Answered when it should, refused when it should.",
    "retrieval_hit": "Expected article retrieved.",
    "citation_hit": "Expected article cited.",
    "correctness": "LLM judge vs reference.",
    "faithfulness": "Every claim supported by the sources.",
}
VERSION_DEFINITIONS = {
    "A_naive": "A = fixed chunks + dense search",
    "B_hybrid": "B = article chunks + hybrid search + re-rank + cut-off",
    "C_full": "C = B + query rewrite + LangGraph",
}
VERSION_LABELS = {name: name for name in VERSION_DEFINITIONS}
VERSION_LABELS["C_full_final_x3"] = "C final (3 runs)"


def refusal_guidance(question: str) -> dict:
    for route in AUTHORITY_ROUTES.values():
        if any(re.search(r"\b" + re.escape(word) + r"\b", question, re.I) for word in route["keywords"]):
            authorities = route["authorities"]
            break
    else:
        authorities = AUTHORITY_ROUTES["default"]["authorities"]
    text = ("Not covered by the laws I search (Labour Law, its Executive Regulation, the 2022 amendment, PDPL). "
            "For this topic, the responsible authority is:")
    links = "\n".join(f"- {a['note'] + ': ' if a['note'] else ''}[{a['name']}]({a['url']})" for a in authorities)
    return {"text": text, "authorities": authorities, "markdown": text + "\n\n" + links}


def follow_up_questions(sources: list, question: str) -> list[str]:
    questions = []
    for source in sources:
        if source["cited"]:
            for suggestion in RELATED_ARTICLES.get((source["source"], source["article"]), []):
                if suggestion.casefold().rstrip("?. ") != question.casefold().rstrip("?. ") and suggestion not in questions:
                    questions.append(suggestion)
    for fallback in ["How many days of annual leave do I get?", "How much notice must be given to end a contract?", "What are my rights over my personal data?"]:
        if len(questions) >= 3:
            break
        if fallback not in questions and fallback.casefold().rstrip("?. ") != question.casefold().rstrip("?. "):
            questions.append(fallback)
    return questions[:3]


def source_cards(sources: list, answer: str) -> tuple[list, str]:
    """Merge retrieved parts of cited articles and renumber display tags only."""
    cited = [source for source in sources if source["cited"]]
    keys = list(dict.fromkeys((s["source"], s["article"]) for s in (cited or sources)))
    cards, mapping = [], {}
    for n, key in enumerate(keys, 1):
        chunks = [s for s in sources if (s["source"], s["article"]) == key]
        chunks.sort(key=lambda s: (s["part"] or 1, s["n"]))
        # Deduplicate identical chunks while retaining all raw indices in the map.
        parts = list(dict.fromkeys(s["part"] or 1 for s in chunks))
        part_text = str(parts[0]) if len(parts) == 1 else (
            f"{parts[0]}–{parts[-1]}" if parts == list(range(parts[0], parts[-1] + 1)) else ", ".join(map(str, parts)))
        suffix = f" · parts {part_text}" if len(parts) > 1 else ""
        unique_chunks = list({(s["part"], s["text"]): s for s in chunks}.values())
        cards.append({
            **chunks[0], "n": n, "label": chunks[0]["label"] + suffix,
            "score": max(s["score"] for s in chunks), "parts": unique_chunks,
            "part_label": f"Parts {part_text} / {chunks[0]['total_parts']}" if len(parts) > 1 else f"Part {part_text} / {chunks[0]['total_parts']}",
            "cited": any(s["cited"] for s in chunks),
        })
        mapping.update({s["n"]: n for s in chunks})
    displayed = re.sub(r"\[S(\d+)\]", lambda m: f"[S{mapping[int(m[1])]}]" if int(m[1]) in mapping else "[source unavailable]", answer)
    displayed = re.sub(r"(\[S\d+\])(?:\s*\1)+", r"\1", displayed)
    return cards, displayed


def submit_feedback(run_id: str, score: int) -> bool:
    """Send exactly one rating; callers handle session deduplication and toasts."""
    try:
        from langsmith import Client
        from uuid import UUID

        UUID(run_id)
        if score not in (0, 1):
            return False
        Client().create_feedback(run_id=run_id, key="user_rating", score=score)
        return True
    except Exception:
        return False


@lru_cache(maxsize=8)
def _project_url(project_name: str) -> str:
    from langsmith import Client

    return Client().read_project(project_name=project_name).url or "https://smith.langchain.com"


@lru_cache(maxsize=128)
def trace_url(run_id: str) -> str:
    """Build the SDK's private run URL even while a trace is still uploading."""
    try:
        from langsmith import Client
        from langsmith.utils import get_tracer_project
        from uuid import UUID

        UUID(run_id)
        project = _project_url(get_tracer_project())
        if project != "https://smith.langchain.com":
            return f"{project}/r/{run_id}?poll=true"
        run = Client().read_run(run_id)
        return run.url or "https://smith.langchain.com"
    except Exception:
        return "https://smith.langchain.com"


def conversation_markdown(messages: list) -> str:
    lines = ["# Qanoon — UAE Labour Law Assistant", "", "Explains the law; not legal advice.", ""]
    for message in messages:
        if message["role"] == "user":
            lines.extend(["## Question", "", message["content"], ""])
        else:
            view = message["view"]
            lines.extend(["## Answer", "", view.get("display_answer", view["answer"]), ""])
            cards = view.get("display_sources", view["sources"])
            if cards and not view["path"].startswith("refused"):
                lines.extend(["### Citations" if any(s["cited"] for s in cards) else "### Retrieved sources (not cited)", ""])
                for source in cards:
                    lines.append(f"- [S{source['n']}] {source['label']} — {source['law_title']} ({source.get('part_label', 'Part ' + str(source['part']))})")
                lines.append("")
    return "\n".join(lines)


def load_evaluation(data_dir: Path | None = None) -> dict:
    """Read the approved aggregate only. v2 is a rejected experiment."""
    import csv
    import math

    base = data_dir or Path(__file__).resolve().parents[1] / 'data/eval'
    path = base / 'final_summary.csv'
    versions = {}
    if path.exists():
        with path.open(newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                name = row.get('version')
                if name not in VERSION_LABELS:
                    continue
                values = {metric: float(row[metric]) for metric in METRIC_DEFINITIONS if row.get(metric)}
                if not all(math.isfinite(value) and 0 <= value <= 1 for value in values.values()):
                    raise ValueError('Evaluation scores must be between zero and one.')
                values['avg_seconds'] = float(row.get('avg_seconds') or 0)
                values['runs'] = int(row.get('runs') or 1)
                versions[name] = values
    records = [
        {'version': VERSION_LABELS[name], 'version_id': name, 'metric': metric, 'score': values[metric]}
        for name in VERSION_LABELS
        for values in [versions.get(name, {})]
        for metric in METRIC_DEFINITIONS if metric in values
    ]
    final = versions.get('C_full_final_x3')
    highlight = None
    if final and all(metric in final for metric in ['decision_correct', 'retrieval_hit', 'correctness', 'faithfulness']):
        decisions, retrieval, correctness = (final[key] for key in ['decision_correct', 'retrieval_hit', 'correctness'])
        if decisions == retrieval == correctness:
            quality = f'{decisions:.0%} correct decisions, retrieval and correctness'
        else:
            quality = f'{decisions:.0%} correct decisions · {retrieval:.0%} retrieval · {correctness:.0%} correctness'
        highlight = f"Final version, {final['runs']} runs: {quality} · {final['faithfulness']:.0%} faithfulness · ~{final['avg_seconds']:.0f} s per answer"
    return {
        'records': records, 'versions': versions, 'highlight': highlight,
        'note': 'Source: data/eval/final_summary.csv. A, B and C each have one run; C final is the average of three runs. Rejected v2 results are excluded.',
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
            "source": metadata.get("source", title),
            "chunk_id": metadata.get("chunk_id", f"result-{n}"),
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
    cards, display_answer = source_cards(sources, answer)
    guidance = refusal_guidance(str(state.get("question", ""))) if path.startswith("refused") else None
    return {
        "answer": answer,
        "display_answer": guidance["markdown"] if guidance else display_answer,
        "display_sources": cards,
        "refusal": guidance,
        "follow_ups": [] if guidance else follow_up_questions(sources, str(state.get("question", ""))),
        "attempts": int(state.get("attempts", 0)),
        "cutoff": 0.10,
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
