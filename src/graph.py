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
   [check draft] --NOT_FOUND------------------> refuse
      |          --no [S#] tags (retry once)--> generate
      | ok
   finalize       turn [S#] tags into readable citations
      |
     END

Usage:
    from src.graph import ask
    result = ask("How many days of annual leave do I get?")
    print(result["answer"], result["sources"])
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
CUTOFF = 0.10        # re-rank score below this = "not relevant" (chosen from data in Step 5)
TOP_N = 4            # max sources sent to the LLM
MAX_RETRIES = 1      # extra generate attempts when the draft has no citations

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
   that contains that article, and name the law in your answer.{retry_note}

Sources:
{context}"""

RETRY_NOTE = ("\n\nIMPORTANT: your previous answer had no source tags. "
              "Every fact MUST end with a tag like [S1].")

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


# ── State: the shared "memory" that flows through every node ───────────────
class RAGState(TypedDict, total=False):
    question: str        # user's question (input)
    rewritten: str       # question in the law's words
    results: list        # [(Document, rerank_score)] that passed the CUTOFF
    top_score: float     # best re-rank score (before the CUTOFF filter)
    draft: str           # latest LLM output
    attempts: int        # how many times generate ran
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
    attempts = state.get("attempts", 0)
    draft = answer_chain.invoke({
        "context": format_context(state["results"]),
        "question": state["question"],
        "retry_note": RETRY_NOTE if attempts else "",
    }).strip()
    return {"draft": draft, "attempts": attempts + 1}


def finalize_node(state: RAGState):
    results = state["results"]
    used = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", state["draft"])})
    sources = list(dict.fromkeys(                     # remove duplicates (e.g. Article 51 part 1 + part 2)
        cite(results[i - 1][0]) for i in used if 0 < i <= len(results)))
    return {"answer": state["draft"], "sources": sources,
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
    if not re.search(r"\[S\d+\]", draft) and state["attempts"] <= MAX_RETRIES:
        return "generate"                                 # retry once with a stricter note
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


def ask(question: str) -> dict:
    """Run one question through the graph. Returns the final state + timing."""
    t0 = time.time()
    out = graph.invoke({"question": question}, config={"run_name": "uae_labour_rag"})
    out["seconds"] = round(time.time() - t0, 1)
    return out
