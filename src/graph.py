"""
LangGraph flow for the UAE Labour Law RAG bot.

    START
      |
   rewrite        LLM: user words -> the law's words ("salary" -> "wage")
      |
   retrieve       hybrid search (original + rewritten) -> re-rank -> drop chunks below CUTOFF
      |
   [enough evidence?] --no--> refuse
      | yes
   generate       LLM: answer ONLY from numbered sources, tag every fact [S1]..
      |
   [check draft] --NOT_FOUND--------------------------------> refuse
      |          --untagged facts / no tags (retry once)----> generate
      | ok
   finalize       v3: drop sentences that still have no [S#] tag; turn tags into citations
      |
     END

v3 (strict=True, the default) adds three guards found in live testing:
  1. Weak evidence (top score < WEAK_EVIDENCE): stricter prompt — answer only what the sources
     literally say about the question asked, otherwise NOT_FOUND.
  2. Sentence-level citation check: a long sentence with no [S#] tag whose words are mostly not in
     the sources (< 60% overlap) is treated as outside knowledge. It triggers one retry; any still
     left after that are removed (refuse if nothing supported is left).
  3. Leading questions: do not adopt an assumption the sources do not support.
strict=False reproduces the evaluated v1 behaviour exactly (used for the before/after comparison).

Usage:
    from src.graph import ask
    result = ask("How many days of annual leave do I get?")            # v3
    result = ask("How many days of annual leave do I get?", strict=False)  # v1
"""
import re
import time
from typing import TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from src.llm import get_llm
from src.rewrite import retrieve_with_rewrite, rewrite

# ── Settings ────────────────────────────────────────────────────────────────
CUTOFF = 0.10          # re-rank score below this = "not relevant" (chosen from data in Step 5)
WEAK_EVIDENCE = 0.50   # v3: below this top score, use the strict "literal answer only" prompt
TOP_N = 4              # max sources sent to the LLM
MAX_RETRIES = 1        # extra generate attempts (missing tags / untagged facts)
SHORT_SENTENCE = 12    # v3: untagged sentences up to this many words are allowed (e.g. "No, they cannot.")
MIN_SUPPORT = 0.60     # v3: an untagged sentence is kept if >= 60% of its content words appear in the sources

REFUSAL = ("I couldn't find this in the UAE laws I cover (Labour Law, its Executive Regulation, "
           "the 2022 amendment and the PDPL). Please check with MOHRE or a legal professional.")

ANSWER_SYSTEM = """You answer questions about UAE labour law and personal data protection.
Use ONLY the numbered sources below. Do not use outside knowledge.

Rules:
1. End every sentence that states a fact with its source tag, e.g. [S1] or [S1][S3].
2. If the sources do not answer the question, reply with exactly: NOT_FOUND
3. If the Executive Regulation adds detail to a Labour Law article, include that detail.
4. If the 2022 Amendment changes an article, follow the amended text and say it was amended.
5. Be short and clear: 2-6 sentences or a short list. Copy numbers exactly (days, %, periods).
6. Explain what the law says; do not give personal legal advice.
7. If the user asks what an article says, summarise that article from the sources.
8. If the user names an article number without naming the law, use the law in the sources
   that contains that article, and name the law in your answer.{extra_rules}{retry_note}

Sources:
{context}"""

STRICT_RULES = """
9. Every sentence that states a fact must have a source tag. If you cannot support a sentence
   from the sources, leave it out. Never add facts from general knowledge (fees, authorities,
   procedures, eligibility) that are not written in the sources.
10. If the question assumes something the sources do not say (for example an "ideal" or "usual"
   value), do not adopt the assumption: state what the sources actually say."""

WEAK_NOTE = """

WEAK EVIDENCE: the sources only loosely match this question. Answer ONLY if the sources directly
answer the question that was asked. If they only mention a related topic, reply with exactly: NOT_FOUND"""

RETRY_NOTE = ("\n\nIMPORTANT: your previous answer had no source tags. "
              "Every fact MUST end with a tag like [S1].")

RETRY_UNTAGGED = ("\n\nIMPORTANT: these sentences in your previous answer had no source tag. "
                  "Either support them with a tag from the sources or remove them:\n{sentences}")

answer_chain = (
    ChatPromptTemplate.from_messages([("system", ANSWER_SYSTEM), ("human", "{question}")])
    | get_llm()
    | StrOutputParser()
)


def cite(d):
    m = d.metadata
    return f"{m['title']}, " + ("Preamble" if m["article"] == 0 else f"Article {m['article']}")


def format_context(results):
    return "\n\n".join(f"[S{i}] {cite(d)}\n{d.page_content}" for i, (d, _) in enumerate(results, 1))


# ── v3: sentence-level citation check ──────────────────────────────────────
TAG = re.compile(r"\[S\d+\]")


def split_units(text):
    """Split an answer into checkable units: each list item / line, then sentences inside it."""
    units = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # split after ". " / "? " / "! " (optionally after a tag), keep the punctuation
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])|(?<=\])\s+(?=[A-Z(\"'])", line)
        units.extend(p.strip() for p in parts if p.strip())
    return units


STOPWORDS = set("""a an the and or of to in on for with by at from as is are be been was were this that these
those it its your you my i we they he she his her their can may must not no yes do does under law uae if any all
such which who what when how than then also only per each""".split())


def content_words(text):
    """Lower-case content words, cut to 5 letters so 'lawsuit'/'lawsuits' match; labour = labor."""
    text = text.lower().replace("labour", "labor")
    return {w[:5] for w in re.findall(r"[a-z]+", text) if w not in STOPWORDS and len(w) > 2}


def support(sentence, context):
    words = content_words(sentence)
    return len(words & content_words(context)) / max(1, len(words))


def untagged_facts(text, context=""):
    """Sentences with no [S#] tag whose words are mostly NOT in the sources (= likely outside knowledge).
    Allowed: lead-ins ending with ':', short sentences, and untagged sentences that restate the sources."""
    bad = []
    for u in split_units(text):
        plain = re.sub(r"^[-*•\d.\)\s]+", "", u)            # strip list markers
        if TAG.search(plain) or plain.endswith(":"):
            continue
        if len(plain.split()) <= SHORT_SENTENCE:
            continue
        if context and support(plain, context) >= MIN_SUPPORT:
            continue
        bad.append(plain)
    return bad


def remove_sentences(text, sentences):
    for s in sentences:
        text = text.replace(s, "")
    text = re.sub(r"^[ \t]*[-*•][ \t]*$", "", text, flags=re.M)   # empty list items
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── State: the shared "memory" that flows through every node ───────────────
class RAGState(TypedDict, total=False):
    question: str        # user's question (input)
    strict: bool         # v3 guards on (default True)
    rewritten: str       # question in the law's words
    results: list        # [(Document, rerank_score)] that passed the CUTOFF
    top_score: float     # best re-rank score (before the CUTOFF filter)
    draft: str           # latest LLM output
    attempts: int        # how many times generate ran
    removed: list        # v3: untagged sentences removed by finalize
    answer: str          # final answer shown to the user
    sources: list        # readable citations
    path: str            # which route the graph took (for evaluation)


# ── Nodes: each one reads the state and returns ONLY the fields it changes ─
def rewrite_node(state: RAGState):
    return {"rewritten": rewrite(state["question"])}


def retrieve_node(state: RAGState):
    _, results = retrieve_with_rewrite(state["question"], top_n=TOP_N, rewritten=state["rewritten"])
    top = results[0][1] if results else 0.0
    kept = [(d, s) for d, s in results if s >= CUTOFF]
    return {"results": kept, "top_score": round(top, 3)}


def generate_node(state: RAGState):
    strict = state.get("strict", True)
    attempts = state.get("attempts", 0)
    extra = STRICT_RULES if strict else ""
    if strict and state.get("top_score", 1.0) < WEAK_EVIDENCE:
        extra += WEAK_NOTE

    note = ""
    if attempts:
        ctx = "\n".join(d.page_content for d, _ in state["results"])
        bad = untagged_facts(state.get("draft", ""), ctx) if strict else []
        note = (RETRY_UNTAGGED.format(sentences="\n".join(f"- {s}" for s in bad))
                if bad and TAG.search(state.get("draft", "")) else RETRY_NOTE)

    draft = answer_chain.invoke({
        "context": format_context(state["results"]),
        "question": state["question"],
        "extra_rules": extra,
        "retry_note": note,
    }).strip()
    return {"draft": draft, "attempts": attempts + 1}


def finalize_node(state: RAGState):
    results = state["results"]
    text = state["draft"]
    removed = []
    if state.get("strict", True):
        ctx = "\n".join(d.page_content for d, _ in results)
        removed = untagged_facts(text, ctx)
        text = remove_sentences(text, removed)
        if not TAG.search(text):                      # nothing supported is left
            return {"answer": REFUSAL, "sources": [], "removed": removed, "path": "refused_unsupported"}

    used = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", text)})
    sources = list(dict.fromkeys(                     # remove duplicates (e.g. Article 51 part 1 + part 2)
        cite(results[i - 1][0]) for i in used if 0 < i <= len(results)))
    return {"answer": text, "sources": sources, "removed": removed,
            "path": "answered" if used else "answered_no_citation"}


def refuse_node(state: RAGState):
    reason = "refused_by_llm" if state.get("draft", "").startswith("NOT_FOUND") else "refused_low_score"
    return {"answer": REFUSAL, "sources": [], "path": reason}


# ── Conditional edges: small functions that pick the next node ─────────────
def route_after_retrieve(state: RAGState):
    return "generate" if state["results"] else "refuse"


def route_after_generate(state: RAGState):
    draft = state["draft"]
    if draft.startswith("NOT_FOUND"):
        return "refuse"
    can_retry = state["attempts"] <= MAX_RETRIES
    if not TAG.search(draft) and can_retry:
        return "generate"                                 # no tags at all -> retry
    ctx = "\n".join(d.page_content for d, _ in state["results"])
    if state.get("strict", True) and untagged_facts(draft, ctx) and can_retry:
        return "generate"                                 # v3: untagged facts -> retry once
    return "finalize"


# ── Build the graph ────────────────────────────────────────────────────────
def build_graph():
    g = StateGraph(RAGState)
    g.add_node("rewrite", rewrite_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_node("finalize", finalize_node)
    g.add_node("refuse", refuse_node)

    g.add_edge(START, "rewrite")
    g.add_edge("rewrite", "retrieve")
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"generate": "generate", "refuse": "refuse"})
    g.add_conditional_edges("generate", route_after_generate,
                            {"generate": "generate", "refuse": "refuse", "finalize": "finalize"})
    g.add_edge("finalize", END)
    g.add_edge("refuse", END)
    return g.compile()


graph = build_graph()


def ask(question: str, strict: bool = True) -> dict:
    """Run one question through the graph. strict=True = v3 guards, False = evaluated v1."""
    t0 = time.time()
    out = graph.invoke({"question": question, "strict": strict},
                       config={"run_name": "uae_labour_rag" + ("" if strict else "_v1")})
    out["seconds"] = round(time.time() - t0, 1)
    return out
